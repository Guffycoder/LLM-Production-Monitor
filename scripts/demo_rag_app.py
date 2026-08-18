"""
Demo RAG app — simulates a support bot answering questions using a small
knowledge base, wrapped by the monitor's RAG-specific eval pipeline.

Deliberately includes a mix of:
  - well-grounded answers (response matches retrieved context)
  - hallucinated answers (response invents details not in the retrieved context)
  - bad-retrieval cases (retriever fetches the wrong chunk entirely)

...so the dashboard has real examples of the groundedness detector catching
each failure mode. This is the part that's actually different from a generic
LLM monitor: it isn't just "was this a good response", it's "was this
response actually supported by what was retrieved."

Usage:
    python scripts/demo_rag_app.py
"""
import os
import time
import random
import requests

API_URL = os.environ.get("MONITOR_API_URL", "http://localhost:8000")

# A tiny fake knowledge base for a fictional SaaS product ("Apixor" style)
KNOWLEDGE_BASE = {
    "refund_policy": "Refunds are available within 14 days of purchase for annual plans, and 7 days for monthly plans. Refunds are processed to the original payment method within 5-7 business days.",
    "data_export": "You can export your data as CSV or JSON from Settings > Data Export. Exports include all workspace data except audit logs, which require an Enterprise plan.",
    "sso": "Single Sign-On (SSO) is available on the Business and Enterprise plans. We support SAML 2.0 and OAuth 2.0. Setup typically takes 15-30 minutes with your IT team.",
    "rate_limits": "The API allows 100 requests per minute on the Free plan, 1000 requests per minute on Pro, and custom limits on Enterprise.",
    "uptime": "Our platform maintains a 99.9% uptime SLA for Business and Enterprise customers, with status updates available at status.example.com.",
}

# (query, correct_kb_key, scenario) — scenario controls what kind of answer we generate
TEST_CASES = [
    ("What's your refund policy?", "refund_policy", "grounded"),
    ("How do I export my data?", "data_export", "grounded"),
    ("Do you support SSO?", "sso", "grounded"),
    ("What are the API rate limits?", "rate_limits", "hallucinated"),   # will invent extra fake details
    ("What's your uptime guarantee?", "uptime", "hallucinated"),        # will invent a fake number
    ("Can I get a refund after 30 days?", "refund_policy", "grounded"), # correctly says no per policy
    ("How does SSO setup work?", "sso", "bad_retrieval"),               # simulate retriever grabbing wrong chunk
]


def fake_retriever(query: str, correct_key: str, scenario: str) -> list[str]:
    """Simulates a retriever. In bad_retrieval scenario, deliberately returns
    an irrelevant chunk to test the retrieval_score metric."""
    if scenario == "bad_retrieval":
        wrong_key = random.choice([k for k in KNOWLEDGE_BASE if k != correct_key])
        return [KNOWLEDGE_BASE[wrong_key]]
    return [KNOWLEDGE_BASE[correct_key]]


def generate_response(query: str, retrieved_chunks: list[str], scenario: str) -> str:
    """
    Simulates the generation step. In a real system this would be an LLM call
    with the retrieved chunks in the prompt. Here we simulate the two failure
    modes directly so the demo reliably produces hallucination examples:
      - grounded:      answer strictly reflects the retrieved chunk
      - hallucinated:  answer adds specific invented details not in the chunk
      - bad_retrieval: answer is grounded in the (wrong) chunk it was given
    """
    context = retrieved_chunks[0]

    if scenario == "hallucinated":
        # Invent specific extra "facts" not present in the real KB entry
        fake_additions = {
            "What are the API rate limits?": " Enterprise customers also get a dedicated 50,000 requests/day burst allowance and priority routing through our EU datacenter.",
            "What's your uptime guarantee?": " We also offer a 15% service credit for every hour of downtime beyond the SLA, automatically applied to your next invoice.",
        }
        addition = fake_additions.get(query, " We also offer additional undocumented benefits for this tier.")
        return context + addition

    # grounded and bad_retrieval scenarios: just paraphrase the given context faithfully
    return f"Based on our policy: {context}"


def run_rag_demo_traffic():
    print(f"Sending {len(TEST_CASES)} RAG demo requests to {API_URL} ...\n")

    for i, (query, correct_key, scenario) in enumerate(TEST_CASES):
        retrieved_chunks = fake_retriever(query, correct_key, scenario)
        response_text = generate_response(query, retrieved_chunks, scenario)

        payload = {
            "model": "demo-rag-bot",
            "prompt": query,
            "response": response_text,
            "latency_ms": random.uniform(300, 1200),
            "tokens_in": len(query.split()),
            "tokens_out": len(response_text.split()),
            "cost_usd": 0.0001,
            "retrieved_chunks": retrieved_chunks,
        }

        r = requests.post(f"{API_URL}/log", json=payload, timeout=15)
        if r.status_code == 200:
            data = r.json()
            hallucination_flag = " 🚨 HALLUCINATION DETECTED" if data["is_hallucination"] else ""
            print(f"[{i+1}/{len(TEST_CASES)}] scenario={scenario:14s} "
                  f"groundedness={data['groundedness_score']}  "
                  f"retrieval={data['retrieval_score']}{hallucination_flag}")
            print(f"    query: {query}")
            if data.get("unsupported_claims") and data["unsupported_claims"] != "[]":
                print(f"    unsupported claims: {data['unsupported_claims']}")
            print()
        else:
            print(f"[{i+1}/{len(TEST_CASES)}] FAILED: {r.status_code} {r.text}")

        time.sleep(0.3)

    print("Done. Check the RAG-specific view:")
    print(f"  {API_URL}/traces/hallucinations")


if __name__ == "__main__":
    run_rag_demo_traffic()
