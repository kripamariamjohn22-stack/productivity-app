"""
Insights page: what your data says. Charts arrive step by step in Phase 4;
for now it holds the CSV export, so you can explore your data in pandas too.
"""

import io
import zipfile
from datetime import date

import streamlit as st

from core import db

db.init_db()
st.title("Insights")

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
st.subheader("Export your data")
st.caption(
    "Every table as a CSV file: open in Excel/Sheets, or in a notebook with "
    "pd.read_csv(\"tasks.csv\")."
)

tables = {name: db.read_table(name) for name in db.list_tables()}

# One zip with every table. io.BytesIO is a "file" that lives in memory,
# so nothing is written to disk; Streamlit hands the bytes to your browser.
buffer = io.BytesIO()
with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
    for name, df in tables.items():
        zf.writestr(f"{name}.csv", df.to_csv(index=False))  # index=False: skip pandas' row numbers
st.download_button(
    "⬇️ Download all tables (.zip)",
    data=buffer.getvalue(),
    file_name=f"productivity-export-{date.today()}.zip",
    mime="application/zip",
)

# Or one table at a time, with a peek at what's inside.
for name, df in tables.items():
    with st.expander(f"{name} · {len(df)} row(s)"):
        st.download_button(
            f"⬇️ {name}.csv", data=df.to_csv(index=False),
            file_name=f"{name}.csv", mime="text/csv", key=f"csv_{name}",
        )
        st.dataframe(df.tail(20), hide_index=True)  # last 20 rows = most recent
