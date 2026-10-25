"""Build a showcase match: simulate -> frames -> events -> moments -> cues -> metrics -> store.

Moments are the rule triggers (`stats.moments`) plus player deviations when a season
history is stored (`stats.deviations`, baselines from `Repo.load_season()`). Metrics are
snapshotted every 30 s and at every moment's end. A rebuild replaces the match's rows.
"""

import time
from pathlib import Path

from pydantic import BaseModel

from matchmind.engine.scenario import load_scenario, scenario_meta
from matchmind.engine.simulate import simulate_match
from matchmind.engine.validate import validate_match
from matchmind.league.league import League, build_league
from matchmind.league.profiles import build_profiles
from matchmind.schemas_profile import Profiles
from matchmind.stats.baselines import player_baselines
from matchmind.stats.deviations import deviation_moments
from matchmind.stats.metrics import compute_metrics
from matchmind.stats.moments import detect_moments
from matchmind.stats.speed import alerts
from matchmind.stats.xt import load_xt
from matchmind.store.blob import TrackingStore
from matchmind.store.db import Repo

LEAGUE_SEED = 2026


class BuildResult(BaseModel):
    match_id: str
    scenario_id: str
    events: int
    moments: int
    deviations: int
    cues: int
    metric_rows: int
    seconds: float


def build_scenario(path: Path, repo: Repo, store: TrackingStore, league: League | None = None,
                   profiles: Profiles | None = None) -> BuildResult:  # fmt: skip
    start = time.perf_counter()
    league = league or build_league(LEAGUE_SEED)
    profiles = profiles or build_profiles(league, seed=LEAGUE_SEED)
    scenario = load_scenario(path)
    meta = scenario_meta(league, scenario)
    data = simulate_match(meta, scenario, level=3, profiles=profiles)
    grid = load_xt()
    mid = meta.match_id

    moments = detect_moments(data, grid)
    details: dict[str, dict[str, float | str]] = {}
    deviations = 0
    season = repo.load_season()
    if season is not None:
        baselines = player_baselines(season, profiles)
        for moment, dev in deviation_moments(data, baselines):
            moments.append(moment)
            details[moment.moment_id] = {"expected": dev.expected, "p_value": dev.p_value,
                                         "baseline_per90": dev.baseline_per90,
                                         "direction": dev.direction}  # fmt: skip
            deviations += 1
    moments.sort(key=lambda m: (m.period, m.t_start, m.moment_id))
    cues = alerts(data.frames, (2, 1e9))
    rows = compute_metrics(data, grid, extra_times=[(m.period, m.t_end) for m in moments])

    repo.delete_match(mid)
    repo.save_match_data(data)
    store.write(mid, data.frames)
    repo.save_moments(mid, moments, details=details)
    repo.save_cues(mid, cues)
    repo.save_metrics(mid, rows)
    repo.save_realism(mid, validate_match(data).model_dump())  # the API serves it
    return BuildResult(match_id=mid, scenario_id=scenario.scenario_id, events=len(data.events),
                       moments=len(moments), deviations=deviations, cues=len(cues),
                       metric_rows=len(rows),
                       seconds=round(time.perf_counter() - start, 1))  # fmt: skip
