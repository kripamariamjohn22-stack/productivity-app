"""
db.py — every piece of database code lives here.

Why one file? So the rest of the app never writes SQL directly.
Pages call simple functions like `add_task(...)` and don't care how
the data is stored. If you ever change the database, you only touch this file.
"""

import os
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd

# The database is a single file. Path(__file__) is this file (core/db.py),
# so .parent.parent is the project root. This works no matter which folder
# you run `streamlit run` from.
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "app.db"

# Optional switch to a different database file, e.g. the demo one:
#   PRODUCTIVITY_DB=data/demo.db streamlit run app.py
# An environment variable is a setting you give a program when you start it,
# so trying the demo never touches your real data/app.db.
if os.environ.get("PRODUCTIVITY_DB"):
    DB_PATH = ROOT / os.environ["PRODUCTIVITY_DB"]  # relative paths start at the project folder
else:
    DB_PATH = DEFAULT_DB


def get_connection():
    """Open a connection to the SQLite file (creates the file if missing)."""
    DB_PATH.parent.mkdir(exist_ok=True)  # make sure data/ exists
    conn = sqlite3.connect(DB_PATH)
    # row_factory lets us read columns by name: row["title"] instead of row[1]
    conn.row_factory = sqlite3.Row
    # SQLite ignores foreign keys unless you switch them on, per connection
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create all tables if they don't exist yet. Safe to run every time."""
    conn = get_connection()
    # executescript runs several SQL statements in one go.
    # "IF NOT EXISTS" means running this twice does nothing harmful.
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            title            TEXT NOT NULL,
            priority         TEXT NOT NULL DEFAULT 'Med'
                             CHECK (priority IN ('High', 'Med', 'Low')),
            due_date         TEXT,            -- 'YYYY-MM-DD'
            tag              TEXT NOT NULL DEFAULT 'personal'
                             CHECK (tag IN ('college', 'internship', 'personal', 'research')),
            status           TEXT NOT NULL DEFAULT 'todo'
                             CHECK (status IN ('todo', 'done', 'dropped')),
            created_at       TEXT NOT NULL,   -- 'YYYY-MM-DD HH:MM:SS'
            completed_at     TEXT,
            times_postponed  INTEGER NOT NULL DEFAULT 0,
            planned_minutes  INTEGER,
            actual_minutes   INTEGER
        );

        CREATE TABLE IF NOT EXISTS habits (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT NOT NULL UNIQUE,
            minimum_version  TEXT,            -- the "bad day" version of the habit
            target_per_week  INTEGER NOT NULL DEFAULT 7
                             CHECK (target_per_week BETWEEN 1 AND 7),
            active           INTEGER NOT NULL DEFAULT 1   -- 1 = shown, 0 = archived
        );

        -- One row = "I did this habit on this day".
        -- No row for a day = not done. That keeps the table small and simple.
        CREATE TABLE IF NOT EXISTS habit_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id    INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
            date        TEXT NOT NULL,          -- 'YYYY-MM-DD'
            is_minimum  INTEGER NOT NULL DEFAULT 0,  -- 1 = only did the minimum version
            UNIQUE (habit_id, date)             -- can't log the same habit twice a day
        );

        -- Local copy of Google Calendar events, so the app still works offline.
        CREATE TABLE IF NOT EXISTS events (
            id         TEXT PRIMARY KEY,   -- Google's own event id
            title      TEXT,
            start      TEXT NOT NULL,      -- ISO datetime, or 'YYYY-MM-DD' for all-day
            end        TEXT,
            all_day    INTEGER NOT NULL DEFAULT 0,
            synced_at  TEXT NOT NULL
        );

        -- Tiny key/value store for app bookkeeping,
        -- e.g. the time of the last calendar sync.
        CREATE TABLE IF NOT EXISTS settings (
            key    TEXT PRIMARY KEY,
            value  TEXT
        );

        -- Phase 2 ---------------------------------------------------------

        -- base_attended / base_missed = classes from BEFORE you started using
        -- the app, so a subject added mid-semester still shows the right %.
        CREATE TABLE IF NOT EXISTS subjects (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            name           TEXT NOT NULL UNIQUE,
            base_attended  INTEGER NOT NULL DEFAULT 0,
            base_missed    INTEGER NOT NULL DEFAULT 0,
            active         INTEGER NOT NULL DEFAULT 1
        );

        -- One row per class. No UNIQUE on (subject, date) on purpose:
        -- a double lab period is two classes on the same day.
        CREATE TABLE IF NOT EXISTS attendance (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id  INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            date        TEXT NOT NULL,
            status      TEXT NOT NULL CHECK (status IN ('attended', 'missed')),
            logged_at   TEXT NOT NULL
        );

        -- Phase 3 ---------------------------------------------------------

        -- Meeting notes: one per calendar event (UNIQUE event_id).
        -- title/start/attendees are COPIED from the event instead of joined,
        -- because the events table is only a cache: a re-sync can delete rows
        -- from it, and your notes must survive that.
        CREATE TABLE IF NOT EXISTS notes (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id      TEXT NOT NULL UNIQUE,
            title         TEXT NOT NULL,
            start         TEXT NOT NULL,
            "end"         TEXT,
            attendees     TEXT,
            agenda        TEXT NOT NULL DEFAULT '',
            notes         TEXT NOT NULL DEFAULT '',
            decisions     TEXT NOT NULL DEFAULT '',
            action_items  TEXT NOT NULL DEFAULT '',   -- one per line
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        );

        -- Weekly class schedule. weekday: 0 = Monday ... 6 = Sunday
        -- (same numbering as Python's date.weekday()).
        CREATE TABLE IF NOT EXISTS timetable (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id  INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            weekday     INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
            start_time  TEXT NOT NULL,   -- 'HH:MM'
            end_time    TEXT NOT NULL,
            room        TEXT
        );
        """
    )
    run_migrations(conn)
    seed_habits(conn)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Migrations: changes to tables that already exist
# ---------------------------------------------------------------------------
# "CREATE TABLE IF NOT EXISTS" can't change a table you already have, so
# editing a CREATE statement above would do nothing to your real database.
# Instead, every change to an existing table is added to the END of this list.
#
# SQLite has a spare number in every database file, PRAGMA user_version
# (starts at 0). We use it to remember how many migrations already ran:
# user_version = 1 means "MIGRATIONS[0] is done", and so on.
#
# Rules: never edit or reorder an entry once it has run; only append new ones.
MIGRATIONS = [
    # 1. Phase 2 step 2: link a logged class to the timetable slot it came from,
    #    so a double lab (two slots, same subject, same day) is tracked per slot.
    #    SET NULL: deleting a slot keeps the attendance history.
    "ALTER TABLE attendance ADD COLUMN slot_id INTEGER REFERENCES timetable(id) ON DELETE SET NULL",
    # 2. Phase 2 step 3: assignments and exams live in the tasks table too.
    #    DEFAULT 'task' means every task you already have becomes a normal task.
    """ALTER TABLE tasks ADD COLUMN type TEXT NOT NULL DEFAULT 'task'
       CHECK (type IN ('task', 'assignment', 'exam'))""",
    # 3. Optional link from an assignment/exam to its subject.
    "ALTER TABLE tasks ADD COLUMN subject_id INTEGER REFERENCES subjects(id) ON DELETE SET NULL",
    # 4. Phase 3: who's invited to each calendar event ("Asha, bob@uni.edu").
    #    Old cached events get it on their next sync.
    "ALTER TABLE events ADD COLUMN attendees TEXT",
    # 5. Phase 3 step 2: which meeting note an action-item task came from.
    #    SET NULL: deleting a note keeps its tasks (they just lose the link).
    "ALTER TABLE tasks ADD COLUMN note_id INTEGER REFERENCES notes(id) ON DELETE SET NULL",
]


def run_migrations(conn):
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for number, sql in enumerate(MIGRATIONS[version:], start=version + 1):
        conn.execute(sql)
        # PRAGMA doesn't accept ? placeholders; `number` is our own int, so this is safe.
        conn.execute(f"PRAGMA user_version = {number}")


# Starting habits from the spec: (name, minimum version, days per week)
SEED_HABITS = [
    ("Read 1 Substack article", "Read 1 paragraph", 5),
    ("No Instagram before 10am", "No Instagram before 9am", 5),
    ("Phone outside room at night", "Phone face-down across the room", 5),
]


def seed_habits(conn):
    """Insert the starter habits once. INSERT OR IGNORE skips names that already exist."""
    conn.executemany(
        "INSERT OR IGNORE INTO habits (name, minimum_version, target_per_week) VALUES (?, ?, ?)",
        SEED_HABITS,
    )



# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

PRIORITIES = ["High", "Med", "Low"]
TAGS = ["college", "internship", "personal", "research"]


def now_str():
    """Current local time as text. SQLite has no real date type, and this
    'YYYY-MM-DD HH:MM:SS' format sorts correctly as plain text."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


TASK_TYPES = ["task", "assignment", "exam"]


def add_task(title, priority="Med", due_date=None, tag="personal", planned_minutes=None,
             type="task", subject_id=None):
    """Insert a new task. due_date is a datetime.date or None.
    type is 'task', 'assignment' or 'exam'; subject_id is optional."""
    conn = get_connection()
    # The ? placeholders let sqlite3 insert values safely.
    # Never build SQL with f-strings: a title like  it's  would break it.
    conn.execute(
        """INSERT INTO tasks (title, priority, due_date, tag, created_at, planned_minutes,
                              type, subject_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (title, priority, due_date.isoformat() if due_date else None, tag, now_str(),
         planned_minutes, type, subject_id),
    )
    conn.commit()
    conn.close()


def get_open_tasks():
    """All unfinished tasks: most urgent due date first, then High > Med > Low.
    The LEFT JOIN adds the subject name (NULL for tasks without a subject)."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT t.*, s.name AS subject, n.title AS meeting
           FROM tasks t
           LEFT JOIN subjects s ON s.id = t.subject_id
           LEFT JOIN notes n ON n.id = t.note_id
           WHERE t.status = 'todo'
           ORDER BY
             t.due_date IS NULL,  -- tasks with no due date go last (FALSE=0 sorts first)
             t.due_date,
             CASE t.priority WHEN 'High' THEN 0 WHEN 'Med' THEN 1 ELSE 2 END"""
    ).fetchall()
    conn.close()
    return rows


def get_closed_tasks(limit=20):
    """Recently finished or dropped tasks, newest first."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM tasks
           WHERE status IN ('done', 'dropped')
           ORDER BY completed_at DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return rows


def get_tasks_for_day(day):
    """Plain tasks that belong on one day's plan: still open and due that day,
    or finished that day (so you can see what you already got done).
    Assignments and exams are left out: the Today page shows them under Deadlines."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT t.*, n.title AS meeting
           FROM tasks t
           LEFT JOIN notes n ON n.id = t.note_id
           WHERE t.type = 'task'
             AND ((t.status = 'todo' AND t.due_date = :day)
                  OR (t.status = 'done' AND substr(t.completed_at, 1, 10) = :day))
           ORDER BY t.status DESC,  -- 'todo' sorts after 'done' alphabetically, so DESC puts open ones first
                    CASE t.priority WHEN 'High' THEN 0 WHEN 'Med' THEN 1 ELSE 2 END""",
        {"day": day.isoformat()},
    ).fetchall()
    conn.close()
    return rows


def get_upcoming_deadlines(today=None, days=14):
    """Open assignments and exams due within `days` days, plus any overdue ones."""
    today = today or date.today()
    conn = get_connection()
    rows = conn.execute(
        """SELECT t.*, s.name AS subject
           FROM tasks t
           LEFT JOIN subjects s ON s.id = t.subject_id
           WHERE t.status = 'todo'
             AND t.type IN ('assignment', 'exam')
             AND t.due_date <= date(:today, '+' || :days || ' days')
           ORDER BY t.due_date""",
        {"today": today.isoformat(), "days": days},
    ).fetchall()
    conn.close()
    return rows


def complete_task(task_id, actual_minutes=None):
    """Mark a task done and record how long it really took."""
    conn = get_connection()
    conn.execute(
        "UPDATE tasks SET status = 'done', completed_at = ?, actual_minutes = ? WHERE id = ?",
        (now_str(), actual_minutes, task_id),
    )
    conn.commit()
    conn.close()


def drop_task(task_id):
    """Give up on a task. We keep the row (instead of deleting it) because
    'what did I drop, and after how many postponements?' is useful data later."""
    conn = get_connection()
    conn.execute(
        "UPDATE tasks SET status = 'dropped', completed_at = ? WHERE id = ?",
        (now_str(), task_id),
    )
    conn.commit()
    conn.close()


def reopen_task(task_id):
    """Undo a Done/Drop click that was a mistake."""
    conn = get_connection()
    conn.execute(
        "UPDATE tasks SET status = 'todo', completed_at = NULL, actual_minutes = NULL WHERE id = ?",
        (task_id,),
    )
    conn.commit()
    conn.close()


def roll_over_tasks(today=None):
    """Move unfinished, overdue tasks to today and count each missed day as one postponement.

    Example: a task due Monday, still open on Thursday, gets due_date = Thursday
    and times_postponed += 3 (Tue, Wed, Thu). Counting days, not app openings,
    means the number is the same whether or not you opened the app that week.

    Running this many times a day is harmless: after the first run the task
    is due today, so it no longer matches "due_date < today".
    Tasks with no due date are never postponed, because they had no deadline to miss.
    Assignments and exams are never rolled over: their dates are set by college,
    so moving them would hide that you're late. They show "overdue" instead.
    """
    today = (today or date.today()).isoformat()
    conn = get_connection()
    # julianday() turns a date into a day number, so subtracting gives days between.
    cur = conn.execute(
        """UPDATE tasks
           SET times_postponed = times_postponed
                                 + CAST(julianday(?) - julianday(due_date) AS INTEGER),
               due_date = ?
           WHERE status = 'todo' AND due_date IS NOT NULL AND due_date < ?
             AND type = 'task'  -- deadlines and exam dates are fixed: they never roll over""",
        (today, today, today),
    )
    conn.commit()
    conn.close()
    return cur.rowcount  # how many tasks were rolled over



# ---------------------------------------------------------------------------
# Habits
# ---------------------------------------------------------------------------

def get_habits():
    """All active (not archived) habits, oldest first."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM habits WHERE active = 1 ORDER BY id").fetchall()
    conn.close()
    return rows


def add_habit(name, minimum_version, target_per_week):
    conn = get_connection()
    conn.execute(
        "INSERT INTO habits (name, minimum_version, target_per_week) VALUES (?, ?, ?)",
        (name, minimum_version or None, target_per_week),
    )
    conn.commit()
    conn.close()


def archive_habit(habit_id):
    """Hide a habit but keep its history (same idea as dropping a task)."""
    conn = get_connection()
    conn.execute("UPDATE habits SET active = 0 WHERE id = ?", (habit_id,))
    conn.commit()
    conn.close()


def get_habit_logs(habit_id):
    """Every day this habit was done, as {date: is_minimum}.
    Loading all of it is fine: even 5 years of daily logs is under 2,000 rows."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT date, is_minimum FROM habit_logs WHERE habit_id = ?", (habit_id,)
    ).fetchall()
    conn.close()
    return {date.fromisoformat(r["date"]): bool(r["is_minimum"]) for r in rows}


