"""The 8 storylines in `scenarios/*.toml`."""

from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from functools import cache
from pathlib import Path

from matchmind.engine.scenario import SCENARIO_DIR, Scenario, load_scenario, scenario_meta
from matchmind.engine.simulate import simulate_match
from matchmind.league.league import build_league
from matchmind.league.profiles import build_profiles

STORYLINES = {
    "comeback_red_card", "press_collapse", "keeper_heroics", "late_sub_wins_it",
    "derby_chaos", "chess_match_0_0", "underdog_low_block", "counter_attack_masterclass",
}  # fmt: skip


def _paths() -> list[Path]:
    return sorted(SCENARIO_DIR.glob("*.toml"))


def test_all_storylines_load() -> None:
    league = build_league()
    scenarios = [load_scenario(p) for p in _paths()]
    assert {s.scenario_id for s in scenarios} == STORYLINES
    for path, s in zip(_paths(), scenarios, strict=True):
        assert path.stem == s.scenario_id
        assert s.beats, s.scenario_id
        meta = scenario_meta(league, s)
        assert (meta.home.club_id, meta.away.club_id) == (s.home_club_id, s.away_club_id)
        assert meta.scenario_id == s.scenario_id and meta.seed == s.seed


def _run(args: tuple[str, int, bool]) -> tuple[str, Counter[str], int, int]:
    """(scenario id, event type counts, home goals, away goals) for one seed."""
    scenario_id, seed, with_beats = args
    league = build_league()
    s = load_scenario(SCENARIO_DIR / f"{scenario_id}.toml")
    s = s.model_copy(update={"seed": seed, "beats": s.beats if with_beats else []})
    meta = scenario_meta(league, s)
    data = simulate_match(meta, s, level=3, tracking=False, profiles=_profiles())
    types = Counter(e.type for e in data.events)
    types.update(f"card:{e.extras['card']}:{e.team_id}" for e in data.events if e.type == "card")
    goals = Counter(e.team_id for e in data.events if e.type == "goal")
    return scenario_id, types, goals[meta.home.club_id], goals[meta.away.club_id]


@cache
def _profiles():  # type: ignore[no-untyped-def]
    return build_profiles(build_league(), seed=2026)


def test_storylines_run() -> None:
    jobs = [(p.stem, load_scenario(p).seed, True) for p in _paths()]
    with ProcessPoolExecutor() as pool:
        results = {sid: types for sid, types, _, _ in pool.map(_run, jobs)}
    s = load_scenario(SCENARIO_DIR / "comeback_red_card.toml")
    assert results["comeback_red_card"][f"card:red:{s.home_club_id}"] >= 1
    assert all(types["shot"] > 0 for types in results.values())


def test_beats_shift_outcome() -> None:
    """The 10-man team in `comeback_red_card` wins more often than without the beats."""
    seeds = range(1, 21)
    jobs = [("comeback_red_card", s, beats) for beats in (True, False) for s in seeds]
    with ProcessPoolExecutor() as pool:
        results = list(pool.map(_run, jobs))
    scripted = [h > a for _, _, h, a in results[:20]]
    control = [h > a for _, _, h, a in results[20:]]
    assert sum(scripted) > sum(control)
    # The goal beats' direct effect: the ten-man side scores at least 0.5 more per match.
    scored = sum(h for _, _, h, _ in results[:20]), sum(h for _, _, h, _ in results[20:])
    assert scored[0] - scored[1] >= 10


def test_scenario_round_trip(tmp_path: Path) -> None:
    s = load_scenario(_paths()[0])
    path = tmp_path / "x.toml"
    lines = [f'scenario_id = "{s.scenario_id}"', f'title = "{s.title}"',
             f'home_club_id = "{s.home_club_id}"', f'away_club_id = "{s.away_club_id}"',
             f"seed = {s.seed}"]  # fmt: skip
    path.write_text("\n".join(lines) + "\n")
    assert load_scenario(path) == Scenario(**{**s.model_dump(), "beats": []})
