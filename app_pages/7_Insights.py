"""
Insights page: what your data says, plus a CSV export of everything.

Pattern for every insight: core/analytics.py does the maths on a pandas
DataFrame and returns numbers; this page only draws them.
"""

import io
import zipfile
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from core import analytics, db

db.init_db()
st.title("Insights")

# Colours: one fixed colour per meaning, used the same way in every chart.
PLANNED_COLOR = "#2a78d6"  # blue
ACTUAL_COLOR = "#eb6834"   # orange
MIN_TASKS = 3  # fewer tasks than this per tag = too little data to say anything

tasks = db.read_table("tasks")

# ---------------------------------------------------------------------------
# Plan vs actual
# ---------------------------------------------------------------------------
st.subheader("Plan vs actual")
weekly, by_tag = analytics.plan_vs_actual(tasks)

if by_tag.empty:
    st.info("No finished tasks with both planned and actual minutes yet. "
            "Enter actual minutes when you click Done, and this fills up.")
else:
    # The headline: one sentence per tag, biggest underestimate first.
    for tag, row in by_tag.iterrows():
        n = int(row["tasks"])  # iterrows() turns numbers into floats; we want "39", not "39.0"
        # ratio 1.53 -> +53 (% longer than planned); 0.91 -> -9 (% shorter)
        pct = round((row["ratio"] - 1) * 100)
        if n < MIN_TASKS:
            st.write(f"**{tag}**: only {n} task(s) so far, not enough to judge.")
        elif pct >= 10:
            st.write(f"**{tag}** takes **{pct}% longer** than you plan ({n} tasks). Plan more time for it.")
        elif pct <= -10:
            st.write(f"**{tag}** takes **{-pct}% less** time than you plan ({n} tasks): you overestimate it.")
        else:
            st.write(f"**{tag}**: your estimates are about right ({pct:+d}%, {n} tasks).")

    weeks_shown = st.radio("Show last", [4, 8, 12], index=1, horizontal=True,
                           format_func=lambda n: f"{n} weeks")
    cutoff = pd.Timestamp(date.today() - timedelta(weeks=weeks_shown))
    recent = weekly[weekly["week"] >= cutoff]

    # Plotly Express wants "long" data: one row per bar. melt() turns the two
    # columns planned_minutes/actual_minutes into rows with a "kind" label.
    long = recent.melt(
        id_vars=["week", "tag"], value_vars=["planned_minutes", "actual_minutes"],
        var_name="kind", value_name="minutes",
    )
    long["kind"] = long["kind"].map({"planned_minutes": "Planned", "actual_minutes": "Actual"})

    fig = px.bar(
        long, x="week", y="minutes", color="kind", barmode="group",
        facet_col="tag", facet_col_wrap=2,          # one small chart per tag
        category_orders={"tag": db.TAGS, "kind": ["Planned", "Actual"]},  # fixed order, never shuffles
        color_discrete_map={"Planned": PLANNED_COLOR, "Actual": ACTUAL_COLOR},
        labels={"week": "", "minutes": "minutes", "kind": ""},
        height=520,
    )
    fig.update_traces(hovertemplate="Week of %{x|%d %b}<br>%{y} min<extra>%{fullData.name}</extra>")
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))  # "tag=college" -> "college"
    # Legend in its own strip above the charts (margin t) so it can't cover a panel title.
    fig.update_layout(bargap=0.25, bargroupgap=0.08, legend_title_text="",
                      legend=dict(orientation="h", yanchor="bottom", y=1.06, x=0),
                      margin=dict(t=70))
    fig.update_xaxes(tickformat="%d %b", showgrid=False)
    fig.update_yaxes(gridcolor="rgba(137,135,129,0.25)")
    st.plotly_chart(fig, width="stretch")
    st.caption("Only finished tasks with both planned and actual minutes count. "
               "The current week is still in progress.")

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
st.subheader("Export your data")
st.caption(
    "Every table as a CSV file: open in Excel/Sheets, or in a notebook with "
    "pd.read_csv(\"tasks.csv\")."
)

tables = {name: db.read_table(name) for name in db.list_tables()}  # tasks is read again: simpler than special-casing it

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
