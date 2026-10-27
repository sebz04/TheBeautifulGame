"""Lead wording must match the score at the moment (TASK-24.4): seen live, "Morejo gives
Chapinero the lead" at 1–1 and "Monero's goal puts Laureles ahead" at 2–2."""

import pytest

from matchmind.agents.scoreline import lead_failures, team_variants

TEAMS = team_variants({"chapinero": "Atlético Chapinero", "laureles": "Atlético Laureles"})
LEVEL = {"chapinero": 1, "laureles": 1}
CHAP_AHEAD = {"chapinero": 2, "laureles": 1}


def test_team_variants_keep_the_distinctive_words() -> None:
    assert "chapinero" in TEAMS["chapinero"] and "atletico chapinero" in TEAMS["chapinero"]
    assert "atletico" not in TEAMS["chapinero"]  # shared by both clubs: not a team name


@pytest.mark.parametrize(
    ("lang", "text"),
    [
        ("en", "Morejo gives Chapinero the lead"),
        ("en", "Monero's goal puts Laureles ahead"),
        ("en", "Laureles take the lead through Monero"),
        ("es", "Monero da ventaja a Laureles"),
        ("es", "Laureles se pone por delante"),
        ("pt", "Morejo garante vantagem para Chapinero"),
        ("pt", "Gol coloca o Laureles na frente"),
        ("fr", "Chapinero prend l'avantage"),
        ("fr", "Le but donne l'avantage à Laureles"),
        ("ar", "هدف يمنح Laureles التقدم"),
    ],
)
def test_a_lead_claim_at_a_level_score_fails(lang: str, text: str) -> None:
    failures = lead_failures(text, lang, TEAMS, LEVEL)
    assert len(failures) == 1 and "1–1" in failures[0]


def test_a_true_lead_claim_passes() -> None:
    assert lead_failures("Morejo gives Chapinero the lead", "en", TEAMS, CHAP_AHEAD) == []
    assert lead_failures("Chapinero prend l'avantage", "fr", TEAMS, CHAP_AHEAD) == []


def test_the_wrong_team_leading_fails() -> None:
    failures = lead_failures("Monero puts Laureles ahead", "en", TEAMS, CHAP_AHEAD)
    assert failures and "Laureles" in failures[0]


@pytest.mark.parametrize(
    ("lang", "text"),
    [
        ("en", "Atlético Chapinero leads early game momentum and control"),  # dominance
        ("en", "Chapinero pressed ahead of the break"),  # not a score
        ("es", "Laureles tiene ventaja numérica con un hombre más"),  # numbers, not score
        ("pt", "Laureles pressiona à frente da área"),
        ("fr", "Chapinero presse devant la surface"),
    ],
)
def test_other_meanings_are_not_lead_claims(lang: str, text: str) -> None:
    assert lead_failures(text, lang, TEAMS, LEVEL) == []
