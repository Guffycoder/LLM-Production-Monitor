# 🔭 LLM Production Monitor & Observability Engine

An end-to-end LLM observability platform featuring **distributed trace logging, dual-mode evaluation (heuristics + LLM-as-judge), pre/post-call security guardrails, automated Slack alerting, and a real-time analytics dashboard**.

Inspired by production-scale observability patterns (similar to Langfuse and Arize Phoenix), this system acts as a high-performance gateway between users and LLMs. It monitors cost, latency, quality, and security risks in real-time, providing immediate visibility and alerting for production AI integrations.

[![status](https://img.shields.io/badge/status-active--demo-3ecf8e)](#)
[![python](https://img.shields.io/badge/python-3.10%2B-5b8cff)](#)
[![license](https://img.shields.io/badge/license-MIT-orange)](#)

---

## 📊 Live Dashboard Preview

#### Overview Analytics & Trace Logs
![Overview Dashboard](docs/screenshots/overview_dashboard.png)

#### RAG Hallucination & Groundedness Tab
![RAG Hallucinations Tab](docs/screenshots/hallucinations_tab.png)

---

## ⚡ Why This Project Matters (The Differentiator)

Generic LLM monitors ask a single, generic question: *"Was the AI's output good?"* This is a weak signal for **Retrieval-Augmented Generation (RAG)** systems. 

This platform implements a **decoupled diagnostic architecture** that splits evaluations into two distinct dimensions:

1. **Retrieval Quality Score:** Did the retrieval pipeline fetch the correct, relevant context chunks from the knowledge base?
2. **Groundedness Score:** Did the generator stay faithful *only* to the retrieved facts, or did it hallucinate claims not present in the context?

### The Operational Rationale:
* **High Groundedness + Low Retrieval (0/5):** The search engine fetched the wrong data, but the model remained faithful to it. **Fix:** Re-tune the vector database, chunking strategy, or embedding model.
* **Low Groundedness + High Retrieval (5/5):** The search engine fetched the correct context, but the model hallucinated anyway. **Fix:** Re-write your system prompt, adjust generation temperature, or upgrade the generation model.

*Collapsing these into a single quality metric makes debugging production failures impossible. This platform separates them to point engineers to the exact failure point.*

---

## 🛠️ Core Capabilities

* **🧠 Dual-Layer Evaluation Engine:** Evaluates responses instantly using rule-based metrics (degenerate repetitions, empty outputs, toxic words) and cascades to an LLM-as-judge (Claude Haiku 4.5) for semantic quality scoring. It falls back to robust local heuristics offline or on network failure.
* **🛡️ Pre/Post-Call Guardrails:**
  * **Credential Leakage Detector:** Checks inputs and outputs against high-severity patterns to prevent API keys (OpenAI, Anthropic) or PII (emails, cards, phones) from leaking into logs or facing users.
  * **Semantic Prompt Injection Classifier:** Uses a fast LLM-based binary classifier to catch override attempts (e.g., DAN mode, system prompt extraction, instructions disregard) that standard regex matching fails to intercept.
* **🚨 Real-Time Anomalous Alerting:** A background task runs an active window audit every 5 minutes. If quality scores fall below target thresholds or flagged rates exceed 30%, it automatically dispatches detailed security logs to a Slack webhook.
* **📈 Low-Latency Dashboard:** Single-page dashboard built with Vanilla JS and Chart.js that updates every 5 seconds to visualize trace counts, latency distributions, cost trends, blocked rates, and deep trace details.

---

## 🔌 API Architecture

```
User Prompt ──▶ [ Guardrail Scan ] ──▶ [ LLM Gen ] ──▶ [ Post-Call Eval ] ──▶ DB & Dashboard
                     │                                      │
               (Regex/LLM check)                     (LLM Groundedness)
                     ├──────────────────────────────────────┤
              (Block Malicious)                       (Flag low-score)
```

The FastAPI application exposes the following endpoints:

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/log` | `POST` | Primary ingestion gateway. Sequentially evaluates guardrails, runs evals, and logs the trace to the database. |
| `/traces` | `GET` | Fetches recent trace lists (with limit/pagination). |
| `/traces/flagged` | `GET` | Filters traces to show only requests flagged by guardrails. |
| `/traces/hallucinations` | `GET` | Retrieves traces flagged as ungrounded, including extracted hallucination claims. |
| `/metrics/summary` | `GET` | Serves dashboard analytics aggregates (avg latency, costs, blocked rates). |
| `/alerts/check` | `POST` | Manually triggers the anomaly checker loop. |
| `/health` | `GET` | Health check endpoint. |

---

## 🚀 Quickstart (No API Keys Required)

The monitor is fully functional offline and uses robust heuristics when no Anthropic key is configured.

### 1. Installation
Clone the repository and install the dependencies:
```bash
pip install -r requirements.txt
```

### 2. Start the Observatory Server
Launch the FastAPI server and UI dashboard (served on port `8000`):
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 3. Run Simulated Traffic
In a separate terminal window, execute the traffic generators to generate realistic telemetry:
```bash
# Generate general traces (safe requests, PII leaks, injections)
python scripts/demo_app.py

# Generate RAG-specific traces (grounded, hallucinated, bad-retrieval)
python scripts/demo_rag_app.py
```

### 4. Open the Dashboard
Open your browser to:
**[http://localhost:8000](http://localhost:8000)**

Explore the charts and trace filters, or test endpoints directly via the interactive Swagger docs at `/docs`.

---

## 📁 Repository Structure

```
llm-production-monitor/
├── app/
│   ├── main.py         # FastAPI application, routes, and background scheduler
│   ├── database.py     # SQLAlchemy configuration (SQLite by default, swap-ready for Postgres)
│   ├── schemas.py      # Pydantic data schemas
│   ├── guardrails.py    # Regex & LLM-based pre/post-call guardrails
│   ├── evals.py         # Quality evaluation logic (rule-based + LLM judge)
│   ├── rag_evals.py     # Decoupled RAG diagnostics (retrieval + groundedness check)
│   └── alerting.py      # Background alert loop & Slack integrations
├── dashboard/
│   └── index.html      # Analytics dashboard (Vanilla JS + Chart.js)
├── docs/
│   ├── screenshots/    # Dashboard images and media assets
│   └── walkthrough.md  # Detailed system walkthrough
├── scripts/
│   ├── demo_app.py      # General traffic generator script
│   └── demo_rag_app.py  # RAG telemetry generator script
├── requirements.txt
└── .env.example
```

---

## 🔧 Production Configuration

### Switching to PostgreSQL
To run in production, configure a PostgreSQL database URL in `app/database.py`:
```python
# app/database.py
DATABASE_URL = "postgresql://user:password@localhost:5432/llm_monitor"
```

### Enforcing Live LLM Evaluations
To use Claude Haiku as the live evaluation judge and active injection classifier:
1. Copy `.env.example` to `.env`
2. Set your `ANTHROPIC_API_KEY`
3. Configure `SLACK_WEBHOOK_URL` to receive alert notifications directly in your team's workspace channels.
