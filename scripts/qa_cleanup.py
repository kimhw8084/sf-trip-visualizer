"""Bounded cleanup helpers for real-browser QA runners."""

from __future__ import annotations

import signal
from collections.abc import Callable


CLEANUP_TIMEOUT_SECONDS = 10


class CleanupTimeout(TimeoutError):
    """Raised when a browser cleanup call exceeds its local bound."""


def bounded_cleanup(action: Callable[[], None], label: str, timeout: int = CLEANUP_TIMEOUT_SECONDS) -> str | None:
    """Run cleanup without allowing a browser shutdown bug to erase evidence."""

    if not hasattr(signal, "SIGALRM"):
        try:
            action()
        except Exception as error:  # pragma: no cover - macOS is the supported QA host
            return f"{label} cleanup failed: {error}"
        return None

    def interrupt(_signum, _frame):
        raise CleanupTimeout(f"{label} cleanup exceeded {timeout}s")

    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, 0)
    signal.signal(signal.SIGALRM, interrupt)
    signal.setitimer(signal.ITIMER_REAL, timeout)
    try:
        action()
    except CleanupTimeout as error:
        return str(error)
    except Exception as error:
        return f"{label} cleanup failed: {error}"
    finally:
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)
        signal.signal(signal.SIGALRM, previous_handler)
    return None
