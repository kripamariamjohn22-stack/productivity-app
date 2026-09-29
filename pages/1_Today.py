"""
Today page: calendar events, today's tasks and habits in one place.

Calendar events and timetable classes have times, so they form a timeline
with a "now" line.
Below it: assignments/exams coming up soon, then tasks and habits (which
don't have times) in an "Anytime today" block you can tick off right here.
"""

from datetime import date, datetime, time

import streamlit as st

from core import analytics, db, gcal

db.init_db()
today = date.today()
db.roll_over_tasks()  # same as the To-do page: overdue tasks become today's tasks

# ---------------------------------------------------------------------------
# Sync with Google Calendar
# ---------------------------------------------------------------------------
# session_state survives re-runs but resets when you open a new browser tab.
# So this syncs once when you open the app, not on every single click.
if "synced_once" not in st.session_state:
    st.session_state.synced_once = True
    st.session_state.sync_result = gcal.sync_day(today)

title_col, button_col = st.columns([5, 1])
title_col.title(f"Today · {today:%A %d %B}")
if button_col.button("🔄 Sync now"):
    st.session_state.sync_result = gcal.sync_day(today)

ok, message = st.session_state.sync_result
if ok:
    st.caption(f"{message} Last sync: {db.get_setting('last_sync', 'never')}")
else:
    st.warning(message + f" Last successful sync: {db.get_setting('last_sync', 'never')}")

events = db.get_events_for_day(today)
classes = db.get_classes_for_day(today)
tasks = db.get_tasks_for_day(today)
habits = db.get_habits()
habit_logs = db.get_logs_for_date(today)

# One-line summary at the top, so a glance tells you how the day is going.
tasks_done = sum(1 for t in tasks if t["status"] == "done")
st.write(
    f"**{len(events)}** event(s) · **{len(classes)}** class(es) · "
    f"**{tasks_done}/{len(tasks)}** tasks done · **{len(habit_logs)}/{len(habits)}** habits done"
)

# ---------------------------------------------------------------------------
# Timeline: calendar events + today's classes, merged and sorted by time
# ---------------------------------------------------------------------------
st.subheader("Timeline")

for e in events:
    if e["all_day"]:
        st.write(f"📌 **All day** · {e['title']}")

# Put both kinds into one list of dicts with the same keys, so one loop can
# draw them in time order. `slot` is None for calendar events.
# .astimezone() gives every time a time zone, so we can compare them with
# Google's times like 2026-09-29T10:00:00+05:30 (comparing times with and
# without a time zone raises an error in Python).
timeline = [
    {"start": datetime.fromisoformat(e["start"]), "end": datetime.fromisoformat(e["end"]),
     "title": e["title"], "slot": None}
    for e in events if not e["all_day"]
]
for c in classes:
    room = f" · {c['room']}" if c["room"] else ""
    timeline.append({
        "start": datetime.combine(today, time.fromisoformat(c["start_time"])).astimezone(),
        "end": datetime.combine(today, time.fromisoformat(c["end_time"])).astimezone(),
        "title": f"🎓 {c['subject']}{room}",
        "slot": c,
    })
timeline.sort(key=lambda item: item["start"])

now = datetime.now().astimezone()
now_shown = False
for item in timeline:
    if not now_shown and item["start"] > now:
        st.markdown(f"🔴 **now · {now:%H:%M}**")
        now_shown = True

    line = f"{item['start']:%H:%M}–{item['end']:%H:%M} · {item['title']}"
    slot = item["slot"]
    # Classes get a narrow column on the right for the attendance buttons.
    if slot:
        text_col, a_col, b_col = st.columns([6, 1, 1])
    else:
        text_col = st.container()

    if item["end"] < now:
        text_col.caption(f"~~{line}~~")      # already over: greyed out
    elif item["start"] <= now:
        text_col.markdown(f"▶️ **{line}** (happening now)")
    else:
        text_col.markdown(line)

    if slot:
        sid = slot["id"]
        if slot["logged_status"] is None:
            if a_col.button("✅", key=f"cls_att_{sid}", help="Attended"):
                db.log_class(slot["subject_id"], today, "attended", slot_id=sid)
                st.rerun()
            if b_col.button("❌", key=f"cls_miss_{sid}", help="Missed"):
                db.log_class(slot["subject_id"], today, "missed", slot_id=sid)
                st.rerun()
        else:
            a_col.write("✅" if slot["logged_status"] == "attended" else "❌")
            if b_col.button("↩️", key=f"cls_undo_{sid}", help="Undo"):
                db.delete_class(slot["attendance_id"])
                st.rerun()

