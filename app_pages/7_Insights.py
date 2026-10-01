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
import plotly.graph_objects as go
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
# Postponements
# ---------------------------------------------------------------------------
st.subheader("What gets postponed")
stats = analytics.postponement_stats(tasks)

if stats is None or stats["by_title"].empty:
    st.info("Nothing has been postponed yet. Unfinished tasks roll over each day, and they'll show up here.")
else:
    st.write(f"**{stats['share_postponed']:.0%}** of your tasks get postponed at least once.")
    if stats["stuck_count"]:
        fate = stats["fate"]
        st.write(
            f"Of the **{stats['stuck_count']}** tasks postponed 3+ times: "
            f"{fate.get('done', 0):.0%} got done eventually, {fate.get('dropped', 0):.0%} were dropped, "
            f"{fate.get('todo', 0):.0%} are still open."
        )

    left, right = st.columns([2, 3])
    by_tag = stats["by_tag"].reset_index()  # reset_index turns the tag index back into a column
    fig = px.bar(
        by_tag, x="avg_postponed", y="tag", orientation="h",
        text=by_tag["avg_postponed"].map("{:.1f}".format),  # value printed on each bar
        color_discrete_sequence=[PLANNED_COLOR],  # one series = one colour, no legend needed
        labels={"avg_postponed": "postponements per task", "tag": ""},
        title="Average postponements per task", height=260,
        custom_data=["tasks", "share_postponed"],
    )
    fig.update_traces(
        hovertemplate="%{y}: %{x:.1f} per task<br>%{customdata[1]:.0%} of %{customdata[0]} tasks postponed<extra></extra>",
        textposition="outside", cliponaxis=False,
    )
    fig.update_yaxes(categoryorder="total ascending")  # biggest at the top
    fig.update_xaxes(gridcolor="rgba(137,135,129,0.25)")
    fig.update_layout(margin=dict(l=0, r=30, t=40, b=0), bargap=0.35)
    left.plotly_chart(fig, width="stretch")

    top = stats["by_title"].head(10).reset_index()
    # The spec's rule: the open task itself postponed 3+ times -> break it down or drop it?
    top["suggestion"] = ["break it down or drop it?" if n >= 3 else "" for n in top["open_postponed"]]
    right.markdown("**Most-postponed tasks**")
    # Suggestion right after the name, so it's visible without scrolling the table sideways.
    top = top[["title", "suggestion", "tag", "times", "total_postponed", "still_open"]]
    right.dataframe(
        top.rename(columns={
            "title": "task", "times": "times added",
            "total_postponed": "postponements", "still_open": "open now"}),
        hide_index=True, width="stretch",
        column_config={"suggestion": st.column_config.TextColumn(width="medium")},  # room for the full hint
    )

# ---------------------------------------------------------------------------
# Habits vs tasks
# ---------------------------------------------------------------------------
st.subheader("Habits and getting things done")
HABIT_DONE_COLOR = "#1baf7a"  # aqua: did the habit
HABIT_SKIPPED_COLOR = "#b5b3ad"  # neutral grey: didn't

habits_df = db.read_table("habits")
habits_df = habits_df[habits_df["active"] == 1]
daily = analytics.daily_table(tasks, db.read_table("habit_logs"), habits_df)

if daily.empty:
    st.info("No finished tasks or habit check-ins yet.")
else:
    chart_rows = []
    for habit in habits_df["name"]:
        r = analytics.habit_task_link(daily, habit)
        if not r["enough"]:
            st.write(f"**{habit}**: not enough data yet. Need 5+ days with it and 5+ without "
                     f"(have {r['n_with']} and {r['n_without']}).")
            continue
        more_or_fewer = "more" if r["pct"] >= 0 else "fewer"
        sentence = (f"On days you did **{habit}**, you finished **{abs(r['pct']):.0f}% {more_or_fewer}** tasks "
                    f"({r['with_avg']:.1f} vs {r['without_avg']:.1f} per day; "
                    f"{r['n_with']} days with, {r['n_without']} without).")
        if r["p_value"] < 0.05:
            st.write(f"{sentence} A gap this big is unlikely to be chance (p = {r['p_value']:.2f}).")
        else:
            st.write(f"{sentence} But this could easily be chance (p = {r['p_value']:.2f}): keep collecting data.")
        chart_rows += [
            {"habit": habit, "day": "did it", "tasks": r["with_avg"], "days": r["n_with"]},
            {"habit": habit, "day": "didn't", "tasks": r["without_avg"], "days": r["n_without"]},
        ]

    if chart_rows:
        fig = px.bar(
            pd.DataFrame(chart_rows), x="habit", y="tasks", color="day", barmode="group",
            color_discrete_map={"did it": HABIT_DONE_COLOR, "didn't": HABIT_SKIPPED_COLOR},
            category_orders={"day": ["did it", "didn't"]},
            labels={"habit": "", "tasks": "tasks finished per day", "day": ""},
            custom_data=["days"], height=330,
        )
        fig.update_traces(hovertemplate="%{x}<br>%{y:.1f} tasks/day over %{customdata[0]} days<extra>%{fullData.name}</extra>")
        fig.update_layout(bargap=0.35, bargroupgap=0.08, legend=dict(orientation="h", y=1.12, x=0),
                          margin=dict(t=40))
        fig.update_yaxes(gridcolor="rgba(137,135,129,0.25)")
        st.plotly_chart(fig, width="stretch")

    st.caption(
        "This shows what happens *together*, not what *causes* what. A good night's sleep "
        "could make you both read and finish tasks. Today isn't counted because it isn't over. "
        "p = how often randomly shuffled days give a gap at least this big."
    )

