# TraceMind — Judge / agent evaluator handoff

## Reproducibility and test entry points

The submission root is the `BuildSprint-R3-candidate` directory. The official four JSON commands are in `tracemind.py` (bonus `audit` also supported). The command runner is `tools/run_days.py`, and the public scorer is `tools/score.py` inside the organizer's evaluation pack.

### Judge-source package (clean, no organizer data/answers)

Set `R3_PACK` to the directory containing the organizer-provided `data/` folder. That directory supplies `data/people.json`, `data/clients.json`, and `data/days/day-NN.jsonl`, plus the official harness. From a copy of the submission code **placed into that pack**, run:

```powershell
python -m unittest discover -s tests -v
python tools/run_days.py --cmd "python tracemind.py" --days 1-5 --out runs/judge-check
python tools/score.py --run runs/judge-check --days 1-5
python tools/agent_privacy_audit.py
```

The source-only submission intentionally omits organizer-provided datasets and answer keys. Its dataset-dependent tests will be marked **SKIPPED** until an organizer pack is mounted, rather than generating cascading `Unknown demo persona` errors. **Do not interpret skipped tests as passing tests.** Set `R3_PACK` to the directory containing `data/` and run the suite again; all 198 tests are expected to execute when the public fixtures are present. For a fully self-contained local reproduction, use the separate **local verification bundle**, which includes the public fixture pack.

### Model evaluation (optional but necessary to assess language generalization)

```powershell
python -m pip install -r model-requirements.txt
Copy-Item .env.example .env
# Edit .env locally. Set TRACEMIND_USE_LLM=auto (the default), OPENAI_API_KEY, TRACEMIND_MODEL.
python tools/smoke_hybrid_model.py
```

No model key is included. If a key is provided in the environment, the model is activated automatically for the CLI unless TRACEMIND_USE_LLM=0. Model-assisted ingestion extracts corrections/Hinglish commitments and persists grounded facts; question and brief model calls are conditional. A model outage triggers bounded retry/fallback. Actual OpenAI correctness and cost **were not verified** by the package author.

### Vector database evaluation

```powershell
python -m pip install -r vector-requirements.txt
python tools/vector_db_smoke.py
python tools/vector_db_smoke.py --real-model
```

The Qdrant local backend uses permission-scoped source IDs and only shared/team embeddings, plus BM25 fusion. The mock Qdrant unit tests passed; the **real Qdrant smoke test must still be run in the judge environment**.

### UI (no Node required to view compiled demo)

```powershell
python -m pip install -r studio-requirements.txt
python launch_studio.py
```

Open `http://127.0.0.1:8765`. Compiled frontend assets are included. The Studio is localhost-only, and its persona switcher is explicitly not secure authentication. Local drafts, calls, meetings and tasks require approval; no real outgoing message or phone call is made.

## Scoring coverage (not a claim about hidden tests)

Public machine scorer: briefs 20/20; answers 15/15; honesty 15/15; memory 15/15; privacy 10/10; cost 10/10; subtotal **85/85**. Hidden improvement 5 points and design/live review 10 points are unavailable to the author. There is **no evidence supporting a guaranteed 100/100** result. See `DESIGN_NOTE.md`, `EVALUATION.md`, and `SECURITY_AUDIT.md` for reproducibility and limitations.

## Assisted-development disclosure

ChatGPT and Kiro were used for implementation assistance, regression-test development, reviews and documentation. The candidate is responsible for understanding and validating their own code.

## Important: baseline vs model-on

**Verified offline:** 198 Python tests, public scorer 85/85, privacy audit zero violations. **Not yet verified:** live-key OpenAI public score and the hidden-day score. The agent should run `tools/smoke_hybrid_model.py` with its own key before any model-on replay. To compare model vs offline scores, use separate SQLite paths and separate run directories. `tools/audit_model_usage.py` summarizes reported ask/brief usage; ingest's SDK usage remains visible in the `ingest` JSON but isn't persisted by the organizer's runner.
