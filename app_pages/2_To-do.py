"""
To-do page: add tasks, finish or drop them, and see which ones keep getting postponed.

Streamlit re-runs this whole file from top to bottom every time you click
something. That's why there's no "event loop": each click = fresh run
that reads the latest data from the database and redraws the page.
"""

from datetime import date, datetime, timedelta

import streamlit as st

from core import analytics, db, gcal, pomodoro

st.set_page_config(page_title="To-do", layout="wide")
db.init_db()  # in case this page is opened directly before the home page

# Roll over overdue tasks every time the page loads (safe to repeat, see db.py).
rolled = db.roll_over_tasks()
if rolled:
    st.info(f"Rolled over {rolled} unfinished task(s) to today.")

st.title("To-do")

# Result of the last block/unblock click (saved before st.rerun, shown here).
if "block_message" in st.session_state:
    ok, message = st.session_state.pop("block_message")
    (st.success if ok else st.error)(message)

# ---------------------------------------------------------------------------
# Add a task
# ---------------------------------------------------------------------------
# st.form groups inputs so the page only re-runs when you press the button,
# not on every keystroke. clear_on_submit empties the boxes afterwards.
with st.form("add_task", clear_on_submit=True):
    st.subheader("Add a task")
    title = st.text_input("Title")
    col1, col2, col3, col4 = st.columns(4)
    priority = col1.selectbox("Priority", db.PRIORITIES, index=1)  # default: Med
    tag = col2.selectbox("Tag", db.TAGS)
    due = col3.date_input("Due date", value=date.today())
    planned = col4.number_input("Planned minutes", min_value=0, step=15, value=30)
    col5, col6, col7 = st.columns([1, 1, 2])
    task_type = col5.selectbox("Type", db.TASK_TYPES, format_func=str.capitalize)
    # Subject is optional: None shows as "—". It's mainly for assignments/exams.
    subject_names = {s["id"]: s["name"] for s in db.get_subjects_with_counts()}
    subject_id = col6.selectbox(
        "Subject", [None, *subject_names],
        format_func=lambda sid: "—" if sid is None else subject_names[sid],
    )
    no_due = col7.checkbox("No due date")

    if st.form_submit_button("Add task"):
        if not title.strip():
            st.error("Give the task a title.")
        elif task_type != "task" and no_due:
            st.error("Assignments and exams need a date.")
        else:
            db.add_task(
                title.strip(),
                priority=priority,
                due_date=None if no_due else due,
                tag=tag,
                planned_minutes=planned or None,  # 0 means "didn't plan"
                type=task_type,
                subject_id=subject_id,
            )
            st.success(f"Added: {title.strip()}")

# ---------------------------------------------------------------------------
# Open tasks
# ---------------------------------------------------------------------------
st.subheader("Open tasks")
open_tasks = db.get_open_tasks()
if not open_tasks:
    st.write("Nothing to do. 🎉")

TYPE_LABELS = {"task": "", "assignment": "📝 Assignment · ", "exam": "📖 Exam · "}

