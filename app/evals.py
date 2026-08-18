"""
Eval engine.

Two layers, same pattern used by Langfuse / Arize Phoenix / Opik:
  1. Rule-based evals  -> fast, free, deterministic (length, banned words, format)
  2. LLM-as-judge eval -> a cheap/fast model scores quality 1-5

If ANTHROPIC_API_KEY is not set, the judge falls back to a heuristic so the
whole pipeline still runs end-to-end without any external dependency.
"""
import os
import re
import json

BANNED_WORDS = ["idiot", "stupid", "kill yourself", "hate you"]
MAX_REASONABLE_LEN = 4000


def rule_based_eval(response: str) -> list[str]:
    """Returns a list of rule violations found in the response. Empty list = clean."""
    issues = []

    if not response or not response.strip():
        issues.append("empty_response")
        return issues

    if len(response) > MAX_REASONABLE_LEN:
        issues.append("response_too_long")

    lower = response.lower()
    for word in BANNED_WORDS:
        if word in lower:
            issues.append(f"banned_word:{word}")

    # crude repeated-token check, catches degenerate/looping generations
    words = lower.split()
    if len(words) > 20:
        most_common = max(set(words), key=words.count)
        if words.count(most_common) / len(words) > 0.3:
            issues.append("degenerate_repetition")

    return issues


def llm_judge_eval(prompt: str, response: str) -> tuple[float, str]:
    """
    Scores a response 1-5 using a judge model.
    Falls back to a lightweight heuristic if no API key is configured,
    so the project runs fully offline for grading/demo purposes.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        return _heuristic_score(prompt, response)

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        judge_prompt = f"""You are grading an AI assistant's response for quality.

User prompt: {prompt}
Assistant response: {response}

Score the response from 1-5 on overall quality (relevance, correctness, clarity).
Respond ONLY with valid JSON: {{"score": <int 1-5>, "reason": "<one short sentence>"}}"""

        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{"role": "user", "content": judge_prompt}],
        )
        text = msg.content[0].text.strip()
        text = re.sub(r"^```json|```$", "", text).strip()
        data = json.loads(text)
        return float(data["score"]), data.get("reason", "")
    except Exception as e:
        # Never let eval failures take down the logging pipeline
        fallback_score, fallback_reason = _heuristic_score(prompt, response)
        return fallback_score, f"{fallback_reason} (judge call failed: {e})"


def _heuristic_score(prompt: str, response: str) -> tuple[float, str]:
    """No-API-key fallback: rough heuristic so the pipeline is still demoable."""
    issues = rule_based_eval(response)
    if issues:
        return 1.0, f"rule violations: {', '.join(issues)}"
    if len(response.strip()) < 10:
        return 2.0, "response very short, likely low quality"
    return 4.0, "no rule violations detected (heuristic score, no judge model configured)"


def run_full_eval(prompt: str, response: str) -> dict:
    """Combines rule-based + judge eval into a single result used by the API layer."""
    rule_issues = rule_based_eval(response)
    score, reason = llm_judge_eval(prompt, response)

    if rule_issues:
        # Rule violations always cap the score, regardless of what the judge said
        score = min(score, 2.0)
        reason = f"{reason} | rule issues: {', '.join(rule_issues)}"

    return {"eval_score": score, "eval_reason": reason, "rule_issues": rule_issues}
