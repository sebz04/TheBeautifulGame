import numpy as np
import pytest

from matchmind.engine.decisions import (
    DecisionContext,
    Option,
    choose,
    decision_extras,
    enumerate_options,
    score_option,
    shot_xg,
)
from matchmind.schemas import PlayerPos, TrackingFrame
from matchmind.stats.xt import load_xt

HOME, AWAY = "home", "away"


def _frame(
    home: list[tuple[float, float]], away: list[tuple[float, float]], ball: tuple[float, float]
) -> TrackingFrame:
    players = [
        PlayerPos(player_id=f"{team}-{i}", team_id=team, x=x, y=y, vx=0.0, vy=0.0)
        for team, xy in ((HOME, home), (AWAY, away))
        for i, (x, y) in enumerate(xy)
    ]
    return TrackingFrame(match_id="m", frame=0, period=1, t=0.0, ball=(*ball, 0.11),
                         players=players)  # fmt: skip


def _ctx(**kw: object) -> DecisionContext:
    base: dict[str, object] = {"team_id": HOME, "attacks_right": True, "xt": load_xt(),
                               "goalkeepers": frozenset({"home-0", "away-0"})}  # fmt: skip
    base.update(kw)
    return DecisionContext(**base)  # type: ignore[arg-type]


# Home attacks right. Carrier home-1 in midfield; away defends with a line at x = 80.
HOME_XY = [(5.0, 34.0), (50.0, 34.0), (45.0, 15.0), (60.0, 50.0), (78.0, 30.0)]
AWAY_XY = [(102.0, 34.0), (80.0, 20.0), (80.0, 40.0), (60.0, 52.0), (55.0, 20.0)]


def _options(home: list[tuple[float, float]] = HOME_XY, carrier: int = 1) -> list[Option]:
    frame = _frame(home, AWAY_XY, home[carrier])
    return enumerate_options(frame, f"home-{carrier}", _ctx())


def test_score_option_formula() -> None:
    assert score_option(0.8, 0.05, 0.01) == pytest.approx(0.8 * 0.05 - 0.01)


def test_enumerates_passes_and_carries_but_no_shot_from_midfield() -> None:
    opts = _options()
    kinds = {o.kind for o in opts}
    assert {"pass", "carry"} <= kinds
    assert "shot" not in kinds
    targets = {o.target_player_id for o in opts if o.kind == "pass"}
    assert targets == {"home-0", "home-2", "home-3", "home-4"}
    assert all(0.0 <= o.pc_prob <= 1.0 for o in opts)


def test_shot_offered_near_goal() -> None:
    home = [(5.0, 34.0), (92.0, 36.0), (45.0, 15.0), (60.0, 50.0), (78.0, 30.0)]
    frame = _frame(home, AWAY_XY, home[1])
    shots = [o for o in enumerate_options(frame, "home-1", _ctx()) if o.kind == "shot"]
    assert len(shots) == 1 and shots[0].end[0] == pytest.approx(105.0)


def test_marked_teammate_scores_below_open_teammate() -> None:
    by_target = {o.target_player_id: o for o in _options() if o.kind == "pass"}
    # home-3 at (60, 50) has away-3 two metres away; home-2 at (45, 15) is free.
    assert by_target["home-3"].pc_prob < by_target["home-2"].pc_prob


def test_offside_teammate_scores_near_zero() -> None:
    home = [(5.0, 34.0), (50.0, 34.0), (45.0, 15.0), (60.0, 50.0), (90.0, 34.0)]  # beyond line
    by_target = {o.target_player_id: o for o in _options(home) if o.kind == "pass"}
    assert by_target["home-4"].pc_prob == 0.0
    assert by_target["home-4"].score <= 0.0
    assert by_target["home-4"].score < max(o.score for o in by_target.values())


def test_clearance_offered_under_pressure_in_own_third() -> None:
    home = [(3.0, 34.0), (12.0, 30.0), (20.0, 50.0), (30.0, 10.0), (40.0, 34.0)]
    away = [(102.0, 34.0), (13.5, 31.0), (25.0, 40.0), (60.0, 52.0), (55.0, 20.0)]
    frame = _frame(home, away, home[1])
    kinds = {o.kind for o in enumerate_options(frame, "home-1", _ctx())}
    assert "clear" in kinds
    frame_free = _frame(home, AWAY_XY, home[1])
    assert "clear" not in {o.kind for o in enumerate_options(frame_free, "home-1", _ctx())}


def test_direction_is_mirrored_when_attacking_left() -> None:
    mirrored = [(105.0 - x, 68.0 - y) for x, y in [(5.0, 34.0), (92.0, 36.0), (45.0, 15.0)]]
    away = [(105.0 - x, 68.0 - y) for x, y in AWAY_XY]
    frame = _frame(mirrored, away, mirrored[1])
    shots = [o for o in enumerate_options(frame, "home-1", _ctx(attacks_right=False))
             if o.kind == "shot"]  # fmt: skip
    assert len(shots) == 1 and shots[0].end[0] == pytest.approx(0.0)


def test_shot_xg_falls_with_distance_and_angle() -> None:
    central = [shot_xg((105.0 - d, 34.0), True, 0.5) for d in (6.0, 11.0, 16.0, 25.0)]
    assert central == sorted(central, reverse=True)
    assert 0.35 < central[0] < 0.65 and 0.15 < central[1] < 0.35 and central[3] < 0.08
    assert shot_xg((94.0, 10.0), True, 0.5) < central[1]  # same distance band, tight angle
    assert shot_xg((11.0, 34.0), False, 0.5) == pytest.approx(central[1])
    assert shot_xg((94.0, 34.0), True, 0.9) > shot_xg((94.0, 34.0), True, 0.1)


def _scripted(scores: list[float]) -> list[Option]:
    return [Option(kind="pass", target_player_id=f"p{i}", end=(50.0, 34.0), score=s)
            for i, s in enumerate(scores)]  # fmt: skip


def test_choice_skill() -> None:
    options = _scripted([0.20, 1.0, 0.6, 0.5, 0.4, 0.0])
    best = options[1]

    def best_share(skill: float) -> float:
        rng = np.random.default_rng(11)
        return sum(choose(options, skill, rng) is best for _ in range(1000)) / 1000

    assert best_share(0.95) > 0.70
    assert best_share(0.2) < 0.45


def test_choice_temperature_modifier() -> None:
    options = _scripted([1.0, 0.8, 0.7])
    rng_a, rng_b = np.random.default_rng(2), np.random.default_rng(2)
    calm = sum(choose(options, 0.6, rng_a, temperature_mult=0.94) is options[0]
               for _ in range(2000))  # fmt: skip
    rattled = sum(choose(options, 0.6, rng_b, temperature_mult=1.06) is options[0]
                  for _ in range(2000))  # fmt: skip
    assert calm > rattled


def test_choice_is_seeded() -> None:
    options = _scripted([0.3, 0.9, 0.5])
    a = [choose(options, 0.5, np.random.default_rng(4)) for _ in range(5)]
    b = [choose(options, 0.5, np.random.default_rng(4)) for _ in range(5)]
    assert a == b


def test_decision_extras() -> None:
    options = _scripted([0.2, 0.9, 0.5])
    extras = decision_extras(options[2], options)
    assert extras["chosen_score"] == pytest.approx(0.5)
    assert extras["best_score"] == pytest.approx(0.9)
    assert extras["best_option"] == {"kind": "pass", "target": "p1", "end": [50.0, 34.0]}
