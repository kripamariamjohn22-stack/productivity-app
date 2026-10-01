"""
Timetable page: enter your weekly class schedule once.
Today's classes then show up on the Today page with attended/missed buttons.
"""

from datetime import time

import streamlit as st

from core import db

db.init_db()
st.title("Timetable")

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

subjects = db.get_subjects_with_counts()
if not subjects:
    st.info("Add your subjects on the Attendance page first, then come back here.")
    st.stop()  # stop running the rest of this page

# ---------------------------------------------------------------------------
# Add a class
# ---------------------------------------------------------------------------
with st.form("add_slot"):
    st.subheader("Add a class")
    c1, c2, c3, c4, c5 = st.columns([3, 2, 1, 1, 2])
    # The dropdown holds subject ids (Streamlit can't store database rows in a
    # widget); format_func turns each id into its name for display.
    names = {s["id"]: s["name"] for s in subjects}
    subject_id = c1.selectbox("Subject", list(names), format_func=lambda sid: names[sid])
    weekday = c2.selectbox("Day", range(7), format_func=lambda d: DAYS[d])
    start = c3.time_input("Start", value=time(9, 0), step=300)  # step = 5 minutes
    end = c4.time_input("End", value=time(10, 0), step=300)
    room = c5.text_input("Room (optional)")
    # No clear_on_submit here: when adding the same class for several days,
    # you only change the day and press Add again.
    if st.form_submit_button("Add class"):
        if end <= start:
            st.error("End time must be after the start time.")
        else:
            db.add_timetable_slot(subject_id, weekday, start, end, room.strip())
            st.success(f"Added {names[subject_id]} on {DAYS[weekday]} {start:%H:%M}–{end:%H:%M}.")

# ---------------------------------------------------------------------------
# The week
# ---------------------------------------------------------------------------
st.subheader("Your week")
slots = db.get_timetable()
if not slots:
    st.write("No classes yet.")

for weekday, day_name in enumerate(DAYS):
    day_slots = [s for s in slots if s["weekday"] == weekday]
    if not day_slots:
        continue  # skip empty days (e.g. Sunday) instead of showing a blank heading
    st.markdown(f"**{day_name}**")
    for slot in day_slots:
        text_col, delete_col = st.columns([8, 1])
        room_text = f" · {slot['room']}" if slot["room"] else ""
        text_col.write(f"{slot['start_time']}–{slot['end_time']} · {slot['subject']}{room_text}")
        if delete_col.button("Delete", key=f"del_{slot['id']}"):
            db.delete_timetable_slot(slot["id"])
            st.rerun()
