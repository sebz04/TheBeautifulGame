"""The stats store: one SQLAlchemy schema for SQLite (local) and Azure SQL (cloud).

Only portable column types are used (JSON is stored as text), so no SQL is
dialect-specific. Times are (period, t) pairs. Saving a match's events, metrics,
moments, or cues replaces that match's earlier rows, so rebuilds never duplicate.
"""

import json
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    Engine,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    and_,
    create_engine,
    delete,
    insert,
    inspect,
    or_,
    select,
    text,
)
from sqlalchemy.pool import StaticPool

from matchmind.league.season import MatchResult, Season, StandingRow
from matchmind.schemas import (
    AgentRun,
    Event,
    Insight,
    MatchData,
    MatchMeta,
    MetricRow,
    Moment,
    OverlayCue,
    PersonalizedText,
    Recap,
)
from matchmind.schemas_profile import Discipline
from matchmind.stats.player_lines import PlayerMatchLine

__all__ = ["AgentRun", "MetricRow", "Repo"]

MatchTime = tuple[int, float]
ID = 96  # id column width (portable VARCHAR)

md = MetaData()
matches = Table(
    "matches",
    md,
    Column("match_id", String(ID), primary_key=True),
    Column("scenario_id", String(ID)),
    Column("seed", Integer),
    Column("home_id", String(ID)),
    Column("away_id", String(ID)),
    Column("engine_version", String(32)),
    Column("meta_json", Text),
)
events = Table(
    "events",
    md,
    Column("event_id", String(ID), primary_key=True),
    Column("match_id", String(ID), index=True),
    Column("period", Integer),
    Column("t", Float),
    Column("type", String(32)),
    Column("team_id", String(ID)),
    Column("player_id", String(ID)),
    Column("x", Float),
    Column("y", Float),
    Column("end_x", Float),
    Column("end_y", Float),
    Column("outcome", Boolean),
    Column("receiver_id", String(ID)),
    Column("ball_speed_ms", Float),
    Column("extras_json", Text),
)
metrics = Table(
    "metrics",
    md,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("match_id", String(ID)),
    Column("period", Integer),
    Column("t", Float),
    Column("scope", String(16)),
    Column("scope_id", String(ID)),
    Column("name", String(64)),
    Column("value", Float),
    Column("kind", String(16)),
    Index("ix_metric_lookup", "match_id", "name", "scope", "scope_id", "period", "t"),
)
moments = Table(
    "moments",
    md,
    Column("moment_id", String(ID), primary_key=True),
    Column("match_id", String(ID), index=True),
    Column("period", Integer),
    Column("t_start", Float),
    Column("t_end", Float),
    Column("kind", String(32)),
    Column("level", String(16)),
    Column("team_id", String(ID)),
    Column("player_id", String(ID)),
    Column("trigger_metric", String(64)),
    Column("trigger_value", Float),
    Column("event_ids_json", Text),
    Column("details_json", Text),  # e.g. a deviation's expected, baseline_per90, p_value
)
insights = Table(
    "insights",
    md,
    Column("insight_id", String(ID), primary_key=True),
    Column("match_id", String(ID), index=True),
    Column("moment_id", String(ID)),
    Column("body_json", Text),
)
personalized = Table(
    "personalized",
    md,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("insight_id", String(ID), index=True),
    Column("persona", String(16)),
    Column("lang", String(8)),
    Column("club_id", String(ID)),
    Column("player_id", String(ID)),
    Column("body_json", Text),
)
overlay_cues = Table(
    "overlay_cues",
    md,
    Column("cue_id", String(160), primary_key=True),
    Column("match_id", String(ID), index=True),
    Column("period", Integer),
    Column("t_in", Float),
    Column("body_json", Text),
)
agent_runs = Table(
    "agent_runs",
    md,
    Column("run_id", String(ID), primary_key=True),
    Column("agent", String(32)),
    Column("moment_id", String(ID), index=True),
    Column("status", String(16)),
    Column("attempts", Integer),
    Column("latency_ms", Integer),
    Column("trace_id", String(ID)),
    Column("error", Text),
    Column("tokens_in", Integer, default=0),
    Column("tokens_out", Integer, default=0),
)
# Live lines (key "line:<insight_id>") and the recap (key "recap:<match_id>").
narratives = Table(
    "narratives",
    md,
    Column("key", String(ID + 8), primary_key=True),
    Column("match_id", String(ID), index=True),
    Column("kind", String(8)),
    Column("body_json", Text),
)
season_results = Table(
    "season_results",
    md,
    Column("match_id", String(ID), primary_key=True),
    Column("round", Integer),
    Column("body_json", Text),
)
season_standings = Table(
    "season_standings",
    md,
    Column("position", Integer, primary_key=True),
    Column("club_id", String(ID)),
    Column("body_json", Text),
)
season_player_lines = Table(
    "season_player_lines",
    md,
    Column("match_id", String(ID), primary_key=True),
    Column("player_id", String(ID), primary_key=True),
    Column("round", Integer),
    Column("club_id", String(ID)),
    Column("body_json", Text),
)
season_meta = Table(
    "season_meta",
    md,
    Column("key", String(32), primary_key=True),
    Column("body_json", Text),
)


