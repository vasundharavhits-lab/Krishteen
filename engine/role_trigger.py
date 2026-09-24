"""
engine/role_trigger.py — Detects "act as <role>" / "your role is <role>"
style commands and locks Krishteen into that single role for every future
answer, until the user clears it or sets a new one. Persisted via
engine/preferences.py (same file/mechanism as the answer-style setting),
so it survives app restarts.

Usage from command.py / call.py, same pattern as call_trigger.py /
scheduler.py:

    from engine.role_trigger import handle_role_command
    result = handle_role_command(query)
    if result is not None:
        # it was a role set/clear/query command, `result` is the reply text
        ...
    else:
        # not a role command, fall through as normal
"""

import re

from engine.preferences import get_role, set_role, clear_role
from engine.ai import clear_session

# "act as a doctor", "pretend to be my lawyer", "your role is customer
# support agent", "from now on you are a fitness coach", etc.
_SET_ROLE_RE = re.compile(
    r'\b(?:act as|behave as|behave like|pretend to be|pretend you(?:\'re| are)|'
    r'you are now|you\'re now|from now on you are|from now on you\'re|be a|be an|'
    r'your role is|set your role to|switch to the role of|switch your role to|'
    r'take on the role of|assume the role of)\s+(?:a |an |the )?(?P<role>.+)',
    re.IGNORECASE
)

# "stop acting as a doctor", "clear your role", "back to normal", etc.
_CLEAR_ROLE_RE = re.compile(
    r'\b(clear your role|reset your role|remove your role|stop acting as|'
    r'stop being|no more role|drop the role|exit role|leave role|'
    r'go back to normal|back to normal|be yourself again|be yourself|'
    r'you are no longer|you\'re no longer|forget your role)\b',
    re.IGNORECASE
)

# "what's your role", "what role are you in right now", etc.
_ASK_ROLE_RE = re.compile(
    r'\b(what is your role|what\'s your role|what role are you|'
    r'which role are you|current role|do you have a role)\b',
    re.IGNORECASE
)

_TRAILING_JUNK_RE = re.compile(r'\s*(please|for me|from now on|okay|ok)\s*$', re.IGNORECASE)


def _clean_role_text(raw):
    text = raw.strip(" ,.!\n\t")
    text = _TRAILING_JUNK_RE.sub('', text).strip(" ,.!")
    return text


def handle_role_command(query, session_id="chat"):
    """
    Checks if `query` is a role set/clear/query command.
    Returns a reply string to speak/show if it was handled, otherwise None
    (meaning: fall through to normal routing, e.g. askAI(query)).

    session_id should match whatever session_id is passed to askAI() for
    this call/chat — switching or clearing a role also wipes that
    session's leftover conversation history, so an earlier topic (e.g.
    a customer-support question) can't bleed into the new role's replies
    (e.g. a diet suggestion right after switching to fitness coach).
    """
    query = query.strip()
    if not query:
        return None

    lowered = query.lower()

    if _ASK_ROLE_RE.search(lowered):
        role = get_role()
        if role:
            return f'Right now I\'m locked into the role of "{role}".'
        return "I'm not locked into any specific role right now — just regular Krishteen."

    if _CLEAR_ROLE_RE.search(lowered):
        had_role = get_role()
        clear_role()
        clear_session(session_id)
        if had_role:
            return f'Okay, dropping the "{had_role}" role — back to being regular Krishteen.'
        return "I wasn't locked into a role anyway, but noted."

    match = _SET_ROLE_RE.search(query)
    if match:
        role_text = _clean_role_text(match.group('role'))
        if not role_text:
            return "Sure — what role should I take on?"
        set_role(role_text)
        clear_session(session_id)
        return f'Got it — from now on I\'ll act strictly as "{role_text}", until you tell me otherwise.'

    return None