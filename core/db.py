"""
db.py — every piece of database code lives here.

Why one file? So the rest of the app never writes SQL directly.
Pages call simple functions like `add_task(...)` and don't care how
the data is stored. If you ever change the database, you only touch this file.
"""

import sqlite3
from datetime import date, datetime
from pathlib import Path

# The database is a single file. Path(__file__) is this file (core/db.py),
# so .parent.parent is the project root. This works no matter which folder
# you run `streamlit run` from.
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"


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
        -- e.g. "last date we rolled over unfinished tasks".
        CREATE TABLE IF NOT EXISTS settings (
            key    TEXT PRIMARY KEY,
            value  TEXT
        );
        """
    )
    seed_habits(conn)
    conn.commit()
    conn.close()


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


def add_task(title, priority="Med", due_date=None, tag="personal", planned_minutes=None):
    """Insert a new task. due_date is a datetime.date or None."""
    conn = get_connection()
    # The ? placeholders let sqlite3 insert values safely.
    # Never build SQL with f-strings: a title like  it's  would break it.
    conn.execute(
        """INSERT INTO tasks (title, priority, due_date, tag, created_at, planned_minutes)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (title, priority, due_date.isoformat() if due_date else None, tag, now_str(), planned_minutes),
    )
    conn.commit()
    conn.close()


def get_open_tasks():
    """All unfinished tasks: most urgent due date first, then High > Med > Low."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM tasks
           WHERE status = 'todo'
           ORDER BY
             due_date IS NULL,  -- tasks with no due date go last (FALSE=0 sorts first)
             due_date,
             CASE priority WHEN 'High' THEN 0 WHEN 'Med' THEN 1 ELSE 2 END"""
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
    """
    today = (today or date.today()).isoformat()
    conn = get_connection()
    # julianday() turns a date into a day number, so subtracting gives days between.
    cur = conn.execute(
        """UPDATE tasks
           SET times_postponed = times_postponed
                                 + CAST(julianday(?) - julianday(due_date) AS INTEGER),
               due_date = ?
           WHERE status = 'todo' AND due_date IS NOT NULL AND due_date < ?""",
        (today, today, today),
    )
    conn.commit()
    conn.close()
    return cur.rowcount  # how many tasks were rolled over


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
