# TraceMind final privacy and memory security audit

This is an implementation/security review of the uploaded final-candidate code, not a certification or a claim of 100% attack resistance.

## Threat model and access guarantees

The official grader supplies `--person` as the trusted identity. The core's `Engine.allowed(person, at)` checks `org`, visibility (`team`, `private` author only, `restricted` readers only), observation time and per-person topic/source forgetting before evidence reaches answer generation. Source-linked derived facts are joined against this currently allowed set rather than treated as an independently authorized memory database. Fact outputs cite source record IDs. A user cannot get the raw original message from another organization through the intended engine API.

The Studio's UI persona picker is **not authentication**. To avoid accidentally exposing this impersonation interface, the API rejects non-loopback ASGI clients by default and the launcher binds to `127.0.0.1`. A production deployment needs proper identity verification and authorization rather than trusting a user-selected persona.

## LLM-specific restrictions

Optional OpenAI ingestion selects only team-visible messages and partitions requests by organization/client. Private/restricted text does not go into these prompts. Messages inside workplace sources remain untrusted content. Model-proposed fact claims must identify IDs from the actual submitted batch, have text anchors in the original source and pass conservative checks for negated owners, unsupported names, numeric claims and missing time expressions. Model-enabled CLI branches can fall back to local rules. An explicit `TRACEMIND_USE_LLM=0` prevents remote model calls even if a key is present; by default, a supplied key enables the CLI (auto mode). The Studio still requires a separate explicit remote-consent setting. The tool-calling Studio does not execute external communication; proposals require local human approval.

Prompt-injection defenses reduce risk but **do not guarantee semantic safety**. A correctly cited record may still be misinterpreted, and a sophisticated adversary may bypass keyword-based sanitization. The host application remains responsible for permission/tool boundaries, not the model.

## Vector database

Qdrant Local is a persisted retrieval index for team-only records, containing a vector and minimal non-text payload. Every request independently limits searches to currently allowed source IDs and revalidates returned hits. Qdrant persistence is **not** a universal erasure mechanism: user-scoped forgetting prevents retrieval for that user, but shared vectors may remain for other authorized users. Full legal deletion would also need physical vector lifecycle management, backups/retention controls, and authenticated identities. Qdrant runtime itself was not verified here because its package was unavailable; contract tests were run with a mock client.

## Verified audit results

- Official public days 1–5: 85/85 points, privacy 10/10, 0 leak flags. Actual 2026-11-21 replay after the code changes.
- Python suite: 198/198 tests (includes new cross-org, stale-feedback, fail-closed source, model opt-out, model injection, memory-backlog and bounded-outage tests).
- `python tools/agent_privacy_audit.py`: PASS, 165 persona/day scopes, 113,095 authorized record-scope checks, 149,585 forbidden record-scope checks, 178 brief source references and 60 ask/matched source references; 0 authorization/citation violations. These are repeated scope-record assertions, **not** 262,680 distinct workplace records.
- The offline checker does not use answer-key data and does not call OpenAI or Qdrant. It is not proof that private data cannot be extracted through an untested integration or a compromised local machine.

## Known limits / recommended evaluator tests

1. Real OpenAI key: run the synthetic SDK smoke test; then replay the public days with model enabled and compare both scores and token cost. No paid SDK calls were made during packaging.
2. Real local vector store: run both Qdrant smoke tests and verify vector re-use across a process restart.
3. Model grounding: adversarial prompts with fabricated numbers, forged source IDs, prompt injections, paraphrased contradictions and mixed-org records; semantic entailment remains an open problem.
4. Forgetting: remember the difference between user-scoped suppression and physical deletion across shared source copies/vector stores.
5. Production deployment: do not expose Studio beyond loopback without real user authentication, key custody, audit logging and rate limiting.
6. Hidden-day adaptability: model extraction has a bounded call budget and a retry backlog; there is no measured hidden-day score or guarantee of improving every subsequent day.

No `.env`, real API key, local SQLite state or cached vector DB should be committed. The judge-source ZIP intentionally excludes organizer public answer keys and data fixtures.

## Model-ready release note

The CLI now defaults to `TRACEMIND_USE_LLM=auto`. Supplying a key authorizes transmission of eligible team-visible model candidate text; use `TRACEMIND_USE_LLM=0` if no external transmission is permitted. A configured key alone does not make Studio remote tools available. The new request-level guard counts instructions and evidence before sending to OpenAI. If the server reports more than the allowed request limit, the model output is rejected, but billed token usage is still metered. Test limits are per request; one model attempt is allowed per scored question.
