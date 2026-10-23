# Synthetic Match Engine

**Status:** level 1 built (TASK-4, fallback); level 3 built (TASK-9: the coupled loop using the TASK-8 kinematics, roles, and modifiers) and the default; level 4 (TASK-10: tactics, match flow, set pieces, scenarios) runs inside it.

## Levels (layered, each keeps the same output format)
1. Formation-anchored baseline (`engine/baseline.py`). Stays in the code as a fallback.
2. Kinematic, role-based players (`kinematics.py`): speed and acceleration caps, fatigue.
3. Event-coupled loop (`coupled.py`, `ball.py`, `decisions.py`, `constants.py`): ball physics, on-ball choices scored by pitch control × xT.
4. Tactics, set pieces, and scenarios (`tactics.py`, `set_pieces.py`, `scenario.py`, `scenarios/*.toml`).

## Entry points
- `engine/lineup.py`: `match_meta(league, fixture, seed, scenario_id="none") -> MatchMeta`. Squads are ordered **starting XI first** (GK, DF, MF, FW; best by `skill` per line, then by id), then the bench. `starting_xi(squad, formation)`; `FORMATION_LINES` (4-3-3, 4-2-3-1, 4-4-2, 3-5-2). Added time: 1–4 min + 0–59 s (first half), 3–7 min + 0–59 s (second). Kickoff 19:30 Colombia time (UTC-5).
- `engine/simulate.py`: `simulate_match(meta, scenario=None, level=3, tracking=True, profiles=None)`. `tracking=False` skips frames (identical events; level 3 about 4 s vs 13 s). `level=1` runs the baseline, `level=3` the coupled loop (`meta.engine_version` becomes `l3-0.1`). `profiles` turns on the modifier layer (`coupled.mods_from_profiles`: kickoff mods with match-day form); without it, mods are neutral. `scenario` is typed `object` until TASK-10.
- `engine/formations.py`: `formation_anchors(formation) -> (11, 2)` (d, w) in the team frame (attacking toward d = 105; GK 5 m, lines evenly spaced from 30 m to 62 m, at most 16 m apart in width). `to_team_frame(xy, attacks_right)` is its own inverse. Home attacks right in period 1.

## Level 1 (`engine/baseline.py`)
Each 0.1 s tick: (1) on-ball logic emits events from the current positions, (2) the frame is recorded, (3) players move. Off-ball target = anchor + `BLOCK_SHIFT` 0.35 × (ball − centre), ±4 m depth in or out of possession, width × 0.75 out of possession, smoothed (τ 0.9 s, speed cap 5.5 + 2.5·pace m/s). The nearest opponent presses the carrier. Ball phases: `held` (attached to the carrier, who drifts forward at 1.2 m/s), `flight` (straight line, height arc for passes over 22 m), `loose` (the nearest player of each team chases; an opponent winning it logs an `interception`), `dead` (the taker walks to the spot, then play resumes).
- Actions when the hold ends (1.5 + Exp(1.9) s; keepers 2–5 s): shot (only within 32 m of goal, probability falls with distance), carry (14%, or 20% in the final third; 3.5–5.5 m/s for 1.5–3.5 s), otherwise a pass. Receiver weights favour 16 m passes, forward progress, and open teammates. Success = sigmoid(skill, distance, pressure on passer and receiver). Failed passes are intercepted where the best-placed opponent cuts the line, or (18%) run out over the touchline.
- **Pass consistency:** a completed pass's receiver follows a scripted straight run that ends at the pass end point exactly at arrival (runs capped at 8 m/s); the passer holds the ball at release.
- Tackles: a defender within 1.5 m attempts with probability 0.012 per tick; 20% of attempts are fouls (free kick). Shots: xG from distance and angle; goal, save (the keeper holds), or wide (goal kick). Restarts: throw-in, goal kick, corner, free kick, and kickoff after a goal (45 s pause).
- No cards or substitutions at level 1.
- `launch_pass` decides the whole flight (receive, out, or interception) before changing state, and abandons the pass if it would land after the half ends. The 200-seed xT run exposed a crash when this happened after the state had changed (fixed in TASK-7).
- Frames are recorded as numpy arrays and turned into models once per half with `schemas.trusted` (no validation) and the GC paused. A full match takes about 7 s.

