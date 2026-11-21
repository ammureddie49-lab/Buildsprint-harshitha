# TraceMind v6 — Scoring-focused model readiness

This revision keeps the original CLI, SQLite memory, ACL, Studio, Qdrant, and unchanged organizer harness.

## High-priority fixes

- CLI default model flag now `auto`: enables remote OpenAI with an operator-provided key; `TRACEMIND_USE_LLM=0` always forces offline. Studio still has independent remote consent.
- Both OpenAI call paths now share model/key/pricing selection; unknown unpriced models fail closed.
- Model gateway preflights full input prompts (instruction + payload + overhead) against 4,000 ask / 8,000 brief budgets. `tiktoken` is optional; fallback is conservatively byte-bounded. SDK usage is counted even when the generated answer is rejected.
- At most one hybrid-model attempt per scored ask, preventing duplicated 4,000-token prompt requests.
- Broader model candidate triage for 15 synthetic unseen-style English/Hinglish updates, without precomputing any official answers.
- Derived hybrid memory version increment to allow reprocessing if upgrading a local database.
- `tools/audit_model_usage.py` summarizes per-ask/brief reported tokens/cost from a scorer run; the organizer's runner does not save ingest stdout.
- Updated docs, removed missing `HYBRID_V4_README.md` reference, preserved all public privacy checks.

## Verified

- 198 Python tests passing (11 additional synthetic model-readiness tests over prior 187).
- 85/85 offline public scorer with LLM=0 and vector=0.
- Public fixture privacy invariant audit PASS, 0 violations.

## Not claimed

- Live OpenAI model-on public score, spend, or hidden-day score. The organizer must configure a real authorized key and run the smoke/replay tests.
- Production-grade user authentication, universal physical vector erasure, or perfect hallucination elimination.
