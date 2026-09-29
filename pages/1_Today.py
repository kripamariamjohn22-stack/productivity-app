"""
Today page: calendar events, today's tasks and habits in one place.

Calendar events have times, so they form a timeline with a "now" line.
Tasks and habits don't have times, so they sit in an "Anytime today" block
underneath, where you can tick them off without leaving the page.
"""

from datetime import date, datetime

import streamlit as st

from core import db, gcal

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
tasks = db.get_tasks_for_day(today)
habits = db.get_habits()
habit_logs = db.get_logs_for_date(today)

# One-line summary at the top, so a glance tells you how the day is going.
tasks_done = sum(1 for t in tasks if t["status"] == "done")
st.write(
    f"**{len(events)}** event(s) · **{tasks_done}/{len(tasks)}** tasks done · "
    f"**{len(habit_logs)}/{len(habits)}** habits done"
)

# ---------------------------------------------------------------------------
# Timeline: calendar events
# ---------------------------------------------------------------------------
st.subheader("Timeline")

for e in events:
    if e["all_day"]:
        st.write(f"📌 **All day** · {e['title']}")

timed = [e for e in events if not e["all_day"]]
# .astimezone() gives "now" a time zone, so we can compare it with Google's
# times like 2026-09-29T10:00:00+05:30 (comparing with and without a
# time zone raises an error in Python).
now = datetime.now().astimezone()
now_shown = False
for e in timed:
    start = datetime.fromisoformat(e["start"])
    end = datetime.fromisoformat(e["end"])
    if not now_shown and start > now:
        st.markdown(f"🔴 **now · {now:%H:%M}**")
        now_shown = True
    line = f"{start:%H:%M}–{end:%H:%M} · {e['title']}"
    if end < now:
        st.caption(f"~~{line}~~")      # already over: greyed out
    elif start <= now:
        st.markdown(f"▶️ **{line}** (happening now)")
    else:
        st.markdown(line)
if not now_shown and timed:
    st.markdown(f"🔴 **now · {now:%H:%M}** · no more events today")
if not events:
    st.write("No calendar events today (or not synced yet).")

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
