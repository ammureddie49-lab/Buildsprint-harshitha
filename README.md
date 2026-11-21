# TraceMind — The Work Assistant That Remembers

**BUILDSprint R3 · Final audited candidate implementation**

TraceMind is an evidence-grounded workplace memory and meeting assistant. It reads time-ordered email, chat, task, document, spreadsheet, calendar and note records. It preserves changing facts and user feedback across processes, creates short meeting briefs, answers with real citations, and refuses or clarifies when it cannot safely answer. All graded behavior works through a JSON-only Python CLI; a local React/Three.js + FastAPI Studio is included for demonstrations.

**Submission status:** Offline public scorer **85/85** (all available machine-scored day 1–5 points), **198 automated Python tests passing**, and a separate public-fixture privacy-invariant audit with **zero authorization/citation violations**. **This is not a 100/100 or hidden-day claim.** Five points for hidden-day improvement and ten points for design/live review remain unscored; real OpenAI and Qdrant runtime execution were not available in the packaging environment.

## 1. Run the officially graded CLI (no key, Docker, or vector dependencies)

Use Python 3.11+ from the `BuildSprint-R3-candidate` directory. The CLI is offline without a configured key. If an operator supplies a key, the default `TRACEMIND_USE_LLM=auto` enables selective language interpretation; `TRACEMIND_USE_LLM=0` forces offline mode.

```powershell
python -m unittest discover -s tests -v
python tools/run_days.py --cmd "python tracemind.py" --days 1-5 --out runs/my-final-check
python tools/score.py --run runs/my-final-check --days 1-5
python tools/agent_privacy_audit.py
```

The full **local verification bundle** includes the supplied public `data/` and `answers/` fixtures. The **clean judge/source submission** intentionally excludes them. If you run its test suite without the organizer's dataset, dataset-dependent integration tests report **SKIPPED**, not passed; other synthetic/security tests continue to run. To execute **all 198 tests**, use the Local Verification ZIP or set `R3_PACK` to the folder containing `data/people.json` and `data/days/day-01.jsonl`. For PowerShell:

```powershell
$env:R3_PACK = "C:\path\to\organizer-pack"   # replace with the actual folder containing data/
python -m unittest discover -s tests -v
```

The organizer supplies hidden days and private answers externally; never hard-code answer keys into the application.

### Four required commands

```powershell
python tracemind.py ingest --day 1
python tracemind.py brief --person p02 --date 2026-11-03
python tracemind.py ask --person p02 --at "2026-11-02T18:00:00Z" --ask "Who handles billing for NB?"
python tracemind.py forget --person p02 --what "Forget my Dubai trip"
```

All commands output machine-readable JSON to stdout. Each CLI invocation is a separate process and persists state through SQLite. An optional `audit --person P` command is also implemented for source-scoped introspection.

## 2. Design and architecture

```text
Organizer daily JSONL + previous day's feedback
          |
          v
  Deterministic ingestion (SQLite source records, task state, feedback)
          |
          +-- optional bounded OpenAI SDK extraction for corrections,
          |    Hinglish commitments, decisions, blockers, owners
          |         |
          |         v
          |    source-validated hybrid_facts + temporal_facts
          v
  Requester/org/visibility/as-of/forget ACL gate
          |
          +-- Fast structured memory & rule-based answer
          +-- FTS5/BM25 lexical evidence retrieval
          +-- optional local MiniLM embeddings + persistent Qdrant index
          +-- optional OpenAI SDK reasoning over bounded, authorized evidence
          |
          v
  Python-side source, time, permission & numeric/name checks
          |
          v
  JSON answer / brief / clarify / refuse / abstain
```

**SQLite is the source of truth.** Qdrant indexes semantic vectors only for `team` records; its payload stores source IDs, organization/client/time and a content fingerprint, not raw message bodies. Search results are revalidated against the requester's current authorized source IDs. Qdrant is a retrieval index, **not** a trusted memory database, and vector similarity is not proof of a fact.

**Model interpretation is selective.** The CLI only sends candidate **team-visible** natural-language records, partitioned by organization and client, in batches of at most five, subject to a configurable call budget. Python checks source IDs and fact content before storing extracted claims. The SDK is optional and never required for the public offline scorer. `TRACEMIND_USE_LLM=0` makes no paid model requests.

**Memory is temporal.** Original records and interpreted facts retain source provenance. Corrections are evaluated with author authority and recency; user feedback is effective only after its observation day; suppressed topics and preferences are person-scoped. In later days, ignored feedback topics affect only that requester's briefs. Forgotten record IDs cannot be cited in that requester's subsequent answers. Shared-source forget is access suppression rather than guaranteed erasure of all other users' copies or Qdrant vectors.

## 3. Optional model integration (for judges)

The official OpenAI Python SDK is used directly, **without LangGraph**. Configure on the evaluation machine (do not commit any secrets):

```powershell
python -m pip install -r model-requirements.txt
Copy-Item .env.example .env
```

Set in `.env`:

```ini
TRACEMIND_USE_LLM=auto
OPENAI_API_KEY=THE_EVALUATOR_OWN_KEY
TRACEMIND_MODEL=gpt-4.1-mini
TRACEMIND_MAX_INGEST_CALLS=12
```

Run `python tools/smoke_hybrid_model.py` to validate the **real** SDK once with synthetic, not workplace, evidence. The CLI uses an explicit call budget, scoped prompts, failure fallback, and token/cost metering; any key-enabled remote runs may incur API charges. The model path has been exercised with *mocked* Responses API clients, **not a paid live evaluation**. Do not claim its hidden-day accuracy or spending is already measured. If using a different model, supply `TRACEMIND_PRICE_INPUT_PER_M` and `TRACEMIND_PRICE_OUTPUT_PER_M`; an unknown unpriced model is disabled to avoid misreporting zero cost. See `MODEL_EVALUATION.md` for mode and token-budget details.