pomo_totals = db.get_pomodoro_totals()  # {task_id: (count, minutes)}
for task in open_tasks:
    # Every widget needs a unique key, otherwise Streamlit can't tell the
    # "Done" button of task 3 apart from the "Done" button of task 7.
    tid = task["id"]
    # Wider columns for the text buttons (Done, Drop) than for the emoji ones.
    info, minutes_col, pomo_col, block_col, done_col, drop_col = st.columns([5, 1.6, 0.8, 1, 1, 1])

    planned_text = f" · planned {task['planned_minutes']} min" if task["planned_minutes"] else ""
    n_pomos, pomo_minutes = pomo_totals.get(tid, (0, 0))
    planned_text += f" · 🍅×{n_pomos} = {pomo_minutes} min" if n_pomos else ""
    subject_text = f" · {task['subject']}" if task["subject"] else ""
    subject_text += f" · 📝 from “{task['meeting']}”" if task["meeting"] else ""
    days_left, when = analytics.countdown(task["due_date"])
    info.markdown(
        f"**{task['title']}**  \n"
        f"{TYPE_LABELS[task['type']]}{task['priority']} · {task['tag']}{subject_text}"
        f" · due {when}{planned_text}"
    )
    # Deadlines get a coloured note when they're close or already missed.
    if task["type"] != "task" and days_left is not None:
        if days_left < 0:
            info.error(f"{task['type'].capitalize()} overdue by {-days_left} day(s)!")
        elif days_left <= 2:
            info.warning(f"{task['type'].capitalize()} {when}!")
    if task["times_postponed"] >= 3:
        info.warning(f"Postponed {task['times_postponed']}x — break it down or drop it?")
    elif task["times_postponed"] > 0:
        info.caption(f"Postponed {task['times_postponed']}x")

    # Pre-fill actual minutes with your Pomodoro time if you used the timer,
    # else the plan, so if it matched you just click Done.
    actual = minutes_col.number_input(
        "Actual min", min_value=0, step=5,
        value=pomo_minutes or task["planned_minutes"] or 0,
        key=f"actual_{tid}_{pomo_minutes}",  # new key when Pomodoro time changes (see Today page)
    )
    pomodoro.start_button(pomo_col, tid)

    # 🗓️ Time block in Google Calendar. A popover is a small panel that opens
    # on click, so the row stays compact.
    blocks = db.get_time_blocks(task_id=tid)
    with block_col.popover("🗓️" if not blocks else f"🗓️{len(blocks)}", help="Block time in Google Calendar"):
        for blk in blocks:
            start = datetime.fromisoformat(blk["start"])
            end = datetime.fromisoformat(blk["end"])
            text_c, remove_c = st.columns([3, 1])
            text_c.write(f"🎯 {start:%a %d %b %H:%M}–{end:%H:%M}")
            if remove_c.button("✖", key=f"unblock_{blk['id']}", help="Remove from Google Calendar"):
                ok, message = gcal.remove_block(blk)
                st.session_state["block_message"] = (ok, message)
                st.rerun()
        # Default: the task's due date (or today) at the next full hour.
        next_hour = (datetime.now() + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        due = date.fromisoformat(task["due_date"]) if task["due_date"] else date.today()
        day = st.date_input("Day", value=max(due, date.today()), key=f"block_day_{tid}")
        at_time = st.time_input("Start", value=next_hour.time(), step=900, key=f"block_time_{tid}")
        length = st.number_input("Minutes", min_value=15, step=15,
                                 value=task["planned_minutes"] or 30, key=f"block_len_{tid}")
        if st.button("Block time", key=f"block_{tid}", type="primary"):
            # .astimezone() attaches your computer's time zone, so Google puts
            # the block at YOUR 14:00, not 14:00 UTC.
            start = datetime.combine(day, at_time).astimezone()
            ok, message = gcal.create_block(task, start, int(length))
            st.session_state["block_message"] = (ok, message)
            st.rerun()
    if done_col.button("Done", key=f"done_{tid}"):
        db.complete_task(tid, actual_minutes=actual or None)
        st.rerun()  # redraw straight away so the task disappears from the list
    if drop_col.button("Drop", key=f"drop_{tid}"):
        db.drop_task(tid)
        st.rerun()

# ---------------------------------------------------------------------------
# Recently closed
# ---------------------------------------------------------------------------
with st.expander("Recently done / dropped"):
    closed = db.get_closed_tasks()
    if not closed:
        st.write("Nothing yet.")
    for task in closed:
        info, undo_col = st.columns([8, 1])
        if task["status"] == "done":
            mins = f" · {task['actual_minutes']} min" if task["actual_minutes"] else ""
            info.write(f"✅ {task['title']}{mins} · {task['completed_at']}")
        else:
            info.write(f"🗑️ ~~{task['title']}~~ · dropped after {task['times_postponed']} postponement(s)")
        if undo_col.button("Undo", key=f"undo_{task['id']}"):
            db.reopen_task(task["id"])
            st.rerun()
