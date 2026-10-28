# Evaluations

## Verifier (TASK-18.2)

Golden set: `evals/verifier_golden.jsonl`, 40 insights written by code from three built matches (`scripts/build_verifier_golden.py`): 20 correct (all 5 languages) and 20 with one planted error each, 12 for the number check and 8 for the wording check. Run `scripts/run_foundry_eval.py`: the full `verify` with `gpt-4.1-mini` in Foundry and prompt `verifier.v1.md`, 1 run(s), 2026-10-27.

| Measure | Result | Target |
|---|---|---|
| Recall on planted errors | 20/20 = 1.00 | ≥ 0.95 ✅ |
| … caught by the number check | 12/12 = 1.00 | 1.00 (deterministic) |
| … caught by the Verifier agent | 8/8 = 1.00 | |
| Precision | 20/20 = 1.00 | |
| False alarms on correct insights | 0/20 = 0.00 | |
| Median time per model check | 2457 ms | |

<!-- notes: kept when this report is regenerated -->
### How the Verifier got here (3 runs each, same golden set)

| Change | Recall | Precision | False alarms |
|---|---|---|---|
| First run: claims with raw values, one `ok` + `problems` answer | 0.93 | 0.86 | 9/60 (all translations) |
| Facts as statements with names; events just before each cited one | 0.93 | 0.93 | 4/60 |
| Facts without values; "statistics are not events"; a who-error example | 0.92 | 1.00 | 0/60 |
| One verdict per statement (`supported`, `not_covered`, `contradicted`, `invented`); temperature 0 | **0.95** | **1.00** | **0/60** |

### Known gaps
Deferred to TASK-25.2 (after deployment) on 2026-10-25. The metric-meaning part of the second gap was fixed in the Explainer prompt at the start of TASK-19.

- **Numbers are matched by value, not meaning. Fixed for team numbers in TASK-25.2** (`agents/owners.py`): a number is tied to the team named before it in its clause, so `e19` (one team's PPDA given to the other side) and `e18` ("leaving Chapinero with 10 players") are now caught by code before the model is asked. Player numbers are still matched by value.
- **Interpretation slips. Fixed for PPDA in TASK-25.2** (`agents/meaning.py`): a sentence that mentions PPDA and says a team "faces" or "suffers" pressure without naming who applies it fails in code (all 5 languages; on stored texts it found 5 insights and 17 fan texts, all slips). Recap sentences that quote stats from two moments as if at once fail too (`mixed_moments`). Stretching a stat at one moment into "since" still relies on the prompts.
- In the 2026-10-27 run, "caught by the Verifier agent" counts the 8 wording errors; `e18` and `e19` among them are now caught by code (`agents/owners.py`) before the model is asked.
- The golden set is written by code from templates, so its sentences are simpler than the Explainer's.
