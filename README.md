# LLM Production Monitor

A working, end-to-end LLM observability platform: **tracing + LLM-as-judge evals + guardrails + Slack alerting + a live dashboard** — built from scratch to understand the patterns used by production tools like Langfuse, Arize Phoenix, and OpenLIT.

Inspired by monitoring challenges typically seen in SaaS integration-monitoring platforms.

![status](https://img.shields.io/badge/status-working%20demo-3ecf8e)
![python](https://img.shields.io/badge/python-3.10+-5b8cff)

## What it does

Every LLM call gets logged and automatically:
1. **Scanned for input risk** — prompt injection patterns, PII in the user's message
2. **Scored by an eval engine** — rule-based checks (length, banned words, degenerate output) + an LLM-as-judge score (1–5) via Claude Haiku
3. **Checked by output guardrails** — low-quality or rule-violating responses get flagged
4. **Tracked for cost & latency** — every trace records tokens, cost, and latency
5. **Monitored for anomalies** — a background job checks the flagged-rate every 5 minutes and fires a Slack alert if it crosses a threshold
6. **Visualized live** — a dashboard shows latency/eval trends and a filterable trace table, auto-refreshing every 5 seconds

## Architecture

```
Your LLM App                  Monitor API (FastAPI)
     │                              │
     │  POST /log(prompt, response) │
     ├─────────────────────────────▶│
     │                              ├─▶ guardrails.check_input()   (pre-call risk scan)
     │                              ├─▶ evals.run_full_eval()      (rule-based + LLM judge)
     │                              ├─▶ guardrails.check_output()  (flag low-quality output)
     │                              └─▶ SQLite (traces table)
     │                                     │
     │                              Dashboard (HTML/JS + Chart.js)
     │                                     │  GET /metrics/summary, /traces
     │                                     ▼
     │                              Live charts + trace table
     │
     │                        Background job (every 5 min)
     │                                     │
     │                              alerting.check_and_alert()
     │                                     │
     │                                     ▼
     │                              Slack webhook (if configured)
```

## Quickstart (zero API keys required)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the API + dashboard
uvicorn app.main:app --reload

# 3. In a second terminal, generate demo traffic
python scripts/demo_app.py

# 4. Open the dashboard
open http://localhost:8000
```

That's it — you'll see traces, eval scores, and a couple of flagged entries (the demo script deliberately sends a prompt-injection attempt, a message with PII, and some low-quality responses so the guardrails have something to catch).

## Running with real LLM calls + judge model

```bash
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY=sk-ant-...
export $(cat .env | xargs)   # or use python-dotenv / your shell's env loading

uvicorn app.main:app --reload
python scripts/demo_app.py
```

With a key set: the demo bot calls Claude Haiku for real responses, and the eval engine uses Claude Haiku as an actual LLM-as-judge instead of the offline heuristic.

## Enabling Slack alerts

```bash
# In .env:
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ
```

Create a webhook at https://api.slack.com/messaging/webhooks. Without one, alerts still fire — they just print to the server console instead.

## Project structure

```
llm-production-monitor/
├── app/
│   ├── main.py         # FastAPI app, endpoints, background scheduler
│   ├── database.py     # SQLAlchemy models (SQLite by default)
│   ├── schemas.py      # Pydantic request/response models
│   ├── evals.py        # Rule-based + LLM-as-judge evaluation
│   ├── guardrails.py   # Input/output guardrail checks
│   └── alerting.py     # Threshold checks + Slack webhook
├── dashboard/
│   └── index.html      # Single-page live dashboard (vanilla JS + Chart.js)
├── scripts/
│   └── demo_app.py     # Generates realistic demo traffic
├── requirements.txt
└── .env.example
```

## Swapping SQLite for Postgres

`app/database.py` has a single `DATABASE_URL` constant. For production:

```python
DATABASE_URL = "postgresql://user:password@localhost:5432/monitor"
```

(and `pip install psycopg2-binary`)

## API reference

| Endpoint | Method | Description |
|---|---|---|
| `/log` | POST | Log an LLM call — runs evals + guardrails automatically |
| `/traces` | GET | List recent traces |
| `/traces/flagged` | GET | List only flagged traces |
| `/metrics/summary` | GET | Aggregate stats (latency, cost, eval score, flagged rate) |
| `/alerts/check` | POST | Manually trigger the alert threshold check |
| `/health` | GET | Health check |

## What this demonstrates

- **Evals** — rule-based + LLM-as-judge scoring pipeline
- **Guardrails** — pre-call (input) and post-call (output) risk detection
- **Automation** — background scheduled job, Slack webhook integration
- **Observability** — cost/latency/quality tracked per-request, visualized live

## Why this exists

This is a deliberately smaller, from-scratch version of what tools like [Langfuse](https://github.com/langfuse/langfuse), [Arize Phoenix](https://github.com/Arize-ai/phoenix), and [OpenLIT](https://github.com/openlit/openlit) do at production scale — built to understand the underlying patterns (trace schema design, judge-model evals, guardrail thresholds, alerting loops) rather than to compete with them.
