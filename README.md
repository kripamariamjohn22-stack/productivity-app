# Personal Productivity App

A local-only Streamlit app for my tasks, habits, calendar and (later) college stuff and insights.
Only for me: no login, no deployment.

## Setup (once)

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
source venv/bin/activate
streamlit run app.py
```

Then open http://localhost:8501 in your browser.

## What each file does

| File | What it's for |
|------|---------------|
| `app.py` | Entry point. Creates the database, shows the home screen. |
| `pages/` | One file per page. Streamlit adds each one to the sidebar. |
| `pages/2_To-do.py` | To-do list: add, finish, drop, undo; postponement warnings. |
| `core/db.py` | All database code: creating tables and reading/writing data. |
| `core/gcal.py` | Google Calendar sync *(Step 4)* |
| `core/analytics.py` | Plan vs actual, streaks, insights *(Phase 4)* |
| `data/app.db` | The SQLite database. Created automatically. **Not in git.** |
| `credentials.json` / `token.json` | Google login files. **Never commit these.** |

## Progress

- [x] Phase 1 · Step 1 — skeleton + database
- [x] Phase 1 · Step 2 — to-do list
- [ ] Phase 1 · Step 3 — habit tracker
- [ ] Phase 1 · Step 4 — Google Calendar sync
- [ ] Phase 1 · Step 5 — Today page
