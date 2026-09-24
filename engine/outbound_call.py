"""
engine/outbound_call.py — Shared Twilio outbound-calling logic.

This is the same call-placing code outbound.py (CLI) uses, pulled into
engine/ so it can also be triggered from voice/typed chat via
engine/call_trigger.py, without duplicating the Twilio setup.
"""

import os
import urllib.parse

from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")


def place_call(to_number: str, purpose: str) -> str:
    """Places a real outbound call via Twilio. Returns the Call SID.
    Raises RuntimeError if config is missing, or twilio.base.exceptions.TwilioRestException
    if Twilio itself rejects the request (e.g. unverified trial number)."""
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER):
        raise RuntimeError("Missing TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_PHONE_NUMBER in .env")
    if not PUBLIC_BASE_URL:
        raise RuntimeError("Missing PUBLIC_BASE_URL in .env (your ngrok https URL, no trailing slash)")

    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

    purpose_encoded = urllib.parse.quote(purpose)
    answer_url = f"{PUBLIC_BASE_URL}/outbound-answer?purpose={purpose_encoded}"

    call = client.calls.create(
        to=to_number,
        from_=TWILIO_PHONE_NUMBER,
        url=answer_url,
        status_callback=f"{PUBLIC_BASE_URL}/call-status",
        status_callback_event=["completed"],
    )
    return call.sid