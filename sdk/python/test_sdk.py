"""
Integration smoke tests for the ledgerai SDK.

Requires the agent-cost-tracker API to be running at http://127.0.0.1:8000.
Run with:  pytest sdk/python/test_sdk.py -v
"""
import re
import uuid

import httpx
import pytest

from ledgerai import BudgetExceededError, LedgerAnthropic

LEDGER_URL = "http://127.0.0.1:8000"
AGENT_ID = f"pytest-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def client():
    return LedgerAnthropic(ledger_url=LEDGER_URL, agent_id=AGENT_ID, mock=True)


@pytest.fixture(scope="module")
def api():
    return httpx.Client(base_url=LEDGER_URL, timeout=10.0)


# ---------------------------------------------------------------------------
# Budget check
# ---------------------------------------------------------------------------

def test_budget_check_passes(api):
    """GET /api/v1/budgets/check returns allowed=true for a fresh agent."""
    resp = api.get("/api/v1/budgets/check", params={"agent_id": AGENT_ID})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["allowed"] is True, f"Expected allowed=true, got: {data}"


def test_budget_check_blocked_raises(monkeypatch):
    """BudgetExceededError is raised when the budget check returns allowed=false."""
    def fake_get(url, **kwargs):
        class R:
            status_code = 200
            def raise_for_status(self): pass
            def json(self):
                return {"allowed": False, "reason": "Daily limit exceeded", "daily_remaining_usd": 0.0}
        return R()

    from ledgerai import _tracker as tracker_mod
    monkeypatch.setattr(tracker_mod.httpx.Client, "get", lambda self, url, **kw: fake_get(url, **kw))

    blocked_client = LedgerAnthropic(ledger_url=LEDGER_URL, agent_id=AGENT_ID, mock=True)
    with pytest.raises(BudgetExceededError) as exc_info:
        blocked_client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=10,
            messages=[{"role": "user", "content": "say hi"}],
        )
    assert exc_info.value.daily_remaining_usd == 0.0
    assert "exceeded" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Cost logging
# ---------------------------------------------------------------------------

def test_messages_create_returns_mock_response(client):
    """mock=True response has the expected shape and text."""
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=10,
        messages=[{"role": "user", "content": "say hi"}],
    )
    assert response.role == "assistant"
    assert response.content[0].text == "[mock response]"
    assert response.usage.input_tokens == 100
    assert response.usage.output_tokens == 50


def test_cost_log_recorded(api):
    """After a mock call, POST /api/v1/costs/log has recorded a cost entry."""
    # Trigger a call so there's definitely a log entry for this agent.
    c = LedgerAnthropic(ledger_url=LEDGER_URL, agent_id=AGENT_ID, mock=True)
    c.messages.create(
        model="claude-haiku-4-5",
        max_tokens=10,
        messages=[{"role": "user", "content": "say hi"}],
    )

    resp = api.get("/api/v1/costs/summary", params={"agent_id": AGENT_ID, "period": "daily"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total_calls"] >= 1
    assert data["total_cost_usd"] > 0


def test_cost_log_post_returns_valid_cost(api):
    """POST /api/v1/costs/log directly returns a 201 with a positive cost_usd."""
    payload = {
        "agent_id": AGENT_ID,
        "provider": "anthropic",
        "model": "claude-haiku-4-5",
        "input_tokens": 100,
        "output_tokens": 50,
        "request_id": str(uuid.uuid4()),
    }
    resp = api.post("/api/v1/costs/log", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "cost_usd" in data
    assert isinstance(data["cost_usd"], float)
    assert data["cost_usd"] > 0
