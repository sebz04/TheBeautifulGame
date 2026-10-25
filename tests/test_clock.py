import pytest

from matchmind.clock import match_minute, minute_label


@pytest.mark.parametrize(
    ("period", "t", "label", "minute"),
    [
        (1, 0.0, "1'", 1),
        (1, 59.9, "1'", 1),
        (1, 60.0, "2'", 2),
        (1, 2699.0, "45'", 45),
        (1, 2700.0, "45+1'", 46),  # stoppage time
        (1, 2830.0, "45+3'", 48),
        (2, 638.5, "56'", 56),  # 55:38 elapsed is the 56th minute
        (2, 2699.0, "90'", 90),
        (2, 2950.0, "90+5'", 95),
    ],
)
def test_minute_label_follows_football_convention(
    period: int, t: float, label: str, minute: int
) -> None:
    assert minute_label(period, t) == label  # type: ignore[arg-type]
    assert match_minute(period, t) == minute  # type: ignore[arg-type]
