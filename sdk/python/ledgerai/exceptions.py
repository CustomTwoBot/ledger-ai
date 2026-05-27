from __future__ import annotations


class BudgetExceededError(Exception):
    def __init__(self, reason: str | None, daily_remaining_usd: float | None):
        self.reason = reason
        self.daily_remaining_usd = daily_remaining_usd
        msg = f"Budget exceeded: {reason}" if reason else "Budget exceeded"
        super().__init__(msg)
