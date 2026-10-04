"""
Winter arc page: a month-long challenge with 9 daily goals, a score out of 9,
a streak of good days, this month's book and a log of new things learned.

Same pattern as the Habits page: every widget saves the whole day the moment
it changes (on_change), so there's no Save button to forget.
"""

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import analytics, db

db.init_db()

settings = db.get_winter_arc_settings()
start = date.fromisoformat(settings["arc_start"])
end = date.fromisoformat(settings["arc_end"])
daily_pages = int(settings["arc_daily_pages"])
total_pages = int(settings["arc_book_pages"])
today = date.today()

FLAWLESS_LABELS = {
    "skin": "Skincare + SPF", "hair": "Hair done", "face": "Face basics",
    "outfit": "Outfit planned", "shoes": "Clean shoes", "scent": "Scent",
}
CATEGORIES = ["", "Science", "Money", "History", "Random"]

st.title("❄️ Winter arc")
st.caption(f"{start:%d %b} to {end:%d %b}. 7 or more out of 9 counts as a good day.")

# ---------------------------------------------------------------------------
# Which day
# ---------------------------------------------------------------------------
# You can fill in a past day, but not the future. Before the arc starts,
# the picker sits on day 1 so you can see what's coming.
latest = min(max(today, start), end)
day = st.date_input("Logging for", value=latest, min_value=start, max_value=latest)
row = db.get_winter_arc_day(day)


def saved(field, default):
    """The stored value for this day, or `default` if nothing is stored yet."""
    if row is None or row[field] is None:
        return default
    return row[field]


def k(field):
    # The key includes the date, so switching days gives fresh widgets
    # instead of Streamlit remembering the previous day's values.
    return f"arc_{field}_{day}"


def save_day():
    """Runs when any widget changes: read every widget for this day, write one row."""
    s = st.session_state
    values = {f: s.get(k(f)) for f in db.WINTER_ARC_FIELDS}
    for f in ["skin", "hair", "face", "outfit", "shoes", "scent",
              "slept_on_time", "matiks", "career"]:
        values[f] = int(bool(values[f]))          # checkboxes -> 0/1
    values["water_glasses"] = values["water_glasses"] or 0
    for f in ["fact", "fact_source", "fact_category"]:
        values[f] = (values[f] or "").strip()
    db.save_winter_arc_day(day, values)


# ---------------------------------------------------------------------------
# Today's 9 goals
# ---------------------------------------------------------------------------
left, right = st.columns(2)

with left:
    st.subheader("Body")
    st.number_input("👟 Steps (goal 10,000)", min_value=0, step=500, value=saved("steps", None),
                    key=k("steps"), on_change=save_day, placeholder="Steps so far")
    st.checkbox("😴 Asleep by 11:30 (12 max)", value=bool(saved("slept_on_time", 0)),
                key=k("slept_on_time"), on_change=save_day)
    st.number_input("💧 Glasses of water (goal 10 = 2.5 L)", min_value=0, max_value=30, step=1,
                    value=int(saved("water_glasses", 0)), key=k("water_glasses"), on_change=save_day)
    st.number_input("📱 Phone screen time in hours (goal under 5)", min_value=0.0, max_value=24.0,
                    step=0.5, value=saved("screen_hours", None), key=k("screen_hours"),
                    on_change=save_day, placeholder="Check at night")

    st.subheader("✨ Looking flawless")
    cols = st.columns(2)
    for i, (field, label) in enumerate(FLAWLESS_LABELS.items()):
        cols[i % 2].checkbox(label, value=bool(saved(field, 0)), key=k(field), on_change=save_day)

with right:
    st.subheader("Brain")
    st.number_input(f"📖 Pages of {settings['arc_book_title']} (goal {daily_pages})", min_value=0,
                    step=1, value=saved("pages", None), key=k("pages"), on_change=save_day,
                    placeholder="Pages read today")
    st.checkbox("🧮 Matiks", value=bool(saved("matiks", 0)), key=k("matiks"), on_change=save_day)
    st.checkbox("💻 1 hour on career (30 min on exam days counts)", value=bool(saved("career", 0)),
                key=k("career"), on_change=save_day)
    st.text_input("💡 One new thing I learned", value=saved("fact", ""), key=k("fact"),
                  on_change=save_day)
    st.text_input("Source link (optional)", value=saved("fact_source", ""), key=k("fact_source"),
                  on_change=save_day)
    st.selectbox("Category", CATEGORIES, index=CATEGORIES.index(saved("fact_category", "") or ""),
                 format_func=lambda c: c or "Pick one", key=k("fact_category"), on_change=save_day)

