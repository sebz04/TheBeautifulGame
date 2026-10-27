"""A number must belong to the team the sentence gives it to (TASK-25.2, planted error e19:
"Atlético Chapinero allow 8.7 passes per defensive action" quoting Laureles' PPDA)."""

import pytest

from matchmind.agents.owners import owner_failures
from matchmind.agents.scoreline import team_variants
from matchmind.schemas import Claim

TEAMS = team_variants({"chapinero": "Atlético Chapinero", "laureles": "Atlético Laureles"})


def _c(metric: str, value: float, scope: str, unit: str = "") -> Claim:
    return Claim(text=metric, metric=metric, value=value, unit=unit,
                 ref=f"metric:{metric}@1:1262.3/{scope}")  # fmt: skip


LAU = [_c("ppda_10min", 8.67, "team:laureles"), _c("possession", 0.46, "team:laureles", "%")]


def test_e19_number_given_to_the_wrong_team_fails() -> None:
    text = ("By 22', Atlético Chapinero allow 8.7 passes per defensive action over the last "
            "10 minutes and have 46% of the ball.")  # fmt: skip
    failures = owner_failures(text, "en", LAU, TEAMS)
    assert len(failures) == 1 and "Laureles" in failures[0] and "Chapinero" in failures[0]
    assert "'8.7'" in failures[0]  # 46% is 13 words away: too far to tie to Chapinero


@pytest.mark.parametrize(
    ("lang", "text"),
    [
        ("en", "Atlético Laureles allow 8.7 passes per defensive action."),
        ("en", "Laureles' press: 8.7 passes per defensive action, and Chapinero can't play."),
        ("en", "Chapinero sit deep while their opponents keep 46% of the ball."),
        ("en", "Chapinero are pinned back by a 46% share for Laureles."),
        ("en", "Chapinero were pinned back by 46% possession."),
        ("en", "Possession is 46% after the break."),  # no team named
        ("es", "El Prado aprovechó la baja presión de Laureles, controlando el 46 % del balón."),
        ("es", "Chapinero sufre contra un rival con 46 % del balón."),
        ("fr", "Laureles a 46 % du ballon."),
        ("en", "They outshot Chapinero 46 to 30."),
        ("en", "We must press Chapinero and protect our 46%."),
        ("pt", "Chapinero sofreu com a posse de 46% e 12 finalizações do Laureles."),
        ("fr", "Chapinero domine les 10 dernières minutes."),
    ],
)
def test_right_or_unclear_owners_pass(lang: str, text: str) -> None:
    assert owner_failures(text, lang, LAU, TEAMS) == []


def test_player_and_game_claims_are_not_checked() -> None:
    claims = [_c("xg", 0.41, "player:ala-17")]
    assert owner_failures("Chapinero's best chance was worth 0.41.", "en", claims, TEAMS) == []


def test_a_value_both_teams_share_passes() -> None:
    claims = [*LAU, _c("possession", 0.46, "team:chapinero", "%")]
    assert owner_failures("Chapinero have 46% of the ball.", "en", claims, TEAMS) == []


def test_other_languages() -> None:
    assert owner_failures("Chapinero tiene el 46 % del balón.", "es", LAU, TEAMS)
    assert owner_failures("Chapinero tem 46% de posse.", "pt", LAU, TEAMS)
    assert owner_failures("Chapinero a 46 % du ballon.", "fr", LAU, TEAMS)
