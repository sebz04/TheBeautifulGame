"""Fictional player and manager names.

First names are common given names for each nationality; surnames are composed from
syllables so full names don't belong to real players. Tests check a blocklist.
"""

import numpy as np

# ISO 3166-1 alpha-3 codes; weights reflect a Colombian league's squads (mostly domestic,
# with Venezuelan, Brazilian, Peruvian, and other South American imports).
NATIONALITY_WEIGHTS: dict[str, float] = {
    "COL": 0.68, "VEN": 0.05, "BRA": 0.06, "PER": 0.05, "ECU": 0.04, "ARG": 0.04,
    "URY": 0.03, "PRY": 0.02, "CHL": 0.02, "BOL": 0.01,
}  # fmt: skip

_REGION = {
    "COL": "colombian", "VEN": "caribbean_hispanic", "BRA": "lusophone", "PER": "andean",
    "ECU": "andean", "BOL": "andean", "ARG": "southern_cone", "URY": "southern_cone",
    "PRY": "southern_cone", "CHL": "southern_cone",
}  # fmt: skip

_FIRST = {
    "colombian": ["Juan Camilo", "Juan David", "Andrés Felipe", "Jhon", "Duván", "Yeison", "Brayan", "Stiven", "Cristian", "Sebastián", "Santiago", "Mateo", "Luis Fernando", "Wílmar", "Jéfferson", "Déiver", "Harold", "Edwin", "Camilo", "Daniel", "Jhojan", "Kevin", "Carlos", "Mauricio"],
    "caribbean_hispanic": ["Yordan", "Darwin", "Jhonder", "Eduard", "Yeferson", "Josué", "Rómulo", "Salomón"],
    "lusophone": ["João", "Thiago", "Rafael", "Gustavo", "Lucas", "Felipe", "Caio", "Matheus", "Vitor", "Gabriel"],
    "andean": ["Piero", "Renato", "Yoshimar", "Christofer", "Édison", "Jhilmar", "Bryan", "Wálter", "Marcelo"],
    "southern_cone": ["Facundo", "Nicolás", "Agustín", "Matías", "Gonzalo", "Franco", "Joaquín", "Thiago", "Bruno", "Lautaro"],
}  # fmt: skip

_SURNAME_PARTS = {
    "colombian": (["Val", "Mor", "Cas", "Ar", "Fer", "Var", "Ri", "Zam", "Ban", "Lo", "Car", "Ose", "Mos", "Pal", "Bal", "Mon"], ["ado", "ero", "eda", "ino", "ales", "ardo", "illo", "ona", "ejo", "arro", "ancia", "era"]),
    "caribbean_hispanic": (["Her", "Sal", "Ren", "Mach", "Osu", "Ron"], ["nández", "azar", "dón", "ado", "na", "jas"]),
    "lusophone": (["Bra", "Ca", "Fon", "Mo", "Sil", "Tei", "Mar", "Gui"], ["galhães", "rvalho", "seca", "reira", "veira", "xeira", "tins", "marães"]),
    "andean": (["Qui", "Hua", "Ma", "Cha", "Ya", "Tu", "Llo", "Pa"], ["spe", "mán", "mani", "vez", "nqui", "pac", "na", "ucar"]),
    "southern_cone": (["Ben", "Gal", "Fer", "Al", "Ro", "Oli", "Pe", "Sa"], ["ítez", "arza", "reyra", "mirón", "dríguez", "vera", "ralta", "bella"]),
}  # fmt: skip


def draw_nationality(rng: np.random.Generator) -> str:
    codes = list(NATIONALITY_WEIGHTS)
    weights = np.array(list(NATIONALITY_WEIGHTS.values()))
    return str(rng.choice(codes, p=weights / weights.sum()))


def make_name(rng: np.random.Generator, nationality: str) -> str:
    region = _REGION.get(nationality, "colombian")
    first = str(rng.choice(_FIRST[region]))
    starts, ends = _SURNAME_PARTS[region]
    surname = f"{rng.choice(starts)}{rng.choice(ends)}"
    return f"{first} {surname}"


def language_of(nationality: str) -> str:
    """Coarse shared-language group, used for squad chemistry."""
    return "pt" if _REGION.get(nationality) == "lusophone" else "es"
