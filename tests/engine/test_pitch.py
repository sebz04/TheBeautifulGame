import math

import pytest

from matchmind.engine.pitch import (
    PITCH_LENGTH,
    PITCH_WIDTH,
    clamp_to_pitch,
    distance,
    zone_index,
)


def test_pitch_dimensions():
    assert (PITCH_LENGTH, PITCH_WIDTH) == (105.0, 68.0)


def test_zone_index_edges():
    assert zone_index(105.0, 68.0) == (15, 11)
    assert zone_index(0, 0) == (0, 0)
    assert zone_index(-1, 70) == (0, 11)


def test_zone_index_interior_and_custom_grid():
    assert zone_index(52.5, 34.0) == (8, 6)
    assert zone_index(104.9, 0.1, nx=32, ny=21) == (31, 0)


def test_clamp_to_pitch():
    assert clamp_to_pitch(-3.0, 80.0) == (0.0, 68.0)
    assert clamp_to_pitch(50.0, 30.0) == (50.0, 30.0)


@pytest.mark.parametrize(("a", "b", "expected"), [((0, 0), (3, 4), 5.0), ((1, 1), (1, 1), 0.0)])
def test_distance(a, b, expected):
    assert math.isclose(distance(a, b), expected)


def test_attacks_right_by_period() -> None:
    from matchmind.engine.pitch import attacks_right

    assert attacks_right(is_home=True, period=1) and not attacks_right(is_home=True, period=2)
    assert not attacks_right(is_home=False, period=1) and attacks_right(is_home=False, period=2)
