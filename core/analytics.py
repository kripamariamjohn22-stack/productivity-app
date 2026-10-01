"""
analytics.py — turns raw rows into numbers: streaks, attendance maths, insights (Phase 4).

Nothing in here touches the database or Streamlit. Functions take plain Python
data in and give plain data back, which makes them easy to test on their own.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def week_start(day):
    """The Monday of the week `day` falls in. weekday() is 0 for Monday."""
    return day - timedelta(days=day.weekday())


def count_in_week(logs, monday):
    """How many days in the week starting `monday` have a log.
    `logs` is {date: is_minimum}; minimum-version days count too — that's the point
    of a minimum version: a small win still keeps the chain going."""
    return sum(1 for i in range(7) if monday + timedelta(days=i) in logs)


def habit_summary(logs, target, today=None):
    """Everything the habit page shows in text: this week's progress and the streak.

    Flexible streak = number of weeks in a row where the target was met.
    The current week is still in progress, so it only adds to the streak once
    the target is hit — but NOT hitting it yet doesn't break the streak either.
    """
    today = today or date.today()
    this_monday = week_start(today)
    done_this_week = count_in_week(logs, this_monday)
    days_left = 7 - today.weekday()  # including today

    streak = 1 if done_this_week >= target else 0
    monday = this_monday - timedelta(days=7)
    earliest = min(logs) if logs else today  # stop looking before the first ever log
    while monday >= week_start(earliest) and count_in_week(logs, monday) >= target:
        streak += 1
        monday -= timedelta(days=7)

    return {
        "done_this_week": done_this_week,
        "needed": max(target - done_this_week, 0),
        "days_left": days_left,
        "streak_weeks": streak,
    }


def heatmap_grid(logs, today=None, weeks=26):
    """Build the GitHub-style grid: 7 rows (Mon..Sun) x `weeks` columns.

    Cell values: 0 = not done, 1 = minimum version, 2 = full habit,
    None = in the future (drawn as an empty gap).
    Returns two DataFrames with the same shape: the numbers, and hover text.
    """
    today = today or date.today()
    first_monday = week_start(today) - timedelta(weeks=weeks - 1)
    mondays = [first_monday + timedelta(weeks=w) for w in range(weeks)]

    values = pd.DataFrame(index=WEEKDAYS, columns=mondays, dtype="object")
    labels = pd.DataFrame(index=WEEKDAYS, columns=mondays, dtype="object")
    for monday in mondays:
        for i, weekday in enumerate(WEEKDAYS):
            day = monday + timedelta(days=i)
            if day > today:
                values.loc[weekday, monday] = None
                labels.loc[weekday, monday] = ""
            elif day not in logs:
                values.loc[weekday, monday] = 0
                labels.loc[weekday, monday] = f"{day:%a %d %b}: not done"
            elif logs[day]:
                values.loc[weekday, monday] = 1
                labels.loc[weekday, monday] = f"{day:%a %d %b}: minimum version"
            else:
                values.loc[weekday, monday] = 2
                labels.loc[weekday, monday] = f"{day:%a %d %b}: done"
    return values, labels


def attendance_status(attended, missed, target=75):
    """Current % and how much slack you have, for one subject.

    All maths is done with whole numbers (no floats), so there are no
    rounding surprises like 74.99999% counting as below 75.

    can_miss:    most classes you can skip in a row and still be >= target.
      We need   100 * attended >= target * (attended + missed + x)
      so        x <= (100*attended - target*(attended+missed)) / target
    must_attend: fewest classes you must attend in a row to get back to target.
      We need   100 * (attended + y) >= target * (attended + missed + y)
      so        y >= (target*(attended+missed) - 100*attended) / (100 - target)
    """
    total = attended + missed
    if total == 0:
        return {"percent": None, "can_miss": 0, "must_attend": 0}

    percent = 100 * attended / total  # float is fine here: it's only for display
    slack = 100 * attended - target * total
    if slack >= 0:
        # // rounds down, which is what we want: you can't skip half a class.
        return {"percent": percent, "can_miss": slack // target, "must_attend": 0}
    if target >= 100:
        # Already missed one with a 100% target: no amount of attending fixes it.
        return {"percent": percent, "can_miss": 0, "must_attend": None}
    # -(-a // b) is a whole-number way to round UP (ceil) a / b.
    return {"percent": percent, "can_miss": 0, "must_attend": -(-(-slack) // (100 - target))}


def countdown(due_date, today=None):
    """How far away a deadline is, as (days_left, text).
    days_left is negative when overdue. due_date is 'YYYY-MM-DD' text or None."""
    if not due_date:
        return None, "no date"
    today = today or date.today()
    days = (date.fromisoformat(due_date) - today).days
    if days < 0:
        return days, f"overdue by {-days} day(s)"
    if days == 0:
        return days, "today"
    if days == 1:
        return days, "tomorrow"
    return days, f"in {days} days"


# ---------------------------------------------------------------------------
# Phase 4: plan vs actual
# ---------------------------------------------------------------------------

def plan_vs_actual(tasks):
    """Planned vs actual minutes per tag per week, from the tasks table.

    Only finished tasks that have BOTH numbers count: comparing a task's plan
    with "unknown" would make you look faster than you are.
    Returns (weekly, by_tag):
      weekly: one row per (week, tag) with planned and actual minute totals
      by_tag: one row per tag with totals, task count and ratio = actual / planned
    """
    done = tasks[
        (tasks["status"] == "done")
        & tasks["planned_minutes"].notna()
        & tasks["actual_minutes"].notna()
    ].copy()  # .copy() so adding a column below doesn't warn about changing `tasks`

    # Week = the Monday the task was finished in. to_period("W-SUN") means
    # "weeks ending on Sunday"; .start_time gives that week's Monday.
    done["week"] = pd.to_datetime(done["completed_at"]).dt.to_period("W-SUN").dt.start_time

    weekly = (
        done.groupby(["week", "tag"], as_index=False)[["planned_minutes", "actual_minutes"]].sum()
    )
    by_tag = done.groupby("tag").agg(
        planned=("planned_minutes", "sum"),
        actual=("actual_minutes", "sum"),
        tasks=("id", "count"),
    )
    by_tag["ratio"] = by_tag["actual"] / by_tag["planned"]
    return weekly, by_tag.sort_values("ratio", ascending=False)


# ---------------------------------------------------------------------------
# Phase 4: postponements
# ---------------------------------------------------------------------------

def postponement_stats(tasks):
    """What gets pushed to tomorrow, and what happens to it afterwards.

    Only plain tasks count: assignments and exams never roll over, so they'd
    make every tag look better than it is.
    Returns a dict with:
      share_postponed: fraction of tasks postponed at least once (0.0–1.0)
      by_tag:  per tag -> tasks, average postponements, share postponed
      by_title: per task title -> how often it appeared, total postponements,
                how many are still open (titles you reuse, like "Gym", add up),
                and open_postponed: postponements of the task that's open now
      fate:    for tasks postponed 3+ times -> share done / dropped / still open
    """
    t = tasks[tasks["type"] == "task"].copy()
    if t.empty:
        return None
    t["postponed"] = t["times_postponed"] > 0  # True/False column; .mean() of it = share

    by_tag = t.groupby("tag").agg(
        tasks=("id", "count"),
        avg_postponed=("times_postponed", "mean"),
        share_postponed=("postponed", "mean"),
    ).sort_values("avg_postponed", ascending=False)

    by_title = t.groupby("title").agg(
        tag=("tag", "first"),
        times=("id", "count"),
        total_postponed=("times_postponed", "sum"),
        still_open=("status", lambda s: (s == "todo").sum()),
    )
    # For the "break it down or drop it?" hint we need the CURRENT open task's
    # count, not the title's lifetime total (13 old "Gym" tasks don't make
    # today's one stuck). reindex lines it up with by_title; titles with no
    # open task get NaN, which fillna turns into 0.
    open_postponed = t[t["status"] == "todo"].groupby("title")["times_postponed"].max()
    by_title["open_postponed"] = open_postponed.reindex(by_title.index).fillna(0).astype(int)
    by_title = by_title[by_title["total_postponed"] > 0].sort_values(
        ["total_postponed", "still_open"], ascending=False
    )

    stuck = t[t["times_postponed"] >= 3]
    # value_counts(normalize=True) gives shares instead of counts, e.g. done: 0.7
    fate = stuck["status"].value_counts(normalize=True).to_dict() if len(stuck) else {}

    return {
        "share_postponed": t["postponed"].mean(),
        "by_tag": by_tag,
        "by_title": by_title,
        "fate": fate,
        "stuck_count": len(stuck),
    }


# ---------------------------------------------------------------------------
# Phase 4: habits vs tasks
# ---------------------------------------------------------------------------

def daily_table(tasks, habit_logs, habits, today=None):
    """One row per day: how many tasks you finished, and True/False per habit.

    Starts at the first day with any data and stops YESTERDAY: today isn't
    over, so counting it would make today look like a bad day.
    """
    today = today or date.today()
    done_days = pd.to_datetime(tasks.loc[tasks["status"] == "done", "completed_at"]).dt.normalize()
    log_days = pd.to_datetime(habit_logs["date"])
    if done_days.empty and log_days.empty:
        return pd.DataFrame()

    first = min(d.min() for d in (done_days, log_days) if not d.empty)
    days = pd.date_range(first, pd.Timestamp(today) - pd.Timedelta(days=1), freq="D")
    daily = pd.DataFrame(index=days)
    # value_counts counts tasks per day; reindex fills days with none as 0.
    daily["tasks_done"] = done_days.value_counts().reindex(days, fill_value=0)

    for _, habit in habits.iterrows():
        habit_days = set(log_days[habit_logs["habit_id"] == habit["id"]])
        daily[habit["name"]] = daily.index.isin(habit_days)
    return daily


def habit_task_link(daily, habit, shuffles=2000, seed=0):
    """Compare tasks finished on days you did `habit` vs days you didn't.

    p_value: the share of random shuffles that give a gap at least this big.
    Idea: if the habit had nothing to do with it, then which days are
    "habit days" is just a label, and shuffling the labels should often
    produce gaps as big as the real one. Small p_value (< 0.05) = the real
    gap is rare by chance. It still doesn't prove the habit CAUSES it.
    """
    did = daily[habit].to_numpy()
    tasks_done = daily["tasks_done"].to_numpy()
    n_with, n_without = int(did.sum()), int((~did).sum())
    if n_with < 5 or n_without < 5:
        return {"enough": False, "n_with": n_with, "n_without": n_without}

    with_avg = tasks_done[did].mean()
    without_avg = tasks_done[~did].mean()
    real_gap = abs(with_avg - without_avg)

    rng = np.random.default_rng(seed)  # fixed seed = same answer every time you reload
    bigger = 0
    for _ in range(shuffles):
        fake = rng.permutation(did)  # same number of habit days, randomly placed
        if abs(tasks_done[fake].mean() - tasks_done[~fake].mean()) >= real_gap:
            bigger += 1

    return {
        "enough": True,
        "n_with": n_with, "n_without": n_without,
        "with_avg": with_avg, "without_avg": without_avg,
        "pct": (with_avg / without_avg - 1) * 100 if without_avg else None,
        "p_value": bigger / shuffles,
    }


# ---------------------------------------------------------------------------
# Phase 4: when you finish tasks
# ---------------------------------------------------------------------------

def completion_times(tasks):
    """When tasks get marked done: weekday × hour counts and a few summaries.

    Note: completed_at is when you clicked Done, not when you did the work.
    Returns None if there are no finished tasks, else a dict with:
      grid:        DataFrame, rows Mon..Sun, columns = hours, values = task counts
      per_weekday: average tasks finished per Monday, per Tuesday, ...
                   (count ÷ how many Mondays the data covers, so a weekday
                   that happens to appear one extra time isn't favoured)
      best_window: (start_hour, share) for the busiest 2-hour window
      total:       number of finished tasks
    """
    times = pd.to_datetime(tasks.loc[tasks["status"] == "done", "completed_at"]).dropna()
    if times.empty:
        return None

    # crosstab counts every (weekday, hour) pair: a ready-made 2D table.
    grid = pd.crosstab(times.dt.dayofweek, times.dt.hour)
    hours = range(times.dt.hour.min(), times.dt.hour.max() + 1)  # only the hours you're active
    grid = grid.reindex(index=range(7), columns=hours, fill_value=0)
    grid.index = WEEKDAYS

    all_days = pd.date_range(times.min().normalize(), times.max().normalize(), freq="D")
    weekdays_seen = pd.Series(all_days.dayofweek).value_counts().reindex(range(7), fill_value=0)
    per_weekday = pd.Series(grid.sum(axis=1).to_numpy() / weekdays_seen.clip(lower=1).to_numpy(),
                            index=WEEKDAYS)

    # Busiest 2-hour window: add up each hour with the next one, pick the max.
    per_hour = grid.sum(axis=0)
    two_hour = per_hour + per_hour.shift(-1, fill_value=0)
    start = int(two_hour.idxmax())
    return {
        "grid": grid,
        "per_weekday": per_weekday,
        "best_window": (start, two_hour.max() / len(times)),
        "total": len(times),
    }


# ---------------------------------------------------------------------------
# Phase 4: weekly review
# ---------------------------------------------------------------------------

def weekly_review(tasks, habit_logs, habits, monday):
    """Everything the Weekly review page shows for the week starting `monday`.

    Note: the app stores HOW MANY times a task was postponed, not on which
    days, so "skipped" here means dropped that week or still open at its end.
    """
    start = pd.Timestamp(monday)
    end = start + pd.Timedelta(days=7)  # next Monday 00:00 (not included)
    completed = pd.to_datetime(tasks["completed_at"])
    created = pd.to_datetime(tasks["created_at"])

    def finished_between(a, b, status):
        return tasks[(tasks["status"] == status) & (completed >= a) & (completed < b)]

    done = finished_between(start, end, "done")
    dropped = finished_between(start, end, "dropped")
    prev_done = finished_between(start - pd.Timedelta(days=7), start, "done")
    # Open at the end of the week = existed by then, and not done/dropped by then.
    closed_by_end = tasks["status"].isin(["done", "dropped"]) & (completed < end)
    left_open = tasks[(created < end) & ~closed_by_end]

    logs = habit_logs[(pd.to_datetime(habit_logs["date"]) >= start) & (pd.to_datetime(habit_logs["date"]) < end)]
    habit_rows = []
    for _, h in habits.iterrows():
        days = int((logs["habit_id"] == h["id"]).sum())
        habit_rows.append({"habit": h["name"], "days": days, "target": int(h["target_per_week"]),
                           "kept": days >= h["target_per_week"]})

    timed = done[done["actual_minutes"].notna()]
    time_split = timed.groupby("tag")["actual_minutes"].sum().sort_values(ascending=False)
    planned = timed[timed["planned_minutes"].notna()]

    return {
        "done": done, "dropped": dropped, "left_open": left_open,
        "prev_done_count": len(prev_done),
        "habits": pd.DataFrame(habit_rows),
        "time_split": time_split,
        "minutes": int(time_split.sum()),
        # plan vs actual for tasks that have both numbers
        "planned_total": int(planned["planned_minutes"].sum()),
        "actual_total": int(planned["actual_minutes"].sum()),
        "by_tag_ratio": planned.groupby("tag").agg(
            planned=("planned_minutes", "sum"), actual=("actual_minutes", "sum"), n=("id", "count")),
    }


def week_insights(review, daily):
    """Candidate insights for the week, most important first (a fixed order,
    so it's always clear why one was picked). `daily` = daily_table() up to
    the end of the week, for the habit link."""
    found = []

    # 1. This week's biggest plan overrun (3+ tasks, 20%+ over).
    ratios = review["by_tag_ratio"]
    ratios = ratios[ratios["n"] >= 3]
    if not ratios.empty:
        over = (ratios["actual"] / ratios["planned"] - 1) * 100
        tag = over.idxmax()
        if over[tag] >= 20:
            found.append(f"**{tag}** took **{over[tag]:.0f}% longer** than planned this week "
                         f"({int(ratios.loc[tag, 'actual'])} min vs {int(ratios.loc[tag, 'planned'])} planned).")

    # 2. Big change from the week before (30%+, and at least 5 tasks to compare).
    now, before = len(review["done"]), review["prev_done_count"]
    if before >= 5 and abs(now - before) / before >= 0.3:
        word = "more" if now > before else "fewer"
        found.append(f"You finished **{abs(now - before)} {word}** tasks than the week before ({now} vs {before}).")

    # 3. A task that's stuck: still open at the week's end after 3+ postponements.
    stuck = review["left_open"][review["left_open"]["times_postponed"] >= 3]
    if not stuck.empty:
        worst = stuck.sort_values("times_postponed", ascending=False).iloc[0]
        found.append(f"**{worst['title']}** has been postponed **{worst['times_postponed']}x**. "
                     "Break it down or drop it?")

    # 4. The strongest habit link that passes the chance check.
    best = None
    for habit in [c for c in daily.columns if c != "tasks_done"]:
        r = habit_task_link(daily, habit)
        if r["enough"] and r["p_value"] < 0.05 and r["pct"] and r["pct"] > 0:
            if best is None or r["pct"] > best[1]["pct"]:
                best = (habit, r)
    if best:
        habit, r = best
        found.append(f"On days you did **{habit}**, you finished **{r['pct']:.0f}% more** tasks "
                     f"(so far, unlikely to be chance).")
    return found


# ---------------------------------------------------------------------------
# Phase 5: mood & energy
# ---------------------------------------------------------------------------

HIGH_ENERGY = "energy 4–5"


def mood_vs_tasks(daily, mood_log):
    """Join each day's mood/energy rating onto the daily table.

    Only days you actually rated are kept: a missing rating isn't a "low"
    rating, so guessing one would bias the result.
    Returns (rated, by_energy):
      rated:     daily rows that have a rating, plus mood, energy and a
                 True/False HIGH_ENERGY column (ready for habit_task_link)
      by_energy: per energy level 1–5 -> average tasks finished, number of days
    """
    if daily.empty or mood_log.empty:
        return pd.DataFrame(), pd.DataFrame()
    ratings = mood_log.assign(date=pd.to_datetime(mood_log["date"])).set_index("date")[["mood", "energy"]]
    # join() matches rows by index (the date); how="inner" keeps only dates in both.
    rated = daily[["tasks_done"]].join(ratings, how="inner")
    rated[HIGH_ENERGY] = rated["energy"] >= 4
    by_energy = rated.groupby("energy")["tasks_done"].agg(avg="mean", days="count").reset_index()
    return rated, by_energy
