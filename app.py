"""
app.py — the front door of the app.

Run it with:  streamlit run app.py
Streamlit automatically turns every file inside pages/ into a page in the
sidebar, so this file only needs to set things up and show a home screen.
"""

import streamlit as st

from core import db

st.set_page_config(page_title="Productivity", layout="wide")

# Make sure the database and tables exist before any page tries to use them.
# It's cheap and safe to run on every reload ("IF NOT EXISTS").
db.init_db()

st.title("My Productivity App")
st.write("Step 1 works: the database is ready. Pages will appear in the sidebar as we build them.")

# Quick sanity check so you can see the seed habits made it into the database.
conn = db.get_connection()
habits = conn.execute("SELECT name, minimum_version, target_per_week FROM habits").fetchall()
conn.close()

st.subheader("Habits in the database")
for h in habits:
    st.write(f"- **{h['name']}** — minimum: _{h['minimum_version']}_ — target {h['target_per_week']}/7 days")
