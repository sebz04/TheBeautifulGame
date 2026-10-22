# Stats Engine

**Status:** pitch control (TASK-6, 6.1) and xT (TASK-7) built; the rest planned (TASK-11–14). Deterministic only (Constitution I).

| Metric | Module | Status | Notes |
|---|---|---|---|
| Pitch control | `stats/pitch_control.py` | done | Spearman 2018; vectorized; parity-tested against Friends of Tracking |
| xT | `stats/xt.py` | done | Singh 2019 value iteration on synthetic events only; grid in `data/models/xt_grid.npy` |
| Pass quality | `stats/passes.py` | planned | Distance, accuracy, difficulty |
| Speed and alerts | `stats/speed.py` | planned | Sprint > 7.0 m/s for ≥ 1 s |
| PPDA, field tilt, momentum, control vs. chaos | `stats/team.py` | planned | |
| Moments | `stats/moments.py` | planned | Rule triggers |
| Counterfactual | `stats/counterfactual.py` | planned | Reuses the engine's option scoring |
| Materialization | `stats/metrics.py` | planned | `metrics_at(t)`: event-exact, on demand, no look-ahead (agents, MCP, Verifier). Stored rows: 30 s grid for charts plus a snapshot at each moment's `t_end` |

## Pitch control (`stats/pitch_control.py`)
- `pitch_control_at(frame, attacking_team, targets (N, 2), params=None, goalkeepers=frozenset(), attacks_right=None) -> (N,)` in [0, 1]; the ball starts at `frame.ball`.
- `pitch_control_grid(frame, attacking_team, nx=32, ny=21, ...) -> (ny, nx)`, where row 0 is y near 0 and `grid_centres(nx, ny)` gives cell centres.
- `PCParams` uses the Friends of Tracking defaults: speed 5 m/s, reaction 0.7 s, sigma 0.45 s, lambda 4.3, `kappa_def` 1, `gk_factor` 3, ball speed 15 m/s, dt 0.04 s, tolerance 0.01.
- **Pass `goalkeepers`.** `TrackingFrame` has no positions, so the caller names the keepers (`MatchMeta` squads). Only the *defending* keeper gets the ×3 control rate, as in the reference, so home and away surfaces add up to 1 only without that bonus.
- **Offside (TASK-6.1):** pass `attacks_right` (from `engine.pitch.attacks_right(is_home, period)`) to drop offside attackers first. `offside_players(frame, attacking_team, attacks_right, tol=0.2)` uses the reference rule: beyond max(second-last defender, ball, halfway line) + 0.2 m, with no "interfering with play". `attacks_right=None` applies no offside rule. Same sets as the reference's `check_offsides`; the filtered grid is within 0.02 of it. Counterfactuals and level-3 decisions must pass the direction.
- Vectorized over every target and player. Each target stops integrating where the reference loop would; head-start shortcuts and far-player pruning are the same.
- Parity: within 0.02 per cell of the vendored reference (`tests/reference/`) on 5 frames. A 32×21 grid takes about 13 ms (benchmark < 50 ms).
- Pitch control is evaluated at events and moments, not every frame (see `decisions.md`).

## xT (`stats/xt.py`, `scripts/train_xt.py`)
- **Attacking-right frame.** Events are stored in absolute coordinates. `normalize_events(data)` mirrors each event so the acting team attacks toward x = 105, and `train_xt` expects normalized events. `xt_added(grid, event, attacks_right=True)` mirrors on the fly; pass the acting team's direction.
- `transition_model(events, nx=16, ny=12) -> XTModel` (shoot, move, goal per shot, and transitions of completed moves; failed moves stay in the denominator). `solve_xt(model, iters=50)` and `train_xt(events, nx, ny, iters) -> (ny, nx)` (row 0 is y near 0). `load_xt(path=None)`, `xt_value(grid, x, y)` (off-pitch points use the nearest cell), and `xt_added` (completed pass or carry: end minus start; otherwise `None`).
- Moves are passes and carries. Kickoffs are restarts, not choices, so they're excluded.
- **Checks:** a 2-cell example worked by hand, and value iteration agrees with an exact `np.linalg.solve` (1e-9 at 500 iterations, 1e-3 at the default 50). socceraction can't be installed (it pins numpy < 2).
- **Current grid:** level 1, 200 seeds, 318k events, provenance in `data/models/xt_grid.json`. Own half about 0.003–0.005, rising through the final third to about 0.30 in front of goal. Cells with no actions are 0. Retrained at level 3 in TASK-10. Training takes about 3 min on 8 cores (`tracking=False`).
