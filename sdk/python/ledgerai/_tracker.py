from __future__ import annotations

import uuid

import httpx

from .exceptions import BudgetExceededError


class CostTracker:
    def __init__(self, ledger_url: str, agent_id: str) -> None:
        self._base = ledger_url.rstrip("/")
        self.agent_id = agent_id
        self._http = httpx.Client(timeout=10.0)

    def check_budget(self) -> None:
        resp = self._http.get(
            f"{self._base}/api/v1/budgets/check",
            params={"agent_id": self.agent_id},
        )
        resp.raise_for_status()
        data = resp.json()
        if not data["allowed"]:
            raise BudgetExceededError(
                reason=data.get("reason"),
                daily_remaining_usd=data.get("daily_remaining_usd"),
            )

    def log_cost(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> dict:
        payload = {
            "agent_id": self.agent_id,
            "provider": provider,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "request_id": str(uuid.uuid4()),
        }
        resp = self._http.post(f"{self._base}/api/v1/costs/log", json=payload)
        resp.raise_for_status()
        return resp.json()