def get_logs_for_date(day):
    """Which habits were done on one day, as {habit_id: is_minimum}."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT habit_id, is_minimum FROM habit_logs WHERE date = ?", (day.isoformat(),)
    ).fetchall()
    conn.close()
    return {r["habit_id"]: bool(r["is_minimum"]) for r in rows}


def set_habit_log(habit_id, day, done, is_minimum=False):
    """Record (or un-record) a habit for one day.

    done=True  -> make sure there's a row (update is_minimum if one exists)
    done=False -> delete the row, because "no row" means "not done"
    """
    conn = get_connection()
    if done:
        # "Upsert": insert, or if (habit_id, date) already exists, update it instead.
        # This works because of the UNIQUE (habit_id, date) rule on the table.
        conn.execute(
            """INSERT INTO habit_logs (habit_id, date, is_minimum) VALUES (?, ?, ?)
               ON CONFLICT (habit_id, date) DO UPDATE SET is_minimum = excluded.is_minimum""",
            (habit_id, day.isoformat(), int(is_minimum)),
        )
    else:
        conn.execute(
            "DELETE FROM habit_logs WHERE habit_id = ? AND date = ?",
            (habit_id, day.isoformat()),
        )
    conn.commit()
    conn.close()



# ---------------------------------------------------------------------------
# Calendar events (local cache of Google Calendar)
# ---------------------------------------------------------------------------

# "Which events belong to this day?" is used by both functions below, so it
# lives in one place. Timed events: the date part of `start` matches.
# All-day events: Google's end date is EXCLUSIVE (a one-day event on the 29th
# has end = the 30th), so the event covers `day` if start <= day < end.
_EVENTS_ON_DAY = """(all_day = 0 AND substr(start, 1, 10) = :day)
                    OR (all_day = 1 AND start <= :day AND "end" > :day)"""


def replace_events_for_day(day, events):
    """Swap the cached events for one day with a fresh list from Google.

    Delete-then-insert (instead of only inserting) means an event you deleted
    in Google Calendar also disappears here. Both steps run in one transaction:
    if anything fails, neither happens, so the cache is never half-updated.
    """
    conn = get_connection()
    with conn:  # `with conn` = commit if everything worked, roll back if not
        conn.execute(f"DELETE FROM events WHERE {_EVENTS_ON_DAY}", {"day": day.isoformat()})
        conn.executemany(
            """INSERT OR REPLACE INTO events (id, title, start, "end", all_day, attendees, synced_at)
               VALUES (:id, :title, :start, :end, :all_day, :attendees, :synced_at)""",
            [{**e, "synced_at": now_str()} for e in events],
        )
    conn.close()


def get_events_for_day(day):
    """Cached events for one day: all-day ones first, then by start time."""
    conn = get_connection()
    rows = conn.execute(
        f"SELECT * FROM events WHERE {_EVENTS_ON_DAY} ORDER BY all_day DESC, start",
        {"day": day.isoformat()},
    ).fetchall()
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# Settings (tiny key/value store)
# ---------------------------------------------------------------------------

def get_setting(key, default=None):
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_connection()
    conn.execute(
        """INSERT INTO settings (key, value) VALUES (?, ?)
           ON CONFLICT (key) DO UPDATE SET value = excluded.value""",
        (key, value),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

def add_subject(name, base_attended=0, base_missed=0):
    conn = get_connection()
    conn.execute(
        "INSERT INTO subjects (name, base_attended, base_missed) VALUES (?, ?, ?)",
        (name, base_attended, base_missed),
    )
    conn.commit()
    conn.close()


def archive_subject(subject_id):
    """Hide a subject at the end of the semester; its history stays."""
    conn = get_connection()
    conn.execute("UPDATE subjects SET active = 0 WHERE id = ?", (subject_id,))
    conn.commit()
    conn.close()


def get_subjects_with_counts():
    """Every active subject with its total attended and missed classes.

    LEFT JOIN keeps subjects that have no attendance rows yet (a plain JOIN
    would drop them). GROUP BY squashes each subject's rows into one line.
    In SQLite, (status = 'attended') is 1 or 0, so SUM() counts the matches.
    COALESCE(x, 0) turns "no rows at all" (NULL) into 0.
    """
    conn = get_connection()
    rows = conn.execute(
        """SELECT s.id, s.name,
                  s.base_attended + COALESCE(SUM(a.status = 'attended'), 0) AS attended,
                  s.base_missed   + COALESCE(SUM(a.status = 'missed'), 0)   AS missed
           FROM subjects s
           LEFT JOIN attendance a ON a.subject_id = s.id
           WHERE s.active = 1
           GROUP BY s.id
           ORDER BY s.name"""
    ).fetchall()
    conn.close()
    return rows


def log_class(subject_id, day, status, slot_id=None):
    """Record one class as 'attended' or 'missed'.
    slot_id is set when it's logged from a timetable class on the Today page."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO attendance (subject_id, date, status, logged_at, slot_id)
           VALUES (?, ?, ?, ?, ?)""",
        (subject_id, day.isoformat(), status, now_str(), slot_id),
    )
    conn.commit()
    conn.close()


def get_last_class(subject_id):
    """The most recently logged class for a subject (or None), for the Undo button."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM attendance WHERE subject_id = ? ORDER BY id DESC LIMIT 1",
        (subject_id,),
    ).fetchone()
    conn.close()
    return row


