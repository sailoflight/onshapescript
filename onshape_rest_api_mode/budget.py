"""Shared quota-budget guard for live Onshape verification runs.

Encodes the verification lessons recorded in docs/verification/live/README.md
and the "verification ladder" in docs/verification/llm-experience-fs.md:

- **Preflight before mutating** — a run must never start if its budget exceeds
  the remaining annual quota (`operations.preflight` is the gate).
- **Account as you go** — the passive ledger (`config/api-usage.json`, counts
  2xx/3xx only) is the source of truth for this run's spend. Never guess.
- **Configurable, not hard-coded** — every script passes its own `budget` from
  the command line instead of baking in a constant that goes stale as the
  ledger moves.
- **Batch verification has declining returns** — the guard surfaces `spent` /
  `remaining` so a run can stop early and report honestly rather than burning
  the whole budget.
"""

from __future__ import annotations

from typing import Any

from onshape_rest_api_mode.client import (
    LiveApiDisabled,
    OnshapeClient,
    RateLimitedHold,
    _live_disabled_reason,
    live_api_enabled,
    rate_limit_reason,
)
from onshape_rest_api_mode.operations import api_usage, preflight


class BudgetExceeded(RuntimeError):
    """Raised when a run would start already over budget or past preflight."""


def live_blocker(
    estimate_calls: int,
    label: str,
    client: OnshapeClient | None = None,
) -> str | None:
    """Return a reason string if a live operation must NOT run, else None.

    The single gate every live entrypoint checks BEFORE its first request. It
    combines (1) the explicit LIVE_API_ENABLED opt-in, (2) the passive
    rate-limit hold (remaining 0 with a long Retry-After) and (3) the
    annual-quota preflight. Zero network cost; safe to call with no credentials
    configured (the hold check still runs offline, and the preflight is skipped
    — the live op itself will then fail on missing credentials with a clear
    error rather than silently burning quota).
    """
    if not live_api_enabled():
        return _live_disabled_reason(label)
    hold = rate_limit_reason()
    if hold:
        return hold
    try:
        client = client or OnshapeClient()
    except Exception:
        # No credentials/state: the live operation itself will raise a clear
        # error. Nothing to gate here.
        return None
    gate = preflight(estimate_calls, label, client)
    if not gate["canProceed"]:
        return gate["blockedReason"]
    return None


class BudgetGuard:
    """Per-run budget over the passive quota ledger, gated by preflight.

    Usage::

        guard = BudgetGuard(budget, "is* probe")   # preflights; raises if blocked
        for candidate in work:
            if guard.exceeded():
                break
            ... make calls ...
        guard.summary()                            # budget / spent / remaining
    """

    def __init__(self, budget: int, label: str, client: OnshapeClient | None = None):
        self.label = label
        self.budget = int(budget)
        # Explicit opt-in first: real requests are not a script default. The
        # flag check is zero-cost and precedes client construction, the hold
        # and quota checks, so a disabled run stops before reading credentials,
        # state or the ledger at all (and a missing-credentials KeyError can't
        # mask the clean LiveApiDisabled message).
        if not live_api_enabled():
            raise LiveApiDisabled(_live_disabled_reason(label))
        self.client = client or OnshapeClient()
        # Refuse to start while the account is under a rate-limit hold: the
        # ledger (remaining 0 + Retry-After) is checked BEFORE preflight so a
        # run can't waste requests on a still-limited account.
        hold = rate_limit_reason(self.client._usage)
        if hold:
            raise RateLimitedHold(hold)
        self.start = int(self.client._usage.get("consumed", 0) or 0)
        gate = preflight(self.budget, label, self.client)
        if not gate["canProceed"]:
            raise BudgetExceeded(gate["blockedReason"] or "budget exceeds remaining annual quota")
        self._annual_remaining = gate["details"].get("remaining")

    @property
    def spent(self) -> int:
        """Ledgered (2xx/3xx) calls consumed by THIS run so far."""
        return int(self.client._usage.get("consumed", 0) or 0) - self.start

    @property
    def remaining(self) -> int:
        return max(0, self.budget - self.spent)

    def exceeded(self) -> bool:
        return self.spent >= self.budget

    def summary(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "budget": self.budget,
            "spent": self.spent,
            "remaining": self.remaining,
            "annualRemaining": self._annual_remaining,
        }
