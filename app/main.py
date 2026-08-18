"""
LLM Production Monitor — main API.

Endpoints:
  POST /log              -> log an LLM call, runs evals + guardrails automatically
  GET  /traces           -> list recent traces (filterable)
  GET  /traces/flagged   -> just the flagged ones
  GET  /metrics/summary  -> aggregate stats for the dashboard
  POST /alerts/check     -> manually trigger the alert threshold check
"""
import time
from fastapi import FastAPI, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func
from apscheduler.schedulers.background import BackgroundScheduler

import json
from app.database import init_db, get_db, Trace, SessionLocal
from app.schemas import LogRequest, TraceOut, MetricsSummary
from app import evals, guardrails, alerting, rag_evals

app = FastAPI(title="LLM Production Monitor", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()
    scheduler = BackgroundScheduler()
    scheduler.add_job(_scheduled_alert_check, "interval", minutes=5)
    scheduler.start()


def _scheduled_alert_check():
    db = SessionLocal()
    try:
        alerting.check_and_alert(db)
    finally:
        db.close()


@app.post("/log", response_model=TraceOut)
def log_call(payload: LogRequest, db: Session = Depends(get_db)):
    """
    Core ingestion endpoint. In a real integration this is what you'd call
    right after every LLM API call in your application (see scripts/demo_app.py).
    """
    # 1. Pre-call guardrail (in a live system you'd run this BEFORE calling the LLM;
    #    here we check the logged prompt retroactively since we're wrapping calls that already happened)
    input_blocked, input_block_reason = guardrails.check_input(payload.prompt)

    # 2. Eval the response
    eval_result = evals.run_full_eval(payload.prompt, payload.response)

    # 3. Post-call guardrail
    flagged, flag_reason = guardrails.check_output(
        payload.response, eval_result["eval_score"], eval_result["rule_issues"]
    )

    # 4. RAG-specific evals — only run when the caller passed retrieved_chunks.
    #    This is what a generic LLM monitor doesn't do: score groundedness
    #    against the actual retrieved context, not just "is this a good response?"
    rag_result = None
    if payload.retrieved_chunks:
        rag_result = rag_evals.run_rag_eval(payload.prompt, payload.response, payload.retrieved_chunks)
        if rag_result["is_hallucination"] and not flagged:
            flagged = True
            flag_reason = f"hallucination: groundedness={rag_result['groundedness_score']}, unsupported claims found"

    trace = Trace(
        model=payload.model,
        prompt=payload.prompt,
        response=payload.response,
        latency_ms=payload.latency_ms,
        tokens_in=payload.tokens_in,
        tokens_out=payload.tokens_out,
        cost_usd=payload.cost_usd,
        eval_score=eval_result["eval_score"],
        eval_reason=eval_result["eval_reason"],
        flagged=flagged,
        flag_reason=flag_reason,
        input_blocked=input_blocked,
        input_block_reason=input_block_reason,
        retrieved_context="\n---\n".join(payload.retrieved_chunks) if payload.retrieved_chunks else None,
        retrieval_score=rag_result["retrieval_score"] if rag_result else None,
        groundedness_score=rag_result["groundedness_score"] if rag_result else None,
        unsupported_claims=json.dumps(rag_result["unsupported_claims"]) if rag_result else None,
        is_hallucination=rag_result["is_hallucination"] if rag_result else False,
    )
    db.add(trace)
    db.commit()
    db.refresh(trace)
    return trace


@app.get("/traces", response_model=list[TraceOut])
def list_traces(limit: int = Query(100, le=1000), db: Session = Depends(get_db)):
    return db.query(Trace).order_by(Trace.timestamp.desc()).limit(limit).all()


@app.get("/traces/flagged", response_model=list[TraceOut])
def list_flagged(limit: int = Query(100, le=1000), db: Session = Depends(get_db)):
    return (
        db.query(Trace)
        .filter(Trace.flagged == True)  # noqa: E712
        .order_by(Trace.timestamp.desc())
        .limit(limit)
        .all()
    )


@app.get("/traces/hallucinations", response_model=list[TraceOut])
def list_hallucinations(limit: int = Query(100, le=1000), db: Session = Depends(get_db)):
    """RAG-specific view: responses flagged as ungrounded/hallucinated, separate
    from generic quality flags — this is the distinguishing feature of this monitor."""
    return (
        db.query(Trace)
        .filter(Trace.is_hallucination == True)  # noqa: E712
        .order_by(Trace.timestamp.desc())
        .limit(limit)
        .all()
    )


@app.get("/metrics/summary", response_model=MetricsSummary)
def metrics_summary(db: Session = Depends(get_db)):
    total = db.query(func.count(Trace.id)).scalar() or 0
    if total == 0:
        return MetricsSummary(
            total_traces=0, avg_latency_ms=0, avg_cost_usd=0, total_cost_usd=0,
            avg_eval_score=None, flagged_count=0, flagged_rate=0, blocked_count=0,
        )

    avg_latency = db.query(func.avg(Trace.latency_ms)).scalar() or 0
    avg_cost = db.query(func.avg(Trace.cost_usd)).scalar() or 0
    total_cost = db.query(func.sum(Trace.cost_usd)).scalar() or 0
    avg_eval = db.query(func.avg(Trace.eval_score)).scalar()
    flagged_count = db.query(func.count(Trace.id)).filter(Trace.flagged == True).scalar() or 0  # noqa: E712
    blocked_count = db.query(func.count(Trace.id)).filter(Trace.input_blocked == True).scalar() or 0  # noqa: E712

    return MetricsSummary(
        total_traces=total,
        avg_latency_ms=round(avg_latency, 2),
        avg_cost_usd=round(avg_cost, 6),
        total_cost_usd=round(total_cost, 4),
        avg_eval_score=round(avg_eval, 2) if avg_eval else None,
        flagged_count=flagged_count,
        flagged_rate=round(flagged_count / total, 3),
        blocked_count=blocked_count,
    )


@app.post("/alerts/check")
def trigger_alert_check(db: Session = Depends(get_db)):
    return alerting.check_and_alert(db)


@app.get("/health")
def health():
    return {"status": "ok", "time": time.time()}


# Serve the dashboard at /
app.mount("/", StaticFiles(directory="dashboard", html=True), name="dashboard")
