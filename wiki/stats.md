# Stats Engine

**Status:** pitch control (TASK-6, 6.1) and xT (TASK-7) built; the rest planned (TASK-11–14). Deterministic only (Constitution I).

| Metric | Module | Status | Notes |
|---|---|---|---|
| Pitch control | `stats/pitch_control.py` | done | Spearman 2018; vectorized; parity-tested against Friends of Tracking |
| Pass quality | `stats/passes.py` | done | Difficulty, xT added, accuracy |
| Team metrics | `stats/team.py` | done | PPDA, field tilt, momentum, control vs chaos |
| Speed and alerts | `stats/speed.py` | done | Ball/shot speed, player motion, speed/distance/name-tag cues |
| Player match lines | `stats/player_lines.py` | done | Per-player stat lines (season history, live) |
| xT | `stats/xt.py` | done | Singh 2019 value iteration on synthetic events only; grid in `data/models/xt_grid.npy` |
| Pass quality | `stats/passes.py` | planned | Distance, accuracy, difficulty |
| Speed and alerts | `stats/speed.py` | planned | Sprint > 7.0 m/s for ≥ 1 s |
| PPDA, field tilt, momentum, control vs. chaos | `stats/team.py` | planned | |
| Moments | `stats/moments.py` | done | Rule triggers, merging, formation classifier |
| Baselines, deviations | `stats/baselines.py`, `stats/deviations.py` | done | Shrunk per-90 baselines; live player discrepancies |
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
- **Current grid (TASK-10.3):** level 3 with profiles (engine `l4-0.1`), 300 seeds, 533k events, provenance in `data/models/xt_grid.json`. Own half about 0.002–0.005, rising through the final third to about 0.30 in front of goal. Cells with no actions are 0. Training takes about 4 min on 8 cores (`scripts/train_xt.py --level 3 --seeds 300`, `tracking=False`). Goals are read from `shot.outcome`; level 3 sets it on every scoring shot, including deflected ones.

