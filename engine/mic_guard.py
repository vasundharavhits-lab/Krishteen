"""
Tiny mutual-exclusion helper so only one part of the app — the always-on
'Hey Krishteen' wake-word listener, the one-shot mic button, or live Call
mode — is ever recording from the microphone at the same time.

Everything else in the app should wrap actual mic access like:

    if not try_acquire_mic(timeout=5):
        ...  # someone else has it, back off
    try:
        ...  # use sr.Microphone() here
    finally:
        release_mic()
"""

import threading

_lock = threading.Lock()


def try_acquire_mic(timeout=0):
    """Blocks up to `timeout` seconds trying to get exclusive mic access.
    timeout=0 (default) means: try once, don't wait, return immediately."""
    return _lock.acquire(timeout=timeout)


def release_mic():
    try:
        _lock.release()
    except RuntimeError:
        # release() called without a matching acquire — ignore, nothing to do
        pass