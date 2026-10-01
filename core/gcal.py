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

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from core import db

ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_PATH = ROOT / "credentials.json"
TOKEN_PATH = ROOT / "token.json"

# What the app may do with your Google account:
#   calendar.readonly    -> READ all your calendars (never change them)
#   calendar.app.created -> create its OWN extra calendar ("Productivity blocks")
#                           and add/edit/delete events in calendars it created.
#                           It cannot touch your main calendar or any other one.
# If this list changes, get_credentials() notices that token.json is missing a
# permission and asks you to log in again.
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.app.created",
]
BLOCKS_CALENDAR_NAME = "Productivity blocks"


def _token_has_all_scopes():
    """True if the saved login already includes every permission in SCOPES.
    token.json is JSON, and Google saves the granted scopes in it."""
    try:
        granted = set(json.loads(TOKEN_PATH.read_text()).get("scopes", []))
    except (OSError, ValueError):
        return False
    return set(SCOPES) <= granted  # <= on sets means "is a subset of"


def get_credentials():
    """Return valid Google credentials, logging in through the browser if needed."""
    if not CREDENTIALS_PATH.exists():
        raise FileNotFoundError(
            "credentials.json not found in the project folder. "
            "See 'Google Calendar setup' in README.md."
        )

    creds = None
    if TOKEN_PATH.exists() and not _token_has_all_scopes():
        # Logged in before a permission was added (e.g. read-only from Phase 1):
        # throw the old login away so Google asks for the new permission.
        TOKEN_PATH.unlink()
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
    # Attendees: use their name if Google has one, else their email.
    # Skip yourself ("self") and meeting rooms ("resource").
    attendees = [
        a.get("displayName") or a.get("email", "?")
        for a in item.get("attendees", [])
        if not a.get("self") and not a.get("resource")
    ]
    return {
        "id": item["id"],
        "title": item.get("summary", "(no title)"),  # untitled events have no summary
        "start": item["start"][key],
        "end": item["end"][key],
        "all_day": int(all_day),
        "attendees": ", ".join(attendees) or None,
    }


def get_service():
    """A Google Calendar API client, logged in. (Tests replace this with a fake.)"""
    return build("calendar", "v3", credentials=get_credentials(), cache_discovery=False)


def fetch_events(day):
    """Ask Google for every event on `day` in your primary calendar."""
    service = get_service()
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



# ---------------------------------------------------------------------------
# Phase 5: time blocks (writing to Google Calendar)
# ---------------------------------------------------------------------------

def _blocks_calendar_id(service):
    """Id of the app's own "Productivity blocks" calendar, creating it the first time.

    The id is remembered in settings. If you deleted that calendar in Google,
    calendars().get fails, and we simply create a new one.
    """
    calendar_id = db.get_setting("blocks_calendar_id")
    if calendar_id:
        try:
            service.calendars().get(calendarId=calendar_id).execute()
            return calendar_id
        except HttpError:
            pass  # gone (deleted in Google): make a fresh one below
    created = service.calendars().insert(body={"summary": BLOCKS_CALENDAR_NAME}).execute()
    db.set_setting("blocks_calendar_id", created["id"])
    return created["id"]


def create_block(task, start, minutes):
    """Put a time block for `task` into the Productivity blocks calendar.

    start: timezone-aware datetime. Returns (ok, message), like sync_day, so
    the page can show an error instead of crashing.
    """
    end = start + timedelta(minutes=minutes)
    try:
        service = get_service()
        calendar_id = _blocks_calendar_id(service)
        event = service.events().insert(calendarId=calendar_id, body={
            "summary": f"🎯 {task['title']}",
            "description": "Time block created by your productivity app.",
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": end.isoformat()},
        }).execute()
    except Exception as err:
        return False, f"Couldn't create the block ({type(err).__name__}): {str(err).rstrip('.')}."
    db.add_time_block(task["id"], calendar_id, event["id"], start, end)
    return True, f"Blocked {start:%a %d %b %H:%M}–{end:%H:%M} for “{task['title']}”."


def remove_block(block):
    """Delete a block from Google Calendar and from the app.
    If it's already gone in Google (deleted by hand), just forget it locally."""
    try:
        get_service().events().delete(calendarId=block["calendar_id"], eventId=block["event_id"]).execute()
    except HttpError as err:
        if err.resp.status not in (404, 410):  # 404/410 = already deleted: that's fine
            return False, f"Couldn't remove the block: {err}"
    except Exception as err:
        return False, f"Couldn't remove the block ({type(err).__name__}): {err}"
    db.delete_time_block(block["id"])
    return True, "Block removed."


if __name__ == "__main__":
    db.init_db()
    ok, message = sync_day()
    print(message)
    for e in db.get_events_for_day(date.today()):
        when = "all day" if e["all_day"] else f"{e['start'][11:16]}–{e['end'][11:16]}"
        print(f"  {when:>13}  {e['title']}")
