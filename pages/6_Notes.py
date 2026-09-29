"""
Meeting notes page: pick a calendar event, write notes in a fixed template.

You can arrive here two ways:
  - from the 📝 button next to an event on the Today page (event pre-selected)
  - by opening this page and picking a date + event yourself
"""

from datetime import date, datetime

import streamlit as st

from core import db, gcal

db.init_db()
st.title("Meeting notes")


def when_text(event):
    """'Tue 29 Sep · 10:00–11:00' for timed events, 'Tue 29 Sep · all day' otherwise."""
    if event["all_day"]:
        return f"{date.fromisoformat(event['start']):%a %d %b} · all day"
    start = datetime.fromisoformat(event["start"])
    end = datetime.fromisoformat(event["end"])
    return f"{start:%a %d %b} · {start:%H:%M}–{end:%H:%M}"


# ---------------------------------------------------------------------------
# Pick an event
# ---------------------------------------------------------------------------
# The Today page puts the date and event id into session_state before it
# switches here. Widgets with the same key= pick those values up automatically.
# A widget may get its starting value from value= OR from session_state, not
# both, so the "today" default goes into session_state too (only if empty).
st.session_state.setdefault("notes_date", date.today())
day_col, sync_col = st.columns([4, 1])
day = day_col.date_input("Date", key="notes_date")
if sync_col.button("🔄 Sync this day"):
    ok, message = gcal.sync_day(day)
    (st.success if ok else st.warning)(message)

events = db.get_events_for_day(day)
if not events:
    st.info("No cached events on this day. Click “Sync this day” to fetch them from Google Calendar.")
    st.stop()

labels = {e["id"]: f"{when_text(e)} · {e['title']}" for e in events}
# If the remembered event isn't on this day (e.g. you changed the date),
# forget it, otherwise the selectbox would complain about an unknown option.
if st.session_state.get("notes_event_id") not in labels:
    st.session_state.pop("notes_event_id", None)
event_id = st.selectbox("Event", list(labels), format_func=labels.get, key="notes_event_id")
event = db.get_event(event_id)
existing = db.get_note_for_event(event_id)

# ---------------------------------------------------------------------------
# The note
# ---------------------------------------------------------------------------
st.subheader(event["title"])
st.write(f"🕒 {when_text(event)}")
st.write(f"👥 {event['attendees'] or 'No other attendees (or not synced since Phase 3).'}")
if existing:
    st.caption(f"Last saved {existing['updated_at']}")

# Keys include the event id, so switching events shows that event's text
# instead of Streamlit keeping what you typed for the previous one.
with st.form(f"note_{event_id}"):
    agenda = st.text_area("Agenda", existing["agenda"] if existing else "", key=f"agenda_{event_id}")
    notes = st.text_area("Notes", existing["notes"] if existing else "", height=200, key=f"notes_{event_id}")
    decisions = st.text_area("Decisions", existing["decisions"] if existing else "", key=f"decisions_{event_id}")
    action_items = st.text_area(
        "Action items (one per line)", existing["action_items"] if existing else "",
        key=f"actions_{event_id}",
    )
    if st.form_submit_button("💾 Save notes"):
        db.save_note(event, agenda.strip(), notes.strip(), decisions.strip(), action_items.strip())
        st.success("Saved.")

# ---------------------------------------------------------------------------
# Recent notes
# ---------------------------------------------------------------------------
st.subheader("Recent notes")
for note in db.get_recent_notes():
    with st.expander(f"{note['start'][:10]} · {note['title']}"):
        if note["attendees"]:
            st.write(f"👥 {note['attendees']}")
        # Show only the sections you actually filled in.
        for heading, text in [("Agenda", note["agenda"]), ("Notes", note["notes"]),
                              ("Decisions", note["decisions"]), ("Action items", note["action_items"])]:
            if text:
                st.markdown(f"**{heading}**")
                st.text(text)  # st.text keeps your line breaks exactly as typed
