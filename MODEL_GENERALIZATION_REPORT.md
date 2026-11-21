# Generalization and current test gaps (not a hidden-day score)

## What may improve graded results

1. **Highest possible gain:** actual live-key interpretation of previously unseen corrections, commitments, and context queries. The key-enabled model route now turns on automatically unless explicitly disabled. A real five-day model-on replay is still necessary and has **not** been performed.
2. **Privacy remains critical:** model calls receive authorized team-visible records only; the original Python authorization gates are retained. A single leak may cap the overall evaluation, so privacy must be tested again with the live model.
3. **Memory:** previously interpreted corrections survive restarts; the ingestion backlog can recover records skipped during a model outage. Model extraction now has broader phrase triage, not hidden-day-specific regex answers.
4. **Cost limits:** input prompt preflight includes instructions, evidence and an overhead reserve; known model pricing is estimated from measured tokens and the response's usage. Model-on totals are not available without a key.

## Fifteen synthetic, previously unused workplace phrasings

The release tests these examples as *model-extraction candidates*, not successful live LLM interpretations: `Friday tak kar dunga`, `kal subah tak bhej dungi`, `parso tak ho jayega`, `deliver the contract tomorrow`, `finished before EOD`, `agreed, due Friday`, `complete QA review before Monday`, `submit the design by tomorrow`, `aaj shaam tak share`, `blocked until approvals`, `billing shifted to Arjun`, `responsibility transferred`, `deadline delayed`, `confirm handoff`, and `customer escalation tomorrow`. See `tests/test_model_readiness.py`.

## Three current *risk examples* (not falsely claimed test failures)

- A previously unseen ownership correction might be phrased without any expected trigger; semantic interpretation improves flexibility but the filter can still miss it.
- A model could return a true-looking summary with a real source ID but unsupported semantic content. Citation checking is necessary, not sufficient, to prove entailment.
- Hidden-day inputs may exceed the model context budget or may arrive without the evaluator's key; a safe local fallback remains available, but could miss hard paraphrases.

**There are no presently failed outputs on the published five-day machine-scored dataset.** The three historical failures documented in `EVALUATION.md` are clearly identified as fixed development bugs, not disguised as current worst outputs.

## Measured local results

- 198/198 Python tests
- 85/85 offline public scorer days 1–5
- Privacy audit: PASS, zero violations on public fixture
- Real Qdrant MiniLM smoke: passed on the developer's Windows installation in a separately shared log; not repeated in the packaging environment
- Model-on OpenAI score/cost/hidden-day results: not measured
