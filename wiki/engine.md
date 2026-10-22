# Synthetic Match Engine

**Status:** level 1 built (TASK-4); levels 2–4 planned (TASK-8 to TASK-10).

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