# ---------------------------------------------------------------------------
# Mood & energy
# ---------------------------------------------------------------------------
st.subheader("Mood and energy")
MOOD_COLOR = "#4a3aa7"    # violet
ENERGY_COLOR = "#eda100"  # yellow
MIN_RATED_DAYS = 7

mood_log = db.read_table("mood_log")
rated, by_energy = analytics.mood_vs_tasks(daily, mood_log)

if len(rated) < MIN_RATED_DAYS:
    st.info(f"Rate your mood and energy on the Today page. This needs {MIN_RATED_DAYS}+ rated days "
            f"(you have {len(rated)}; today counts from tomorrow, once the day is over).")
else:
    r = analytics.habit_task_link(rated, analytics.HIGH_ENERGY)
    if r["enough"]:
        more_or_fewer = "more" if r["pct"] >= 0 else "fewer"
        sentence = (f"On high-energy days (4–5) you finished **{abs(r['pct']):.0f}% {more_or_fewer}** tasks "
                    f"({r['with_avg']:.1f} vs {r['without_avg']:.1f} per day; "
                    f"{r['n_with']} vs {r['n_without']} days).")
        if r["p_value"] < 0.05:
            st.write(f"{sentence} Unlikely to be chance (p = {r['p_value']:.2f}).")
        else:
            st.write(f"{sentence} Could easily be chance (p = {r['p_value']:.2f}): keep rating your days.")

    left, right = st.columns(2)
    # Left: mood and energy over time. Daily ratings jump around a lot, so we
    # plot a 7-day rolling average: each point = mean of that day and the 6
    # before it ("7D" = calendar days, so skipped days don't stretch the window).
    smooth = rated[["mood", "energy"]].rolling("7D", min_periods=3).mean().dropna()
    trend = smooth.reset_index(names="day").melt(
        id_vars="day", value_vars=["mood", "energy"], var_name="rating", value_name="score")
    fig = px.line(
        trend, x="day", y="score", color="rating",
        color_discrete_map={"mood": MOOD_COLOR, "energy": ENERGY_COLOR},
        labels={"day": "", "score": "", "rating": ""}, title="Mood and energy (7-day average)", height=300,
    )
    fig.update_traces(line_width=2,
                      hovertemplate="Week to %{x|%a %d %b}: %{y:.1f}<extra>%{fullData.name}</extra>")
    fig.update_yaxes(range=[0.5, 5.5], dtick=1, gridcolor="rgba(137,135,129,0.25)")
    fig.update_xaxes(showgrid=False, tickformat="%d %b")
    fig.update_layout(legend=dict(orientation="h", y=1.12, x=0), margin=dict(t=60, l=0, r=0))
    left.plotly_chart(fig, width="stretch")

    # Right: average tasks finished at each energy level.
    fig = px.bar(
        by_energy, x="energy", y="avg", color_discrete_sequence=[PLANNED_COLOR],
        labels={"energy": "energy that day", "avg": "tasks finished per day"},
        title="Tasks finished by energy level", height=300, custom_data=["days"],
    )
    fig.update_traces(hovertemplate="Energy %{x}: %{y:.1f} tasks/day over %{customdata[0]} days<extra></extra>")
    fig.update_xaxes(dtick=1)
    fig.update_yaxes(gridcolor="rgba(137,135,129,0.25)")
    fig.update_layout(margin=dict(t=60, l=0, r=0), bargap=0.35)
    right.plotly_chart(fig, width="stretch")
    st.caption("Only days you rated count: a skipped rating isn't a low one. "
               "As with habits, this shows what happens together, not what causes what.")

# ---------------------------------------------------------------------------
# When you finish tasks
# ---------------------------------------------------------------------------
st.subheader("When you get things done")
MIN_FOR_TIMES = 20  # below this, a weekday × hour grid is mostly empty squares
times = analytics.completion_times(tasks)

if times is None or times["total"] < MIN_FOR_TIMES:
    have = 0 if times is None else times["total"]
    st.info(f"Needs at least {MIN_FOR_TIMES} finished tasks (you have {have}).")
else:
    per_day = times["per_weekday"]
    start, share = times["best_window"]
    st.write(f"Your best day is **{per_day.idxmax()}** ({per_day.max():.1f} tasks on average); "
             f"the slowest is **{per_day.idxmin()}** ({per_day.min():.1f}).")
    st.write(f"**{share:.0%}** of your tasks get done between **{start}:00 and {start + 2}:00**.")

    grid = times["grid"]
    # Hover text for every square, same shape as the grid.
    hover = [[f"{day} {h}:00–{h + 1}:00: {grid.loc[day, h]} task(s)" for h in grid.columns]
             for day in grid.index]
    fig = go.Figure(go.Heatmap(
        z=grid.values, x=[f"{h}:00" for h in grid.columns], y=list(grid.index),
        customdata=hover, hovertemplate="%{customdata}<extra></extra>",
        # Grey for 0, then light -> dark blue: "nothing" never looks like "a little".
        colorscale=[[0, "#ecebe7"], [0.001, "#cde2fb"], [0.5, "#5598e7"], [1, "#104281"]],
        xgap=2, ygap=2, colorbar=dict(title="tasks", thickness=12),
    ))
    fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0),
                      yaxis=dict(autorange="reversed"))  # Monday on top
    st.plotly_chart(fig, width="stretch")
    st.caption("Times are when you clicked Done, not necessarily when you did the work. "
               "Best/slowest day = average per Monday, per Tuesday, … so a weekday that appears "
               "one extra time in your data isn't favoured.")

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