if not now_shown and timeline:
    st.markdown(f"🔴 **now · {now:%H:%M}** · nothing else scheduled today")
if not timeline and not events:
    st.write("No calendar events or classes today (or not synced yet).")

# ---------------------------------------------------------------------------
# Deadlines: assignments and exams in the next 7 days (and overdue ones)
# ---------------------------------------------------------------------------
deadlines = db.get_upcoming_deadlines(today, days=7)
if deadlines:
    st.subheader("Deadlines")
for d in deadlines:
    days_left, when = analytics.countdown(d["due_date"], today)
    icon = "📖" if d["type"] == "exam" else "📝"
    subject = f" · {d['subject']}" if d["subject"] else ""
    line = f"{icon} **{d['title']}**{subject} · {when}"
    text_col, done_col = st.columns([7, 1])
    # Colour by urgency: red = missed or today, yellow = within 2 days.
    if days_left <= 0:
        text_col.error(line)
    elif days_left <= 2:
        text_col.warning(line)
    else:
        text_col.markdown(line)
    if done_col.button("Done", key=f"deadline_done_{d['id']}"):
        db.complete_task(d["id"])
        st.rerun()

# ---------------------------------------------------------------------------
# Anytime today: tasks
# ---------------------------------------------------------------------------
st.subheader("Anytime today")
st.markdown("**Tasks**")
if not tasks:
    st.write("No tasks due today. Add some on the To-do page.")

for task in tasks:
    tid = task["id"]
    if task["status"] == "done":
        mins = f" · {task['actual_minutes']} min" if task["actual_minutes"] else ""
        st.write(f"✅ ~~{task['title']}~~{mins}")
        continue

    info, minutes_col, done_col = st.columns([6, 2, 1])
    planned = f" · planned {task['planned_minutes']} min" if task["planned_minutes"] else ""
    info.markdown(f"⬜ **{task['title']}**  \n{task['priority']} · {task['tag']}{planned}")
    if task["times_postponed"] >= 3:
        info.warning(f"Postponed {task['times_postponed']}x — break it down or drop it?")
    actual = minutes_col.number_input(
        "Actual min", min_value=0, step=5,
        value=task["planned_minutes"] or 0, key=f"today_actual_{tid}",
    )
    if done_col.button("Done", key=f"today_done_{tid}"):
        db.complete_task(tid, actual_minutes=actual or None)
        st.rerun()

# ---------------------------------------------------------------------------
# Anytime today: habits
# ---------------------------------------------------------------------------
st.markdown("**Habits**")


def save_log(habit_id):
    """Same rule as the Habits page: 'minimum only' on its own still counts as done."""
    full = st.session_state[f"today_full_{habit_id}"]
    minimum = st.session_state.get(f"today_min_{habit_id}", False)
    db.set_habit_log(habit_id, today, done=full or minimum, is_minimum=minimum and not full)


for habit in habits:
    hid = habit["id"]
    is_min = habit_logs.get(hid, False)
    col_full, col_min = st.columns([2, 3])
    col_full.checkbox(
        habit["name"], value=hid in habit_logs and not is_min,
        key=f"today_full_{hid}", on_change=save_log, args=(hid,),
    )
    if habit["minimum_version"]:
        col_min.checkbox(
            f"Only the minimum: {habit['minimum_version']}", value=is_min,
            key=f"today_min_{hid}", on_change=save_log, args=(hid,),
        )
