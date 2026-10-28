"""PPDA read as pressure faced (TASK-25.2): PPDA measures a team's own pressing, so "faces less
pressure with a PPDA of 6.67" misreads it. Cases are from stored agent texts."""

import pytest

from matchmind.agents.meaning import ppda_slips
from matchmind.schemas import Claim


@pytest.mark.parametrize(
    ("lang", "text"),
    [
        ("en", "Chapinero now enjoys 54.2% territory and a lower PPDA of 6.67, indicating they "
               "face less pressure."),
        ("en", "Atlético Laureles faced less pressure with a PPDA of 24.3 in the last minutes."),
        ("en", "El Prado's PPDA is 4.58, showing they face intense pressure."),
        ("es", "Unión Manrique enfrenta menos presión con un PPDA de 8,38."),
        ("pt", "Chapinero controla 54,2% do campo e sofre menos pressão (PPDA 6,67)."),
        ("fr", "Unión Manrique bénéficie d'un PPDA de 6,43, subissant moins de pression."),
    ],
)  # fmt: skip
def test_ppda_read_as_pressure_faced_fails(lang: str, text: str) -> None:
    assert len(ppda_slips(text, lang)) == 1  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("lang", "text"),
    [
        ("en", "Their pressing allowed only 4.7 passes per defensive action, keeping El Poblado "
               "under pressure."),
        ("en", "We faced tough pressure from Sporting Getsemaní, with a low PPDA of 4.58."),
        ("es", "San Fernando sufrió la presión de El Poblado, que permitió solo 7 pases por "
               "acción defensiva."),
        ("fr", "Getsemaní subit la pression d'Atlético El Prado, qui limite nos passes à 9 par "
               "action défensive."),
        ("en", "Laureles face less pressure now."),  # no PPDA: nothing to misread
        ("en", "Laureles' PPDA rose to 9.0: their press has faded."),
    ],
)  # fmt: skip
def test_correct_pressure_wording_passes(lang: str, text: str) -> None:
    assert ppda_slips(text, lang) == []  # type: ignore[arg-type]


def _claim(metric: str, value: float, at: str, team: str = "laureles") -> Claim:
    return Claim(text=metric, metric=metric, value=value, unit="",
                 ref=f"metric:{metric}@{at}/team:{team}")  # fmt: skip


def test_a_recap_sentence_mixing_two_moments_fails() -> None:
    from matchmind.agents.meaning import mixed_moments

    claims = [_claim("ppda_10min", 9.0, "1:1200.0"), _claim("momentum", 0.33, "2:900.0")]
    text = "Laureles' press faded to 9.0 and their momentum reached 0.33. They lost."
    failures = mixed_moments(text, "en", claims)
    assert len(failures) == 1 and "21'" in failures[0] and "61'" in failures[0]
    dated = "Laureles' press faded to 9.0 at 21', and their momentum reached 0.33 at 61'."
    assert mixed_moments(dated, "en", claims) == []  # it says when each was


def test_one_moment_per_sentence_passes() -> None:
    from matchmind.agents.meaning import mixed_moments

    claims = [_claim("ppda_10min", 9.0, "1:1200.0"), _claim("momentum", 0.33, "2:900.0"),
              _claim("possession", 54.0, "1:1200.0", "chapinero")]  # fmt: skip
    text = (
        "By 20' Laureles' press had faded to 9.0 and Chapinero had 54% of the ball. "
        "Later their momentum reached 0.33."
    )
    assert mixed_moments(text, "en", claims) == []
