# Evaluations

## Verifier (TASK-18.2)

Golden set: `evals/verifier_golden.jsonl`, 40 insights written by code from three built matches (`scripts/build_verifier_golden.py`): 20 correct (all 5 languages) and 20 with one planted error each, 12 for the number check and 8 for the wording check. Run `scripts/run_foundry_eval.py`: the full `verify` with `gpt-4.1-mini` in Foundry and prompt `verifier.v1.md`, 3 run(s), 2026-10-25.

| Measure | Result | Target |
|---|---|---|
| Recall on planted errors | 57/60 = 0.95 | ≥ 0.95 ✅ |
| … caught by the number check | 36/36 = 1.00 | 1.00 (deterministic) |
| … caught by the Verifier agent | 21/24 = 0.88 | |
| Precision | 57/57 = 1.00 | |
| False alarms on correct insights | 0/60 = 0.00 | |
| Median time per model check | 2111 ms | |

**Missed errors:**

- `e19` wrong_team_press (run 1)
- `e19` wrong_team_press (run 2)
- `e19` wrong_team_press (run 3)

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
- **Interpretation slips pass.** Live insights have read PPDA as pressure faced rather than pressing done, and stretched a stat at one moment into "since". The events don't contradict these, so the Verifier lets them through; prompt guidance on reading each metric would help.
- The golden set is written by code from templates, so its sentences are simpler than the Explainer's.
