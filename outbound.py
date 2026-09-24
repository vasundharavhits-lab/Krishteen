"""
outbound.py — CLI entry point to trigger Krishteen to call a real number.
Thin wrapper around engine/outbound_call.py's place_call(), which is the
same function used when you ask Krishteen to call someone by voice/chat
(see engine/call_trigger.py).

Usage:
    python outbound.py +919876543210 "book a dentist appointment for Tuesday"

REQUIREMENTS
-------------
- Your FastAPI voice server must already be running (e.g.
  uvicorn voice_server.server:app --host 0.0.0.0 --port 8000)
- ngrok must be tunneling that port, and PUBLIC_BASE_URL in .env must match
  the ngrok https URL
- On a Twilio trial account, the destination number MUST be verified first
  in the Twilio console under Phone Numbers > Verified Caller IDs.
"""

import sys

from engine.outbound_call import place_call


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('Usage: python outbound.py "+919876543210" "book a dentist appointment"')
        sys.exit(1)

    
    number = sys.argv[1]
    call_purpose = " ".join(sys.argv[2:])

    try:
        
        sid = place_call(number, call_purpose)
        
        print(f"Calling {number} — Call SID: {sid}")
    except Exception as e:
        print(f"Failed to place call: {e}")
        sys.exit(1)