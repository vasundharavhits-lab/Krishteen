"""
Local alarm / reminder / appointment scheduler for Krishteen.

100% free and offline (besides the initial `pip install dateparser`):
- No Twilio, no calendar API, no cloud service.
- Persisted in the same SQLite DB as the rest of the app (engine/config.DB_NAME).
- A background thread polls every few seconds and "fires" anything that's due,
  speaking it out loud (pyttsx3) and pushing it to the UI (eel).

Usage from command.py / call.py:
    from engine.scheduler import handle_scheduling_command
    result = handle_scheduling_command(query)
    if result is not None:
        # it was an alarm/reminder/appointment command, `result` is the reply text
        ...
    else:
        # not a scheduling command, fall through to askAI(query) as normal
"""

import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta

import eel
import pyttsx3

from engine.config import DB_NAME

try:
    import dateparser
    from dateparser.search import search_dates
    _HAS_DATEPARSER = True
except ImportError:
    _HAS_DATEPARSER = False
    print("[scheduler] 'dateparser' is not installed — run: pip install dateparser")

_lock = threading.Lock()
_watcher_started = False

# --- Trigger phrases -------------------------------------------------------

ALARM_TRIGGERS = ["set an alarm", "set alarm", "wake me up", "set a wake up"]
REMINDER_TRIGGERS = ["remind me", "set a reminder", "set reminder"]
APPOINTMENT_TRIGGERS = [
    "book an appointment", "book appointment", "schedule an appointment",
    "schedule a meeting", "set an appointment", "add an appointment",
    "book a meeting",
]
LIST_TRIGGERS = [
    "what's on my schedule", "whats on my schedule", "list my reminders",
    "list my alarms", "list my appointments", "show my reminders",
    "show my appointments", "upcoming reminders", "upcoming appointments",
]
CANCEL_TRIGGERS = ["cancel reminder", "cancel alarm", "cancel appointment", "delete reminder"]


# --- DB ----------------------------------------------------------------

def _get_conn():
    # check_same_thread=False because the watcher thread and the eel/main
    # thread both touch this connection function.
    return sqlite3.connect(DB_NAME, check_same_thread=False)


def init_scheduler_db():
    """Creates the reminders table if it doesn't exist yet. Safe to call every startup."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            due_at TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'reminder',
            fired INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()


def _add_reminder(title, due_at: datetime, kind='reminder'):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO reminders (title, due_at, kind, created_at) VALUES (?, ?, ?, ?)',
        (title.strip() or kind.capitalize(), due_at.isoformat(), kind, datetime.now().isoformat())
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


def list_upcoming(limit=20):
    """Returns upcoming (not-yet-fired) items, soonest first."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        'SELECT id, title, due_at, kind FROM reminders WHERE fired = 0 ORDER BY due_at ASC LIMIT ?',
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "due_at": r[2], "kind": r[3]} for r in rows]

