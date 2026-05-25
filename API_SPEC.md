# API Specification

## POST /api/v1/costs/log

Logs a single LLM call. Called by the SDK on every request.
Request:
{
"agent_id": "my-agent",
"provider": "anthropic",
"model": "claude-sonnet-4-6",
"input_tokens": 1200,
"output_tokens": 400,
"request_id": "uuid"
}
Response:
{
"cost_usd": 0.0096,
"daily_remaining_usd": 43.50,
"hard_stop": false
}

## GET /api/v1/costs/summary?agent_id=X&period=daily

Returns cost breakdown for dashboard.

## POST /api/v1/budgets/set

Creates or updates a budget for an agent.

## GET /api/v1/budgets/check?agent_id=X

Returns whether agent is allowed to proceed.
This is the hard stop endpoint. SDK calls this before every LLM call.
Response:
{
"allowed": true/false,
"reason": "Daily limit exceeded",
"daily_remaining_usd": 0.00
}
