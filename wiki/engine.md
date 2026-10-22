# Synthetic Match Engine

**Status:** level 1 built (TASK-4); level-2 building blocks in progress (TASK-8); levels 3–4 planned (TASK-9, TASK-10).

## Levels (layered, each keeps the same output format)
1. Formation-anchored baseline (`engine/baseline.py`). Stays in the code as a fallback.
2. Kinematic, role-based players (`kinematics.py`): speed and acceleration caps, fatigue.
3. Event-coupled loop (`simulate.py`, `ball.py`, `decisions.py`): ball physics, on-ball choices scored by pitch control × xT.
4. Tactics and scenarios (`tactics.py`, `scenario.py`, `scenarios/*.yaml`).

## Entry points
- `engine/lineup.py`: `match_meta(league, fixture, seed, scenario_id="none") -> MatchMeta`. Squads are ordered **starting XI first** (GK, DF, MF, FW; best by `skill` per line, then by id), then the bench. `starting_xi(squad, formation)`; `FORMATION_LINES` (4-3-3, 4-2-3-1, 4-4-2, 3-5-2). Added time: 1–4 min + 0–59 s (first half), 3–7 min + 0–59 s (second). Kickoff 19:30 Colombia time (UTC-5).
- `engine/simulate.py`: `simulate_match(meta, scenario=None, level=3, tracking=True)`. `tracking=False` skips frames (identical events, about 2.8 s vs 6.5 s; for training and season history). `level=1` runs the baseline; `level=3` raises `NotImplementedError` until TASK-9. `scenario` is typed `object` until TASK-10 defines `Scenario`.
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

## Level 2 kinematics (`engine/kinematics.py`, TASK-8.1)
`step_player(state: PlayerState(pos, vel, energy), target, urgency, attrs: Player, dt=0.1) -> PlayerState`: seek with arrival (braking speed sqrt(2 · 5 · 0.8 · dist)).
- Speeds: cruise = top speed × (0.25 + 0.75 · urgency). `v_max(pace) = 8 + 2 · pace` m/s; `max_speed(player, energy)` = `v_max` × (0.85 + 0.15 · energy).
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

## Set pieces and out of play (planned: TASK-9, TASK-10)
Level 1 today, per match: about 31 throw-ins, 13 goal kicks, **0 corners** (nothing makes defenders put the ball out), 45 free kicks (fouls are about 2× too frequent), and **no penalties** (box fouls restart as free kicks). Planned fixes:
- **TASK-9:** out of play follows the ball's path, and the last touch decides the restart. Clearances, blocked shots, and parried saves can put the ball out.
- **TASK-10:** corner delivery (`crossing`) and aerial duels (`aerial` + height) leading to headers; direct free kicks within about 30 m (`finishing`); penalties (about 0.76 conversion, composure subtle). Shots tagged `extras.set_piece`.
- New realism ranges: throw-ins, goal kicks, corners, fouls, penalties, and set-piece goal share.

## Profile → behavior mapping (design; built in TASK-8.3)
Caps: `SUBTLE_CAP = 0.06` by default, `STORYLINE_CAP = 0.20` while a scenario beat targets the player or team. Active modifiers are recorded in `Event.extras["mods"]`.

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
_Fill in from `engine/constants.py` once it exists._

## Realism (`engine/validate.py`, `engine/realism_ranges.py`, `scripts/realism_report.py`)
`validate_match(data) -> RealismReport` checks every per-team metric in `RANGES` (check names like `passes:<club_id>`); `team_stats(data)` exposes the raw values. `validate_many(iterable)` averages over team-matches, adds `in_range_share` and `goals_per_match`, and consumes a generator one match at a time. Possession is the share of passes; PPDA = opponent passes in their own 60% ÷ our tackles, interceptions, and fouls in that zone (at least 1 action); distance, top speed, and sprints (> 7.0 m/s for ≥ 1 s) come from outfield players' frames.

Level 1 over 20 seeds (`docs/realism.md`): 6/11 pass. Passing, completion (0.82), shots (12.8), on-target ratio, possession, and distance (9.7 km) are in range. PPDA (3.2) and tackles (91.5) are far off (pressing on every carrier); top speed (7.4 m/s) and sprints (9.6) sit just under (speed caps); goals (2.15 per match) sit just under. The fixes are owned by TASK-8 to TASK-10.

## Scenarios
_List the storyline YAML files and what each one tests._
