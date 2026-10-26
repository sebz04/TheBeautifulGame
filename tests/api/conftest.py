"""One built match (the comeback scenario) with a seeded insight, texts, recap, and runs."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from matchmind.api.app import create_app
from matchmind.engine.scenario import SCENARIO_DIR
from matchmind.league.season import MatchResult, Season, standings
from matchmind.pipeline.build_match import build_scenario
from matchmind.schemas import AgentRun, Claim, Insight, MatchMeta, PersonalizedText, Recap
from matchmind.stats.player_lines import PlayerMatchLine
from matchmind.store.blob import LocalBackend, TrackingStore
from matchmind.store.db import Repo


@dataclass
class Built:
    repo: Repo
    store: TrackingStore
    meta: MatchMeta
    insight: Insight


@pytest.fixture(scope="session")
def built(tmp_path_factory: pytest.TempPathFactory) -> Built:
    tmp = Path(tmp_path_factory.mktemp("api"))
    repo, store = Repo("sqlite:///:memory:"), TrackingStore(LocalBackend(tmp))
    result = build_scenario(SCENARIO_DIR / "comeback_red_card.toml", repo, store)
    meta = repo.get_match_meta(result.match_id)
    assert meta is not None
    # A moment that cites a decision (a big chance), so /why has a counterfactual.
    moment = next(m for m in repo.list_moments(meta.match_id)
                  if any("best_score" in (e.extras if (e := repo.get_event(i)) else {})
                         for i in m.event_ids))  # fmt: skip
    home, away = meta.home.club_id, meta.away.club_id
    # A one-round stored season, so player baselines ("vs season average") exist.
    result_ = MatchResult(match_id="r00-x", round=1, date="2026-08-01", home_id=home,
                          away_id=away, home_goals=1, away_goals=1)  # fmt: skip
    lines = [PlayerMatchLine(match_id="r00-x", round=1, player_id=p.player_id, club_id=home,
                             minutes=90, passes=40, forward_passes=15)
             for p in meta.home_squad[:11]]  # fmt: skip
    table = standings([result_], [home, away])
    repo.save_season(Season(rounds=1, results=[result_], standings=table, player_lines=lines,
                            milestones={}, discipline={}, unavailable={}))  # fmt: skip
    ref = f"metric:ppda_10min@{moment.period}:{moment.t_end}/team:{moment.team_id or home}"
    insight = Insight(
        insight_id=f"{moment.moment_id}-ins", moment_id=moment.moment_id,
        match_id=meta.match_id, level=moment.level, headline="The press switched off",
        why="They allow 9.0 passes per defensive action.", recommendation="Step up.",
        claims=[Claim(text="9.0 passes", metric="ppda_10min", value=9.0, unit="", ref=ref)],
        event_ids=moment.event_ids[:3], confidence="high", verified=True, source="agent",
        trace_id="abc123", prompt_version="explainer.v1",
    )  # fmt: skip
    repo.save_insight(insight)
    repo.save_personalized([
        PersonalizedText(insight_id=insight.insight_id, persona="analyst", lang=lang,
                         headline=f"Analyst {lang}", body="9.0 passes per action.",
                         verified=True)
        for lang in ("en", "es")
    ] + [PersonalizedText(insight_id=insight.insight_id, persona="club_fan", lang="en",
                          club_id=home, headline="For the home fans", body="Press again!",
                          verified=True)])  # fmt: skip
    repo.save_recap(Recap(match_id=meta.match_id, title="A comeback", paragraphs=["They won."],
                          key_numbers=[], verified=True, source="agent"))  # fmt: skip
    repo.log_agent_run(AgentRun(run_id="r1", agent="explainer", moment_id=moment.moment_id,
                                status="ok", attempts=1, latency_ms=900, trace_id="abc123",
                                error=None, tokens_in=10, tokens_out=5))  # fmt: skip
    return Built(repo, store, meta, insight)


@pytest.fixture(scope="session")
def client(built: Built) -> Iterator[TestClient]:
    with TestClient(create_app(repo=built.repo, store=built.store)) as c:
        yield c