def _upto(table: Table, col_t: str, t: MatchTime) -> Any:
    period, tt = t
    return or_(table.c.period < period, and_(table.c.period == period, table.c[col_t] <= tt))


def _from(table: Table, col_t: str, t: MatchTime) -> Any:
    period, tt = t
    return or_(table.c.period > period, and_(table.c.period == period, table.c[col_t] >= tt))


class Repo:
    def __init__(self, url: str) -> None:
        kw: dict[str, Any] = {}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kw = {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}}
        self.engine: Engine = create_engine(url, **kw)
        md.create_all(self.engine)
        self._add_missing_columns()

    def _add_missing_columns(self) -> None:
        """Columns added after a table first shipped (``create_all`` won't alter it)."""
        existing = {c["name"] for c in inspect(self.engine).get_columns("agent_runs")}
        with self.engine.begin() as c:
            for col in ("tokens_in", "tokens_out"):
                if col not in existing:
                    c.execute(text(f"ALTER TABLE agent_runs ADD {col} INTEGER DEFAULT 0"))

    # ---- matches and events ---------------------------------------------------------------

    def delete_match(self, match_id: str) -> None:
        """Everything about a match (events, metrics, moments, insights, cues)."""
        with self.engine.begin() as c:
            ids = [
                r[0]
                for r in c.execute(
                    select(insights.c.insight_id).where(insights.c.match_id == match_id)
                )
            ]
            if ids:
                c.execute(delete(personalized).where(personalized.c.insight_id.in_(ids)))
            for table in (matches, events, metrics, moments, insights, overlay_cues):
                c.execute(delete(table).where(table.c.match_id == match_id))

    def save_match_data(self, data: MatchData) -> None:
        """The match's meta and events (frames go to the tracking store)."""
        m = data.meta
        with self.engine.begin() as c:
            c.execute(delete(events).where(events.c.match_id == m.match_id))
            c.execute(delete(matches).where(matches.c.match_id == m.match_id))
            c.execute(
                insert(matches).values(
                    match_id=m.match_id,
                    scenario_id=m.scenario_id,
                    seed=m.seed,
                    home_id=m.home.club_id,
                    away_id=m.away.club_id,
                    engine_version=m.engine_version,
                    meta_json=m.model_dump_json(),
                )
            )
            rows = [
                {**e.model_dump(exclude={"extras"}), "extras_json": json.dumps(e.extras)}
                for e in data.events
            ]
            if rows:
                c.execute(insert(events), rows)

    def get_event(self, event_id: str) -> Event | None:
        with self.engine.connect() as c:
            r = c.execute(select(events).where(events.c.event_id == event_id)).mappings().first()
        if r is None:
            return None
        extras = json.loads(r["extras_json"])
        return Event(**{k: v for k, v in r.items() if k != "extras_json"}, extras=extras)

    def list_matches(self) -> list[str]:
        with self.engine.connect() as c:
            return [
                r[0] for r in c.execute(select(matches.c.match_id).order_by(matches.c.match_id))
            ]

    def get_match_meta(self, match_id: str) -> MatchMeta | None:
        with self.engine.connect() as c:
            row = c.execute(
                select(matches.c.meta_json).where(matches.c.match_id == match_id)
            ).first()
        return None if row is None else MatchMeta.model_validate_json(row[0])

    def get_events(
        self,
        match_id: str,
        t_from: MatchTime | None = None,
        t_to: MatchTime | None = None,
        types: Iterable[str] | None = None,
    ) -> list[Event]:
        """Events in time order, optionally within [t_from, t_to] and of the given types."""
        if t_from is not None and t_to is not None and t_from > t_to:
            raise ValueError(f"empty window: {t_from} > {t_to}")
        q = select(events).where(events.c.match_id == match_id)
        if t_from is not None:
            q = q.where(_from(events, "t", t_from))
        if t_to is not None:
            q = q.where(_upto(events, "t", t_to))
        if types is not None:
            q = q.where(events.c.type.in_(list(types)))
        q = q.order_by(events.c.period, events.c.t, events.c.event_id)
        with self.engine.connect() as c:
            rows = c.execute(q).mappings().all()
        return [
            Event(
                **{k: v for k, v in r.items() if k != "extras_json"},
                extras=json.loads(r["extras_json"]),
            )
            for r in rows
        ]

    # ---- metrics ----------------------------------------------------------------------------

    def save_metrics(self, match_id: str, rows: Sequence[MetricRow]) -> None:
        with self.engine.begin() as c:
            c.execute(delete(metrics).where(metrics.c.match_id == match_id))
            if rows:
                c.execute(insert(metrics), [r.model_dump() for r in rows])

    def list_metrics(self, match_id: str) -> list[MetricRow]:
        q = (
            select(metrics)
            .where(metrics.c.match_id == match_id)
            .order_by(
                metrics.c.period,
                metrics.c.t,
                metrics.c.scope,
                metrics.c.scope_id,
                metrics.c.name,
                metrics.c.kind,
            )
        )
        with self.engine.connect() as c:
            return [
                MetricRow(**{k: v for k, v in r.items() if k != "id"})
                for r in c.execute(q).mappings()
            ]

    def get_snapshot(
        self, match_id: str, period: int, t: float, kind: str = "moment"
    ) -> list[MetricRow]:
        """All rows stored at exactly (period, t) of one kind."""
        q = (
            select(metrics)
            .where(
                metrics.c.match_id == match_id,
                metrics.c.period == period,
                metrics.c.t == t,
                metrics.c.kind == kind,
            )
            .order_by(metrics.c.scope, metrics.c.scope_id, metrics.c.name)
        )
        with self.engine.connect() as c:
            rows = c.execute(q).mappings().all()
        return [MetricRow(**{k: v for k, v in r.items() if k != "id"}) for r in rows]

    def get_metric(
        self, match_id: str, name: str, scope: str, scope_id: str, t: MatchTime
    ) -> float | None:
        """The latest stored value at or before (period, t), or None."""
        q = (
            select(metrics.c.value)
            .where(
                metrics.c.match_id == match_id,
                metrics.c.name == name,
                metrics.c.scope == scope,
                metrics.c.scope_id == scope_id,
                _upto(metrics, "t", t),
            )
            .order_by(metrics.c.period.desc(), metrics.c.t.desc())
            .limit(1)
        )
        with self.engine.connect() as c:
            row = c.execute(q).first()
        return None if row is None else row[0]

    # ---- moments, insights, cues, agent runs ----------------------------------------------

    def save_moments(
        self,
        match_id: str,
        items: Sequence[Moment],
        details: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        details = details or {}
        with self.engine.begin() as c:
            c.execute(delete(moments).where(moments.c.match_id == match_id))
            rows = [
                {
                    **m.model_dump(exclude={"event_ids"}),
                    "event_ids_json": json.dumps(m.event_ids),
                    "details_json": json.dumps(details.get(m.moment_id, {})),
                }
                for m in items
            ]
            if rows:
                c.execute(insert(moments), rows)

    def list_moments(self, match_id: str) -> list[Moment]:
        q = (
            select(moments)
            .where(moments.c.match_id == match_id)
            .order_by(moments.c.period, moments.c.t_start, moments.c.moment_id)
        )
        with self.engine.connect() as c:
            rows = c.execute(q).mappings().all()
        return [
            Moment(
                **{k: v for k, v in r.items() if not k.endswith("_json")},
                event_ids=json.loads(r["event_ids_json"]),
            )
            for r in rows
        ]

    def get_moment(self, moment_id: str) -> Moment | None:
        q = select(moments).where(moments.c.moment_id == moment_id)
        with self.engine.connect() as c:
            r = c.execute(q).mappings().first()
        if r is None:
            return None
        ids = json.loads(r["event_ids_json"])
        return Moment(**{k: v for k, v in r.items() if not k.endswith("_json")}, event_ids=ids)

    def moment_details(self, moment_id: str) -> dict[str, Any]:
        with self.engine.connect() as c:
            row = c.execute(
                select(moments.c.details_json).where(moments.c.moment_id == moment_id)
            ).first()
        return {} if row is None else dict(json.loads(row[0]))

    def save_insight(self, insight: Insight) -> None:
        with self.engine.begin() as c:
            c.execute(delete(insights).where(insights.c.insight_id == insight.insight_id))
            c.execute(
                insert(insights).values(
                    insight_id=insight.insight_id,
                    match_id=insight.match_id,
                    moment_id=insight.moment_id,
                    body_json=insight.model_dump_json(),
                )
            )

    def list_insights(self, match_id: str) -> list[Insight]:
        q = select(insights.c.body_json).where(insights.c.match_id == match_id)
        with self.engine.connect() as c:
            return [
                Insight.model_validate_json(r[0])
                for r in c.execute(q.order_by(insights.c.insight_id))
            ]

    def get_insight(self, insight_id: str) -> Insight | None:
        q = select(insights.c.body_json).where(insights.c.insight_id == insight_id)
        with self.engine.connect() as c:
            row = c.execute(q).first()
        return None if row is None else Insight.model_validate_json(row[0])

    def save_personalized(self, texts: Sequence[PersonalizedText]) -> None:
        with self.engine.begin() as c:
            for p in texts:
                c.execute(
                    delete(personalized).where(
                        personalized.c.insight_id == p.insight_id,
                        personalized.c.persona == p.persona,
                        personalized.c.lang == p.lang,
                        personalized.c.club_id.is_(None)
                        if p.club_id is None
                        else personalized.c.club_id == p.club_id,
                        personalized.c.player_id.is_(None)
                        if p.player_id is None
                        else personalized.c.player_id == p.player_id,
                    )
                )
                c.execute(
                    insert(personalized).values(
                        insight_id=p.insight_id,
                        persona=p.persona,
                        lang=p.lang,
                        club_id=p.club_id,
                        player_id=p.player_id,
                        body_json=p.model_dump_json(),
                    )
                )

    def list_personalized(
        self, match_id: str, persona: str | None = None, lang: str | None = None
    ) -> list[PersonalizedText]:
        q = (
            select(personalized.c.body_json)
            .join(insights, insights.c.insight_id == personalized.c.insight_id)
            .where(insights.c.match_id == match_id)
        )
        if persona is not None:
            q = q.where(personalized.c.persona == persona)
        if lang is not None:
            q = q.where(personalized.c.lang == lang)
        with self.engine.connect() as c:
            return [
                PersonalizedText.model_validate_json(r[0])
                for r in c.execute(q.order_by(personalized.c.id))
            ]

    def save_cues(self, match_id: str, cues: Sequence[OverlayCue]) -> None:
        with self.engine.begin() as c:
            c.execute(delete(overlay_cues).where(overlay_cues.c.match_id == match_id))
            if cues:
                c.execute(
                    insert(overlay_cues),
                    [
                        {
                            "cue_id": q.cue_id,
                            "match_id": q.match_id,
                            "period": q.period,
                            "t_in": q.t_in,
                            "body_json": q.model_dump_json(),
                        }
                        for q in cues
                    ],
                )

    def list_cues(self, match_id: str) -> list[OverlayCue]:
        q = (
            select(overlay_cues.c.body_json)
            .where(overlay_cues.c.match_id == match_id)
            .order_by(overlay_cues.c.period, overlay_cues.c.t_in, overlay_cues.c.cue_id)
        )
        with self.engine.connect() as c:
            return [OverlayCue.model_validate_json(r[0]) for r in c.execute(q)]

    def log_agent_run(self, run: AgentRun) -> None:
        with self.engine.begin() as c:
            c.execute(delete(agent_runs).where(agent_runs.c.run_id == run.run_id))
            c.execute(insert(agent_runs).values(**run.model_dump()))

    def list_agent_runs(self, moment_id: str) -> list[AgentRun]:
        q = (
            select(agent_runs)
            .where(agent_runs.c.moment_id == moment_id)
            .order_by(agent_runs.c.run_id)
        )
        with self.engine.connect() as c:
            return [AgentRun(**r) for r in c.execute(q).mappings()]

    def list_match_runs(self, match_id: str) -> list[AgentRun]:
        """Agent runs for a match's moments (moment ids start with the match id)."""
        q = select(agent_runs).where(agent_runs.c.moment_id.like(f"{match_id}-%"))
        with self.engine.connect() as c:
            return [AgentRun(**r) for r in c.execute(q.order_by(agent_runs.c.run_id)).mappings()]

    # ---- live lines and recap -------------------------------------------------------------

    def _put_narrative(self, key: str, match_id: str, kind: str, body: str) -> None:
        with self.engine.begin() as c:
            c.execute(delete(narratives).where(narratives.c.key == key))
            c.execute(insert(narratives).values(key=key, match_id=match_id, kind=kind,
                                                body_json=body))  # fmt: skip

    def clear_agent_outputs(self, match_id: str) -> None:
        """Delete everything the agents wrote for a match (insights, fan texts, live lines,
        recap, passed moments, agent runs), keeping the match, its stats, and its realism
        report: a fresh precompute."""
        with self.engine.begin() as c:
            c.execute(delete(insights).where(insights.c.match_id == match_id))
            c.execute(delete(personalized).where(personalized.c.insight_id.like(f"{match_id}-%")))
            c.execute(delete(narratives).where(
                and_(narratives.c.match_id == match_id, narratives.c.kind != "realism")
            ))  # fmt: skip
            c.execute(delete(agent_runs).where(agent_runs.c.moment_id.like(f"{match_id}-%")))

    def save_live_line(self, match_id: str, insight_id: str, line: str) -> None:
        self._put_narrative(f"line:{insight_id}", match_id, "line", json.dumps(line))

    def list_live_lines(self, match_id: str) -> dict[str, str]:
        """insight_id -> live line."""
        q = select(narratives.c.key, narratives.c.body_json).where(
            and_(narratives.c.match_id == match_id, narratives.c.kind == "line")
        )
        with self.engine.connect() as c:
            return {k.removeprefix("line:"): json.loads(b) for k, b in c.execute(q)}

    def save_passed_moments(self, match_id: str, moment_ids: Iterable[str]) -> None:
        """Moments the Analyst looked at and chose not to surface, so a re-run skips them."""
        for moment_id in moment_ids:
            self._put_narrative(f"passed:{moment_id}", match_id, "passed", "true")

    def list_passed_moments(self, match_id: str) -> set[str]:
        q = select(narratives.c.key).where(
            and_(narratives.c.match_id == match_id, narratives.c.kind == "passed")
        )
        with self.engine.connect() as c:
            return {k.removeprefix("passed:") for (k,) in c.execute(q)}

    def save_realism(self, match_id: str, report: dict[str, Any]) -> None:
        """The match's realism report (``engine.validate.RealismReport`` as a dict)."""
        self._put_narrative(f"realism:{match_id}", match_id, "realism", json.dumps(report))

    def get_realism(self, match_id: str) -> dict[str, Any] | None:
        q = select(narratives.c.body_json).where(narratives.c.key == f"realism:{match_id}")
        with self.engine.connect() as c:
            row = c.execute(q).first()
        return None if row is None else dict(json.loads(row[0]))

    def save_recap(self, recap: Recap) -> None:
        self._put_narrative(f"recap:{recap.match_id}", recap.match_id, "recap",
                            recap.model_dump_json())  # fmt: skip

    def get_recap(self, match_id: str) -> Recap | None:
        q = select(narratives.c.body_json).where(narratives.c.key == f"recap:{match_id}")
        with self.engine.connect() as c:
            row = c.execute(q).first()
        return None if row is None else Recap.model_validate_json(row[0])

    # ---- season -----------------------------------------------------------------------------

    def save_season(self, season: Season) -> None:
        """Replaces the stored season history."""
        with self.engine.begin() as c:
            for table in (season_results, season_standings, season_player_lines, season_meta):
                c.execute(delete(table))
            if season.results:
                c.execute(
                    insert(season_results),
                    [
                        {"match_id": r.match_id, "round": r.round, "body_json": r.model_dump_json()}
                        for r in season.results
                    ],
                )
            if season.standings:
                c.execute(
                    insert(season_standings),
                    [
                        {"position": n + 1, "club_id": s.club_id, "body_json": s.model_dump_json()}
                        for n, s in enumerate(season.standings)
                    ],
                )
            if season.player_lines:
                c.execute(
                    insert(season_player_lines),
                    [
                        {
                            "match_id": ln.match_id,
                            "player_id": ln.player_id,
                            "round": ln.round,
                            "club_id": ln.club_id,
                            "body_json": ln.model_dump_json(),
                        }
                        for ln in season.player_lines
                    ],
                )
            meta = {
                "rounds": season.rounds,
                "milestones": season.milestones,
                "discipline": {k: v.model_dump() for k, v in season.discipline.items()},
                "unavailable": {k: sorted(v) for k, v in season.unavailable.items()},
            }
            c.execute(insert(season_meta).values(key="season", body_json=json.dumps(meta)))

    def load_season(self) -> Season | None:
        with self.engine.connect() as c:
            meta_row = c.execute(
                select(season_meta.c.body_json).where(season_meta.c.key == "season")
            ).first()
            if meta_row is None:
                return None
            results = [
                MatchResult.model_validate_json(r[0])
                for r in c.execute(
                    select(season_results.c.body_json).order_by(
                        season_results.c.round, season_results.c.match_id
                    )
                )
            ]
            table = [
                StandingRow.model_validate_json(r[0])
                for r in c.execute(
                    select(season_standings.c.body_json).order_by(season_standings.c.position)
                )
            ]
            lines = [
                PlayerMatchLine.model_validate_json(r[0])
                for r in c.execute(
                    select(season_player_lines.c.body_json).order_by(
                        season_player_lines.c.round,
                        season_player_lines.c.match_id,
                        season_player_lines.c.player_id,
                    )
                )
            ]
        meta = json.loads(meta_row[0])
        return Season(
            rounds=meta["rounds"],
            results=results,
            standings=table,
            player_lines=lines,
            milestones=meta["milestones"],
            discipline={k: Discipline(**v) for k, v in meta["discipline"].items()},
            unavailable={k: set(v) for k, v in meta["unavailable"].items()},
        )
