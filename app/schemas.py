from pydantic import BaseModel
from typing import Optional
import datetime


class LogRequest(BaseModel):
    model: str = "unknown"
    prompt: str
    response: str
    latency_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


class TraceOut(BaseModel):
    id: int
    timestamp: datetime.datetime
    model: str
    prompt: str
    response: str
    latency_ms: float
    tokens_in: int
    tokens_out: int
    cost_usd: float
    eval_score: Optional[float] = None
    eval_reason: Optional[str] = None
    flagged: bool
    flag_reason: Optional[str] = None
    input_blocked: bool
    input_block_reason: Optional[str] = None

    class Config:
        from_attributes = True


class MetricsSummary(BaseModel):
    total_traces: int
    avg_latency_ms: float
    avg_cost_usd: float
    total_cost_usd: float
    avg_eval_score: Optional[float]
    flagged_count: int
    flagged_rate: float
    blocked_count: int
