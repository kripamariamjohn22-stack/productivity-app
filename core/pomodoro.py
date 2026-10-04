"""
pomodoro.py — the timer shown in the sidebar on every page.

Streamlit only redraws when something happens, so a countdown needs a nudge
every second. @st.fragment(run_every=1) re-runs ONLY this small function
each second, not the whole page (which would reset what you're typing).
"""

from datetime import datetime

import streamlit as st

from core import db


def elapsed_seconds(pomodoro):
    started = datetime.strptime(pomodoro["started_at"], "%Y-%m-%d %H:%M:%S")
    return (datetime.now() - started).total_seconds()


@st.fragment(run_every=1)
def timer():
    p = db.get_running_pomodoro()
    if p is None:
        # Finished or cancelled elsewhere (e.g. another tab): redraw the page.
        st.rerun()

    length_s = p["length"] * 60
    left = length_s - elapsed_seconds(p)
    if left <= 0:
        # Time's up, even if the tab was closed meanwhile: log the full length.
        db.finish_pomodoro(p["id"], p["length"], completed=True)
        # Saved for after the rerun: a toast shown right before st.rerun() can get lost.
        st.session_state["pomodoro_message"] = (
            f"🍅 Done! {p['length']} min logged for “{p['title']}”. Take a 5-minute break.")
        st.rerun()  # whole page, so the task's minutes update

    st.markdown(f"**🍅 {p['title']}**")
    st.markdown(f"## {int(left // 60):02d}:{int(left % 60):02d}")  # // whole minutes, % leftover seconds
    st.progress(1 - left / length_s)
    stop, cancel = st.columns(2)
    if stop.button("Stop & log", help="Log the minutes so far"):
        minutes = int(elapsed_seconds(p) // 60)
        if minutes > 0:
            db.finish_pomodoro(p["id"], minutes, completed=False)
        else:
            db.cancel_pomodoro(p["id"])  # under a minute: nothing worth logging
        st.rerun()
    if cancel.button("Cancel", help="Throw this timer away, log nothing"):
        db.cancel_pomodoro(p["id"])
        st.rerun()


def sidebar():
    """Call once per page run (app.py does). Shows the timer only while one runs,
    so idle pages don't re-run every second."""
    if "pomodoro_message" in st.session_state:
        st.toast(st.session_state.pop("pomodoro_message"))
    if db.get_running_pomodoro():
        with st.sidebar:
            timer()


def start_button(column, task_id):
    """A 🍅 button that starts a timer for this task."""
    if column.button("🍅", key=f"pomo_{task_id}", help=f"Start a {db.POMODORO_MINUTES}-minute focus timer"):
        if not db.start_pomodoro(task_id):
            st.toast("A timer is already running: stop it first (sidebar).")
        st.rerun()