# ---------------------------------------------------------------------------
# Score for the chosen day + streak
# ---------------------------------------------------------------------------
history = db.get_winter_arc_range(start, end)
scores = analytics.winter_arc_scores(history, daily_pages)
day_rows = history[history["date"] == day.isoformat()]

st.divider()
if day_rows.empty:
    checks, score = {}, 0
else:
    checks = analytics.winter_arc_checks(day_rows.iloc[0], daily_pages)
    score = sum(checks.values())

c1, c2, c3 = st.columns(3)
c1.metric("Score", f"{score}/9")
c2.metric("Good-day streak", analytics.winter_arc_streak(scores, start, today))
c3.metric("Good days so far", sum(1 for s in scores.values() if s >= analytics.GOOD_DAY))
if checks:
    missing = [name for name, done in checks.items() if not done]
    st.caption("Still open: " + ", ".join(missing) if missing else "All 9 done. Perfect day.")

# ---------------------------------------------------------------------------
# Book progress
# ---------------------------------------------------------------------------
st.subheader(f"📚 {settings['arc_book_title']} by {settings['arc_book_author']}")
pages_read = int(history["pages"].fillna(0).sum()) if not history.empty else 0
pages_left, pace = analytics.book_pace(pages_read, total_pages, max(today, start), end)
st.progress(min(pages_read / total_pages, 1.0), text=f"{pages_read} of {total_pages} pages")
if pages_left:
    st.write(f"{pace} pages a day to finish by {end:%d %b}.")
else:
    st.write("Finished. Set next month's book below.")

# ---------------------------------------------------------------------------
# Month grid: one square per day, darker = higher score
# ---------------------------------------------------------------------------
st.subheader("Month at a glance")
monday = analytics.week_start(start)
weeks = (end - monday).days // 7 + 1
z, text = [], []
for wd in range(7):
    z_row, t_row = [], []
    for w in range(weeks):
        d = monday + timedelta(days=w * 7 + wd)
        if d < start or d > end or d > today:
            z_row.append(None)                     # outside the arc or still to come
            t_row.append(f"{d:%a %d %b}")
        else:
            z_row.append(scores.get(d, 0))
            t_row.append(f"{d:%a %d %b}: {scores.get(d, 0)}/9")
    z.append(z_row)
    text.append(t_row)

fig = go.Figure(go.Heatmap(
    z=z, x=[f"Week {w + 1}" for w in range(weeks)], y=analytics.WEEKDAYS,
    customdata=text, hovertemplate="%{customdata}<extra></extra>",
    colorscale=[[0, "#dddcd8"], [0.44, "#86b6ef"], [0.78, "#256abf"], [1, "#163f73"]],
    zmin=0, zmax=9, xgap=3, ygap=3, showscale=False,
))
fig.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0), yaxis=dict(autorange="reversed"))
st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------------------
# Things I learned
# ---------------------------------------------------------------------------
st.subheader("💡 Things I learned")
facts = history[history["fact"].fillna("").str.strip() != ""] if not history.empty else history
if facts.empty:
    st.write("Your first fact shows up here once you log it.")
else:
    st.dataframe(
        facts[["date", "fact", "fact_category", "fact_source"]].iloc[::-1],
        column_config={
            "date": "Date", "fact": "What I learned", "fact_category": "Category",
            "fact_source": st.column_config.LinkColumn("Source"),
        },
        hide_index=True, width="stretch",
    )

# ---------------------------------------------------------------------------
# Settings: dates and book (change these for November)
# ---------------------------------------------------------------------------
with st.expander("Arc dates and book"):
    with st.form("arc_settings"):
        new_start = st.date_input("Start", value=start)
        new_end = st.date_input("End", value=end)
        title = st.text_input("Book", value=settings["arc_book_title"])
        author = st.text_input("Author", value=settings["arc_book_author"])
        book_pages = st.number_input("Total pages", min_value=1, value=total_pages)
        target = st.number_input("Daily page goal", min_value=1, value=daily_pages)
        if st.form_submit_button("Save settings"):
            if new_end < new_start:
                st.error("The end date has to be after the start date.")
            else:
                for key, value in {
                    "arc_start": new_start.isoformat(), "arc_end": new_end.isoformat(),
                    "arc_book_title": title.strip() or "My book",
                    "arc_book_author": author.strip(),
                    "arc_book_pages": str(book_pages), "arc_daily_pages": str(target),
                }.items():
                    db.set_setting(key, value)
                st.rerun()
