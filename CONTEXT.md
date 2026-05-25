# Agent Cost Tracker — Product Context

## Problem

LLM teams have no visibility into where their API budget goes
and no way to hard-stop agents before they exceed spending limits.

## Solution

Real-time cost tracking per agent/request + hard budget enforcement
that pauses any agent the moment it hits its limit.

## MVP Scope (build only this)

1. Log every LLM API call with cost
2. Dashboard showing cost by agent, model, and time
3. Budget enforcement: hard stop when limit hit
4. Alerts: notify team when approaching threshold

## Out of Scope for MVP

- Cost optimization suggestions
- Multi-provider routing
- Team/SSO features
- Forecasting

## Target User

Solo developers and startup teams using Claude or OpenAI
to build agents, spending $500-5000/month with zero visibility.

## Tech Stack

- Backend: Python + FastAPI
- Database: PostgreSQL + SQLAlchemy
- Frontend: React (from Claude Design handoff)
- Auth: API keys (simple, no OAuth for MVP)
- Hosting: Railway or Render (cheapest path to prod)

## Competitors

- Helicone (acquired by Mintlify, roadmap uncertain)
- Langfuse (overkill, expensive)
- AI Cost Board (weak features, new)
- We beat them on: agent-specific budget enforcement
