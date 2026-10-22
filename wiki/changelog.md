# Changelog

Format: `YYYY-MM-DD · TASK-ID · summary · pages touched`. Newest first.

- 2026-10-22 · TASK-9.3 · level-3 coupled engine (coupled.py, constants.py), vectorized step_players, shared build_frames, set-piece and offside realism checks; 16/16 checks over 20 seeds; level 3 is the default · README, engine, data-model, decisions
- 2026-10-22 · TASK-9.2 · on-ball decisions (options, offside-filtered pitch control scoring, skill softmax, decision extras), shot_xg, offside EventType · README, engine, data-model
- 2026-10-22 · TASK-9.1 · ball physics (drag, rolling, bounces, lofted angle solve), out of play at the crossing point, restart by last touch, deflections · README, engine, decisions
- 2026-10-21 · TASK-8.3 · modifier layer: capped player and team modifiers, pressure, home, fatigue-dependent run timing, match form, pair chemistry, filtered extras · README, engine
- 2026-10-21 · TASK-8.2 · role targets (mark, press, cover, support, run in behind, hold line, keeper), defensive_line, offside_line, run timing error · README, engine
- 2026-10-21 · TASK-8.1 · level-2 kinematics: seek with arrival, speed/accel/decel caps, energy drain calibrated on a 10.6 km workload · README, engine
- 2026-10-21 · planning · set pieces and out of play: TASK-9/10 additions, new realism ranges, corner_pressure moment · engine, decisions
- 2026-10-21 · TASK-7 · xT (Singh) trained on 200 level-1 matches; normalize_events; simulate_match(tracking=False); fixed an engine crash on passes abandoned at half end; .gitignore now tracks data/models · README, stats, engine
- 2026-10-21 · TASK-6.1 · offside_players and the attacks_right option for pitch control; shared engine.pitch.attacks_right (validate.py reuses it) · README, stats, data-model
- 2026-10-21 · planning · offside design: TASK-6.1 pitch-control filter; runs in behind and timing in TASK-8/9/10; offside_trap moment · engine, decisions
- 2026-10-21 · TASK-6 · vectorized pitch control, Friends of Tracking reference vendored for parity tests, credits in README and notices · README, stats
- 2026-10-21 · TASK-5 · realism validator (validate_match, validate_many, team_stats), report script, level-1 baseline in docs/realism.md (6/11 pass) · README, engine
- 2026-10-21 · planning · event-exact `metrics_at` for MCP and the Verifier; snapshots per moment (plan Tasks 14, 15) · stats, decisions
- 2026-10-21 · TASK-4.2 · level-1 engine: line-ups and match meta, formation anchors, Markov possession chain with consistent pass endpoints, set pieces; schemas.trusted; faster frame reads · README, engine, data-model
- 2026-10-21 · TASK-4.1 · match file I/O: meta.json, events.parquet, long-format frames.parquet; pyarrow added · README, data-model
- 2026-10-21 · TASK-3.5 · league re-themed to Colombia: barrio clubs in 8 cities, 5 derbies, South American nationalities and names, Colombian-scale USD money, compatriot chemistry, Colombian blocklists · README, league, decisions, glossary
- 2026-10-21 · TASK-3.4 · origins, transfer chains, previous league clubs, legends, build_profiles · README, league
- 2026-10-21 · TASK-3.3 · club profiles (status, style, tactics, ownership, budgets) and squad chemistry · README, league
- 2026-10-21 · TASK-3.2 · player profiles from latent factors with real-life distributions · README, league
- 2026-10-21 · TASK-3.1 · 20 LA clubs, squads from latent factors, 38-round fixtures, real-name blocklists · README, league (new)
- 2026-10-21 · TASK-2 · shared pydantic schemas and pitch geometry · README, data-model
- 2026-10-21 · TASK-1.3 · wiki check script, pre-commit hook, CI per-commit wiki step · README, conventions
- 2026-10-21 · TASK-1.2 · CI workflow, license gate, THIRD_PARTY_NOTICES · README, conventions, infra-ops
- 2026-10-21 · TASK-1.1 · uv project, Settings, first tests, README quick start · README, conventions, infra-ops
- 2026-10-21 · planning · constitution, plan, tasks with sub-tasks, open-source review, wiki created · all
