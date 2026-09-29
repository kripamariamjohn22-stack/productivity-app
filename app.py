"""
app.py — the front door of the app.

Run it with:  streamlit run app.py

st.navigation lets us list the pages ourselves (instead of Streamlit guessing
from file names), give them proper titles, and make Today the page you land on.
"""

import streamlit as st

from core import db

st.set_page_config(page_title="Productivity", layout="wide")

# Make sure the database and tables exist before any page tries to use them.
# It's cheap and safe to run on every reload ("IF NOT EXISTS").
db.init_db()

page = st.navigation([
    st.Page("pages/1_Today.py", title="Today", icon="📅", default=True),
    st.Page("pages/2_To-do.py", title="To-do", icon="✅"),
    st.Page("pages/3_Habits.py", title="Habits", icon="🔥"),
    st.Page("pages/4_Attendance.py", title="Attendance", icon="🎓"),
    st.Page("pages/5_Timetable.py", title="Timetable", icon="🗓️"),
])
page.run()