Seed-7 check (first fixture): about 1,000 passes at 83% completion, 17 shots, 1–2 goals, about 180 tackles, 50 fouls, 35 throw-ins, goal kicks, and corners combined. TASK-5 measures realism properly.

## Level 4
Tactics, phases, pressing triggers, cards, substitutions, set pieces, and scenarios: see [engine-level4.md](engine-level4.md).

## Level 2 kinematics (`engine/kinematics.py`, TASK-8.1)
`step_player(state: PlayerState(pos, vel, energy), target, urgency, attrs: Player, dt=0.1) -> PlayerState`: seek with arrival (braking speed sqrt(2 · 5 · 0.8 · dist)).
- Speeds: cruise = top speed × (0.15 + 0.85 · urgency) (0.25 until TASK-9 tuning). `v_max(pace) = 8 + 2 · pace` m/s; `max_speed(player, energy)` = `v_max` × (0.85 + 0.15 · energy).
- Caps: speeding up by `A_MAX` 3.5 m/s², slowing down by `DECEL_MAX` 5 m/s².
- Energy drains `8e-5 · v² · (1.3 − 0.6 · stamina)` per second and recovers 0.002 · (1 − energy) per second below 2 m/s. A realistic 10.6 km workload ends at about 0.48 energy (stamina 0.5): 0.39 at stamina 0.2, 0.57 at 0.8.
- The plan said `9.5 + 0.8 · pace` (about 9.9 m/s for an average player), which is above real top speeds and our 10 m/s realism ceiling.

## Level 2 roles (`engine/roles.py`, TASK-8.2)
`role_target(role, RoleContext(pos, anchor, ball, attacks_right, mark=None, line_depth=None, offside_line=None, run_started=False)) -> (absolute target, urgency)`. Roles work in the team frame (own goal at (0, 34)):
- `press`: 1 m goal-side of the ball (0.95). `mark`: 1.5 m goal-side of `mark` (0.6).
- `cover`: halfway between the anchor and a point 35% of the way from the ball to goal (0.5).
- `support`: 12 m from the ball at 50° forward, on the anchor's side (0.5).
- `gk_position`: on the goal–ball line, 1 + 0.08 × distance, at most 16 m out (0.7).
- `hold_line`: (`line_depth`, anchor width) (0.7). `defensive_line(anchors_depth, ball_depth, line_height)` = mean anchor + 0.35 · (ball − halfway) + (line_height − 0.5) · 16, kept at least 2 m behind the ball and at least 1 m.
- `run_in_behind`: waits 0.2 m onside of `offside_line` (0.45), then runs 14 m behind it (1.0). `offside_line(opponents, ball, attacks_right)` = the deeper of the second-last opponent, the ball, and halfway (absolute x). `draw_timing_error(rng, scale)` ~ N(0, 0.35 s × scale). Released 0.5 s early → offside at the pass; on time or 0.2 s early → onside (tested with kinematics and `offside_players`).