def delete_class(attendance_id):
    conn = get_connection()
    conn.execute("DELETE FROM attendance WHERE id = ?", (attendance_id,))
    conn.commit()
    conn.close()



# ---------------------------------------------------------------------------
# Timetable
# ---------------------------------------------------------------------------

def add_timetable_slot(subject_id, weekday, start_time, end_time, room=None):
    """start_time / end_time are datetime.time objects; stored as 'HH:MM'
    text, which sorts correctly ('09:00' < '14:30')."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO timetable (subject_id, weekday, start_time, end_time, room)
           VALUES (?, ?, ?, ?, ?)""",
        (subject_id, weekday, start_time.strftime("%H:%M"), end_time.strftime("%H:%M"), room or None),
    )
    conn.commit()
    conn.close()


def delete_timetable_slot(slot_id):
    conn = get_connection()
    conn.execute("DELETE FROM timetable WHERE id = ?", (slot_id,))
    conn.commit()
    conn.close()


def get_timetable():
    """The whole week, Monday first, each day in time order. Only active subjects."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT t.*, s.name AS subject
           FROM timetable t
           JOIN subjects s ON s.id = t.subject_id
           WHERE s.active = 1
           ORDER BY t.weekday, t.start_time"""
    ).fetchall()
    conn.close()
    return rows


