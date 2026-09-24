"""
engine/call_trigger.py — Detects a "call <number> ..." voice or typed
command, pulls out the phone number and purpose, and places a real Twilio
call via engine/outbound_call.py.
"""

import re

_PHONE_RE = re.compile(r'\+?\d[\d\s\-]{7,}\d')
_LEADING_CONNECTORS_RE = re.compile(r'^(and|to|then|,)\s*', re.IGNORECASE)


def _extract_phone_number(text):
    match = _PHONE_RE.search(text)
    if not match:
        return None, None
    raw = match.group()
    digits = re.sub(r'[^\d+]', '', raw)
    if not digits.startswith('+'):
        digits = '+' + digits
    return digits, raw


def handle_call_command(query):
    """
    Returns a reply string if this was a "call ..." command (call placed or
    a clarifying question), otherwise None (fall through to normal routing).
    """
    lowered = query.lower()
    if not re.search(r'\bcall\b', lowered):
        return None

    number, raw_match = _extract_phone_number(query)
    if not number:
        return ("Sure — what number should I call? Please include the "
                "country code, for example plus 91 followed by the number.")

    purpose_text = query.replace(raw_match, '')
    purpose_text = re.sub(r'\bcall\b', '', purpose_text, count=1, flags=re.IGNORECASE)
    purpose_text = _LEADING_CONNECTORS_RE.sub('', purpose_text.strip())
    purpose = purpose_text.strip(" ,.-")
    if not purpose:
        purpose = "a general matter"

    try:
        from engine.outbound_call import place_call
        place_call(number, purpose)
    except Exception as e:
        return f"Sorry, I couldn't place that call. {str(e)}"

    return f"Okay, calling {number} now — {purpose}."