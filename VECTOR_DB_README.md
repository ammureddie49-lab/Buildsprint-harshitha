# TraceMind v5 — Real Persistent Vector Database (Qdrant Local)

**What was added:** a real Qdrant vector store that persists dense embeddings for shared workplace evidence and fuses ranked vector hits with the existing SQLite FTS5/BM25 evidence search. Local Qdrant runs with **no Docker, no Qdrant Cloud account, no LangGraph, and no OpenAI key**. The original scored CLI stays offline by default.

## Installation on Windows (Kiro / PowerShell)

From the `BuildSprint-R3-candidate` project root:

```powershell
python -m pip install -r studio-requirements.txt
python -m pip install -r vector-requirements.txt
python tools/vector_db_smoke.py
python tools/vector_db_smoke.py --real-model
python -m unittest discover -s tests -v
```

The first smoke test **calls a real local Qdrant client** and confirms upserts, a query, and persistence across closing/reopening the DB with an artificial 3-dimensional embedding. The second uses the actual local MiniLM model with 384-dimensional embeddings and checks the same behavior. Neither contacts OpenAI, reads official answer keys, or sends workplace data to the cloud. The first MiniLM run may download weights; network access is only needed for obtaining the model initially.

If you receive an import error, ensure those dependencies were installed into the same Python interpreter you are using to launch the app. Offline installation requires cached wheels and cached MiniLM weights.

## Studio: simplest demo

```powershell
cd studio-frontend
npm install
cd ..
python launch_studio.py
```

Open `http://127.0.0.1:5173` → **Ask TraceMind** → select **Vector DB** → ask a question. The first vector query embeds and persists shared team records in `.tracemind-qdrant/`; subsequent queries reuse document vectors and embed only the new question. Data and vectors remain local. The existing short-lived Neural/Hybrid mode is still available through the API but the frontend shows **Vector DB** to keep the UX simple.

API: `GET /api/vector-status` reports *installed dependencies*, not an invented number of indexed records. `POST /api/ask` with `mode: "vector"` requests Qdrant+BM25 retrieval. If Qdrant is missing, the API returns a visible error and falls back to authorized lexical retrieval rather than claiming vector search ran.

## Optional graded CLI routing

The scorer's current deterministic route is left alone by default. When the organizers provide their own OpenAI key, the existing SDK integration can be enabled independently with `TRACEMIND_USE_LLM=1`. To also use Qdrant in its unresolved-question retrieval fallback, set:

```powershell
$env:TRACEMIND_VECTOR_DB="1"
$env:TRACEMIND_SEMANTIC="1"
```

Or put `TRACEMIND_VECTOR_DB=1` into your local `.env` if your launcher loads it. Do not set this globally for timed official CLI evaluation unless you have measured cold-start times. Every `python tracemind.py ask ...` launches a fresh interpreter and may load MiniLM again; a long-lived Studio server avoids that repeated startup overhead. Qdrant local mode should not be opened simultaneously by multiple processes using the same storage directory. Use `TRACEMIND_QDRANT_PATH` to isolate stores as needed.

### Show an offline baseline first

```powershell
$env:TRACEMIND_USE_LLM="0"
$env:TRACEMIND_VECTOR_DB="0"
python tools/run_days.py --cmd "python tracemind.py" --days 1-5 --out runs/vector-offline
python tools/score.py --run runs/vector-offline --days 1-5
```

This tests compatibility without making external API calls or loading a vector model. For the optional model route, the organizers can later configure `OPENAI_API_KEY`, `TRACEMIND_USE_LLM=1`, and `TRACEMIND_MODEL` in their own environment. Never include a real key in a ZIP or Git repository. Our real OpenAI model quality is **not measured** here.

## Security, provenance, and memory semantics

1. **ACL-before-index:** each query starts from `Engine.allowed(person, at)`, which already enforces organization, time cutoff, restricted readers, and user-specific forget filters.
2. **Shared-only index:** Qdrant permanently stores **only `visibility=team`** records. Private and restricted messages are never embedded in the persistent vector DB.
3. **No raw text in Qdrant payloads:** payload contains opaque source ID, organization/client/time, and a SHA-256 fingerprint; original text and citations live in the existing SQLite source-of-truth.
4. **Current authorization re-check:** each Qdrant query filters by the exact set of authorized source IDs and organization, then validates every returned source against the same request-scoped allow-list. Forgetting does not resurrect old content just because an older embedding remains in the shared store.
5. **Incremental upsert:** unchanged records keep their persisted vectors; changed records are re-embedded. The vector collection is keyed to embedding model identity.
6. **Evidence ≠ truth:** retrieval only chooses candidate records. The existing factual/temporal memory and citation validation remain responsible for final answers. Qdrant does not execute instructions found in emails.

**Limitations:** Qdrant Local and MiniLM were not installable in the packaging environment, so Python integration tests use an injected fake Qdrant client (12 new tests). Run both `vector_db_smoke.py` commands on Windows for real persistence and model validation. The public five-day score alone cannot establish hidden-day accuracy. First-time indexing of ~1,500 public records is expected to be slower than subsequent queries. This is demo-grade local indexing, not production multi-user authentication.

## Validation at package creation

- **169/169 Python tests** passed on the v5 source (includes 12 new Qdrant integration contract tests with injected mock client).
- **85/85 official public five-day score** passed with LLM and vector DB disabled, retaining a working fallback.
- Real Qdrant runtime, browser npm build, and paid OpenAI calls **remain to be verified on the user's machine**.
