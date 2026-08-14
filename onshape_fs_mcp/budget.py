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

from onshape_fs_mcp.client import OnshapeClient
from onshape_fs_mcp.operations import api_usage, preflight


class BudgetExceeded(RuntimeError):
    """Raised when a run would start already over budget or past preflight."""


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
        self.client = client or OnshapeClient()
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
