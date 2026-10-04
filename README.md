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

## Google Calendar setup (once, ~10 minutes)

This creates `credentials.json`, the file that tells Google "this is my app".
Menu names in Google Cloud change now and then; if something is named slightly
differently, look for the closest match.

1. Go to <https://console.cloud.google.com/> and sign in with the Google account whose calendar you want.
2. **Create a project:** project picker at the top → **New project** → name it `productivity-app` → Create. Make sure it's selected.
3. **Turn on the Calendar API:** search bar → "Google Calendar API" → **Enable**.
4. **Set up the login screen:** menu → **APIs & Services → OAuth consent screen** (may be called **Google Auth Platform**) → **Get started**.
   - App name: `productivity-app`, support email: your email.
   - Audience: **External**.
   - Contact email: your email → agree → **Create**.
5. **Allow yourself to log in:** **Audience** → **Test users** → **Add users** → your Gmail address → Save.
6. **Create the credentials file:** **Clients** (or **Credentials → Create credentials → OAuth client ID**)
   - Application type: **Desktop app**, name: anything → **Create**.
   - **Download JSON**, rename it to exactly `credentials.json`, and put it in the project folder (next to `app.py`).
7. **Log in once from the terminal:**
   ```bash
   python -m core.gcal
   ```
   A browser tab opens. Google will warn **"Google hasn't verified this app"**. That's expected: it's your own app.
   Click **Continue**, tick the calendar permission, **Continue**. The terminal then lists today's events.
   A `token.json` file appears; that's your saved login.

**Check it's safe:** run `git status`. Neither `credentials.json` nor `token.json` should appear.

**If you get logged out every week:** while the app is in "Testing" mode, Google expires the login after 7 days.
The app notices and simply opens the browser login again. To stop this, go to **Audience → Publish app**
(it stays private: only accounts that log in can use it, and you'll still see the "unverified" warning).

### Time blocks (Phase 5): what the app may change

The app asks Google for two permissions:

| Permission | What it allows |
|---|---|
| `calendar.readonly` | **Read** your calendars (Today page, meeting notes). Never changes them. |
| `calendar.app.created` | Create **its own** calendar, "Productivity blocks", and add/remove events **only in calendars it created**. It cannot touch your main calendar. |

- **First time after updating:** the app sees your old read-only login is missing the new permission
  and opens the browser login once more. Google lists both permissions; click **Continue**.
- **If Google says the request is denied:** in Google Cloud go to **Google Auth Platform → Data Access →
  Add or remove scopes**, tick `.../auth/calendar.app.created`, save, and run the app again.
- **To remove everything the app wrote:** in Google Calendar, Settings → "Productivity blocks" →
  **Remove calendar → Delete**. (Removing single blocks: the 🗓️ button on the To-do page.)
- **To take the permission back completely:** <https://myaccount.google.com/permissions> → your app → **Remove access**,
  then delete `token.json`.

## Trying the app with demo data

Your real data lives in `data/app.db`. To look around with ~8 weeks of fake data instead:

```bash
python -m core.demo                                  # build data/demo.db (re-run any time to reset it)
PRODUCTIVITY_DB=data/demo.db streamlit run app.py    # Mac / Linux
```

On Windows (PowerShell): `$env:PRODUCTIVITY_DB="data/demo.db"; streamlit run app.py`
(then close that terminal, or run `Remove-Item Env:PRODUCTIVITY_DB`, to go back to your real data).

A yellow note in the sidebar reminds you when you're not on your real data.
A normal `streamlit run app.py` always uses `data/app.db`.

## Exploring your data in a notebook

Download the zip from **📊 Insights → Export**, unzip it, then:

```python
import pandas as pd
tasks = pd.read_csv("tasks.csv", parse_dates=["created_at", "completed_at"])
tasks.groupby("tag")["actual_minutes"].sum()
```

## What each file does

| File | What it's for |
|------|---------------|
| `app.py` | Entry point. Creates the database and lists the pages (Today opens first). |
| `app_pages/` | One file per page, listed in `app.py`. (Not called `pages/` on purpose: Streamlit treats a folder with that exact name specially and would skip `app.py`.) |
| `app_pages/1_Today.py` | Today: sync, timeline of events + classes, deadlines for the next 7 days, today's tasks and habits, mood/energy rating. |
| `app_pages/2_To-do.py` | To-do list (tasks, assignments, exams): add, finish, drop, undo; postponement warnings, countdowns, 🍅 timer, 🗓️ time blocks. |
| `app_pages/3_Habits.py` | Habit check-in (full or minimum), weekly progress, streak, heatmap. |
| `app_pages/4_Attendance.py` | Attendance per subject: log attended/missed, % and "can miss X / must attend Y". |
| `app_pages/5_Timetable.py` | Weekly class schedule. Today's classes appear on the Today page with ✅/❌ buttons. |
| `app_pages/6_Notes.py` | Meeting notes per calendar event: Agenda / Notes / Decisions / Action items (each action item becomes a task). |
| `app_pages/7_Insights.py` | Insights: plan vs actual, what gets postponed, habits vs tasks, mood/energy, best hours/days + CSV export of every table. |
| `app_pages/8_Weekly_review.py` | Weekly review: done, skipped, time split and a top insight for any week. |
| `app_pages/9_Winter_arc.py` | Winter arc challenge: 9 daily goals with a score out of 9, good-day streak, month grid, book progress and a log of things learned. Dates and book are set on the page. |
| `core/pomodoro.py` | The 🍅 focus timer: start buttons on task rows, countdown in the sidebar on every page. |
| `core/october_plan.py` | Loads the Winter Arc October plan once: finish-line tasks with due dates + weekly habits. Run `python -m core.october_plan`; running it again adds nothing twice. |
| `core/demo.py` | Builds `data/demo.db` with ~8 weeks of fake data so the charts have something to show. |
| `core/db.py` | All database code: creating tables, migrations (changes to existing tables), reading/writing data. |
| `core/gcal.py` | Google login, reading a day's events (with attendees), and writing time blocks to the app's own "Productivity blocks" calendar. Test with `python -m core.gcal`. |
| `core/analytics.py` | Number crunching: habit streaks, heatmap grid, attendance maths; insights in Phase 4. |
| `data/app.db` | The SQLite database. Created automatically. **Not in git.** |
| `credentials.json` / `token.json` | Google login files. **Never commit these.** |

## Progress

- [x] Phase 1 · Step 1 — skeleton + database
- [x] Phase 1 · Step 2 — to-do list
- [x] Phase 1 · Step 3 — habit tracker
- [x] Phase 1 · Step 4 — Google Calendar sync
- [x] Phase 1 · Step 5 — Today page
- [x] Phase 2 · Step 1 — attendance tracker
- [x] Phase 2 · Step 2 — timetable (on Today page)
- [x] Phase 2 · Step 3 — assignments & exams with countdowns
- [x] Phase 3 · Step 1 — meeting notes page
- [x] Phase 3 · Step 2 — action items become tasks
- [x] Phase 4 · Step 1 — CSV export
- [x] Phase 4 · Step 2 — plan vs actual (+ demo data)
- [x] Phase 4 · Step 3 — most-postponed tasks and tags
- [x] Phase 4 · Step 4 — habit vs task correlation
- [x] Phase 4 · Step 5 — best hours/days
- [x] Phase 4 · Step 6 — weekly review
- [x] Phase 5 · Step 1 — daily mood/energy log
- [x] Phase 5 · Step 2 — Pomodoro timer
- [x] Phase 5 · Step 3 — write time-blocked tasks to Google Calendar
- [x] Winter arc — October challenge page (9 daily goals, streak, book, facts log)
