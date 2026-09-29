"""
analytics.py — turns raw rows into numbers: streaks, attendance maths, insights (Phase 4).

Nothing in here touches the database or Streamlit. Functions take plain Python
data in and give plain data back, which makes them easy to test on their own.
"""

from datetime import date, timedelta

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
