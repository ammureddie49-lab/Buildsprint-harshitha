# TraceMind — One-Page Design Note

**BuildSprint Round 3 | The Work Assistant That Remembers**

**Problem.** A meeting assistant must tell an employee what changed since the last client meeting, remember corrections and preferences, answer historical questions with evidence, and never reveal records the employee cannot access. TraceMind implements the required four-command JSON CLI in Python; the local Studio is optional.

### 1. Choosing records for each brief

On `ingest --day N`, TraceMind loads only day N and the previously available feedback into SQLite. For `brief --person P --date D`, it finds P's meetings and the prior meeting for each client, then selects developments that matter: changed owners, deadlines, statuses, document versions, decisions, blockers, and open promises. It downranks routine noise, follows person-specific feedback effective from the correct day, and cites the original record IDs. If nothing meaningful changed, it returns `nothing_new` with empty lists instead of filler.

### 2. What is remembered, corrected, or forgotten

Original records remain the source of truth; structured task fields and derived claims carry timestamps and source provenance. Contradictions are resolved by **authority before recency**: an authorized correction can replace an older claim, while a lower-authority comment cannot silently overwrite an authoritative update. The `ask --at` cutoff prevents seeing future information. Preferences and ignored topics belong to the requesting person. `forget` suppresses matching information for that requester, including after reingestion; shared-data suppression is **not** universal physical deletion of all copies or vector embeddings.

### 3. Privacy and trust boundaries

Python checks **organization → team/private/restricted visibility → requester → historical time → forget policy** before providing evidence. Private records are accessible only to their author; restricted records only to permitted readers. Cross-organization data is never a valid source. The optional external LLM receives only eligible **team-visible** evidence, divided by organization/client; no private or restricted bodies are forwarded. The optional Qdrant index stores team-visible embeddings and minimal IDs/metadata, then rechecks authorized source IDs before returning results. Text inside an email is treated as data, never a system instruction. Unsupported citations, names, dates, or numbers are rejected or handled conservatively.

### 4. Model use, budgets, and fallback

Deterministic ingestion, SQLite task state, and FTS5/BM25 are sufficient for offline operation. When an authorized API key is configured, bounded OpenAI calls may interpret unfamiliar corrections, Hinglish commitments, and ambiguous questions from selected evidence—not the full workspace. Requests use preflight input budgets of **4,000 tokens per question** and **8,000 per brief**; responses report SDK usage and configured USD pricing when available. When the key, network, quota, or model is unavailable, rules-based behavior remains available. The LLM does not grant access or create authoritative sources.

### 5. Evidence and limitations

**Verified public offline scorer: 85/85** on days 1–5 (briefs 20, answers 15, honesty 15, memory 15, privacy 10, cost 10). Local privacy-invariant auditing reported zero authorization/citation violations on the supplied fixture. A later local run found 200 tests with zero failures and 48 fixture-dependent skips; a full 200-test replay with the mounted dataset and a successful live OpenAI generation are not yet documented for the latest edits. **Hidden days 6–15, model-on accuracy/cost, and live review are unverified.** Studio's persona selector is a localhost demo, not production authentication.

**How to reproduce:** `R3_PACK` points to the organizer pack; run `python tools/run_days.py --cmd "python tracemind.py" --days 1-5 --out runs/check` and `python tools/score.py --run runs/check --days 1-5`. See `README.md` and `SECURITY_AUDIT.md`.
