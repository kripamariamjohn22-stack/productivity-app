"""
Habits page: tick off today's habits, see weekly progress, streaks and a heatmap.
"""

import sqlite3
from datetime import date

import plotly.graph_objects as go
import streamlit as st

from core import analytics, db

st.set_page_config(page_title="Habits", layout="wide")
db.init_db()

st.title("Habits")

# Heatmap colours: one blue, light -> dark, so "more done" always looks darker.
# Grey means "not done" (not red: a missed day isn't an error, just nothing).
COLOR_NONE = "#dddcd8"
COLOR_MIN = "#86b6ef"
COLOR_FULL = "#256abf"


def save_log(habit_id, day):
    """Runs when either checkbox changes. Reads both boxes and writes one row.
    'Minimum only' ticked on its own still counts as done."""
    full = st.session_state[f"full_{habit_id}_{day}"]
    minimum = st.session_state[f"min_{habit_id}_{day}"]
    db.set_habit_log(habit_id, day, done=full or minimum, is_minimum=minimum and not full)


def heatmap_figure(logs):
    values, labels = analytics.heatmap_grid(logs)
    fig = go.Figure(
        go.Heatmap(
            z=values.values.tolist(),
            x=list(values.columns),
            y=list(values.index),
            customdata=labels.values.tolist(),
            hovertemplate="%{customdata}<extra></extra>",
            # 3 flat colour bands for the values 0, 1, 2 (instead of a smooth gradient)
            colorscale=[
                [0.0, COLOR_NONE], [0.33, COLOR_NONE],
                [0.33, COLOR_MIN], [0.66, COLOR_MIN],
                [0.66, COLOR_FULL], [1.0, COLOR_FULL],
            ],
            zmin=0, zmax=2,
            showscale=False,
            xgap=2, ygap=2,  # little gaps so each day reads as its own square
        )
    )
    fig.update_layout(
        height=190,
        margin=dict(l=0, r=0, t=10, b=0),
        yaxis=dict(autorange="reversed"),  # Monday on top, like a calendar
        xaxis=dict(showgrid=False, tickformat="%b"),
    )
    return fig


# ---------------------------------------------------------------------------
# Check-in
# ---------------------------------------------------------------------------
# A date picker so you can fill in yesterday if you forgot.
day = st.date_input("Logging for", value=date.today(), max_value=date.today())
todays_logs = db.get_logs_for_date(day)
habits = db.get_habits()

st.subheader("Check-in")
for habit in habits:
    hid = habit["id"]
    logged = hid in todays_logs
    is_min = todays_logs.get(hid, False)
    col_full, col_min = st.columns([2, 3])
    # The key includes the date, so switching dates gives fresh checkboxes
    # instead of Streamlit remembering the old day's ticks.
    col_full.checkbox(
        habit["name"], value=logged and not is_min,
        key=f"full_{hid}_{day}", on_change=save_log, args=(hid, day),
    )
    if habit["minimum_version"]:
        col_min.checkbox(
            f"Only the minimum: {habit['minimum_version']}", value=is_min,
            key=f"min_{hid}_{day}", on_change=save_log, args=(hid, day),
        )
    else:
        # No minimum defined: keep a hidden False value so save_log still works.
        st.session_state[f"min_{hid}_{day}"] = False

# ---------------------------------------------------------------------------
# Progress per habit
# ---------------------------------------------------------------------------
st.subheader("Progress")
st.caption("Heatmap: grey = not done · light blue = minimum version · dark blue = full habit")

for habit in habits:
    logs = db.get_habit_logs(habit["id"])
    target = habit["target_per_week"]
    s = analytics.habit_summary(logs, target)

    st.markdown(f"#### {habit['name']}")
    if s["needed"] == 0:
        week_text = f"This week: {s['done_this_week']}/{target} ✅ target met"
    elif s["needed"] > s["days_left"]:
        week_text = (f"This week: {s['done_this_week']}/{target} — can't hit the target now, "
                     "but every day still counts")
    else:
        week_text = (f"This week: {s['done_this_week']}/{target} — "
                     f"{s['needed']} more in the {s['days_left']} day(s) left")
    st.write(week_text)
    st.write(f"🔥 Streak: {s['streak_weeks']} week(s) in a row at {target}/7")
    st.plotly_chart(heatmap_figure(logs), width="stretch", key=f"heat_{habit['id']}")

# ---------------------------------------------------------------------------
# Manage habits
# ---------------------------------------------------------------------------
with st.expander("Add or archive habits"):
    with st.form("add_habit", clear_on_submit=True):
        name = st.text_input("Habit")
        minimum = st.text_input("Minimum version (the tiny bad-day version)")
        target = st.slider("Target days per week", 1, 7, 5)
        if st.form_submit_button("Add habit"):
            if not name.strip():
                st.error("Give the habit a name.")
            else:
                try:
                    db.add_habit(name.strip(), minimum.strip(), target)
                    st.rerun()
                except sqlite3.IntegrityError:
                    # The habits table has UNIQUE on name.
                    st.error("You already have a habit with that name (maybe an archived one).")

    st.write("Archiving hides a habit but keeps its history.")
    for habit in habits:
        if st.button(f"Archive “{habit['name']}”", key=f"archive_{habit['id']}"):
            db.archive_habit(habit["id"])
            st.rerun()
