# Database Schema

## costs

- id: UUID (primary key)
- agent_id: string (which agent made the call)
- provider: string (openai, anthropic)
- model: string (gpt-4, claude-sonnet, etc)
- input_tokens: integer
- output_tokens: integer
- cost_usd: decimal(10,6)
- timestamp: datetime
- request_id: string (idempotency)

## budgets

- id: UUID (primary key)
- agent_id: string (unique)
- daily_limit_usd: decimal(10,2)
- monthly_limit_usd: decimal(10,2)
- daily_spent_usd: decimal(10,2)
- monthly_spent_usd: decimal(10,2)
- is_hard_stop_enabled: boolean
- updated_at: datetime

## alerts

- id: UUID (primary key)
- agent_id: string
- alert_type: enum (approaching_limit, hard_stop, spike)
- threshold_pct: integer (e.g. 80)
- message: text
- sent_at: datetime

## Cost Calculation Rules

- GPT-4o: input $2.50/1M, output $10.00/1M
- GPT-3.5-turbo: input $0.50/1M, output $1.50/1M
- Claude Sonnet 4.6: input $3.00/1M, output $15.00/1M
- Claude Haiku 4.5: input $0.80/1M, output $4.00/1M
