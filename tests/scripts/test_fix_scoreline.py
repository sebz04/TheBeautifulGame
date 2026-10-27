from fix_scoreline import sweep

from matchmind.engine.lineup import match_meta
from matchmind.league.fixtures import build_fixtures
from matchmind.league.league import build_league
from matchmind.schemas import Claim, Event, Insight, MatchData, Moment, PersonalizedText
from matchmind.store.db import Repo


def _world() -> tuple[Repo, str, str]:
    league = build_league()
    meta = match_meta(league, build_fixtures(league, seed=2026)[0], seed=7)
    repo = Repo("sqlite://")
    mid, home, away = meta.match_id, meta.home.club_id, meta.away.club_id
    goal = lambda i, team, t: Event(  # noqa: E731
        event_id=f"{mid}-e{i:05d}", match_id=mid, period=1, t=t, type="goal", team_id=team,
        player_id=None, x=100, y=34, end_x=None, end_y=None, outcome=True, receiver_id=None,
        ball_speed_ms=None)  # fmt: skip
    repo.save_match_data(
        MatchData(meta=meta, events=[goal(1, away, 600.0), goal(2, home, 1200.0)], frames=[])
    )
    moment = Moment(moment_id=f"{mid}-m001", match_id=mid, period=1, t_start=1190.0, t_end=1210.0,
                    kind="goal", level="player", team_id=home, player_id=None,
                    trigger_metric="goals", trigger_value=1.0,
                    event_ids=[f"{mid}-e00002"])  # fmt: skip
    repo.save_moments(mid, [moment])
    return repo, mid, meta.home.name


def _insight(mid: str, headline: str) -> Insight:
    return Insight(insight_id=f"{mid}-m001-ins", moment_id=f"{mid}-m001", match_id=mid,
                   level="player", headline=headline, why="w", recommendation="r", claims=[],
                   event_ids=[], confidence="high", verified=True, source="agent", trace_id=None,
                   prompt_version="explainer.v1")  # fmt: skip


def test_sweep_replaces_texts_that_claim_a_false_lead() -> None:
    repo, mid, home = _world()  # 1–1 after the moment's goal
    repo.save_insight(_insight(mid, "A goal levels it"))
    bad = PersonalizedText(
        insight_id=f"{mid}-m001-ins",
        persona="casual",
        lang="en",
        headline=f"Goal gives {home} the lead",
        body="b",
        verified=True,
    )
    good = bad.model_copy(update={"lang": "es", "headline": "Gol del empate"})
    repo.save_personalized([bad, good])
    found = sweep(repo, apply=False)
    assert found == {"insights": 0, "texts": 1, "templates": 0}
    assert sweep(repo, apply=True) == {"insights": 0, "texts": 1, "templates": 0}
    fixed = repo.list_personalized(mid, persona="casual", lang="en")[0]
    assert fixed.source == "template" and "lead" not in fixed.headline.lower()
    assert repo.list_personalized(mid, lang="es")[0].headline == "Gol del empate"
    assert sweep(repo, apply=False) == {"insights": 0, "texts": 0, "templates": 0}


def test_sweep_replaces_a_false_lead_insight_and_all_its_texts() -> None:
    repo, mid, home = _world()
    repo.save_insight(_insight(mid, f"Morejo gives {home} the lead"))
    text = PersonalizedText(insight_id=f"{mid}-m001-ins", persona="analyst", lang="fr",
                            headline="h", body="b", verified=True)  # fmt: skip
    repo.save_personalized([text])
    assert sweep(repo, apply=True)["insights"] == 1
    ins = repo.list_insights(mid)[0]
    assert ins.source == "template" and "lead" not in ins.headline.lower()
    texts = repo.list_personalized(mid)
    assert texts and all(t.source == "template" for t in texts)
    assert repo.list_live_lines(mid)[ins.insight_id] == ins.headline


def test_sweep_replaces_a_text_that_gives_a_number_to_the_wrong_team() -> None:
    repo, mid, home = _world()
    away_id = repo.get_match_meta(mid).away.club_id  # type: ignore[union-attr]
    claim = Claim(text="share of the ball", metric="possession", value=0.46, unit="%",
                  ref=f"metric:possession@1:1200.0/team:{away_id}")  # fmt: skip
    repo.save_insight(_insight(mid, "A goal levels it").model_copy(update={"claims": [claim]}))
    body = f"{home} have 46% of the ball."
    bad = PersonalizedText(insight_id=f"{mid}-m001-ins", persona="casual", lang="en",
                           headline="h", body=body, verified=True)  # fmt: skip
    repo.save_personalized([bad])
    assert sweep(repo, apply=True)["texts"] == 1
    assert repo.list_personalized(mid)[0].source == "template"


def test_sweep_re_renders_stale_templates() -> None:
    repo, mid, _ = _world()
    repo.save_insight(_insight(mid, "A goal levels it"))
    stale = PersonalizedText(insight_id=f"{mid}-m001-ins", persona="casual", lang="en",
                             headline="What just happened: the match", body="In short:",
                             verified=True, source="template")  # fmt: skip
    repo.save_personalized([stale])
    assert sweep(repo, apply=True)["templates"] == 1
    assert repo.list_personalized(mid)[0].headline == "What just happened"
    assert sweep(repo, apply=False)["templates"] == 0
