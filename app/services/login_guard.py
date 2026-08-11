"""Einfache, globale Brute-Force-Sperre für den Login (In-Memory, Einzelprozess).

Nicht pro IP, sondern global fuer die ganze App - ausreichend fuer ein privates
Einzelnutzer-Tool. State geht bei einem Neustart verloren, das ist hier akzeptabel.
"""

import time
from threading import Lock

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60

_lock = Lock()
_state = {"failures": 0, "locked_until": 0.0}


def is_locked() -> bool:
    with _lock:
        return time.time() < _state["locked_until"]


def seconds_until_unlock() -> int:
    with _lock:
        remaining = _state["locked_until"] - time.time()
        return max(0, int(remaining))


def register_failure() -> None:
    with _lock:
        _state["failures"] += 1
        if _state["failures"] >= MAX_ATTEMPTS:
            _state["locked_until"] = time.time() + LOCKOUT_SECONDS
            _state["failures"] = 0


def register_success() -> None:
    with _lock:
        _state["failures"] = 0
        _state["locked_until"] = 0.0
