"""Fictional player and manager names.

First names are common given names for each nationality; surnames are composed from
syllables so full names don't belong to real players. Tests check a blocklist.
"""

import numpy as np

# ISO 3166-1 alpha-3 codes, weights reflect a Los Angeles-based league's squads.
NATIONALITY_WEIGHTS: dict[str, float] = {
    "USA": 0.40, "MEX": 0.13, "SLV": 0.03, "GTM": 0.02, "CAN": 0.04, "JAM": 0.02,
    "COL": 0.03, "ARG": 0.03, "BRA": 0.04, "URY": 0.01, "ENG": 0.04, "ESP": 0.03,
    "FRA": 0.03, "DEU": 0.02, "NLD": 0.01, "NGA": 0.02, "GHA": 0.02, "KOR": 0.03,
    "JPN": 0.03, "PHL": 0.02,
}  # fmt: skip

_REGION = {
    "USA": "anglo", "CAN": "anglo", "ENG": "anglo", "JAM": "caribbean",
    "MEX": "hispanic", "SLV": "hispanic", "GTM": "hispanic", "COL": "hispanic",
    "ARG": "hispanic", "URY": "hispanic", "ESP": "hispanic", "PHL": "hispanic",
    "BRA": "lusophone", "FRA": "french", "DEU": "germanic", "NLD": "germanic",
    "NGA": "west_african", "GHA": "west_african", "KOR": "korean", "JPN": "japanese",
}  # fmt: skip

_FIRST = {
    "anglo": ["Jake", "Tyler", "Owen", "Caleb", "Marcus", "Ethan", "Ryan", "Dylan", "Logan", "Connor", "Miles", "Jordan", "Nathan", "Cole", "Wes", "Grant"],
    "caribbean": ["Andre", "Kemar", "Shamar", "Damion", "Javain", "Ricardo", "Leon", "Oneil"],
    "hispanic": ["Diego", "Luis", "Carlos", "Mateo", "Javier", "Andrés", "Héctor", "Iván", "Rafael", "Emilio", "Joaquín", "Tomás", "Bruno", "Santiago", "Adrián", "Rodrigo"],
    "lusophone": ["João", "Thiago", "Rafael", "Gustavo", "Lucas", "Felipe", "Caio", "Matheus"],
    "french": ["Hugo", "Théo", "Lucas", "Mathis", "Bastien", "Yanis", "Noah", "Enzo"],
    "germanic": ["Lukas", "Jonas", "Niklas", "Tim", "Daan", "Bram", "Felix", "Jannik"],
    "west_african": ["Kwame", "Emeka", "Chidi", "Kofi", "Tunde", "Yaw", "Obinna", "Femi"],
    "korean": ["Min-jun", "Seo-jun", "Ji-ho", "Hyun-woo", "Do-yun", "Jae-won", "Tae-yang", "Sung-min"],
    "japanese": ["Haruto", "Sota", "Ren", "Kaito", "Riku", "Yuto", "Daiki", "Takumi"],
}  # fmt: skip

_SURNAME_PARTS = {
    "anglo": (["Hal", "Whit", "Brad", "Cor", "Ash", "Pen", "Ren", "Thorn", "Mar", "Sel"], ["ford", "ley", "wick", "ton", "by", "more", "kin", "well", "ridge", "den"]),
    "caribbean": (["Black", "Gor", "Fen", "Mal", "Bra", "Thom"], ["wood", "don", "ton", "colm", "nett", "son"]),
    "hispanic": (["Val", "Mor", "Cas", "Al", "Fer", "Var", "Ri", "Que", "Zam", "Ban", "Lo", "Ar"], ["ado", "ero", "eda", "ino", "ales", "ardo", "illo", "ona", "uez", "arro"]),
    "lusophone": (["Bra", "Ca", "Fon", "Mo", "Sil", "Tei"], ["galhães", "rvalho", "seca", "reira", "veira", "xeira"]),
    "french": (["Bel", "Du", "Mar", "Lan", "Ro", "Fon"], ["court", "mont", "ceau", "glade", "chet", "taine"]),
    "germanic": (["Brand", "Hol", "Kess", "Lind", "Van der ", "Stei"], ["mann", "berg", "ler", "hoven", "Velde", "ner"]),
    "west_african": (["Ade", "Oko", "Ase", "Nwa", "Ama", "Ola"], ["bayo", "nkwo", "mah", "chukwu", "koh", "wale"]),
    "korean": (["Kim", "Park", "Lee", "Choi", "Jung", "Kang", "Yoon", "Han"], [""]),
    "japanese": (["Tana", "Naka", "Mori", "Hayashi", "Ishi", "Fuji"], ["ka", "mura", "ta", "", "zaki", "moto"]),
}  # fmt: skip


def draw_nationality(rng: np.random.Generator) -> str:
    codes = list(NATIONALITY_WEIGHTS)
    weights = np.array(list(NATIONALITY_WEIGHTS.values()))
    return str(rng.choice(codes, p=weights / weights.sum()))


def make_name(rng: np.random.Generator, nationality: str) -> str:
    region = _REGION.get(nationality, "anglo")
    first = str(rng.choice(_FIRST[region]))
    starts, ends = _SURNAME_PARTS[region]
    surname = f"{rng.choice(starts)}{rng.choice(ends)}"
    if region == "korean":
        return f"{surname} {first}"  # family name first
    return f"{first} {surname}"


def language_of(nationality: str) -> str:
    """Coarse shared-language group, used for squad chemistry."""
    return {
        "anglo": "en", "caribbean": "en", "west_african": "en", "hispanic": "es",
        "lusophone": "pt", "french": "fr", "germanic": "de", "korean": "ko", "japanese": "ja",
    }[_REGION.get(nationality, "anglo")]  # fmt: skip
