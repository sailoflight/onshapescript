"""Per-process pacing guard for real browser actions.

Real browser actions are the three browser_* operations that actually drive the
page or run arbitrary page code: ``browser_click``, ``browser_scroll`` and
``browser_eval``. They are shaped by two rules read from ``config/browser.toml``
``[pacing]``:

* ``max_actions_per_minute`` — a hard per-process cap. ``ActionGuard.pace()``
  raises :class:`ActionRateExceeded` when the trailing 60-second window is
  already full, so a runaway loop cannot hammer the UI faster than configured.
* ``min_delay_s`` / ``max_delay_s`` — a uniform-random delay slept before each
  real action. This is honest rate shaping to keep the automation gentle on the
  page; it is NOT a stealth or "humanization" feature and makes no claim about
  hiding automation.

``clock`` / ``sleep`` / ``rng`` are injectable so tests can exercise the cap and
delay logic without wall-clock sleeps or real randomness.
"""

from __future__ import annotations

import random
import time
from typing import Callable

from onshape_browser_mode.config import load_browser_config


class ActionRateExceeded(RuntimeError):
    """A real browser action was refused because the per-minute cap is full."""


class ActionGuard:
    """Enforce the [pacing] contract before each real browser action."""

    def __init__(
        self,
        max_actions_per_minute: int | None = None,
        min_delay_s: float | None = None,
        max_delay_s: float | None = None,
        *,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        if (
            max_actions_per_minute is None
            or min_delay_s is None
            or max_delay_s is None
        ):
            pacing = load_browser_config().pacing
        else:
            pacing = None
        self.max_actions_per_minute = (
            pacing.max_actions_per_minute
            if max_actions_per_minute is None
            else max_actions_per_minute
        )
        self.min_delay_s = pacing.min_delay_s if min_delay_s is None else min_delay_s
        self.max_delay_s = pacing.max_delay_s if max_delay_s is None else max_delay_s
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._rng = rng if rng is not None else random.Random()
        # Timestamps (from self._clock) of the real actions in the current window.
        self._action_times: list[float] = []

    def _prune(self, now: float) -> None:
        cutoff = now - 60.0
        self._action_times = [t for t in self._action_times if t > cutoff]

    def check(self) -> None:
        """Raise :class:`ActionRateExceeded` when the window is already full."""
        now = self._clock()
        self._prune(now)
        cap = self.max_actions_per_minute
        if cap > 0 and len(self._action_times) >= cap:
            wait = 60.0 - (now - self._action_times[0])
            raise ActionRateExceeded(
                f"browser action cap reached ({cap} actions/min); "
                f"retry in about {max(wait, 0.0):.1f}s"
            )

    def delay_seconds(self) -> float:
        """Uniform-random pacing delay inside ``[min_delay_s, max_delay_s]``."""
        return self._rng.uniform(self.min_delay_s, self.max_delay_s)

    def pace(self) -> None:
        """Enforce the cap, sleep the randomized delay, then record the action."""
        self.check()
        delay = self.delay_seconds()
        if delay > 0:
            self._sleep(delay)
        self._action_times.append(self._clock())

    def recent_action_count(self) -> int:
        """Number of recorded real actions still inside the 60-second window."""
        self._prune(self._clock())
        return len(self._action_times)


_guard: ActionGuard | None = None


def get_guard() -> ActionGuard:
    """Return the process-wide action guard singleton."""
    global _guard
    if _guard is None:
        _guard = ActionGuard()
    return _guard
