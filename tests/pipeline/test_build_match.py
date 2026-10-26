from functools import cache
from pathlib import Path

import pytest

from matchmind.engine.scenario import SCENARIO_DIR
from matchmind.pipeline.build_match import BuildResult, build_scenario
from matchmind.schemas import MatchData
from matchmind.stats.metrics import compute_metrics, metrics_at
from matchmind.stats.xt import load_xt
from matchmind.store.blob import LocalBackend, TrackingStore
from matchmind.store.db import Repo

GRID = load_xt()


@cache
def _built(tmp: str) -> tuple[BuildResult, Repo, TrackingStore]:
    repo = Repo("sqlite:///:memory:")
    store = TrackingStore(LocalBackend(Path(tmp)))
    result = build_scenario(SCENARIO_DIR / "comeback_red_card.toml", repo, store)
    return result, repo, store


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[BuildResult, Repo, TrackingStore]:
    return _built(str(tmp_path_factory.mktemp("tracking")))


def _match(built: tuple[BuildResult, Repo, TrackingStore]) -> MatchData:
    result, repo, store = built
    meta = repo.get_match_meta(result.match_id)
    assert meta is not None
    return MatchData(
        meta=meta, events=repo.get_events(result.match_id), frames=store.read_all(result.match_id)
    )


def test_build_match_end_to_end(built: tuple[BuildResult, Repo, TrackingStore]) -> None:
    result, repo, store = built
    mid = result.match_id
    assert repo.list_matches() == [mid] and store.exists(mid)
    moments = repo.list_moments(mid)
    assert len(moments) == result.moments > 0
    assert any(m.kind == "red_card" for m in moments)
    rows = repo.list_metrics(mid)
    meta = repo.get_match_meta(mid)
    assert meta is not None
    teams = {r.scope_id for r in rows if r.scope == "team"}
    assert teams == {meta.home.club_id, meta.away.club_id}
    assert {r.scope for r in rows} == {"team", "player"}
    assert repo.list_cues(mid)
    assert result.seconds > 0


def test_build_stores_the_realism_report(built: tuple[BuildResult, Repo, TrackingStore]) -> None:
    result, repo, _ = built
    stored = repo.get_realism(result.match_id)
    assert stored is not None and stored["checks"] and isinstance(stored["ok"], bool)


def test_every_moment_has_a_snapshot(built: tuple[BuildResult, Repo, TrackingStore]) -> None:
    result, repo, _ = built
    meta = repo.get_match_meta(result.match_id)
    assert meta is not None
    snaps = {
        (r.period, r.t, r.scope_id)
        for r in repo.list_metrics(result.match_id)
        if r.kind == "moment" and r.scope == "team"
    }
    for m in repo.list_moments(result.match_id):
        for team in (meta.home.club_id, meta.away.club_id):
            assert (m.period, m.t_end, team) in snaps, m.moment_id


def test_snapshot_equals_metrics_at(built: tuple[BuildResult, Repo, TrackingStore]) -> None:
    result, repo, _ = built
    data = _match(built)
    rows = repo.list_metrics(result.match_id)
    picks = rows[:: max(len(rows) // 40, 1)]
    for r in picks:
        live = metrics_at(data, GRID, r.period, r.t, r.scope, r.scope_id)
        assert live.get(r.name) == pytest.approx(r.value), (r.name, r.period, r.t)
        assert repo.get_metric(
            result.match_id, r.name, r.scope, r.scope_id, (r.period, r.t)
        ) == pytest.approx(r.value)


def test_metrics_at_no_lookahead(built: tuple[BuildResult, Repo, TrackingStore]) -> None:
    data = _match(built)
    home = data.meta.home.club_id
    star = data.meta.home_squad[10].player_id
    for period, t in ((1, 1200.0), (2, 600.0)):
        cut = data.model_copy(
            update={
                "events": [e for e in data.events if (e.period, e.t) <= (period, t)],
                "frames": [f for f in data.frames if (f.period, f.t) <= (period, t)],
            }
        )
        assert metrics_at(data, GRID, period, t, "team", home) == metrics_at(
            cut, GRID, period, t, "team", home
        )
        assert metrics_at(data, GRID, period, t, "player", star) == metrics_at(
            cut, GRID, period, t, "player", star
        )


def test_metric_names() -> None:
    from matchmind.stats.metrics import PLAYER_METRICS, TEAM_METRICS

    assert {"goals", "xg", "possession", "ppda", "momentum", "control_chaos", "territory"} <= set(
        TEAM_METRICS
    )
    assert {"passes", "pass_accuracy", "xt_added", "shots", "minutes"} <= set(PLAYER_METRICS)


def test_rebuild_replaces_rows(built: tuple[BuildResult, Repo, TrackingStore]) -> None:
    result, repo, store = built
    before = (
        len(repo.get_events(result.match_id)),
        len(repo.list_metrics(result.match_id)),
        len(repo.list_moments(result.match_id)),
        len(repo.list_cues(result.match_id)),
    )
    again = build_scenario(SCENARIO_DIR / "comeback_red_card.toml", repo, store)
    after = (
        len(repo.get_events(again.match_id)),
        len(repo.list_metrics(again.match_id)),
        len(repo.list_moments(again.match_id)),
        len(repo.list_cues(again.match_id)),
    )
    assert again.match_id == result.match_id and before == after
    assert repo.list_matches() == [result.match_id]


def test_compute_metrics_grid_and_extra_times(
    built: tuple[BuildResult, Repo, TrackingStore],
) -> None:
    data = _match(built)
    rows = compute_metrics(data, GRID, step_s=600.0, extra_times=[(1, 123.4)])
    grid_t = sorted({(r.period, r.t) for r in rows if r.kind == "grid"})
    assert grid_t[:3] == [(1, 0.0), (1, 600.0), (1, 1200.0)]
    assert {(r.period, r.t) for r in rows if r.kind == "moment"} == {(1, 123.4)}
