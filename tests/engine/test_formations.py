import numpy as np
import pytest

from matchmind.engine.formations import formation_anchors, to_team_frame
from matchmind.engine.lineup import FORMATION_LINES


def test_anchors_shape_and_order() -> None:
    for formation, (df, _mf, _fw) in FORMATION_LINES.items():
        a = formation_anchors(formation)
        assert a.shape == (11, 2)
        assert a[0, 0] < a[1:, 0].min()  # keeper deepest
        assert np.all(np.diff(a[1:, 0]) >= 0)  # lines run back to front
        assert np.all((a[:, 1] > 0) & (a[:, 1] < 68))
        assert len(np.unique(a[1 : 1 + df, 0])) == 1  # the back line is flat


def test_bad_formation_rejected() -> None:
    with pytest.raises(ValueError):
        formation_anchors("4-4-3")


def test_team_frame_is_its_own_inverse() -> None:
    xy = np.array([[10.0, 5.0], [100.0, 60.0]])
    assert np.allclose(to_team_frame(to_team_frame(xy, False), False), xy)
    assert np.allclose(to_team_frame(xy, False)[0], [95.0, 63.0])
    assert np.allclose(to_team_frame(xy, True), xy)