## Ball physics (`engine/ball.py`, TASK-9.1)
- `flight(start, end, kind, speed_ms, loft_deg=None) -> Trajectory` (`t`, `xyz` at 10 Hz, `duration`, `reaches_end`, `positions_at(t)`, `out_of_play()`). Integrated in 0.02 s sub-steps.
- Air drag `DRAG_K = 0.010`/m (dv/dt = −k|v|v, a real ball's value); rolling resistance `ROLL_DECEL = 0.7` m/s²; bounces keep 50% of vertical and 75% of horizontal speed. A 30 m ground pass at 15 m/s takes 2.5 s; a soft one stops short.
- Lofted balls: `loft_for(speed, distance)` solves the launch angle (8–45°) so the first bounce lands on the target. Shots fly at 5° by default.
- `draw_speed(rng, kind, distance, skill)`: ground 10–22, lofted 14–30, shots 18–32 m/s (harder for longer balls, harder shots for better players).
- A trajectory stops at the first sample after it crosses a line; `out_of_play()` gives the time and the exact point on the line. `in_goal_mouth(point)`: on a goal line, within 3.66 m of the centre, under 2.44 m.
- `restart_for(point, last_touch_attacks_right)`: touchline → throw-in; goal line → goal kick if the last touch was by the team attacking that goal, corner otherwise.
- `deflect(rng, incoming, speed, "block" | "parry")`: a block keeps 20–60% of the speed, turned by N(0, 55°); a parry keeps 15–35%, pushed ±85° ± N(0, 30°) to one side, so some go behind for corners.

## Decisions (`engine/decisions.py`, TASK-9.2)
- `enumerate_options(frame, carrier_id, ctx: DecisionContext) -> list[Option]`: passes to teammates 4–60 m away (aimed up to 1 s ahead of a moving teammate), through balls 7 m ahead of teammates at least 5 m deeper (within 40 m), three 7 m carries (0°, ±35°), a shot within 30 m, and a clearance when pressed within 5 m in the own third.
- Score: `score_option(pc, xt_gain, risk) = pc · xt_gain − risk`, where `pc` is offside-filtered pitch control at the end point (0 for a pass to a visibly offside teammate) and `risk = (1 − pc) · (0.01 + xT here + opponent xT at the end) / risk_weight` (losing the ball loses what we had). A shot scores `xg − keep_weight · xT(here) − shot_cost`; a clearance adds `clear_bonus` (engine sets them: 0.55, 0.03, 0.01).
- Shot xG in the options includes pressure (`pressure_factor`): × 0.6 per defender within 1.5 m, × 0.8 per defender within 1 m of the line to goal, × 0.6 if the keeper is within 3 m. The engine shoots with that xG × (0.85 + 0.3 · skill).
- `shot_xg(pos, attacks_right, skill)`: logistic in the goal's opening angle and distance (about 0.39 at 6 m, 0.18 at 11 m, 0.09 at 16 m, 0.04 at 25 m, central; bias −1.7 since TASK-10.1), × (0.85 + 0.3·skill).
- `choose(options, skill, rng, temperature_mult=1.0)`: softmax over min-max normalized scores, temperature `(0.05 + 0.6·(1 − skill)) × decision_temperature`. Skill 0.95 picks the best of a typical set > 70% of the time; skill 0.2 < 45%.
- `decision_extras(chosen, options)` → `chosen_score`, `best_score`, `best_option` for `Event.extras`. About 1 ms per decision.

## Level 3 loop (`engine/coupled.py`, TASK-9.3)
`Coupled(meta, tracking, profiles=None)` (profiles give mods, club tactics, roles); `simulate_coupled(meta, tracking, profiles)`. Each tick: `logic` → ball position → record → `move` (`step_players`, vectorized `step_player`).
- **Decisions** every 0.8–2.0 s of possession, on a frame 0.3 s old (`PERCEPTION_LAG_TICKS`). Restarts (throw-in ≤ 30 m, kickoff, goal kick, corner) and keepers only pass or clear.
- **Kicks** follow `ball.flight` with angle error `PASS_ERR_DEG · (1.5 − skill) · pass_error`. Passes ≥ 30 m and corners are lofted. A ball that would roll into the passer's own net is played softer. At the kick, a Bernoulli draw `pc^0.55 · (0.9 + 0.1·skill)` decides receiver vs the opponent who can reach the path first (6.5 m/s after 0.3 s); with no such opponent, the receiver takes a heavy touch.
- **Control:** within 1.2 m of the ball's path since the last tick and under 1.8 m high (keepers 2 m in their box, any ball but the shot itself). The pass ends at the receiver's feet (`extras.arrival_t`). After planned arrival + 0.6 s anyone may collect. An opponent winning it logs an `interception`; within 25 m of his goal a defender instead gets a safe touch half the time (a `clearance` with `extras.deflection`, aimed 80% at his goal line, 8–15 m/s, never into his own goal).
- **Shots:** aim inside a post, error `SHOT_ERR_DEG` 17° · (1.5 − skill), loft 2–18°. A defender within 1.6 m of the line blocks with 0.5 (`extras.blocked`, deflected); on target, the keeper saves with `1 − 3·xg + 0.15·(skill − 0.5)` (0.3–0.97, so goals track xG), catching 75% of shots under 22 m/s and 30% above, else parrying (`extras.parried`, pushed away from goal).
- **Out of play:** at the trajectory's crossing point; goal mouth → goal (scorer = shooter, else own goal), else `restart_for` by last touch. `out` events carry `extras.restart`. Throw-ins: nearest opponent; corners: nearest attacker; goal kicks: keeper at 5.5 m.
- **Duels:** the nearest defender within 1.5 m tries 2.6% per tick; 45% of tries are fouls (× 0.18 in his own box; `award_foul`, `extras.mods`); wins `0.5 + 0.3·Δskill`, half knock it loose.
- **Off ball:** the phase shape (`tactics.formation_shape`) shifted 0.35 with the ball (deadband 5 m, urgency distance/45, 0.05–0.5); the defending DF line holds `defensive_line`; players in possession stay 1 m onside (but the runner); nearest defender presses (zone 45 + 60·press_intensity m from goal, else contains 4 m off), next covers; two nearest teammates support; after a turnover players over 6 m from their spot run back (0.85) for 5 s.
- **Phases** (`team_phase`): in possession `counter` for 6 s after winning the ball in open play, else `build_up`; out of possession `set_piece` (defending a corner or free kick within 35 m), `high_press` (a pressing trigger, or ball 70+ m from goal with press_intensity ≥ 0.55), `low_block` (ball within 35 m, or 55 m for teams pressing < 0.35), else `mid_block`.
- **Pressing triggers:** when a team receives after a back pass into its last 40 m (losing 6+ m), a heavy touch, or while running toward its own goal (> 2.5 m/s), the other team reacts with probability press_intensity if a defender is within 10 m: a `pressure` event (`extras.trigger`), `high_press` shape, and the nearest two close down for 3 s.
- **Runs and offside:** the most advanced forward hovers 0.2 m onside. Before each decision he runs with probability `1 − exp(−rate · window)`, `rate = tactics.runs_in_behind_rate` (or a neutral rate without profiles), releasing at the decision minus `N(0, 0.35 · run_timing_sd)`; offside is judged on the real frame at the kick and flagged when he controls the ball (`offside` event, `timing_error_s`, mods; free kick to the defenders). Tested: 0.5 s early → offside, on time → onside.
- Events stay dicts until the half ends (sorted by time, then ids assigned), so ends and outcomes are written when the ball is controlled.

## Profile → behavior mapping (`engine/modifiers.py`, TASK-8.3)
Caps: `SUBTLE_CAP = 0.06` by default, `STORYLINE_CAP = 0.20` while a scenario beat targets the player or team.
- `Modifiers.for_player(profile, club, MatchContext(minute, score_diff, is_home, energy, confidence, storyline, congestion_days, form)) -> PlayerMods`. Each property is a multiplier (`foul_rate`, `decision_temperature`, `pass_error`, ...); `effects` holds the raw effects.
- `Modifiers.for_team(club, ctx) -> TeamMods`: tactics `press_intensity`, `line_height`, `tempo`, `width`, `directness` (uncapped settings), plus capped `chase_urgency` (losing after minute 60, stronger with low job security) and `home_boost`.
- Traits enter as `dev(x) = clip((x − 0.5)/0.25, ±1)`, with term weights summing to at most 1, so nothing saturates early. Composure counts double when the game is late and close (minute 75+, margin ≤ 1). The home crowd adds `max(0, home_advantage − 0.5) · 0.3` to composure and confidence. Run timing = −½·mean(discipline, composure, experience) + ½·fatigue.
- `match_form(profile, rng)` draws match-day form from N(0, 0.25 + 0.75 · (1 − consistency)), clipped to [−1, 1], and passed in through the context. `pair_mods(chemistry)` gives pass completion and early runs for a passing pair.
- **Record only what's relevant:** `to_extras(only=(...))` keeps the action's own modifiers for `Event.extras["mods"]`. A player has about 16 non-zero effects, too many to attach to every event.
- **Size (400 players, neutral context):** mean |effect| about 0.03 for aggression and technical traits, with 13–14% of players at the cap; composure and run timing about 0.01–0.015 (they're scaled by pressure and fatigue).

| Attribute | Behavior |
|---|---|
| composure | decision temperature under pressure, late, close score |
| aggression | tackle attempts, fouls, cards, press urgency |
| confidence | in-match state: up after success, down after errors; risk and shooting |
| leadership | teammates' composure; shape after conceding |
| consistency | match-day form variance |
| work_rate | off-ball distance, pressing, energy drain |
| tactical_discipline | how tightly the player holds the formation anchor |
| risk_tolerance | xT gain vs completion weight in option scoring |
| technical ratings | error of the matching action (pass, touch, dribble, shot, cross, tackle, aerial, GK) |
| injury / schedule | starting energy |
| home advantage | composure and confidence |
| chemistry (pair) | pass completion, run timing |
| tactical_discipline, composure, experience, fatigue | spread of run timing → offsides (subtle) |
| crossing, aerial + height, finishing, composure | corner delivery, aerial duels, direct free kicks, penalties |
| tactical identity (club) | shape, pressing triggers, line height, tempo, width, directness |
| manager style / job security | in-game changes and sub timing when losing |
| career ambitions | narrative only |

## Key constants
All level-3 tunables are in `engine/constants.py` (timing, shape, pressing, runs, control, passing, shooting, duels); tuning changes only that file. `kinematics.MIN_CRUISE_SHARE` is 0.15 (a walk at urgency 0).

## Realism (`engine/validate.py`, `engine/realism_ranges.py`, `scripts/realism_report.py`)
`validate_match(data) -> RealismReport` checks every per-team metric in `RANGES` (check names like `passes:<club_id>`); `team_stats(data)` exposes the raw values. `validate_many(iterable)` averages over team-matches, adds `in_range_share` and `goals_per_match`, and consumes a generator one match at a time. Possession is the share of passes; PPDA = opponent passes in their own 60% ÷ our tackles, interceptions, and fouls in that zone (at least 1 action); distance, top speed, and sprints (> 7.0 m/s for ≥ 1 s) come from outfield players' frames.

Distance and sprints are per full match (players on for a sixth of it or more, scaled to the whole match), so substitutes don't dilute them. Per match over many matches: goals 2.2–3.4, penalties 0.2–0.4, set-piece goal share 0.20–0.35. Also per team: offsides 0–6, throw-ins 15–30, goal kicks 4–12, corners 2–9 (credited to the team awarded the restart, i.e. the opponent of the last touch), fouls 8–18.

Level 3 with profiles, set pieces, and the retrained xT (TASK-10.5, `docs/realism.md`): **18/18 pass**. Passes 620, completion 0.82, shots 12.5, on target 0.42, PPDA 7.7, tackles 17.6, 12.3 km, top speed 9.2, sprints 29.6, offsides 2.45, throw-ins 26.2, goal kicks 4.1, corners 3.0, fouls 10.9, 2.90 goals and 0.30 penalties per match, set-piece goal share 0.22. Thin margins: goal kicks, set-piece share.

Earlier, at TASK-9 (no profiles): **16/16 pass** (passes 623, completion 0.83, shots 13.1, on target 0.37, PPDA 8.8, tackles 19.7, 11.7 km, top speed 9.1, sprints 10.8, offsides 1.9, throw-ins 26.3, goal kicks 5.7, corners 2.4, fouls 11.6, 2.25 goals per match). Thin margins: sprints, corners, goals.

Level 1 over 20 seeds: 6/11 pass. Passing, completion (0.82), shots (12.8), on-target ratio, possession, and distance (9.7 km) are in range. PPDA (3.2) and tackles (91.5) are far off (pressing on every carrier); top speed (7.4 m/s) and sprints (9.6) sit just under (speed caps); goals (2.15 per match) sit just under. The fixes are owned by TASK-8 to TASK-10.

## Scenarios
See [engine-level4.md](engine-level4.md). Storyline files: TASK-10.3.
