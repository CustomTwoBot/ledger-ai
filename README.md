# LedgerAI

Cost tracking and budget enforcement for LLM-powered agents.

LedgerAI is a FastAPI service backed by PostgreSQL. Agents log each LLM call (provider, model, token counts), the server prices it, attributes it to the calling user, and enforces per-agent daily and monthly budgets. A Python SDK wraps the Anthropic and OpenAI clients so that budget checks and cost logging happen automatically around each request, and a web dashboard shows spend by agent, model, and time.

**Live demo:** https://agent-cost-tracker-production.up.railway.app/dashboard

## Core features

- **Per-call cost logging** – `POST /api/v1/costs/log` prices a call from its token counts using a built-in rate table and stores it. Logging is idempotent on `request_id`.
- **Per-agent budgets** – daily and/or monthly USD limits per `agent_id`, with optional hard stop. Spend counters reset automatically at the start of each day and month.
- **Pre-call budget check** – `GET /api/v1/budgets/check` returns whether an agent may proceed, its remaining daily budget, and a `near_limit` (≥ 80%) or `hard_stop` warning.
- **Threshold alerts** – when logged spend crosses `ALERT_THRESHOLD_PCT` (default 80%) or reaches 100% of a budget, an alert record is written to the `alerts` table (deduplicated per agent per hour). Alerts are stored but not yet exposed through the API.
- **Spend reporting** – summary totals with per-model and per-agent breakdowns, a daily time series, and a recent-calls feed, all scoped to the authenticated user.
- **API-key authentication** – every data endpoint requires an `X-API-Key` header. Keys belong to a user account; all of a user's keys share the same data, and one user can never read another's.
- **Python SDK** – drop-in `LedgerAnthropic` and `LedgerOpenAI` clients that check the budget before each call, raise `BudgetExceededError` when blocked, and log usage afterwards.
- **Dashboard** – single-page web UI (Overview, Agents, Trends, Recent, Settings tabs) served by the API, with an email sign-up gate that issues an API key and a 30-second auto-refresh.

## Architecture

```
  Agent code ── ledgerai SDK ──►  FastAPI app  ◄── Dashboard (browser)
  (Anthropic / OpenAI clients)    (app/)            served at /dashboard
                                     │
                              SQLAlchemy 2.0
                                     │
                         PostgreSQL (schema managed by Alembic)
```

| Layer | Technology |
|---|---|
| API | Python, FastAPI, Pydantic / pydantic-settings, Uvicorn |
| Database | PostgreSQL, SQLAlchemy 2.0, Alembic migrations |
| Auth & limits | API keys (`X-API-Key`), slowapi rate limiting |
| Frontend | Prebuilt single-file React dashboard (`frontend/Dashboard.html`) |
| SDK | Python package `ledgerai` (httpx; optional `anthropic` / `openai` extras) |
| Hosting | Railway (`Procfile`; migrations run as a pre-deploy step) |

**Data model** (`app/models.py`):

- `users`: one row per account (email, plus a currently unused `github_id` column).
- `api_keys`: credentials, each owned by a user (`user_id`), with an `is_active` flag.
- `costs`: one row per logged LLM call, owned by a `user_id`. `owner_key` records which key logged it.
- `budgets`: per-agent limits and running spend, unique on `(agent_id, user_id)`.
- `alerts`: `approaching_limit` / `hard_stop` records written during cost logging.

**Security-related behaviour** in the code: security headers and a Content-Security-Policy on every response (`app/main.py`), the interactive API docs pages (`/docs`, `/redoc`) disabled, rate limits of 100 requests/minute per API key on data endpoints and 10/hour per IP on `signup` and `create-key`.

## Repository structure

```
.
├── app/
│   ├── main.py            # FastAPI app, middleware, static routes
│   ├── auth.py            # API-key dependency and rate limiter
│   ├── config.py          # Settings (DATABASE_URL, ALERT_THRESHOLD_PCT)
│   ├── database.py        # SQLAlchemy engine and session
│   ├── models.py          # ORM models
│   ├── schemas.py         # Request/response models
│   ├── pricing.py         # Per-model token prices and cost calculation
│   └── routers/           # auth, costs, budgets, dashboard endpoints
├── alembic/               # Migration environment and versions/
├── frontend/              # Dashboard.html, privacy.html
├── sdk/python/            # ledgerai SDK package, SDK README, smoke tests
├── API_SPEC.md            # Endpoint notes
├── DATABASE_SCHEMA.md     # Original schema notes
├── CONTEXT.md             # Product context and MVP scope
├── alembic.ini
├── Procfile
└── requirements.txt
```

