# Model activation, privacy and score-readiness

The **CLI** uses `TRACEMIND_USE_LLM=auto` by default and enables its OpenAI Responses API path when `OPENAI_API_KEY` or `TRACEMIND_API_KEY` is set. With no key it operates offline. An explicit `TRACEMIND_USE_LLM=0` overrides the presence of a key and prevents paid model calls. The Studio's separate remote-model consent gate is unchanged.

The model receives only candidate **team-visible** evidence, with the caller's organization, time, client and forgetting filters applied first. Ingestion batches are separated by organization/client. SQL data and source permissions—not the model—remain authoritative.

The gateway preflights every call using the model tokenizer if `tiktoken` is installed; otherwise it applies a conservative UTF-8 byte ceiling. The preflight includes the system instruction, serialized data and a 256-token overhead reserve. `ask` is capped at 4,000 input tokens, `brief` at 8,000, and ingestion batches at 8,000. The Responses API's actual input/output token usage is recorded when available. Costs for known named models have estimates; for a different model set `TRACEMIND_PRICE_INPUT_PER_M` and `TRACEMIND_PRICE_OUTPUT_PER_M`. These estimates are not billing receipts.

### Operator test (requires explicit authorization and a paid API key)

```powershell
$env:R3_PACK = 'C:\path\to\organizer-pack'
$env:TRACEMIND_USE_LLM = 'auto'
$env:TRACEMIND_MODEL = 'gpt-4.1-mini'
# Supply your API key privately via OPENAI_API_KEY, not in Git.
python -m pip install -r model-requirements.txt
python tools/smoke_hybrid_model.py
python tools/run_days.py --cmd 'python tracemind.py' --days 1-5 --out runs/model-on
python tools/score.py --run runs/model-on --days 1-5
python tools/audit_model_usage.py --run runs/model-on
```

For the existing 85/85 offline baseline, set `TRACEMIND_USE_LLM=0`. A model-on score has **not** been verified until the above run is completed.

### Cautions

- If the evaluator does not supply an API key, the system still runs offline; no external model can be conjured without credentials.
- The model could lower an otherwise correct public answer; validate the model-on score before relying on it.
- The ingestion model-call count is bounded; model availability and pricing vary.
- Requester-scoped forgetting is suppression, not verified physical deletion of all shared vector copies/backups.
