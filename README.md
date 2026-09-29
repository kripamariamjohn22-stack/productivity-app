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

## What each file does

| File | What it's for |
|------|---------------|
| `app.py` | Entry point. Creates the database and lists the pages (Today opens first). |
| `pages/` | One file per page. A new page must also be added to the list in `app.py`. |
| `pages/1_Today.py` | Today: sync, timeline of events + classes, deadlines for the next 7 days, today's tasks and habits. |
| `pages/2_To-do.py` | To-do list (tasks, assignments, exams): add, finish, drop, undo; postponement warnings and countdowns. |
| `pages/3_Habits.py` | Habit check-in (full or minimum), weekly progress, streak, heatmap. |
| `pages/4_Attendance.py` | Attendance per subject: log attended/missed, % and "can miss X / must attend Y". |
| `pages/5_Timetable.py` | Weekly class schedule. Today's classes appear on the Today page with ✅/❌ buttons. |
| `core/db.py` | All database code: creating tables, migrations (changes to existing tables), reading/writing data. |
| `core/gcal.py` | Google login + reading today's events into the database. Test with `python -m core.gcal`. |
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
- [ ] Phase 3 — meeting notes
