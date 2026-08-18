"""
RAG-specific evals — this is the differentiator.

Generic LLM monitors (Langfuse, Phoenix, etc.) score "is this response good?"
This module answers a narrower, RAG-specific question: "is this response
actually SUPPORTED by what was retrieved, or is the model hallucinating on
top of the context it was given?"

Two scores:
  1. retrieval_relevance  -> did the retriever fetch chunks relevant to the query?
                             (a bad retrieval means the model never had a chance)
  2. groundedness         -> does the response's content actually appear in /
                             follow from the retrieved chunks?
                             (low groundedness = hallucination, even if the
                             retrieval itself was fine)

These are reported SEPARATELY on purpose. A response can be well-written and
still fail groundedness — that distinction is exactly what a generic eval
("is this a good response?") misses, and why RAG systems need their own
monitoring layer instead of reusing generic LLM evals.
"""
import os
import re
import json


def _stem(word: str) -> str:
    """Extremely light stemming so 'refund'/'refunds', 'export'/'exports' etc.
    match. This is a heuristic, not a real stemmer (e.g. Porter) — good enough
    to reduce trivial plural mismatches without pulling in an NLP dependency."""
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {_stem(w) for w in words}


def _sentence_split(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s for s in sentences if len(s.strip()) > 0]


def retrieval_relevance_score(query: str, retrieved_chunks: list[str]) -> tuple[float, str]:
    """
    Heuristic: how much lexical overlap exists between the query and what was
    retrieved. Low overlap suggests the retriever fetched the wrong chunks —
    a failure mode entirely separate from generation quality, and one that
    generic LLM evals never catch because they only look at the final answer.
    """
    if not retrieved_chunks:
        return 0.0, "no chunks retrieved"

    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.0, "empty query"

    combined = " ".join(retrieved_chunks)
    chunk_tokens = _tokenize(combined)

    overlap = query_tokens & chunk_tokens
    score = len(overlap) / len(query_tokens)

    reason = f"{len(overlap)}/{len(query_tokens)} query terms found in retrieved context"
    return round(min(score, 1.0) * 5, 2), reason  # scale to 1-5 like other evals


def groundedness_score_heuristic(response: str, retrieved_chunks: list[str]) -> tuple[float, list[str]]:
    """
    No-API-key fallback: for each sentence in the response, check whether its
    key terms appear anywhere in the retrieved context. Sentences with low
    overlap are flagged as "unsupported" — a rough but zero-dependency proxy
    for hallucination detection.
    """
    if not response.strip():
        return 0.0, ["empty response"]

    context_tokens = _tokenize(" ".join(retrieved_chunks))
    sentences = _sentence_split(response)
    if not sentences:
        return 0.0, ["no sentences to evaluate"]

    unsupported = []
    supported_count = 0

    for sentence in sentences:
        sent_tokens = _tokenize(sentence)
        # ignore very short/filler sentences (greetings, transitions)
        meaningful_tokens = {t for t in sent_tokens if len(t) > 3}
        if not meaningful_tokens:
            supported_count += 1
            continue

        overlap = meaningful_tokens & context_tokens
        coverage = len(overlap) / len(meaningful_tokens)

        if coverage >= 0.4:
            supported_count += 1
        else:
            unsupported.append(sentence.strip())

    score = round((supported_count / len(sentences)) * 5, 2)
    return score, unsupported


def groundedness_score_llm_judge(query: str, response: str, retrieved_chunks: list[str]) -> tuple[float, list[str], str]:
    """
    Uses an LLM judge WITH the retrieved context visible, to check whether
    each claim in the response is actually supported by it. This is more
    accurate than the lexical heuristic above because it catches paraphrased
    hallucinations (same meaning, different words) that word-overlap misses.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        score, unsupported = groundedness_score_heuristic(response, retrieved_chunks)
        return score, unsupported, "heuristic (no judge model configured)"

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        context_block = "\n---\n".join(retrieved_chunks)
        judge_prompt = f"""You are checking whether an AI's response is grounded in the retrieved context it was given, or whether it hallucinated claims not supported by that context.

RETRIEVED CONTEXT:
{context_block}

USER QUERY: {query}

AI RESPONSE: {response}

Identify any specific claims in the AI RESPONSE that are NOT supported by the RETRIEVED CONTEXT.
Respond ONLY with valid JSON:
{{"groundedness_score": <1-5, where 5 = fully grounded, 1 = mostly hallucinated>, "unsupported_claims": ["<claim 1>", "<claim 2>"]}}
If everything is grounded, unsupported_claims should be an empty list."""

        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": judge_prompt}],
        )
        text = msg.content[0].text.strip()
        text = re.sub(r"^```json|```$", "", text).strip()
        data = json.loads(text)
        return float(data["groundedness_score"]), data.get("unsupported_claims", []), "llm-judge"
    except Exception as e:
        score, unsupported = groundedness_score_heuristic(response, retrieved_chunks)
        return score, unsupported, f"heuristic (judge call failed: {e})"


def run_rag_eval(query: str, response: str, retrieved_chunks: list[str]) -> dict:
    """Combines retrieval + groundedness scoring into one result for the API layer."""
    retrieval_score, retrieval_reason = retrieval_relevance_score(query, retrieved_chunks)
    groundedness, unsupported_claims, method = groundedness_score_llm_judge(query, response, retrieved_chunks)

    is_hallucination = groundedness < 3.0 and len(unsupported_claims) > 0

    return {
        "retrieval_score": retrieval_score,
        "retrieval_reason": retrieval_reason,
        "groundedness_score": groundedness,
        "unsupported_claims": unsupported_claims,
        "groundedness_method": method,
        "is_hallucination": is_hallucination,
    }