**Model outage protection:** extraction attempts are bounded and stop after repeated failures; previously unprocessed candidate records can be retried on the next ingest after service recovery, still subject to budget and source permissions.

## 4. Optional local vector database (Qdrant)

```powershell
python -m pip install -r vector-requirements.txt
python tools/vector_db_smoke.py
python tools/vector_db_smoke.py --real-model
```

The first smoke test verifies an actual persistent Qdrant local collection with **fake workplace data and synthetic vectors**; the second also loads the genuine `sentence-transformers/all-MiniLM-L6-v2` model. The model may need to download weights on first use. Neither test needs an OpenAI key. To select Qdrant in the Studio, choose **Vector DB** in Ask. To opt into vector search on the CLI model-fallback path, set `TRACEMIND_VECTOR_DB=1`; it is off by default to keep short CLI subprocess calls fast. The included Qdrant unit tests use a simulated client; **real Qdrant installation was not testable in the packaging environment**.

## 5. Run the interactive Studio (local demo)

```powershell
python -m pip install -r studio-requirements.txt
python launch_studio.py
```

Open **http://127.0.0.1:8765**. A prebuilt frontend is included, so **npm is not needed to simply launch the demo**. To modify the React app, run `cd studio-frontend; npm install; npm run build; cd ..`; set `TRACEMIND_STUDIO_DEV=1` to launch Vite development mode. The UI includes source citations, meetings, memory, evaluation results, a Three.js visualization, and vector retrieval. Studio action tools can prepare local tasks, call plans, meeting plans, drafts and memory changes with approval; **no real calls, emails or external calendar actions are executed**.

**Security boundary:** Studio is **localhost-only**. The persona selector is a development demo, not user authentication. Do **not** expose the FastAPI service to a public network or claim production tenant security without implementing real authentication/authorization. Private and restricted record bodies are never sent through the Studio's external-model evidence tools.

## 6. Honest results and grading coverage

| Challenge category | Verified public points | Evidence |
|---|---:|---|
| Right briefs | 20/20 | Official 5-day scorer |
| Right answers | 15/15 | Official 5-day scorer |
| Honesty | 15/15 | Official 5-day scorer and source tests |
| Memory | 15/15 | Official 5-day scorer plus temporal/feedback/forget tests |
| Privacy | 10/10 | Official 5-day scorer, 0 public leaks, separate invariant audit |
| Cost and speed | 10/10 | Offline scorer (0 API tokens; wall time reported) |
| **Available machine score** | **85/85** | 5 public days only |
| Getting better on days 6–15 | Not available | Organizer-only hidden grading |
| One-page design/live review | Not available | Evaluated by people / organizer agent |

Our extended audit checks **165 person-day scopes** across supplied public records and validates **178 meeting-brief references** and **60 question/matched references** with no unauthorized IDs. It does not prove full semantic entailment or hidden-day success. See `EVALUATION.md`, `SECURITY_AUDIT.md` and `DESIGN_NOTE.md` for detailed verification and acknowledged limitations.

## 7. Author contributions and AI tooling transparency

The implementation and adversarial tests were developed and iterated using **ChatGPT and Kiro** as coding/review assistants. The deliverable includes executable source, independent unit tests, a design note, reproducible public scoring instructions, and a live-demo script. Human oversight and independent testing of code and outputs remain essential. No judge API keys or private credentials are bundled.

## 8. Critical limits

- **No guarantee of full 100/100 marks**: hidden days 6–15, human/agent design scoring and live OpenAI behavior were not available to validate.
- **Not production authentication**: the Studio deliberately rejects remote clients; a persona selector is not a login.
- **No complete semantic entailment proof**: source checks and conservative model validation reduce, but cannot eliminate, factual hallucinations.
- **No guaranteed physical vector deletion** after one person's topic forget: request-scoped retrieval is suppressed, shared evidence may remain for others.
- **Cold Qdrant/MiniLM startup** can be substantial for a new CLI process; use Studio for a warm interactive demo and benchmark before enabling for timed evaluation.

**Files to start with:** `tracemind.py`, `tracemind_hybrid.py`, `tracemind_temporal.py`, `tracemind_vector_db.py`, `studio_api.py`, `DESIGN_NOTE.md`, `EVALUATION.md`, `SECURITY_AUDIT.md`.

## Model-ready CLI (not a hidden-score guarantee)

The scored CLI defaults to **auto**: it uses OpenAI **only** if a key is supplied via the environment or an uncommitted `.env`. `TRACEMIND_USE_LLM=0` always disables remote calls, even if a key exists. The Studio has a **separate explicit consent requirement**. Model calls use a preflight input budget (4,000 for asks, 8,000 for briefs, 8,000 for ingestion batches) with an optional `tiktoken` tokenizer; when absent, a conservative byte-based ceiling is used. Actual SDK token usage is checked after the call. Do not assume the model-on public score is 85/85 without running it with a real key.

### Scoring-focused changes in this model-ready release

- Unified key activation: default `auto`, explicit `0` force-off, with one coherent SDK/pricing configuration.
- Added `tiktoken`-aware prompt preflight with conservative byte fallback, server usage checks, and at-most-one model attempt per question.
- Expanded model-extraction **candidate triage** for unfamiliar workplace phrasings without hardcoded client identities or hidden answers.
- Added 11 synthetic regression tests and `tools/audit_model_usage.py` (brief/ask usage only).
- Preserved the original 85/85 offline public scorer and independent privacy audit.

See `MODEL_EVALUATION.md` and `MODEL_GENERALIZATION_REPORT.md`. **A live model-on public score has not been measured.**