def list_all(limit=200):
    """Returns ALL reminders (past and upcoming, fired or not) for the calendar view."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        'SELECT id, title, due_at, kind, fired FROM reminders ORDER BY due_at ASC LIMIT ?',
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "due_at": r[2], "kind": r[3], "fired": bool(r[4])} for r in rows]

def cancel_reminder(rid):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute('DELETE FROM reminders WHERE id = ?', (rid,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def _cancel_most_recent_matching(text):
    """'cancel reminder call mom' -> best-effort match on title, most recent first."""
    items = list_upcoming(limit=100)
    text = text.lower()
    for item in items:
        if item["title"].lower() in text or text.strip() in item["title"].lower():
            if cancel_reminder(item["id"]):
                return item
    return None


# --- Natural language parsing -----------------------------------------

def _strip_trigger(text, triggers):
    lowered = text.lower()
    for trig in triggers:
        idx = lowered.find(trig)
        if idx != -1:
            return text[:idx] + text[idx + len(trig):]
    return text


def _parse_datetime_and_title(text, triggers):
    """
    Removes the trigger phrase, then uses dateparser to find the date/time
    portion of the remaining text and strips it out too, leaving the title.
    Returns (title, due_datetime) or (None, None) if no date/time was found.
    """
    remainder = _strip_trigger(text, triggers).strip()

    if not _HAS_DATEPARSER:
        return None, None

    settings = {'PREFER_DATES_FROM': 'future', 'RETURN_AS_TIMEZONE_AWARE': False}
    found = search_dates(remainder, settings=settings)
    if not found:
        return None, None

    matched_text, due_at = found[0]

    # Guard against picking a due date in the past due to ambiguous phrasing
    if due_at < datetime.now():
        due_at = due_at + timedelta(days=1)

    title = remainder.replace(matched_text, "").strip(" ,.-")
    # Clean up leftover connector words like "to", "for", "about"
    title = re.sub(r'^(to|for|about|that)\s+', '', title, flags=re.IGNORECASE).strip()

    return title, due_at


def _format_when(due_at: datetime):
    now = datetime.now()
    if due_at.date() == now.date():
        return f"today at {due_at.strftime('%I:%M %p').lstrip('0')}"
    if due_at.date() == (now + timedelta(days=1)).date():
        return f"tomorrow at {due_at.strftime('%I:%M %p').lstrip('0')}"
    return due_at.strftime('%A, %b %d at %I:%M %p').replace(' 0', ' ')


# --- Public entry point --------------------------------------------------

def handle_scheduling_command(query):
    """
    Checks if `query` is an alarm/reminder/appointment/list/cancel command.
    Returns a reply string to speak if it was handled, otherwise None
    (meaning: fall through to the normal AI chat path).
    """
    lowered = query.lower()

    if not _HAS_DATEPARSER and any(t in lowered for t in ALARM_TRIGGERS + REMINDER_TRIGGERS + APPOINTMENT_TRIGGERS):
        return ("I can't set that yet because the 'dateparser' package isn't installed. "
                "Run: pip install dateparser and restart me.")

    if any(t in lowered for t in LIST_TRIGGERS):
        items = list_upcoming()
        if not items:
            return "You don't have anything scheduled right now."
        lines = [f"{it['kind'].capitalize()}: {it['title']} — {_format_when(datetime.fromisoformat(it['due_at']))}"
                 for it in items[:5]]
        return "Here's what's coming up. " + " | ".join(lines)

    if any(t in lowered for t in CANCEL_TRIGGERS):
        target_text = _strip_trigger(lowered, CANCEL_TRIGGERS).strip()
        item = _cancel_most_recent_matching(target_text) if target_text else None
        if not item and target_text == "":
            items = list_upcoming(limit=1)
            if items:
                cancel_reminder(items[0]["id"])
                item = items[0]
        if item:
            return f"Cancelled: {item['title']}."
        return "I couldn't find a matching reminder to cancel. Try 'list my reminders' first."

    if any(t in lowered for t in ALARM_TRIGGERS):
        title, due_at = _parse_datetime_and_title(query, ALARM_TRIGGERS)
        if not due_at:
            return "What time should I set the alarm for?"
        _add_reminder(title or "Alarm", due_at, kind="alarm")
        return f"Alarm set for {_format_when(due_at)}."

    if any(t in lowered for t in APPOINTMENT_TRIGGERS):
        title, due_at = _parse_datetime_and_title(query, APPOINTMENT_TRIGGERS)
        if not due_at:
            return "When is the appointment, and what's it for?"
        _add_reminder(title or "Appointment", due_at, kind="appointment")
        return f"Appointment booked: {title or 'Appointment'} — {_format_when(due_at)}."

    if any(t in lowered for t in REMINDER_TRIGGERS):
        title, due_at = _parse_datetime_and_title(query, REMINDER_TRIGGERS)
        if not due_at:
            return "Sure — when should I remind you, and about what?"
        _add_reminder(title or "Reminder", due_at, kind="reminder")
        return f"Okay, I'll remind you to {title or 'that'} — {_format_when(due_at)}."

    return None


# --- Background watcher --------------------------------------------------

def _speak(text):
    try:
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        if len(voices) > 1:
            engine.setProperty('voice', voices[1].id)
        engine.setProperty('rate', 170)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except Exception as e:
        print("[scheduler] TTS error:", e)


def _fire(rid, title, kind):
    label = {"alarm": "Alarm", "reminder": "Reminder", "appointment": "Appointment"}.get(kind, "Reminder")
    message = f"{label}: {title}"
    try:
        eel.ReminderFired(message, kind)
    except Exception as e:
        print("[scheduler] Couldn't push to UI:", e)
    _speak(message)


def _watch_loop(check_interval_seconds):
    while True:
        time.sleep(check_interval_seconds)
        now = datetime.now()
        try:
            conn = _get_conn()
            cur = conn.cursor()
            cur.execute('SELECT id, title, kind FROM reminders WHERE fired = 0 AND due_at <= ?', (now.isoformat(),))
            due = cur.fetchall()
            for rid, title, kind in due:
                cur.execute('UPDATE reminders SET fired = 1 WHERE id = ?', (rid,))
            conn.commit()
            conn.close()
        except Exception as e:
            print("[scheduler] watcher DB error:", e)
            due = []

        for rid, title, kind in due:
            _fire(rid, title, kind)


def start_alarm_watcher(check_interval_seconds=15):
    """Call once at app startup (from main.py)."""
    global _watcher_started
    with _lock:
        if _watcher_started:
            return
        _watcher_started = True
    init_scheduler_db()
    t = threading.Thread(target=_watch_loop, args=(check_interval_seconds,), daemon=True)
    t.start()


# --- eel-exposed endpoints (for a UI panel) -------------------------------

@eel.expose
def getUpcomingReminders():
    return list_upcoming()


@eel.expose
def getAllReminders():
    """Used by calendar.js for the month-view calendar, which needs to show
    past and already-fired items too, not just what's upcoming."""
    return list_all()


@eel.expose
def cancelReminderById(rid):
    return {"deleted": cancel_reminder(int(rid))}