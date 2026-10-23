import numpy as np
import pytest

from matchmind.engine.decisions import shot_xg
from matchmind.engine.set_pieces import (
    PENALTY_SPOT,
    aerial_duel,
    corner_delivery,
    free_kick_xg,
    header_xg,
    in_box,
    keeper_claims,
    penalty_scores,
)


def test_aerial_duel_follows_ratings() -> None:
    rng = np.random.default_rng(1)
    strong = sum(aerial_duel(rng, 0.8, 190, 0.4, 178) for _ in range(1000)) / 1000
    weak = sum(aerial_duel(rng, 0.4, 178, 0.8, 190) for _ in range(1000)) / 1000
    even = sum(aerial_duel(rng, 0.5, 183, 0.5, 183) for _ in range(1000)) / 1000
    assert strong > 0.6 and weak < 0.4
    assert even == pytest.approx(0.5, abs=0.05)


def test_height_alone_helps() -> None:
    rng = np.random.default_rng(2)
    tall = sum(aerial_duel(rng, 0.5, 194, 0.5, 176) for _ in range(2000)) / 2000
    assert tall > 0.55


def test_penalty_conversion_about_076() -> None:
    rng = np.random.default_rng(3)
    neutral = np.mean([penalty_scores(rng, 1.0) for _ in range(5000)])
    calm = np.mean([penalty_scores(rng, 1.06) for _ in range(5000)])
    assert neutral == pytest.approx(0.76, abs=0.02)
    assert calm > neutral


def test_free_kick_xg_falls_with_distance_and_rises_with_finishing() -> None:
    near, far = free_kick_xg(20.0, 0.5), free_kick_xg(29.0, 0.5)
    assert 0.04 <= near <= 0.10 and far < near
    assert free_kick_xg(20.0, 0.9) > near
    assert free_kick_xg(35.0, 0.5) == 0.0  # too far to shoot


def test_headers_are_worse_chances_than_shots() -> None:
    spot = (105.0 - 9.0, 34.0)
    assert header_xg(spot, True) < shot_xg(spot, True, 0.5)
    assert header_xg((105.0 - 6.0, 34.0), True) > header_xg((105.0 - 14.0, 34.0), True)


def test_corner_delivery_lands_in_the_box() -> None:
    rng = np.random.default_rng(4)
    good = np.array([corner_delivery(rng, 0.9, right_side=True) for _ in range(500)])
    poor = np.array([corner_delivery(rng, 0.2, right_side=False) for _ in range(500)])
    assert np.mean([in_box(p) for p in good]) > 0.9
    assert np.mean([in_box(p) for p in poor]) > 0.7
    assert good[:, 1].std() < poor[:, 1].std()  # better crossers are more accurate


def test_keeper_claims_balls_near_his_line() -> None:
    rng = np.random.default_rng(5)
    close = np.mean([keeper_claims(rng, (103.5, 34.0), 0.5) for _ in range(1000)])
    far = np.mean([keeper_claims(rng, (93.0, 34.0), 0.5) for _ in range(1000)])
    assert close > 0.4 and far == 0.0


def test_box_and_spot() -> None:
    assert PENALTY_SPOT == (94.0, 34.0)
    assert in_box((95.0, 50.0)) and not in_box((85.0, 34.0)) and not in_box((95.0, 60.0))
