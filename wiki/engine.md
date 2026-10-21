# Synthetic Match Engine

**Status:** planned (TASK-3 to TASK-10).

## Levels (layered, each keeps the same output format)
1. Formation-anchored baseline (`engine/baseline.py`). Stays in the code as a fallback.
2. Kinematic, role-based players (`kinematics.py`): speed and acceleration caps, fatigue.
3. Event-coupled loop (`simulate.py`, `ball.py`, `decisions.py`): ball physics, on-ball choices scored by pitch control × xT.
4. Tactics and scenarios (`tactics.py`, `scenario.py`, `scenarios/*.yaml`).

## Key constants
_Fill in from `engine/constants.py` once it exists._

## Realism
_Link the current `docs/realism.md` summary here (pass/fail per check)._

## Scenarios
_List the storyline YAML files and what each one tests._