def get_classes_for_day(day):
    """Timetable classes on one date, plus whether each was already marked.

    The LEFT JOIN looks for an attendance row for this exact slot on this date:
    found -> logged_status is 'attended'/'missed'; not found -> it's NULL.
    """
    conn = get_connection()
    rows = conn.execute(
        """SELECT t.*, s.name AS subject,
                  a.status AS logged_status, a.id AS attendance_id
           FROM timetable t
           JOIN subjects s ON s.id = t.subject_id AND s.active = 1
           LEFT JOIN attendance a ON a.slot_id = t.id AND a.date = :day
           WHERE t.weekday = :weekday
           ORDER BY t.start_time""",
        {"day": day.isoformat(), "weekday": day.weekday()},
    ).fetchall()
    conn.close()
    return rows



# ---------------------------------------------------------------------------
# Meeting notes
# ---------------------------------------------------------------------------

def get_event(event_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    conn.close()
    return row


def get_note_for_event(event_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM notes WHERE event_id = ?", (event_id,)).fetchone()
    conn.close()
    return row


def action_item_lines(text):
    """Split the Action items box into clean, unique task titles.

    Strips bullets people type out of habit ("- ", "* ", "• ", "[ ] ")
    so "- Email Dr. Rao" and "Email Dr. Rao" count as the same item.
    dict.fromkeys(...) removes duplicates but keeps the original order.
    """
    lines = [re.sub(r"^([-*•]|\[\s?\])\s*", "", line.strip()) for line in text.splitlines()]
    return list(dict.fromkeys(line for line in lines if line))


def save_note(event, agenda, notes, decisions, action_items, tag="college"):
    """Create or update the note for this event, then sync its action items
    into the tasks table. Returns (number of tasks added, number removed).

    Everything happens in one transaction (`with conn`): either the note AND
    its tasks are saved, or nothing is, so they can never get out of step.
    """
    conn = get_connection()
    with conn:
        note_id = _upsert_note(conn, event, agenda, notes, decisions, action_items)
        added, removed = _sync_action_items(conn, note_id, action_items, tag)
    conn.close()
    return added, removed


def _upsert_note(conn, event, agenda, notes, decisions, action_items):
    """Insert or update the notes row and return its id.
    (The leading _ means "only used inside this file".)"""
    conn.execute(
        """INSERT INTO notes (event_id, title, start, "end", attendees,
                              agenda, notes, decisions, action_items, created_at, updated_at)
           VALUES (:event_id, :title, :start, :end, :attendees,
                   :agenda, :notes, :decisions, :action_items, :now, :now)
           ON CONFLICT (event_id) DO UPDATE SET
               -- refresh the copied details too, in case the event was renamed
               title = excluded.title, start = excluded.start, "end" = excluded."end",
               attendees = excluded.attendees,
               agenda = excluded.agenda, notes = excluded.notes,
               decisions = excluded.decisions, action_items = excluded.action_items,
               updated_at = excluded.updated_at""",
        {"event_id": event["id"], "title": event["title"], "start": event["start"],
         "end": event["end"], "attendees": event["attendees"],
         "agenda": agenda, "notes": notes, "decisions": decisions,
         "action_items": action_items, "now": now_str()},
    )
    # After an upsert we don't know if it inserted or updated, so look the id up.
    return conn.execute("SELECT id FROM notes WHERE event_id = ?", (event["id"],)).fetchone()["id"]


def _sync_action_items(conn, note_id, action_items, tag):
    """Make the note's tasks match its Action items box.

    - new line                        -> new task (due today, so it shows on Today)
    - line already has a task         -> nothing (no duplicates on re-save)
    - line gone, task still open      -> task deleted (e.g. you fixed a typo)
    - line gone, task done or dropped -> kept: that's history, not a mistake
    """
    wanted = action_item_lines(action_items)
    existing = {
        row["title"]: row
        for row in conn.execute("SELECT id, title, status FROM tasks WHERE note_id = ?", (note_id,))
    }

    added = 0
    for title in wanted:
        if title not in existing:
            conn.execute(
                """INSERT INTO tasks (title, tag, due_date, created_at, type, note_id)
                   VALUES (?, ?, ?, ?, 'task', ?)""",
                (title, tag, date.today().isoformat(), now_str(), note_id),
            )
            added += 1

    removed = 0
    for title, row in existing.items():
        if title not in wanted and row["status"] == "todo":
            conn.execute("DELETE FROM tasks WHERE id = ?", (row["id"],))
            removed += 1
    return added, removed


def get_tasks_for_note(note_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM tasks WHERE note_id = ? ORDER BY id", (note_id,)
    ).fetchall()
    conn.close()
    return rows


def get_recent_notes(limit=20):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM notes ORDER BY start DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return rows



# ---------------------------------------------------------------------------
# Export (whole tables as pandas DataFrames)
# ---------------------------------------------------------------------------

def list_tables():
    """Names of all our tables. sqlite_master is SQLite's own list of what's
    in the file; names starting with sqlite_ are its internal bookkeeping."""
    conn = get_connection()
    names = [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]
    conn.close()
    return names


def read_table(name):
    """A whole table as a pandas DataFrame.

    Table names can't be ? placeholders, so we only accept names that really
    exist (from list_tables) and wrap them in "quotes" before using them in SQL.
    """
    if name not in list_tables():
        raise ValueError(f"Unknown table: {name}")
    conn = get_connection()
    df = pd.read_sql_query(f'SELECT * FROM "{name}"', conn)
    conn.close()
    return df


if __name__ == "__main__":
    # Lets you run `python -m core.db` to create the database and peek inside.
    init_db()
    conn = get_connection()
    tables = [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )]
    print("Database:", DB_PATH)
    print("Tables:", tables)
    for h in conn.execute("SELECT * FROM habits"):
        print("Habit:", dict(h))
    conn.close()
