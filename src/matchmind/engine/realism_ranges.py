"""Plausible ranges for a top-flight match (per team per match unless noted).

Premier League-referenced and wide enough to include Colombian top-flight levels
(fewer passes per team, about 2.2-2.5 goals per match).
"""

RANGES: dict[str, tuple[float, float]] = {
    "passes": (350, 650),
    "pass_completion": (0.74, 0.90),
    "shots": (5, 22),
    "shots_on_target_ratio": (0.25, 0.50),
    "possession": (0.30, 0.70),
    "ppda": (6, 20),
    "tackles": (10, 25),
    "distance_km_outfield_player": (9.0, 13.0),
    "top_speed_ms": (7.5, 10.0),
    "sprints_per_outfield_player": (10, 50),  # > 7.0 m/s for >= 1 s
    "offsides": (0, 6),
    "throw_ins": (15, 30),  # restarts awarded to the team
    "goal_kicks": (4, 12),
    "corners": (2, 9),
    "fouls": (8, 18),  # committed
    "goals_per_match": (2.2, 3.4),  # mean over many matches (validate_many only)
}

SPRINT_SPEED_MS = 7.0
SPRINT_MIN_S = 1.0
PPDA_ZONE_SHARE = 0.6  # opponent passes in their own 60% of the pitch
