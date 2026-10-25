from functools import cache

import numpy as np
import pytest

from matchmind.engine.decisions import Option
from matchmind.engine.lineup import match_meta
from matchmind.engine.simulate import simulate_match
from matchmind.league.fixtures import build_fixtures
from matchmind.league.league import build_league
from matchmind.league.profiles import build_profiles
from matchmind.schemas import Event, MatchData
from matchmind.stats.counterfactual import (
    DECISION_TYPES,
    Counterfactual,
    counterfactual,
    decision_frame,
    match_counterfactuals,
)
from matchmind.stats.xt import load_xt

GRID = load_xt()


@cache
def _match() -> MatchData:
    league = build_league()
    meta = match_meta(league, build_fixtures(league, seed=2026)[0], seed=7)
    return simulate_match(meta, level=3, profiles=build_profiles(league, seed=2026))


@cache
def _all() -> list[tuple[Event, Counterfactual]]:
    data = _match()
    by_id = {e.event_id: e for e in data.events}
    return [(by_id[c.event_id], c) for c in match_counterfactuals(data, GRID)]


def test_every_decision_is_scored() -> None:
    data = _match()
    decided = [e for e in data.events if e.type in DECISION_TYPES and "best_score" in e.extras]
    assert len(_all()) == len(decided) > 300


def test_best_at_least_chosen() -> None:
    for _, cf in _all():
        assert cf.best.score >= cf.chosen.score - 1e-12
        assert cf.gain == pytest.approx(cf.best.score - cf.chosen.score)
        scores = [o.score for o in cf.alternatives]
        assert scores == sorted(scores, reverse=True) and cf.best == cf.alternatives[0]


def test_matches_engine_extras() -> None:
    """The scoring is the engine's: from the stored match it reproduces the engine's scores.

    Not to 1e-9: frames are stored to 1 cm, which can tip a point into the next xT cell.
    """
    best = np.array([abs(cf.best.score - e.extras["best_score"]) for e, cf in _all()])
    chosen = np.array([abs(cf.chosen.score - e.extras["chosen_score"]) for e, cf in _all()])
    assert np.mean(best <= 1e-3) >= 0.95 and np.mean(chosen <= 1e-3) >= 0.95
    assert np.median(best) < 1e-5


def test_chosen_is_the_option_played() -> None:
    for e, cf in _all():
        played = e.extras["chosen_option"]
        assert cf.chosen.kind == played["kind"]
        assert cf.chosen.target_player_id == played["target"]


def test_single_event_api() -> None:
    data = _match()
    e, expected = _all()[10]
    frame = decision_frame(data, e)
    assert frame.ball[:2] == (e.x, e.y)
    home = data.meta.home.club_id
    keepers = frozenset({data.meta.home_squad[0].player_id, data.meta.away_squad[0].player_id})
    from matchmind.engine.pitch import attacks_right

    cf = counterfactual(e, frame, GRID, attacks_right=attacks_right(e.team_id == home, e.period),
                        goalkeepers=keepers)  # fmt: skip
    assert cf == expected
    assert isinstance(cf.best, Option)


def test_non_decision_event_rejected() -> None:
    data = _match()
    tackle = next(e for e in data.events if e.type == "tackle")
    with pytest.raises(ValueError, match="decision"):
        counterfactual(tackle, data.frames[0], GRID, attacks_right=True)


def test_decision_frame_from_a_window_of_frames() -> None:
    data = _match()
    e, _ = _all()[25]
    window = [f for f in data.frames if f.period == e.period and e.t - 1.0 <= f.t <= e.t]
    cut = data.model_copy(update={"frames": window})
    assert decision_frame(cut, e) == decision_frame(data, e)
