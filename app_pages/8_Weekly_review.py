"""
Weekly review page: an auto-generated summary of one week.
Done · Skipped · Time split · Top insight. Defaults to last week.
"""

from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from core import analytics, db

db.init_db()
st.title("Weekly review")

tasks = db.read_table("tasks")
habit_logs = db.read_table("habit_logs")
habits = db.read_table("habits")
habits = habits[habits["active"] == 1]

if tasks.empty and habit_logs.empty:
    st.info("Nothing to review yet. Finish some tasks or tick some habits first.")
    st.stop()

# ---------------------------------------------------------------------------
# Pick a week (Mondays from your first data until this week, newest first)
# ---------------------------------------------------------------------------
this_monday = analytics.week_start(date.today())
# Convert each column separately: tasks have "2026-09-29 14:05:00", habit logs
# "2026-09-29", and pandas won't parse two formats in one go.
first_dates = [pd.to_datetime(col).min().date()
               for col in (tasks["created_at"], habit_logs["date"]) if not col.empty]
first_day = min(first_dates)
mondays = []
monday = this_monday
while monday >= analytics.week_start(first_day):
    mondays.append(monday)
    monday -= timedelta(days=7)


def week_label(m):
    label = f"{m:%d %b} – {m + timedelta(days=6):%d %b}"
    if m == this_monday:
        return label + " (this week, in progress)"
    if m == this_monday - timedelta(days=7):
        return label + " (last week)"
    return label


# Default: last week, because the current week isn't finished yet.
default = 1 if len(mondays) > 1 else 0
monday = st.selectbox("Week", mondays, index=default, format_func=week_label)

review = analytics.weekly_review(tasks, habit_logs, habits, monday)
# Habit link uses data up to the end of THIS week, so old reviews don't change later.
daily = analytics.daily_table(tasks, habit_logs, habits, today=monday + timedelta(days=7))
insights = analytics.week_insights(review, daily)

# ---------------------------------------------------------------------------
# Headline numbers
# ---------------------------------------------------------------------------
done, dropped, left_open, habit_table = (review["done"], review["dropped"],
                                         review["left_open"], review["habits"])
kept = int(habit_table["kept"].sum()) if not habit_table.empty else 0

c1, c2, c3, c4 = st.columns(4)
# delta = change from the week before; Streamlit colours it green/red.
c1.metric("Tasks done", len(done), delta=len(done) - review["prev_done_count"])
c2.metric("Time logged", f"{review['minutes'] / 60:.1f} h")
c3.metric("Habits kept", f"{kept}/{len(habit_table)}")
c4.metric("Dropped", len(dropped))

# ---------------------------------------------------------------------------
# Top insight
# ---------------------------------------------------------------------------
st.subheader("Top insight")
if insights:
    st.info(insights[0])  # neutral blue: an insight can be good or bad news, green would say "good"
    if len(insights) > 1:
        st.markdown("**Also noticed**")
        for line in insights[1:]:
            st.markdown(f"- {line}")
else:
    st.write("Nothing stood out this week. Insights need a few tasks with planned and actual minutes.")

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
st.subheader("Done")
if done.empty:
    st.write("No tasks finished this week.")
else:
    if review["planned_total"]:
        diff = review["actual_total"] - review["planned_total"]
        st.write(f"Planned {review['planned_total']} min, took {review['actual_total']} min "
                 f"({'+' if diff >= 0 else ''}{diff} min) for tasks with both numbers.")
    with st.expander(f"All {len(done)} finished tasks"):
        st.dataframe(
            done[["title", "tag", "type", "planned_minutes", "actual_minutes", "completed_at"]]
            .sort_values("completed_at"),
            hide_index=True, width="stretch",
        )

# ---------------------------------------------------------------------------
# Skipped
# ---------------------------------------------------------------------------
st.subheader("Skipped")
missed = habit_table[~habit_table["kept"]] if not habit_table.empty else habit_table
if missed.empty and dropped.empty and left_open.empty:
    st.write("Nothing skipped. 🎉")
for row in missed.itertuples():
    st.write(f"🔥 **{row.habit}**: {row.days}/{row.target} days, missed the weekly target.")
if not dropped.empty:
    st.write(f"🗑️ Dropped: {', '.join(dropped['title'])}")
if not left_open.empty:
    st.write(f"⏭️ Still open at the end of the week: **{len(left_open)}** task(s)")
    st.dataframe(left_open[["title", "tag", "due_date", "times_postponed"]],
                 hide_index=True, width="stretch")
st.caption("The app counts how many times a task was postponed, not on which days, so "
           "“skipped” = dropped this week or still open when the week ended.")

# ---------------------------------------------------------------------------
# Time split
# ---------------------------------------------------------------------------
st.subheader("Time split")
split = review["time_split"]
if split.empty:
    st.write("No actual minutes logged this week.")
else:
    df = split.reset_index().rename(columns={"actual_minutes": "minutes"})
    df["share"] = df["minutes"] / df["minutes"].sum()
    fig = px.bar(
        df, x="minutes", y="tag", orientation="h",
        text=[f"{m:.0f} min · {s:.0%}" for m, s in zip(df["minutes"], df["share"])],
        color_discrete_sequence=["#2a78d6"], labels={"tag": "", "minutes": "minutes"},
        height=60 + 45 * len(df),
    )
    fig.update_traces(textposition="outside", cliponaxis=False,
                      hovertemplate="%{y}: %{x:.0f} min<extra></extra>")
    fig.update_yaxes(categoryorder="total ascending")
    fig.update_xaxes(gridcolor="rgba(137,135,129,0.25)")
    fig.update_layout(margin=dict(l=0, r=90, t=10, b=0), bargap=0.35)
    st.plotly_chart(fig, width="stretch")
