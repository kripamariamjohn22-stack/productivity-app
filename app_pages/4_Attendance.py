"""
Attendance page: log each class as attended or missed, and see how much slack you have.
"""

import sqlite3
from datetime import date

import streamlit as st

from core import analytics, db

db.init_db()
st.title("Attendance")

# The target is a setting (not hard-coded) because colleges differ.
# Settings are stored as text, hence int(...).
target = int(db.get_setting("attendance_target", 75))
new_target = st.number_input("Minimum attendance required (%)", 1, 100, target, step=5)
if new_target != target:
    db.set_setting("attendance_target", str(new_target))
    target = new_target

class_day = st.date_input("Class date", value=date.today(), max_value=date.today())

# ---------------------------------------------------------------------------
# Subjects
# ---------------------------------------------------------------------------
subjects = db.get_subjects_with_counts()
if not subjects:
    st.info("No subjects yet. Add them below.")

for subj in subjects:
    sid = subj["id"]
    s = analytics.attendance_status(subj["attended"], subj["missed"], target)
    total = subj["attended"] + subj["missed"]

    st.markdown(f"#### {subj['name']}")
    info, attended_col, missed_col, undo_col = st.columns([5, 1, 1, 1])

    if s["percent"] is None:
        info.write("No classes logged yet.")
    else:
        info.write(f"**{s['percent']:.1f}%** · {subj['attended']}/{total} classes attended")
        if s["must_attend"] is None:
            info.error(f"Can't reach {target}% any more.")
        elif s["must_attend"] > 0:
            info.error(f"⚠️ Below {target}%: attend the next **{s['must_attend']}** class(es) to get back.")
        elif s["can_miss"] == 0:
            info.warning(f"Exactly at the limit: missing the next class drops you below {target}%.")
        else:
            info.success(f"You can miss **{s['can_miss']}** more class(es) and stay at or above {target}%.")

    if attended_col.button("✅ Attended", key=f"att_{sid}"):
        db.log_class(sid, class_day, "attended")
        st.rerun()
    if missed_col.button("❌ Missed", key=f"miss_{sid}"):
        db.log_class(sid, class_day, "missed")
        st.rerun()
    last = db.get_last_class(sid)
    if last and undo_col.button("↩️ Undo", key=f"undo_{sid}",
                                help=f"Remove the last entry: {last['status']} on {last['date']}"):
        db.delete_class(last["id"])
        st.rerun()

# ---------------------------------------------------------------------------
# Add / archive subjects
# ---------------------------------------------------------------------------
with st.expander("Add or archive subjects"):
    with st.form("add_subject", clear_on_submit=True):
        name = st.text_input("Subject name")
        st.caption("Semester already started? Enter the classes so far, so the % is right from day one.")
        c1, c2 = st.columns(2)
        base_attended = c1.number_input("Classes attended so far", min_value=0, step=1)
        base_missed = c2.number_input("Classes missed so far", min_value=0, step=1)
        if st.form_submit_button("Add subject"):
            if not name.strip():
                st.error("Give the subject a name.")
            else:
                try:
                    db.add_subject(name.strip(), base_attended, base_missed)
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("You already have a subject with that name (maybe an archived one).")

    st.write("Archive subjects at the end of the semester. Their history is kept.")
    for subj in subjects:
        if st.button(f"Archive “{subj['name']}”", key=f"archive_{subj['id']}"):
            db.archive_subject(subj["id"])
            st.rerun()