## Local setup

Requirements: Python 3 (the code has been run on 3.12 and 3.14) and a local PostgreSQL server.

```bash
git clone https://github.com/CustomTwoBot/ledger-ai.git
cd ledger-ai

python -m pip install -r requirements.txt

# Create the database and point the app at it
createdb agent_cost_tracker
cp .env.example .env          # edit DATABASE_URL if your credentials differ

# Build the schema, then start the server
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
```

The app runs at `http://127.0.0.1:8000`; the dashboard is at `/dashboard` and a health check at `/health`.

Configuration (environment variables or `.env`):

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/agent_cost_tracker` | PostgreSQL connection string |
| `ALERT_THRESHOLD_PCT` | `80` | Spend percentage that triggers an `approaching_limit` alert |

Get an API key from your local server:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com"}'
```

## SDK usage

Install the SDK from this repository:

```bash
pip install -e "sdk/python[anthropic]"    # or [openai] / [all]
```

```python
from ledgerai import LedgerAnthropic, BudgetExceededError

client = LedgerAnthropic(
    ledger_url="http://127.0.0.1:8000",
    agent_id="research-agent",
    api_key="<your LedgerAI API key>",
)

try:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[{"role": "user", "content": "Hello"}],
    )
except BudgetExceededError as e:
    print(f"Blocked: {e.reason} (remaining today: {e.daily_remaining_usd})")
```

`LedgerOpenAI` works the same way around `client.chat.completions.create(...)`. Each call runs `GET /budgets/check` first and `POST /costs/log` after; the provider response is returned unchanged, and other client attributes pass through to the underlying SDK. `LedgerAnthropic(..., mock=True)` returns a canned response without calling Anthropic, for testing. See [`sdk/python/README.md`](sdk/python/README.md) for details.

## API overview

All `/api/v1` endpoints except `signup` require the `X-API-Key` header. Responses are JSON.

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/auth/signup` | Create an account from an email; returns an API key |
| `GET` | `/api/v1/auth/me` | Details of the calling key and its user |
| `POST` | `/api/v1/auth/create-key` | Issue an additional key for the calling user |
| `POST` | `/api/v1/costs/log` | Log one LLM call; returns `cost_usd`, `daily_remaining_usd`, `hard_stop` |
| `GET` | `/api/v1/costs/summary` | Totals plus by-model / by-agent breakdowns (`period`=`daily`\|`monthly`\|`all`, optional `agent_id`) |
| `GET` | `/api/v1/costs/timeseries` | Daily cost points (`days`, 1–365) |
| `GET` | `/api/v1/costs/recent` | Most recent calls (`limit`, 1–100) |
| `POST` | `/api/v1/budgets/set` | Create or update an agent's limits and hard-stop flag |
| `GET` | `/api/v1/budgets/check` | Whether `agent_id` may proceed, with remaining budget and warning |
| `GET` | `/api/v1/dashboard/stats` | Summary, time series and recent calls in one response |
| `GET` | `/health` | Liveness check |

Example: log a call.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/costs/log \
  -H "X-API-Key: $LEDGERAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "research-agent", "provider": "anthropic", "model": "claude-sonnet-4-6",
       "input_tokens": 1200, "output_tokens": 400, "request_id": "req-001"}'
```

Supported models for pricing (`app/pricing.py`): `gpt-4o`, `gpt-3.5-turbo`, `claude-sonnet-4-6`, `claude-haiku-4-5`. Logging any other model returns `422`.

## Current limitations

- Streaming calls (`stream=True`) are not supported by the SDK.
- Pricing covers only the four models listed above.
- Budget spend counters are stored with two decimal places, so very small per-call costs are rounded.
- Sign-up is email-only (no verification), and there is no key revocation endpoint yet.
- Alerts are recorded in the database but not yet delivered or exposed through the API.
- If the dashboard cannot load data (e.g. missing or invalid key), it falls back to built-in demo data.
- There is no automated test suite for the API yet; `sdk/python/test_sdk.py` contains SDK smoke tests that run against a local server.
