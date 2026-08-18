"""
Database layer for the LLM Production Monitor.
Uses SQLite by default (zero setup) — swap DATABASE_URL for Postgres in production.
"""
import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:///./monitor.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Trace(Base):
    """One row per LLM call — the core event we monitor."""
    __tablename__ = "traces"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    model = Column(String, default="unknown")
    prompt = Column(Text)
    response = Column(Text)

    latency_ms = Column(Float, default=0.0)
    tokens_in = Column(Integer, default=0)
    tokens_out = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)

    # Eval results
    eval_score = Column(Float, nullable=True)       # 1-5, from judge model or rules
    eval_reason = Column(Text, nullable=True)

    # Guardrail results
    flagged = Column(Boolean, default=False)
    flag_reason = Column(Text, nullable=True)
    input_blocked = Column(Boolean, default=False)
    input_block_reason = Column(Text, nullable=True)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
