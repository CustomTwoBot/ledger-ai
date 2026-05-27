# ledgerai

Budget-aware Python SDK that wraps Anthropic and OpenAI clients — checks your agent's budget before every call and logs token costs automatically.

## Quickstart

```python
from ledgerai import LedgerAnthropic
client = LedgerAnthropic(ledger_url="http://localhost:8000", agent_id="my-agent")
response = client.messages.create(model="claude-sonnet-4-6", max_tokens=256, messages=[{"role": "user", "content": "Hello"}])
```

Install: `pip install ledgerai[anthropic]`  (or `ledgerai[openai]` / `ledgerai[all]`)

---

## How it works

Every call goes through two ledger hooks:

1. **Before** — `GET /api/v1/budgets/check?agent_id=<id>` — raises `BudgetExceededError` if `allowed` is `false`.
2. **After** — `POST /api/v1/costs/log` — records token counts and provider/model metadata.

The response object is passed through unchanged, so existing code requires no other modification.

## Configuration

| Parameter | Description |
|-----------|-------------|
| `ledger_url` | Base URL of the agent-cost-tracker API (e.g. `http://localhost:8000`) |
| `agent_id` | Identifier for this agent — used for budget lookup and cost attribution |

All other constructor arguments are forwarded to the underlying SDK client as-is.

## Errors

| Exception | When |
|-----------|------|
| `BudgetExceededError` | Budget check returns `allowed: false` — call never reaches the provider |
| `httpx.HTTPStatusError` | Ledger API returned a non-2xx status |
| `NotImplementedError` | `stream=True` was passed (streaming not yet supported) |

## OpenAI example

```python
from ledgerai import LedgerOpenAI, BudgetExceededError

client = LedgerOpenAI(ledger_url="http://localhost:8000", agent_id="my-agent")

try:
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello"}],
    )
    print(resp.choices[0].message.content)
except BudgetExceededError as e:
    print(f"Blocked — {e}  (remaining: ${e.daily_remaining_usd})")
```

## Notes

- Streaming (`stream=True`) raises `NotImplementedError` in this version.
- All other attributes and methods delegate transparently to the underlying SDK client.
