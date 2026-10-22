# Stats Engine

**Status:** pitch control built (TASK-6); the rest planned (TASK-7, 11–14). Deterministic only (Constitution I).

| Metric | Module | Status | Notes |
|---|---|---|---|
| Pitch control | `stats/pitch_control.py` | done | Spearman 2018; vectorized; parity-tested against Friends of Tracking |
| xT | `stats/xt.py` | planned | Trained on synthetic data only; grid in `data/models/xt_grid.npy` |
| Pass quality | `stats/passes.py` | planned | Distance, accuracy, difficulty |
| Speed and alerts | `stats/speed.py` | planned | Sprint > 7.0 m/s for ≥ 1 s |
| PPDA, field tilt, momentum, control vs. chaos | `stats/team.py` | planned | |
| Moments | `stats/moments.py` | planned | Rule triggers |
| Counterfactual | `stats/counterfactual.py` | planned | Reuses the engine's option scoring |
| Materialization | `stats/metrics.py` | planned | `metrics_at(t)`: event-exact, on demand, no look-ahead (agents, MCP, Verifier). Stored rows: 30 s grid for charts plus a snapshot at each moment's `t_end` |

## Pitch control (`stats/pitch_control.py`)
- `pitch_control_at(frame, attacking_team, targets (N, 2), params=None, goalkeepers=frozenset()) -> (N,)` in [0, 1]; the ball starts at `frame.ball`.
- `pitch_control_grid(frame, attacking_team, nx=32, ny=21, ...) -> (ny, nx)`, where row 0 is y near 0 and `grid_centres(nx, ny)` gives cell centres.
- `PCParams` uses the Friends of Tracking defaults: speed 5 m/s, reaction 0.7 s, sigma 0.45 s, lambda 4.3, `kappa_def` 1, `gk_factor` 3, ball speed 15 m/s, dt 0.04 s, tolerance 0.01.
- **Pass `goalkeepers`.** `TrackingFrame` has no positions, so the caller names the keepers (`MatchMeta` squads). Only the *defending* keeper gets the ×3 control rate, as in the reference, so home and away surfaces add up to 1 only without that bonus.
- Offsides are not applied (yet).
- Vectorized over every target and player. Each target stops integrating where the reference loop would; head-start shortcuts and far-player pruning are the same.
- Parity: within 0.02 per cell of the vendored reference (`tests/reference/`) on 5 frames. A 32×21 grid takes about 13 ms (benchmark < 50 ms).
- Pitch control is evaluated at events and moments, not every frame (see `decisions.md`).

