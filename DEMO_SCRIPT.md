# TraceMind — 5–7 minute final demonstration plan

**Use the complete local verification bundle with supplied public fixtures.** The video must be recorded and narrated by the candidate; this is a script, not a claimed video deliverable.

- **0:00–0:45 Problem:** Explain why a workplace assistant must handle changing owners, timestamps, corrections, human-language commitments, source citations and employee privacy.
- **0:45–1:30 Architecture:** Show SQLite source-of-truth, temporal + hybrid facts, FTS5/BM25, optional local MiniLM/Qdrant, optional OpenAI SDK, Python access gate and FastAPI/React Studio. Explain the split between semantic retrieval and factual authority.
- **1:30–2:35 Stateful replay:** Run `ingest --day 1`, then `ingest --day 2`. Show a verified dated task/ownership answer with source ID. Explain per-day feedback ingestion and historical cutoff.
- **2:35–3:35 Brief and feedback:** Show a public meeting brief with changed tasks, commitments, three suggested sources and one question. Contrast an irrelevant newsletter with a real blocker. Demonstrate person-scoped preferences or explicit negative verdict from the public feedback file.
- **3:35–4:25 Honest withholding:** Show `nothing_new`, an ambiguous Friday task clarification or a source-grounded abstention rather than an invented fact.
- **4:25–5:25 Privacy:** Show a private travel note for its author, demonstrate refusal/inaccessibility for a coworker, then use `forget` and show the note disappears for the requester. Mention that shared-team forget is requester-scoped, not physical deletion from every shared index.
- **5:25–6:20 Engineering evidence:** Show `python -m unittest discover -s tests -q`, `tools/agent_privacy_audit.py`, and the official 85/85 public offline scorer. If the local Qdrant smoke succeeds, demonstrate Vector DB mode. Do not claim a real OpenAI call if you have no key.
- **6:20–7:00 Limitations and judgement:** No LangGraph; bounded model interpretation; source checks; localhost-only Studio; hidden days, real Qdrant and paid API not verified in the package environment. Describe one independent adversarial test and the narrow code fix it motivated.

## Likely 30-minute live coding changes

- Add a new allowed Hinglish commitment phrase, with a direct test that requests vs promises are distinguished.
- Add a feedback preference, then test that it applies to one person and only after their feedback day.
- Harden a new prompt-injection phrasing, prove the original record is still treated as data, not an instruction.
- Add a new privacy test for a different organization or unauthorized source ID.

For each change: write a failing test, implement the smallest fix, rerun the focused test, all Python tests, then the official five-day scorer. **Do not modify organizer answer files or score logic.**
