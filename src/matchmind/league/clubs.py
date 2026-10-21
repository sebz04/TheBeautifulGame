"""The 20 approved clubs, named after barrios in Colombian cities (fixed, not generated).

Kits, stadiums, capacities, and founding years are fictional. Colors are curated so
derby rivals and every pair of kits stay distinguishable on screen.
"""

from dataclasses import dataclass

Region = str  # city slug: "bogota", "medellin", "cali", "barranquilla", ...


@dataclass(frozen=True)
class ClubSeed:
    club_id: str
    name: str
    short: str
    stadium: str
    capacity: int
    founded: int
    primary_color: str
    secondary_color: str
    region: Region


CLUBS: list[ClubSeed] = [
    ClubSeed("chapinero", "Atlético Chapinero", "ACH", "Estadio Los Cerros", 28000, 1924, "#6A1B9A", "#FFFFFF", "bogota"),
    ClubSeed("usaquen", "Club Deportivo Usaquén", "CDU", "Estadio El Cedro", 21000, 1931, "#00843D", "#FFD100", "bogota"),
    ClubSeed("la-candelaria", "Sporting La Candelaria", "SLC", "Estadio Las Aguas", 12000, 1909, "#8B0000", "#F5E6C8", "bogota"),
    ClubSeed("teusaquillo", "Unión Teusaquillo", "UTE", "Estadio La Soledad", 17500, 1938, "#1F2A44", "#C0C0C0", "bogota"),
    ClubSeed("suba", "Deportivo Suba", "DSU", "Estadio Los Humedales", 19500, 1967, "#4B9CD3", "#FFFFFF", "bogota"),
    ClubSeed("laureles", "Atlético Laureles", "ALA", "Estadio La Setenta", 30000, 1913, "#E4002B", "#FFFFFF", "medellin"),
    ClubSeed("el-poblado", "Sporting El Poblado", "SEP", "Estadio Los Balsos", 26000, 1916, "#002D72", "#F2A900", "medellin"),
    ClubSeed("belen", "Deportivo Belén", "DBE", "Estadio Los Alpes", 16500, 1945, "#FF8200", "#1B1B1B", "medellin"),
    ClubSeed("manrique", "Unión Manrique", "UMA", "Estadio El Pinal", 14000, 1952, "#5B6770", "#E35205", "medellin"),
    ClubSeed("san-antonio", "San Antonio Fútbol Club", "SAF", "Estadio La Colina", 22000, 1912, "#7A1F3D", "#F2C14E", "cali"),
    ClubSeed("san-fernando", "Deportivo San Fernando", "DSF", "Estadio El Templete", 25500, 1927, "#00B2A9", "#002147", "cali"),
    ClubSeed("siloe", "Atlético Siloé", "ASI", "Estadio La Loma", 13000, 1959, "#2C5F2D", "#FFE77A", "cali"),
    ClubSeed("el-prado", "Atlético El Prado", "AEP", "Estadio Los Almendros", 27500, 1919, "#FFD700", "#000000", "barranquilla"),
    ClubSeed("barrio-abajo", "Unión Barrio Abajo", "UBA", "Estadio La Ribera", 18000, 1922, "#C8102E", "#1D428A", "barranquilla"),
    ClubSeed("rebolo", "Deportivo Rebolo", "DRE", "Estadio El Arenal", 11500, 1961, "#8A9BA8", "#0B3D2E", "barranquilla"),
    ClubSeed("getsemani", "Sporting Getsemaní", "SGE", "Estadio La Trinidad", 20000, 1905, "#D35400", "#FFFFFF", "cartagena"),
    ClubSeed("manga", "Manga Fútbol Club", "MFC", "Estadio El Muelle", 15500, 1933, "#0072CE", "#FFFFFF", "cartagena"),
    ClubSeed("cabecera", "Atlético Cabecera", "ACA", "Estadio Los Guayacanes", 23500, 1950, "#4B2E83", "#B9975B", "bucaramanga"),
    ClubSeed("el-rodadero", "Club El Rodadero", "CER", "Estadio La Bahía", 16000, 1948, "#00A3E0", "#F4D35E", "santa-marta"),
    ClubSeed("chipre", "Deportivo Chipre", "DCH", "Estadio El Mirador", 19000, 1930, "#000000", "#FFFFFF", "manizales"),
]  # fmt: skip

_DERBIES: list[tuple[str, str]] = [
    ("chapinero", "usaquen"),
    ("laureles", "el-poblado"),
    ("san-antonio", "san-fernando"),
    ("el-prado", "barrio-abajo"),
    ("getsemani", "manga"),
]


def derbies() -> list[tuple[str, str]]:
    return list(_DERBIES)


def derby_rival(club_id: str) -> str | None:
    for a, b in _DERBIES:
        if club_id == a:
            return b
        if club_id == b:
            return a
    return None
