"""
Guardrails.

Pre-call:  scan the INPUT before it ever reaches the model
           (prompt injection patterns, obvious PII)
Post-call: scan the OUTPUT + eval score, decide whether to flag/block it
           before it reaches the end user
"""
import re

PII_PATTERNS = {
    "email": re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
    "phone": re.compile(r"\b\d{10}\b|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
}

INJECTION_PATTERNS = [
    r"ignore (all|any|previous|the above) instructions",
    r"disregard (all|any|previous) (instructions|rules)",
    r"you are now (in )?(dan|developer) mode",
    r"reveal your (system prompt|instructions)",
    r"pretend (you have no|to have no) (restrictions|guardrails|filters)",
]

EVAL_SCORE_THRESHOLD = 2.5  # below this, output gets flagged


def check_input(prompt: str) -> tuple[bool, str | None]:
    """Returns (blocked: bool, reason: str | None). Runs BEFORE the LLM call."""
    lower = prompt.lower()

    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, lower):
            return True, f"possible_prompt_injection:{pattern}"

    for pii_type, pattern in PII_PATTERNS.items():
        if pattern.search(prompt):
            return True, f"pii_detected:{pii_type}"

    return False, None


def check_output(response: str, eval_score: float, rule_issues: list[str]) -> tuple[bool, str | None]:
    """Returns (flagged: bool, reason: str | None). Runs AFTER the LLM call + eval."""
    if rule_issues:
        return True, f"rule_violation: {', '.join(rule_issues)}"

    if eval_score is not None and eval_score < EVAL_SCORE_THRESHOLD:
        return True, f"low_eval_score:{eval_score}"

    for pii_type, pattern in PII_PATTERNS.items():
        if pattern.search(response):
            return True, f"pii_in_output:{pii_type}"

    return False, None


FALLBACK_MESSAGE = "This response was withheld by an automated quality guardrail. Please rephrase your request."
