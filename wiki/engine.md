# Synthetic Match Engine

**Status:** planned (TASK-3 to TASK-10).

## Levels (layered, each keeps the same output format)
1. Formation-anchored baseline (`engine/baseline.py`). Stays in the code as a fallback.
2. Kinematic, role-based players (`kinematics.py`): speed and acceleration caps, fatigue.
3. Event-coupled loop (`simulate.py`, `ball.py`, `decisions.py`): ball physics, on-ball choices scored by pitch control × xT.
4. Tactics and scenarios (`tactics.py`, `scenario.py`, `scenarios/*.yaml`).

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
| tactical identity (club) | shape, pressing triggers, line height, tempo, width, directness |
| manager style / job security | in-game changes and sub timing when losing |
| career ambitions | narrative only |

## Key constants
_Fill in from `engine/constants.py` once it exists._

## Realism
_Link the current `docs/realism.md` summary here (pass/fail per check)._

## Scenarios
_List the storyline YAML files and what each one tests._
