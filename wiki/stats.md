# Stats Engine

**Status:** planned (TASK-6, 7, 11–14). Deterministic only (Constitution I).

| Metric | Module | Status | Notes |
|---|---|---|---|
| Pitch control | `stats/pitch_control.py` | planned | Spearman-style; parity-tested against Friends of Tracking |
| xT | `stats/xt.py` | planned | Trained on synthetic data only; grid in `data/models/xt_grid.npy` |
| Pass quality | `stats/passes.py` | planned | Distance, accuracy, difficulty |
| Speed and alerts | `stats/speed.py` | planned | Sprint > 7.0 m/s for ≥ 1 s |
| PPDA, field tilt, momentum, control vs. chaos | `stats/team.py` | planned | |
| Moments | `stats/moments.py` | planned | Rule triggers |
| Counterfactual | `stats/counterfactual.py` | planned | Reuses the engine's option scoring |
| Materialization | `stats/metrics.py` | planned | Rows every 30 s for the API and MCP |
