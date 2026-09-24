"""
insert_dummy_data.py — Seeds krishteen.db with sample appointments/reminders
for testing the voice agent, without needing to say them out loud each time.

Run once with:  python insert_dummy_data.py
"""

import sqlite3
from datetime import datetime, timedelta
from engine.config import DB_NAME

conn = sqlite3.connect(DB_NAME)
cur = conn.cursor()

# Make sure the table exists (same schema as engine/scheduler.py)
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

now = datetime.now()

dummy_data = [
    ("Dentist appointment with Dr. Sharma",         now + timedelta(days=1, hours=3),  "appointment"),
    ("Client call with Acme Corp",                  now + timedelta(days=1, hours=5),  "appointment"),
    ("Follow up on invoice #1042",                  now + timedelta(days=2),           "reminder"),
    ("Team meeting - Q3 review",                    now + timedelta(days=3, hours=1),  "appointment"),
    ("Wake up for early flight",                    now + timedelta(days=1, hours=-14),"alarm"),
    ("Quick test reminder (fires in 2 minutes)",    now + timedelta(minutes=2),        "reminder"),
    ("Interview with TechNova Solutions",           now + timedelta(days=2, hours=4),  "appointment"),
    ("Call vendor about delayed shipment",          now + timedelta(hours=6),          "reminder"),
    ("Renew domain for krishteen.ai",               now + timedelta(days=5),           "reminder"),
    ("Payment due - Vodafone bill",                 now + timedelta(days=4),           "reminder"),
    ("Doctor checkup - Apollo Hospital",             now + timedelta(days=6, hours=2),  "appointment"),
    ("Weekly standup with dev team",                now + timedelta(days=1, hours=9),  "appointment"),
    ("Pick up parcel from courier office",          now + timedelta(hours=3),          "reminder"),
    ("Investor call - Nimbus Ventures",              now + timedelta(days=3, hours=6),  "appointment"),
    ("Renew car insurance",                          now + timedelta(days=7),           "reminder"),
    ("Gym session",                                  now + timedelta(hours=10),         "alarm"),
    ("Salon appointment - haircut",                  now + timedelta(days=2, hours=7),  "appointment"),
    ("Submit tax documents",                         now + timedelta(days=8),           "reminder"),
    ("Product demo call with Orion Retail",         now + timedelta(days=1, hours=2),  "appointment"),
    ("Birthday reminder - call mom",                 now + timedelta(days=1, hours=8),  "reminder"),
]
for title, due_at, kind in dummy_data:
    cur.execute(
        'INSERT INTO reminders (title, due_at, kind, created_at) VALUES (?, ?, ?, ?)',
        (title, due_at.isoformat(), kind, now.isoformat())
    )

conn.commit()
conn.close()

print(f"Inserted {len(dummy_data)} dummy reminders/appointments into {DB_NAME}.")