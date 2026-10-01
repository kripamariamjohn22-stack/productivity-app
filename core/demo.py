"""
demo.py — fills data/demo.db with ~8 weeks of made-up but realistic data,
so the Insights charts have something to show before you have real history.

    python -m core.demo                                  # (re)build data/demo.db
    PRODUCTIVITY_DB=data/demo.db streamlit run app.py    # look at it

Your real data/app.db is never touched.

The fake data has patterns baked in on purpose, so each insight has
something to find (and you can check the charts find the RIGHT thing):
  - research tasks take ~1.5x the planned time; personal ones a bit less
  - research tasks get postponed the most
  - on "good days" you do more habits AND finish more tasks
  - most tasks get finished late morning or late evening; Sundays are slow
  - mood and energy are higher on good days (so they track tasks too)
"""

import random
from datetime import date, datetime, timedelta

from core import db

DEMO_DB = db.ROOT / "data" / "demo.db"
WEEKS = 8

TITLES = {
    "college": ["Stats problem set", "Read DBMS chapter", "Revise linear algebra", "Lab record",
                "Python assignment", "Prepare seminar slides"],
    "internship": ["Clean survey data", "Write weekly update", "Fix dashboard bug", "Code review",
                   "Standup notes"],
    "research": ["Literature review", "Run baseline model", "Write methods section",
                 "Read 2 papers", "Plot results"],
    "personal": ["Laundry", "Call home", "Plan the week", "Gym", "Pay phone bill"],
}
# Tags aren't equally common: college work dominates.
TAG_WEIGHTS = {"college": 0.4, "internship": 0.25, "research": 0.2, "personal": 0.15}
# actual time ≈ planned × this (with noise).
TIME_FACTOR = {"college": 1.15, "internship": 1.0, "research": 1.5, "personal": 0.9}
# Chance an unfinished task gets pushed again each day (research is the worst).
POSTPONE_CHANCE = {"college": 0.3, "internship": 0.2, "research": 0.55, "personal": 0.35}


def finish_time(day):
    """A random completion time: busiest at 10–12 and 20–23."""
    hour = random.choice([9, 10, 10, 11, 11, 12, 14, 15, 16, 17, 20, 20, 21, 21, 22, 22, 23])
    return datetime.combine(day, datetime.min.time()) + timedelta(hours=hour, minutes=random.randint(0, 59))


def build():
    random.seed(42)  # same "random" data every time, so results are reproducible
    if DEMO_DB.exists():
        DEMO_DB.unlink()  # start from scratch
    db.DB_PATH = DEMO_DB  # point every db function at the demo file
    db.init_db()

    today = date.today()
    start = today - timedelta(weeks=WEEKS)
    habits = db.get_habits()
    conn = db.get_connection()

    day = start
    while day < today:
        # A hidden "good day" coin flip drives both habits and tasks.
        # That shared cause is exactly what the correlation insight should spot.
        good_day = random.random() < 0.6
        slow_sunday = day.weekday() == 6

        # Mood/energy: skipped on ~15% of days (real people forget too).
        if random.random() < 0.85:
            energy = random.choice([3, 4, 4, 5, 5]) if good_day else random.choice([1, 2, 2, 3, 3])
            mood = max(1, min(5, energy + random.choice([-1, 0, 0, 1])))
            conn.execute(
                "INSERT INTO mood_log (date, mood, energy, logged_at) VALUES (?, ?, ?, ?)",
                (day.isoformat(), mood, energy, f"{day} 21:00:00"),
            )

        for habit in habits:
            if random.random() < (0.8 if good_day else 0.35):
                conn.execute(
                    "INSERT INTO habit_logs (habit_id, date, is_minimum) VALUES (?, ?, ?)",
                    (habit["id"], day.isoformat(), int(random.random() < 0.2)),
                )

        for _ in range(random.randint(1, 3) if slow_sunday else random.randint(3, 5)):
            tag = random.choices(list(TAG_WEIGHTS), weights=TAG_WEIGHTS.values())[0]
            title = random.choice(TITLES[tag])
            planned = random.choice([15, 30, 30, 45, 60, 90])
            created = datetime.combine(day, datetime.min.time()) + timedelta(hours=8)

            # Each day, maybe push the task to tomorrow. Less likely on good days.
            push_chance = POSTPONE_CHANCE[tag] * (0.6 if good_day else 1.4)
            postponed, finish_day = 0, day
            while random.random() < push_chance and postponed < 10:
                postponed += 1
                finish_day += timedelta(days=1)

            if finish_day >= today:
                status, completed_at, actual = "todo", None, None  # still open
                finish_day = today
            elif postponed >= 4 and random.random() < 0.5:
                status, completed_at, actual = "dropped", finish_time(finish_day), None
            else:
                status = "done"
                completed_at = finish_time(finish_day)
                # lognormvariate(0, 0.25) is noise around 1.0: usually 0.8–1.25
                actual = round(planned * TIME_FACTOR[tag] * random.lognormvariate(0, 0.25) / 5) * 5

            conn.execute(
                """INSERT INTO tasks (title, priority, due_date, tag, status, created_at,
                                      completed_at, times_postponed, planned_minutes, actual_minutes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (title, random.choice(db.PRIORITIES), finish_day.isoformat(), tag, status,
                 created.strftime("%Y-%m-%d %H:%M:%S"),
                 completed_at.strftime("%Y-%m-%d %H:%M:%S") if completed_at else None,
                 postponed, planned, actual),
            )
        day += timedelta(days=1)

    conn.commit()
    counts = {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
              for t in ("tasks", "habit_logs")}
    conn.close()
    return counts


if __name__ == "__main__":
    counts = build()
    print(f"Built {DEMO_DB} with {counts['tasks']} tasks and {counts['habit_logs']} habit logs.")
    print("Open it with:  PRODUCTIVITY_DB=data/demo.db streamlit run app.py")
