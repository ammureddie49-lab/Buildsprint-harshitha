# TraceMind — Verified evaluation and evidence limits

## Latest public replay (after final security and memory hardening)

Executed the supplied `tools/run_days.py` and `tools/score.py` against the unchanged five public fixture days, with `TRACEMIND_USE_LLM=0` and `TRACEMIND_VECTOR_DB=0`.

| Challenge area | Points | Public checks |
|---|---:|---:|
| Right briefs | 20 / 20 | 7 |
| Right answers | 15 / 15 | 33 |
| Honesty | 15 / 15 | 40 |
| Memory | 15 / 15 | 2 |
| Privacy | 10 / 10 | 40 |
| Cost and speed | 10 / 10 | 40 |
| **Total available public machine points** | **85 / 85** | |
| Getting better (hidden days) | Unavailable / 5 | Hidden evaluations required |
| One-page design + live session | Unavailable / 10 | Evaluator discretion |

**No automatic privacy-leak flags were reported.** Public score does not prove hidden-day correctness or live model performance. The offline run reports zero paid-model input/output tokens because it actually made no paid model calls.

## Separate independent tests

- `python -m unittest discover -s tests -q`: **198/198 pass**, including 18 previous final audit plus 11 new model-readiness final agent/security and hybrid bounded-outage/backlog tests over the prior 169-case suite.
- `python tools/agent_privacy_audit.py`: **PASS**: 165 person/day scopes, 113,095 allowed record/scope assertions, 149,585 denied record/scope assertions, 178 meeting-brief source checks, 60 question/matched source checks; 0 violations. Counts represent repeated checks, not unique records.
- Additional regression tests cover multiple people with the same first name, short-code collisions, future client aliases, model-off no-network guarantees, cross-org identity expansion, ignored feedback (person/time scoped), fabricated names/numbers, prompt injection, model-failure circuit breaking, and mixed-client API call budgets.
- OpenAI Responses API test coverage uses **simulated SDK clients**. Actual paid OpenAI behavior/cost were not tested.
- Qdrant API contract tests use **an injected fake Qdrant backend**. A real Qdrant installation and MiniLM runtime were not available here. Use the included smoke tests on Windows.

## Three actual earlier development failures and how they were corrected

These are historical issues from the initial implementation; there are no current failed public outputs to present as 'worst'.

1. **q01-01, day 1:** failed to resolve "NB" to the correct client on a billing question. We implemented data-derived client aliases and explicit client scoping rather than hardcoding the question ID. Later hardening rejects ambiguous aliases.
2. **ev-cl-ro-03, day 2:** an upcoming same-day meeting was mistakenly treated as an already completed previous meeting, causing `nothing_new`. The prior-meeting boundary was restricted to actually observed events.
3. **q05-02, day 5:** selected an incorrect person when two employees shared the same first name. We added evidence/role/client context and explicit clarification rather than relying on ID ordering.

We reproduced the public score after these fixes, rather than hand-editing the grader results. Source files in `data/` and `answers/`, and the organizer's scoring code, were not modified.

## How to reproduce

```powershell
$env:TRACEMIND_USE_LLM="0"
$env:TRACEMIND_VECTOR_DB="0"
python -m unittest discover -s tests -v
python tools/run_days.py --cmd "python tracemind.py" --days 1-5 --out runs/final-replay
python tools/score.py --run runs/final-replay --days 1-5
python tools/agent_privacy_audit.py
```

**Security caveats:** The Studio persona chooser has no login and is localhost-only; private records remain in SQLite while the authorized owner needs them; forgetting a shared topic is requester-scoped suppression, not guaranteed erasure of every vector copy or backup. **Do not present this prototype as independently penetration-tested or production-certified.**

## Latest model-readiness update

The source-only ZIP has now passed **198/198 Python tests** and reproduced the **85/85 public offline score**, with `TRACEMIND_USE_LLM=0`. The new tests validate `auto / 0 / 1` mode decisions, 4,000-token request budgeting, metering on rejected model output, at-most-one model attempt per question, and triage of 15 synthetic unseen-style phrases. These are not real model outputs. A live-key model-on five-day run is still required to measure its score, exact usage, and spending.

The public privacy invariant audit still returned **PASS** with zero violations; `derived_fact_sources_checked=0` in that offline audit. This is distinct from hybrid derived-fact unit tests.
