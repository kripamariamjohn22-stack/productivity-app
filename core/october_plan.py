"""
october_plan.py — loads the Winter Arc October plan into the app, once.

    python -m core.october_plan

What it adds:
  - TASKS: October's finish lines (research, project, career, book) as to-do
    tasks with due dates, so they show up on the Today page on the right day.
  - HABITS: the weekly rhythm (revise classes, focus block, knowledge notes,
    Sunday scorecard) with a "minimum version" for bad days.
The daily goals (steps, sleep, water...) already live on the Winter arc page.

Safe to run twice: anything that already exists (same title / same habit
name) is skipped, so you never get duplicates.
"""

from datetime import date

from core import db

# (title, due date, tag, priority, planned minutes)
# Tags must be one of db.TAGS: college, internship, personal, research.
# Career work uses "internship" so it's easy to filter.
TASKS = [
    # Week 1: set-up
    ("Answer the 4 Winter Arc audit questions", "2026-10-06", "personal", "High", 20),
    ("Send flagship project examples to Claude", "2026-10-08", "personal", "High", 20),
    ("Set up Zotero + literature matrix sheet", "2026-10-07", "research", "Med", 60),
    ("Write 1-page research scope (question + criteria)", "2026-10-10", "research", "High", 120),
    ("Write search strings for each database", "2026-10-11", "research", "High", 60),
    # Week 2
    ("Get research scope approved by supervisor", "2026-10-14", "research", "High", 30),
    ("Lock the flagship project", "2026-10-15", "personal", "High", 60),
    ("Search log + screen 30-40 abstracts", "2026-10-18", "research", "High", 240),
    ("Write 1-page project brief (user, decision, metric)", "2026-10-18", "personal", "Med", 60),
    # Week 3
    ("Choose dataset + write data card", "2026-10-22", "personal", "High", 120),
    ("Deep-read 6 papers into the matrix", "2026-10-25", "research", "High", 360),
    ("GitHub cleanup: profile README + 4 pinned repos", "2026-10-26", "internship", "Med", 120),
    # Week 4: October finish lines
    ("Deep-read 6 more papers into the matrix", "2026-10-31", "research", "High", 360),
    ("Theme map v1 for the review", "2026-10-31", "research", "Med", 90),
    ("Draft intro + methods (~1,000 words)", "2026-10-31", "research", "High", 180),
    ("EDA notebook with 5-8 findings", "2026-10-31", "personal", "High", 300),
    ("Honest CV v2", "2026-10-31", "internship", "Med", 90),
    ("Finish The Body + one-page notes", "2026-10-31", "personal", "Med", 45),
]

# (name, minimum version, target days per week) — same shape as db.SEED_HABITS
HABITS = [
    ("Revise today's classes", "Revise 1 topic for 10 minutes", 5),
    ("90-min focus block after college", "30-min focus block", 5),
    ("Knowledge note from a new field", "Read 1 article, write 1 idea", 2),
    ("Sunday scorecard + plan next week", "Score the week only", 1),
]


def load():
    db.init_db()
    conn = db.get_connection()
    existing_tasks = {r["title"] for r in conn.execute("SELECT title FROM tasks")}
    existing_habits = {r["name"] for r in conn.execute("SELECT name FROM habits")}
    conn.close()

    added_tasks = 0
    for title, due, tag, priority, minutes in TASKS:
        if title in existing_tasks:
            continue
        db.add_task(title, priority=priority, due_date=date.fromisoformat(due),
                    tag=tag, planned_minutes=minutes)
        added_tasks += 1

    added_habits = 0
    for name, minimum, target in HABITS:
        if name in existing_habits:  # includes archived ones: names are UNIQUE
            continue
        db.add_habit(name, minimum, target)
        added_habits += 1

    return added_tasks, added_habits


if __name__ == "__main__":
    tasks, habits = load()
    print(f"Database: {db.DB_PATH}")
    print(f"Added {tasks} task(s) and {habits} habit(s). Already-present items were skipped.")