## Player match lines (`stats/player_lines.py`, TASK-10.4)
`player_match_lines(data, motion, round_, xt=None) -> list[PlayerMatchLine]`, one per player who appeared. Fields: minutes, passes, completed, forward (5+ m gained), progressive (completed, 10+ m and ≥ 25% closer to goal), key passes and assists (the receiver's next action is a shot or a goal, with only his own carries between), xT added (completed passes and carries), shots, on target (scored or saved next), xG, dribbles (carries), tackles, interceptions, pressures, fouls, distance, sprints, top speed (from `Motion`), box touches, goals, assists, yellow, red.

## Pass quality (`stats/passes.py`, TASK-11.1)
- `pass_quality(event, frame, xt_grid, attacks_right, goalkeepers) -> PassQuality(distance_m, completed, difficulty, xt_added)`.
  - Difficulty: `sigmoid(1.2 · distance/40 + 0.8 · defenders within 3 m of the lane + 1.5 · (1 − pitch control at the end) + 0.4 · lofted − 1.6)`, with fixed weights.
  - Pitch control: offside-filtered, measured on the frame at the pass, with the ball at the kick.
  - Lofted: from `extras.lofted` (level-3 passes record it); without the flag, passes of 30 m or more count as lofted.
  - End points off the pitch are clamped to the edge. `xt_added` is None for failed passes.
- `player_accuracy(events, player_id, t_to=(period, t))`: completed share of the player's passes up to that moment, inclusive (NaN if he has none). The pair is needed because `t` restarts each half.
- In a level-3 match, failed passes are harder on average than completed ones (tested).

## Speed, motion, alerts (`stats/speed.py`, TASK-11.2)
- `ball_speed(event)`: `ball_speed_ms`, else end distance ÷ (`arrival_t` − t), else None. `shot_speed_kmh(event)` = ball speed × 3.6.
- `player_motion(frames, player_id, t_to=(period, t)) -> Motion(distance_m, top_speed_ms, sprints, minutes)`: position steps within each period, frame velocity, sprints above 7.0 m/s for at least 1 s (runs don't carry over half time).
- `alerts(frames, t, thresholds=AlertThresholds(sprint_ms=7.0, sprint_min_s=1.0, distance_step_m=1000)) -> list[OverlayCue]`: every cue triggered up to (period, t), in time order.
  - `speed_alert` (priority 2) plus a `name_tag` (3) at the frame where a run reaches 1 s, once per run.
  - `distance_alert` (1) at each further 1,000 m.
  - Cues last 4 s, with ids `{match}-{kind}-{player}-{period}-{t}`.
- **Cross-check:** distance and top speed agree with floodlight (`DistanceModel` and `VelocityModel`, backward differences) within 2% on a level-3 match (`tests/stats/test_speed.py`). We use backward differences because our frame velocity is the step just taken; central differences smooth the peaks.

## Team metrics (`stats/team.py`, TASK-12.1)
Windows are `(period, t)` pairs, inclusive. Depth is measured from a team's own goal line, which is why the functions take `home_id`.
- `ppda(events, team_id, home_id, t_from, t_to) -> float | None`: opponent passes in their own 60% ÷ our tackles, interceptions, and fouls in that zone. None when we made no such action; never infinite.
- `field_tilt(...) -> float`: our share of passes played in a final third (70+ m from the passer's goal); 0.5 when there are none.
- `momentum_series(events, xt_grid, home_id, window_s=300, step_s=30) -> MomentumSeries(points=[MomentumPoint(period, t, home, away, diff)])`: xT added by completed passes and carries plus shot xG, per team, over the last 5 min of the same half; `diff` = home − away. `.at(period, t)` gives the latest point. A pydantic model, not a DataFrame: pandas is not a runtime dependency.
- `control_chaos(events, frames, t_from, t_to, home_id) -> [0, 1]`: a weighted mean (renormalized when a part is missing) of:
  - turnovers per on-ball event (0.4; typical 0.12);
  - short possessions (0.3; typical 6 on-ball events per possession);
  - pitch-control volatility (0.15; the SD of the home team's mean control on a 16×10 grid every 10 s, frames only);
  - long forward passes of 30 m or more (0.15; typical 15%).
  - Each part is value ÷ (2 × typical), so a typical match sits near 0.5. A level-3 match reads 0.47–0.69 per 10 minutes (about 2 s for a whole match with frames).

## Key moments (`stats/moments.py`, TASK-12.2)
`detect_moments(match, xt_grid) -> list[Moment]`, ids `{match_id}-mNNN` in time order. Windows never cross half time.
- **Player:** goal and red card (the event); big chance (a shot with xG above 0.25).
- **Game:** `momentum_swing`, when the momentum diff changes sign within 5 min by more than 0.08.
- **Team:**
  - `pressing_collapse`: a team that was pressing (PPDA ≤ 12) sees its PPDA in the 10 min after a 5-minute mark rise more than 60% over the 10 min before, with at least 10 opponent passes after the mark.
  - `formation_shift` (frames only): the nearest formation template of a team's mean shape over the last 3 min changes and holds for 3 min.
  - `offside_trap`: 3+ offsides against one team within 20 min, credited to the defenders.
  - `corner_pressure`: 3+ corners for one team within 5 min.
- `classify_formation(outfield)`: splits the sorted depths into each template's number of lines exactly (dynamic programming, `_line_counts`), then picks the template with the closest players per line (4-2-3-1 has four lines).
- `merge_moments(moments, gap_s=60)`: joins same-kind, same-team moments in a half less than 60 s apart (event ids unioned, the larger trigger value kept).
- **Rates:** per unscripted match, about 11 momentum swings, 6 pressing collapses, 1–2 goals, 0.7 big chances, 0.7 corner-pressure spells, and 0.3 offside traps. These are candidates the insight agents rank; the thresholds come from the plan. About 1 s per tracked match.
- **Scripted check:** `press_collapse` gives the away team a `pressing_collapse` within 5 min of its fatigue beat, and `comeback_red_card` gives a `red_card` moment.

## Baselines and player deviations (`stats/baselines.py`, `stats/deviations.py`, TASK-12.3)
- `player_baselines(season, profiles) -> {player_id: PlayerBaseline(minutes, per90, dispersion)}`, covering every player in the profiles.
  - Per-90 rates are shrunk toward the role's rate: `w = minutes / (minutes + 450)`. A player who never played gets the role's rate.
  - Dispersion is per role: variance ÷ mean of per-90 rates from match lines of 45+ minutes, clipped to 1–10.
  - `club_possession` is the club's season share of passes in its own matches (`club_possession(season)`), so a dominant side's players aren't flagged for simply having the ball.
- `TRACKED_STATS`: the count fields of `PlayerMatchLine` except cards.
- `expected_at(baseline, stat, minutes_played, ExpectContext(possession_share, season_possession, team_men, opp_men))`:
  - on-ball stats × possession ÷ season possession; defensive stats × (1 − possession) ÷ (1 − season possession);
  - each missing teammate: × 0.85 attack and × 1.1 defence; each missing opponent: × 1.1 attack.
- `tail_p(observed, mean, dispersion, direction)`: negative binomial with variance `dispersion × mean`, Poisson at dispersion ≤ 1.05 (`math.lgamma`, no scipy).
- `assess(...) -> Deviation | None`: flags when p < 0.01 and the player has 30+ minutes. An "under" also needs 5+ expected, an "over" 3+ observed. Example: 18 forward passes per 90 with 3 by minute 60 → expected 12, p = 0.002, "under".
- `detect_deviations(match, baselines, t=(period, t), stats)`: every flag at that moment, strongest first. Minutes come from the line-ups plus sub and red-card events; counts come from `player_match_lines` on the events so far. Sprints need frames.
- `deviation_moments(match, baselines, stats) -> [(Moment(kind="player_deviation", level="player", trigger_metric=stat, trigger_value=observed), Deviation)]`: checks every 5 min, keeps at most 3 new flags per check, and flags each player once per stat group (`GROUP_OF`: passing stats, and shots/on target/goals, move together). Ids are `{match_id}-dNNN`. The Deviation carries `expected`, `baseline_per90`, and `p_value` for the store (TASK-14).
- **Measured** (season rounds 1–9 as baselines, 20 later fixtures): 0.9 flags per team per match. The most common are interceptions over, forward passes under, and progressive passes over or under.
- **Limit:** counts run from kickoff, so a change late in the match moves them slowly, and a tired player is soon substituted. The plan's "scripted midfielder flagged within 10 minutes" check couldn't hold, so it was dropped. A rolling-window detector (last 15 minutes) is the deferred fix if live narration needs faster flags.

