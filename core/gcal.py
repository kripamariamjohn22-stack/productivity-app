"""
gcal.py — reads events from Google Calendar and saves them in the local database.

How Google login works (OAuth), in short:
  1. credentials.json identifies *this app* to Google (you download it once).
  2. The first time, a browser window opens and YOU say "yes, this app may
     read my calendar". Google hands back a token.
  3. We save that token in token.json so you don't have to log in every time.
Both files are secrets: they're in .gitignore and we never print them.

Try it from the terminal:  python -m core.gcal
"""

from datetime import date, datetime, time, timedelta
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from core import db

ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_PATH = ROOT / "credentials.json"
TOKEN_PATH = ROOT / "token.json"

# Read-only: the app can look at your calendar but cannot change anything.
# If this list ever changes (Phase 5 = write access), delete token.json
# so Google asks for the new permission.
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def get_credentials():
    """Return valid Google credentials, logging in through the browser if needed."""
    if not CREDENTIALS_PATH.exists():
        raise FileNotFoundError(
            "credentials.json not found in the project folder. "
            "See 'Google Calendar setup' in README.md."
        )

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        # Access tokens only last ~1 hour. The refresh token quietly gets a new one.
        try:
            creds.refresh(Request())
        except RefreshError:
            # The refresh token itself was revoked or expired (in "Testing" mode
            # Google expires it after 7 days). Throw it away and log in again.
            TOKEN_PATH.unlink()
            creds = None

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
        # Opens your browser and waits for you to click "Allow".
        # port=0 = pick any free port, so it never clashes with Streamlit's 8501.
        creds = flow.run_local_server(port=0)

    TOKEN_PATH.write_text(creds.to_json())
    return creds


def _parse_event(item):
    """Turn Google's event format into the columns of our `events` table.

    Google uses start.dateTime for timed events and start.date for all-day ones.
    """
    all_day = "date" in item["start"]
    key = "date" if all_day else "dateTime"
    return {
        "id": item["id"],
        "title": item.get("summary", "(no title)"),  # untitled events have no summary
        "start": item["start"][key],
        "end": item["end"][key],
        "all_day": int(all_day),
    }


def fetch_events(day):
    """Ask Google for every event on `day` in your primary calendar."""
    service = build("calendar", "v3", credentials=get_credentials(), cache_discovery=False)
    # .astimezone() attaches your computer's time zone, so "today" means
    # your midnight-to-midnight, not UTC's.
    start = datetime.combine(day, time.min).astimezone()
    end = start + timedelta(days=1)
    response = service.events().list(
        calendarId="primary",
        timeMin=start.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,   # expand repeating events into individual days
        orderBy="startTime",
        maxResults=250,      # one page; nobody has 250 events in a day
    ).execute()
    return [_parse_event(item) for item in response.get("items", [])]


def sync_day(day=None):
    """Fetch one day from Google and update the local cache.

    Returns (ok, message) instead of raising, so the page can show a friendly
    note and keep using the cached events when there's no internet.
    """
    day = day or date.today()
    try:
        events = fetch_events(day)
    except Exception as err:  # no internet, no credentials, Google down...
        # Only the error type and message: never the credentials themselves.
        return False, f"Sync failed ({type(err).__name__}): {str(err).rstrip('.')}. Showing cached events."
    db.replace_events_for_day(day, events)
    db.set_setting("last_sync", db.now_str())
    return True, f"Synced {len(events)} event(s)."


if __name__ == "__main__":
    db.init_db()
    ok, message = sync_day()
    print(message)
    for e in db.get_events_for_day(date.today()):
        when = "all day" if e["all_day"] else f"{e['start'][11:16]}–{e['end'][11:16]}"
        print(f"  {when:>13}  {e['title']}")
