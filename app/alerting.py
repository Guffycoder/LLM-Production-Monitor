"""
Alerting.

Checks recent traces on a rolling window and fires a Slack webhook
if the flagged/error rate crosses a threshold. If SLACK_WEBHOOK_URL
isn't set, alerts just print to console — the pipeline still works
end-to-end for local demo/grading purposes.
"""
import os
import datetime
import requests
from sqlalchemy.orm import Session
from app.database import Trace

FLAGGED_RATE_THRESHOLD = 0.3   # alert if >30% of recent traces are flagged
WINDOW_MINUTES = 15
MIN_TRACES_FOR_ALERT = 5       # don't alert on tiny sample sizes


def check_and_alert(db: Session) -> dict:
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=WINDOW_MINUTES)
    recent = db.query(Trace).filter(Trace.timestamp >= cutoff).all()

    if len(recent) < MIN_TRACES_FOR_ALERT:
        return {"alert_fired": False, "reason": "not enough recent traces to evaluate"}

    flagged = [t for t in recent if t.flagged]
    rate = len(flagged) / len(recent)

    if rate > FLAGGED_RATE_THRESHOLD:
        message = (
            f"🚨 LLM Monitor Alert: {rate:.0%} of the last {len(recent)} responses "
            f"(last {WINDOW_MINUTES} min) were flagged by guardrails/evals. "
            f"Threshold is {FLAGGED_RATE_THRESHOLD:.0%}."
        )
        _send_alert(message)
        return {"alert_fired": True, "flagged_rate": rate, "sample_size": len(recent), "message": message}

    return {"alert_fired": False, "flagged_rate": rate, "sample_size": len(recent)}


def _send_alert(message: str):
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print(f"[ALERT - no SLACK_WEBHOOK_URL configured] {message}")
        return
    try:
        requests.post(webhook_url, json={"text": message}, timeout=5)
    except Exception as e:
        print(f"[ALERT] Failed to send Slack alert: {e}")
