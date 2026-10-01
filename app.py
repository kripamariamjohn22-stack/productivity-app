"""
app.py — the front door of the app.

Run it with:  streamlit run app.py

st.navigation lets us list the pages ourselves (instead of Streamlit guessing
from file names), give them proper titles, and make Today the page you land on.
"""

import streamlit as st

from core import db, pomodoro

st.set_page_config(page_title="Productivity", layout="wide")

# Make sure the database and tables exist before any page tries to use them.
# It's cheap and safe to run on every reload ("IF NOT EXISTS").
db.init_db()

# Make it impossible to forget you're looking at a different database.
if db.DB_PATH != db.DEFAULT_DB:
    st.sidebar.warning(f"Using **{db.DB_PATH.name}**, not your real data.")

# The Pomodoro timer lives in the sidebar, so it's visible on every page.
pomodoro.sidebar()

page = st.navigation([
    st.Page("app_pages/1_Today.py", title="Today", icon="📅", default=True),
    st.Page("app_pages/2_To-do.py", title="To-do", icon="✅"),
    st.Page("app_pages/3_Habits.py", title="Habits", icon="🔥"),
    st.Page("app_pages/4_Attendance.py", title="Attendance", icon="🎓"),
    st.Page("app_pages/5_Timetable.py", title="Timetable", icon="🗓️"),
    st.Page("app_pages/6_Notes.py", title="Meeting notes", icon="📝"),
    st.Page("app_pages/7_Insights.py", title="Insights", icon="📊"),
    st.Page("app_pages/8_Weekly_review.py", title="Weekly review", icon="🗒️"),
])
page.run()
