import pytest
from pydantic import BaseModel, ValidationError

from matchmind.schemas import (
    Claim,
    Club,
    Event,
    Insight,
    MatchData,
    MatchMeta,
    Moment,
    OverlayCue,
    PersonalizedText,
    Player,
    PlayerPos,
    TrackingFrame,
    Variant,
)


def make_event(**overrides) -> Event:
    fields = dict(
        event_id="m1-e00001",
        match_id="m1",
        period=1,
        t=12.3,
        type="pass",
        team_id="home",
        player_id="h7",
        x=30.0,
        y=20.0,
        end_x=45.0,
        end_y=25.0,
        outcome=True,
        receiver_id="h9",
        ball_speed_ms=14.2,
        extras={"best_score": 0.12},
    )
    fields.update(overrides)
    return Event(**fields)


def make_club(club_id: str = "c1") -> Club:
    return Club(
        club_id=club_id,
        name="Harbourside Athletic",
        short="HAR",
        primary_color="#0B3D91",
        secondary_color="#F2C14E",
        formation="4-3-3",
    )


def make_player(player_id: str = "h7", club_id: str = "c1") -> Player:
    return Player(
        player_id=player_id,
        name="Tavo Renkin",
        club_id=club_id,
        number=7,
        position="FW",
        pace=0.8,
        skill=0.7,
        stamina=0.6,
    )


def make_meta() -> MatchMeta:
    return MatchMeta(
        match_id="m1",
        seed=7,
        home=make_club("c1"),
        away=make_club("c2"),
        home_squad=[make_player("h7", "c1")],
        away_squad=[make_player("a4", "c2")],
        scenario_id="comeback_red_card",
        engine_version="0.1.0",
        stadium="Quayside Park",
        kickoff_iso="2026-10-24T15:00:00Z",
        added_time_s=(120.0, 240.0),
    )


def make_claim() -> Claim:
    return Claim(
        text="PPDA rose to 14.2", metric="ppda", value=14.2, unit="", ref="metric:ppda@1800"
    )


EXAMPLES: list[BaseModel] = [
    make_event(),
    PlayerPos(player_id="h7", team_id="home", x=1.0, y=2.0, vx=0.5, vy=-0.5),
    TrackingFrame(
        match_id="m1",
        frame=0,
        period=1,
        t=0.0,
        ball=(52.5, 34.0, 0.0),
        players=[PlayerPos(player_id="h7", team_id="home", x=1.0, y=2.0, vx=0.0, vy=0.0)],
    ),
    make_player(),
    make_club(),
    make_meta(),
    MatchData(meta=make_meta(), events=[make_event()], frames=[]),
    Moment(
        moment_id="m1-mo001",
        match_id="m1",
        period=2,
        t_start=600.0,
        t_end=900.0,
        kind="pressing_collapse",
        level="team",
        team_id="home",
        player_id=None,
        trigger_metric="ppda",
        trigger_value=14.2,
        event_ids=["m1-e00001"],
    ),
    make_claim(),
    Insight(
        insight_id="m1-i001",
        moment_id="m1-mo001",
        match_id="m1",
        level="team",
        headline="The press has gone",
        why="Home allowed far more passes per defensive action after the red card.",
        recommendation="Drop into a mid-block and protect the centre.",
        claims=[make_claim()],
        event_ids=["m1-e00001"],
        confidence="high",
        verified=True,
        source="agent",
        trace_id="abc123",
        prompt_version="explainer.v1",
    ),
    PersonalizedText(
        insight_id="m1-i001",
        persona="club_fan",
        lang="es",
        headline="Se acabó la presión",
        body="...",
        verified=True,
        club_id="c1",
    ),
    Variant(persona="player_focus", player_id="h7"),
    OverlayCue(
        cue_id="m1-q0001",
        match_id="m1",
        period=1,
        t_in=12.3,
        t_out=18.0,
        kind="speed_alert",
        priority=2,
        payload={"player_id": "h7", "speed_ms": 9.1},
    ),
]


@pytest.mark.parametrize("model", EXAMPLES, ids=lambda m: type(m).__name__)
def test_every_model_roundtrips_through_json(model):
    assert type(model).model_validate_json(model.model_dump_json()) == model


def test_event_roundtrip_json():
    event = make_event()
    assert Event.model_validate_json(event.model_dump_json()) == event


@pytest.mark.parametrize("bad_id", ["m1-e1", "m1-e000001x", "m1e00001", "m1-x00001"])
def test_event_id_format(bad_id):
    with pytest.raises(ValidationError):
        make_event(event_id=bad_id)


def test_event_id_must_belong_to_match():
    with pytest.raises(ValidationError):
        make_event(event_id="m2-e00001")


def test_event_is_frozen():
    with pytest.raises(ValidationError):
        make_event().x = 1.0  # type: ignore[misc]


def test_player_attributes_bounded():
    with pytest.raises(ValidationError):
        Player.model_validate({**make_player().model_dump(), "pace": 1.2})


def test_unknown_language_rejected():
    with pytest.raises(ValidationError):
        PersonalizedText.model_validate(
            {
                "insight_id": "i",
                "persona": "casual",
                "lang": "de",
                "headline": "h",
                "body": "b",
                "verified": False,
            }
        )


def test_unknown_persona_rejected():
    with pytest.raises(ValidationError):
        Variant.model_validate({"persona": "pundit"})


def test_period_must_be_1_or_2():
    with pytest.raises(ValidationError):
        make_event(period=3)
