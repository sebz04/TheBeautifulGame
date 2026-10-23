# Engine Level 4: Tactics, Match Flow, Set Pieces, Scenarios

Level 4 runs inside the level-3 loop (`engine/coupled.py`); see [engine.md](engine.md) for the loop, ball, and decisions. Tunables are in `engine/constants.py`.

## Tactics (`engine/tactics.py`, TASK-10.1)
- `formation_shape(formation, phase, n_players=11) -> (n, 2)` (team frame, keeper first): outfield depth `46 + (d − 46) · scale + offset`, width × scale, keeper at a phase depth (`constants.PHASE_SHAPE`): build_up (+4, 1.15, 1.15), counter (+12, 1.3, 1.0), mid_block (−4, 0.8, 0.8), low_block (−16, 0.6, 0.7), high_press (+10, 0.8, 0.85), set_piece (−28, 0.3, 0.55). With 10 or 9 players the most advanced slots go first (the widest of a line), and lines are re-spaced. `shape_lines(formation, n)` gives each row's line.
- `pressing_trigger(last_event, frame, pressing_team, attacks_right) -> bool`: an opponent's back pass (6+ m back, ending in his last 40 m), a poor touch (`extras.heavy_touch`), or the ball-nearest opponent moving toward his own goal faster than 2.5 m/s.
- `runs_in_behind_rate(club, role, opponent_line_height, pace)`: runs per minute in possession = 0.7 × (0.5 + directness) × (0.7 + 0.6·tempo) × role × (0.7 + 0.6·pace) × (0.5 + line height). Role factors: poacher 1.35, pressing/inside forward 1.2, winger 1.1, shadow striker 1.0, false nine 0.8, target man 0.6, others 0.7. A tactic, so uncapped.
- **In the engine (`team_phase`):**
  - In possession: `counter` for 6 s after winning the ball in open play, else `build_up`.
  - Out of possession, in order:
    1. `set_piece`: defending a corner or free kick within 35 m.
    2. `high_press`: after a pressing trigger, or with the ball 70+ m from goal and press_intensity ≥ 0.55.
    3. `low_block`: ball within 35 m, or within 55 m for teams pressing below 0.35.
    4. `mid_block`: everything else.
  - **Pressing triggers:** the team reacts with probability press_intensity, and only if a defender is within 10 m. It emits a `pressure` event (`extras.trigger`); the nearest two then close down for 3 s.

## Match flow (`coupled.py`, TASK-10.2)
- `Coupled(meta, tracking, profiles=None, scenario=None)`. Each slot's ratings come from `load_slot`:
  - `aerial`, `crossing`, `finishing`, height, role and match-day form from the profile;
  - without profiles: skill for every rating, 182 cm, neutral role and form.
- Modifiers refresh every 5 minutes, and after goals, substitutions and beats. The refresh uses the minute, score difference, energy, home side and storyline window (`update_mods`). Tactic overrides from beats are applied on top (`_with_tactics`).
- **Cards (`book`):** each foul is a yellow with probability 0.20 × the fouler's foul_rate modifier, or a red with 0.006 × foul_rate. Keepers are never sent off. A second yellow adds a `card` event with `extras.second_yellow`, then the red.
- **Sent off (`send_off`):** the slot leaves the pitch for good. It's parked off the pitch, left out of frames, decision frames and pitch control, and every nearest-player or interception check. The phase shape then uses `n_players = 10` (or 9).
- **Substitutions:** managers make changes at minutes 60, 68, 76 and 84 (at most 5), at the next dead ball. The most tired outfield player makes way for the best bench player of the same position, who comes on with full energy. The `sub` event has `player_id` = off and `receiver_id` = on. Frames follow `rosters` (who is in each slot, per frame; `baseline.build_frames(..., rosters, roster_idx)`).

## Set pieces (`engine/set_pieces.py`, TASK-10.2)
- **Fouls (`award_foul`):** inside the attacked box → `penalty`; within 17–30 m of goal → a free kick taken by the best finisher; otherwise the fouled player restarts. Defenders foul 0.18× as often in their own box.
- **Penalties:** the best finisher takes it after a 40–70 s pause, with everyone outside the box and the keeper on his line. `penalty_scores` gives 0.76 × composure (the inverse of the decision-temperature modifier); misses are 65% saved, 35% wide. Shots carry `extras.set_piece = "penalty"` and `xg = 0.76`.
- **Direct free kicks:** 55% of free kicks in the 17–30 m band. `free_kick_xg` = 0.10 · e^(−(d − 18)/9) · (0.7 + 0.6·finishing), lofted 8–14°.
- **Corners:** 10% are played short; the rest are delivered.
  - The five best aerial players take box spots.
  - `corner_delivery`: the ball drops around (97, 34 ∓ 3) with SD 2 + 6·(1 − crossing) m.
  - `keeper_claims`: balls dropping into the six-yard box are claimed with probability 0.45 + 0.3·(aerial − 0.5).
  - Otherwise `aerial_duel` between the attacker and defender nearest the drop: sigmoid(3·Δaerial + 0.25·Δheight per 10 cm).
  - The winner reaches up to 2 m and 2.8 m high. An attacker heads at goal (`header_xg` = 0.55 × `shot_xg`, 14 m/s, `extras.header`); a defender heads it clear (a safe touch).
- Goals keep the shot's `set_piece` tag, so set-piece and open-play goals can be split.

## Scenarios (`engine/scenario.py`, TASK-10.2)
`Scenario(scenario_id, title, home_club_id, away_club_id, seed, beats)`, read from TOML by `load_scenario(path)`. Beats are sorted by minute, and each is `Beat(minute 0–90, kind, team, params)`. Beats bias the match; they never teleport it. A beat opens a 15-minute storyline window for its team (modifier cap 20%).

| Kind | Effect |
|---|---|
| `red_card` | The team's next foul (tackle rate × 3 until then) is a red |
| `goal` | Team xG × 1.5 for 15 minutes |
| `sub` | A substitution at the next dead ball (`params.slot` 1–10 to pick who goes off) |
| `tactic_change` | Overrides `press_intensity`, `line_height`, `tempo`, `width`, `directness` (each 0–1) |
| `press_intensity` | Overrides press intensity (`params.value`) |
| `fatigue_spike` | Drains the team's energy (`params.amount`, default 0.2) |
