"""The 20 approved clubs, named after Los Angeles neighborhoods (fixed, not generated).

Kits, stadiums, capacities, and founding years are fictional. Colors are curated so
derby rivals and every pair of kits stay distinguishable on screen.
"""

from dataclasses import dataclass

Region = str  # "eastside" | "central" | "westside" | "valley" | "south"


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
    ClubSeed("boyle-heights", "Boyle Heights Athletic", "BHA", "Hollenbeck Ground", 18500, 1921, "#B22234", "#F2C14E", "eastside"),
    ClubSeed("lincoln-heights", "Lincoln Heights Locomotive", "LHL", "Railyard Park", 14000, 1908, "#1F2A44", "#C0C0C0", "eastside"),
    ClubSeed("el-sereno", "El Sereno Sporting", "ELS", "Hilltop Field", 9800, 1946, "#4B9CD3", "#FFFFFF", "eastside"),
    ClubSeed("highland-park", "Highland Park Albion", "HPA", "Arroyo Stadium", 16200, 1912, "#7A1F3D", "#F5E6C8", "eastside"),
    ClubSeed("eagle-rock", "Eagle Rock United", "ERU", "The Rock", 21000, 1904, "#D35400", "#1B1B1B", "eastside"),
    ClubSeed("echo-park", "Echo Park Rovers", "EPR", "Lakeside Ground", 24500, 1899, "#0072CE", "#FFFFFF", "central"),
    ClubSeed("silver-lake", "Silver Lake Wanderers", "SLW", "Reservoir Park", 23000, 1902, "#8A9BA8", "#0B3D2E", "central"),
    ClubSeed("los-feliz", "Los Feliz Town", "LFT", "Griffith Road", 15500, 1925, "#2C5F2D", "#FFE77A", "central"),
    ClubSeed("koreatown", "Koreatown City", "KTC", "Wilshire Arena", 27000, 1978, "#E4002B", "#003478", "central"),
    ClubSeed("atwater-village", "Atwater Village Kestrels", "AVK", "Riverside Ground", 11200, 1931, "#5E3A87", "#F2C14E", "central"),
    ClubSeed("venice", "Venice Tides", "VNT", "Boardwalk Stadium", 19000, 1910, "#00B2A9", "#F4D35E", "westside"),
    ClubSeed("mar-vista", "Mar Vista Dynamo", "MVD", "Vista Park", 12500, 1955, "#FFD100", "#1D428A", "westside"),
    ClubSeed("westwood", "Westwood Scholars", "WWS", "Campus Field", 17800, 1919, "#2D68C4", "#F2A900", "westside"),
    ClubSeed("san-pedro", "San Pedro Harbor", "SPH", "Dockside Stadium", 20500, 1896, "#002147", "#E35205", "westside"),
    ClubSeed("van-nuys", "Van Nuys Aviators", "VNA", "Airfield Ground", 22500, 1949, "#5B6770", "#FFB81C", "valley"),
    ClubSeed("studio-city", "Studio City Stars", "SCS", "Ventura Lot", 16000, 1938, "#000000", "#FFD700", "valley"),
    ClubSeed("sherman-oaks", "Sherman Oaks Royals", "SOR", "Oakwood Park", 18200, 1927, "#0F4C3A", "#D4AF37", "valley"),
    ClubSeed("leimert-park", "Leimert Park Harmony", "LPH", "Village Green", 13400, 1962, "#009639", "#FDDA24", "south"),
    ClubSeed("crenshaw", "Crenshaw Monarchs", "CRM", "Baldwin Ground", 25000, 1958, "#4B2E83", "#B9975B", "south"),
    ClubSeed("watts", "Watts Union", "WTU", "Towers Park", 15000, 1965, "#C8102E", "#000000", "south"),
]  # fmt: skip

_DERBIES: list[tuple[str, str]] = [
    ("echo-park", "silver-lake"),
    ("boyle-heights", "lincoln-heights"),
    ("venice", "mar-vista"),
    ("leimert-park", "crenshaw"),
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
