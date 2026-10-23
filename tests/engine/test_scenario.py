from pathlib import Path

import pytest
from pydantic import ValidationError

from matchmind.engine.scenario import Beat, Scenario, load_scenario

TOML = """
scenario_id = "test_story"
title = "A test story"
home_club_id = "chapinero"
away_club_id = "laureles"
seed = 11

[[beats]]
minute = 30
kind = "red_card"
team = "home"

[[beats]]
minute = 70
kind = "tactic_change"
team = "away"
params = { press_intensity = 0.9, line_height = 0.8 }
"""


def test_load_scenario(tmp_path: Path) -> None:
    path = tmp_path / "s.toml"
    path.write_text(TOML)
    s = load_scenario(path)
    assert s.scenario_id == "test_story" and s.seed == 11
    assert [b.kind for b in s.beats] == ["red_card", "tactic_change"]
    assert s.beats[1].params == {"press_intensity": 0.9, "line_height": 0.8}
    assert s.beats[0].params == {}


def test_beats_must_be_known_kinds() -> None:
    with pytest.raises(ValidationError):
        Beat(minute=10, kind="teleport", team="home")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Beat(minute=95, kind="goal", team="home")  # beats happen within 90 minutes


def test_beats_sorted_by_minute() -> None:
    s = Scenario(scenario_id="x", title="x", home_club_id="a", away_club_id="b", seed=1,
                 beats=[Beat(minute=60, kind="goal", team="home"),
                        Beat(minute=20, kind="sub", team="away")])  # fmt: skip
    assert [b.minute for b in s.beats] == [20, 60]


def test_tactic_change_params_are_checked() -> None:
    with pytest.raises(ValidationError):
        Beat(minute=10, kind="tactic_change", team="home", params={"press_intensity": 2.0})
    with pytest.raises(ValidationError):
        Beat(minute=10, kind="tactic_change", team="home", params={"formation": "4-4-2"})
