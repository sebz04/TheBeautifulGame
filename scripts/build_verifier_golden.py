"""Build the Verifier's golden set: 20 correct insights and 20 with one planted error each.

Usage: uv run python scripts/build_verifier_golden.py

Insights are written by code from the built matches' real stats and events (so the
correct ones really are correct), in all 5 languages. Each error is planted in a copy of a
correct insight and labelled with the stage that should catch it: ``numbers`` (the
deterministic check) or ``wording`` (the Verifier agent). Every line carries the facts the
Verifier needs, so the set runs without the database. Writes `evals/verifier_golden.jsonl`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from matchmind.agents.verifier import StatsFacts
from matchmind.clock import match_minute, minute_label
from matchmind.config import get_settings
from matchmind.mcp_server.server import StatsService
from matchmind.schemas import Claim, Event, Insight, Lang
from matchmind.store.blob import tracking_store
from matchmind.store.db import Repo

OUT = Path(__file__).resolve().parents[1] / "evals" / "verifier_golden.jsonl"
MATCHES = ["r01-chapinero-v-laureles", "r11-el-poblado-v-san-fernando", "r36-chapinero-v-usaquen"]
ARABIC = str.maketrans("0123456789.", "٠١٢٣٤٥٦٧٨٩٫")


class Item:
    """One golden insight: the English insight, the text to verify, and its facts."""

    def __init__(self, facts: StatsFacts, insight: Insight, lang: Lang, text: str) -> None:
        self.facts, self.insight, self.lang, self.text = facts, insight, lang, text

    def line(self, gid: str, kind: str, stage: str | None) -> dict[str, Any]:
        f = self.facts
        events = f.events(self.insight.event_ids)
        context = events + [b for e in events for b in f.before(e)]
        return {
            "id": gid,
            "kind": kind,
            "planted": stage is not None,
            "stage": stage,
            "lang": self.lang,
            "text": self.text,
            "insight": self.insight.model_dump(),
            "facts": {
                "names": dict(f.names),
                "minutes": sorted(f.minutes),
                "scores": sorted(f.scores),
                "formations": sorted(f.formations),
                "lookups": {_key(c): f.lookup(c) for c in self.insight.claims},
                "events": {e.event_id: e.model_dump() for e in events},
                "thirds": {e.event_id: f.third(e) for e in context},
                "before": {e.event_id: [b.model_dump() for b in f.before(e)] for e in events},
            },
        }

    def mutate(self, text: str | None = None, **insight: Any) -> Item:
        new = self.insight.model_copy(update=insight)
        if text is None:
            text = "\n".join([new.headline, new.why, new.recommendation])
        return Item(self.facts, new, self.lang, text)


def _key(c: Claim) -> str:
    return f"{c.ref}|{c.metric}|{c.unit}"


def _insight(facts: StatsFacts, gid: str, level: str, headline: str, why: str, rec: str,
             claims: list[Claim], events: list[Event]) -> Insight:  # fmt: skip
    return Insight(
        insight_id=f"golden-{gid}", moment_id=f"golden-{gid}", match_id=facts.match_id,
        level=level, headline=headline, why=why, recommendation=rec, claims=claims,  # type: ignore[arg-type]
        event_ids=[e.event_id for e in events], confidence="high", verified=False,
        source="agent", trace_id=None, prompt_version="golden",
    )  # fmt: skip


def _metric(facts: StatsFacts, name: str, team: str, period: int, t: float, text: str,
            unit: str = "") -> Claim:  # fmt: skip
    value = facts.stats.snapshot(facts.meta, period, t)[("team", team)][name]
    ref = f"metric:{name}@{period}:{t}/team:{team}"
    return Claim(text=text, metric=name, value=float(value), unit=unit, ref=ref)


def _team_events(facts: StatsFacts, team: str, types: tuple[str, ...]) -> list[Event]:
    return [e for e in facts._events.values() if e.team_id == team and e.type in types]


def press(facts: StatsFacts, e: Event) -> Item:
    """Team level: PPDA (last 10 min) and possession at an event of the pressing side."""
    team, name = e.team_id, facts.names[e.team_id]
    ppda = _metric(facts, "ppda_10min", team, e.period, e.t, "passes per defensive action")
    poss = _metric(facts, "possession", team, e.period, e.t, "share of the ball", "%")
    m = minute_label(e.period, e.t)
    why = (f"By {m}, {name} allow {ppda.value:.1f} passes per defensive action over the last "
           f"10 minutes and have {poss.value * 100:.0f}% of the ball.")  # fmt: skip
    ins = _insight(facts, "", "team", f"{name} set the tempo", why,
                   f"{name} should keep their pressing height.", [ppda, poss], [e])  # fmt: skip
    return Item(facts, ins, "en", "\n".join([ins.headline, why, ins.recommendation]))


def goal(facts: StatsFacts, e: Event) -> Item:
    team, player = facts.names[e.team_id], facts.names[e.player_id or ""]
    g = Claim(text="scored", metric="goal", value=1.0, unit="", ref=e.event_id)
    xg = _metric(facts, "xg", e.team_id, e.period, e.t, "xG so far")
    m = minute_label(e.period, e.t)
    why = f"{player} scored for {team} at {m}. {team} have {xg.value:.2f} xG so far."
    ins = _insight(facts, "", "player", f"{player} scores at {m}", why,
                   f"{team} should keep feeding {player} in the box.", [g, xg], [e])  # fmt: skip
    return Item(facts, ins, "en", "\n".join([ins.headline, why, ins.recommendation]))


def red(facts: StatsFacts, e: Event) -> Item:
    team, player = facts.names[e.team_id], facts.names[e.player_id or ""]
    card = Claim(text="sent off", metric="card", value=1.0, unit="", ref=e.event_id)
    players = _metric(facts, "players", e.team_id, e.period, e.t, "players left")
    m = minute_label(e.period, e.t)
    why = f"{player} was sent off at {m}, leaving {team} with {players.value:.0f} players."
    ins = _insight(facts, "", "team", f"{team} down a man", why,
                   f"{team} should drop into a compact block.", [card, players], [e])  # fmt: skip
    return Item(facts, ins, "en", "\n".join([ins.headline, why, ins.recommendation]))


def chance(facts: StatsFacts, e: Event) -> Item:
    player = facts.names[e.player_id or ""]
    xg = Claim(
        text="chance worth", metric="xg", value=float(e.extras["xg"]), unit="", ref=e.event_id
    )
    m = minute_label(e.period, e.t)
    why = f"{player} shot at {m} from a chance worth {xg.value:.2f} xG, and did not score."
    ins = _insight(facts, "", "player", f"{player} goes close", why,
                   f"{player} should keep attacking that space.", [xg], [e])  # fmt: skip
    return Item(facts, ins, "en", "\n".join([ins.headline, why, ins.recommendation]))


def regain(facts: StatsFacts, e: Event) -> Item:
    """A successful tackle or interception, described with the third it happened in."""
    team, player = facts.names[e.team_id], facts.names[e.player_id or ""]
    where = {"attacking": "high up the pitch", "middle": "in midfield",
             "defensive": "deep in their own half"}[facts.third(e)]  # fmt: skip
    m = minute_label(e.period, e.t)
    why = f"{player} won the ball back for {team} {where} at {m}."
    ins = _insight(
        facts,
        "",
        "player",
        f"{player} wins it back",
        why,
        f"{team} should keep supporting {player} when he steps in.",
        [],
        [e],
    )
    return Item(facts, ins, "en", "\n".join([ins.headline, why, ins.recommendation]))


def localized(item: Item, lang: Lang) -> Item:
    """The press insight's numbers written the way ``lang`` writes them."""
    ins = item.insight
    ppda, poss = ins.claims[0].value, ins.claims[1].value * 100
    team = item.facts.names[item.facts.events(ins.event_ids)[0].team_id]
    e = item.facts.events(ins.event_ids)[0]
    m, mm = minute_label(e.period, e.t), match_minute(e.period, e.t)
    p1, p0 = f"{ppda:.1f}", f"{poss:.0f}"
    text = {
        "es": f"Hasta el minuto {mm}, {team} permite {p1.replace('.', ',')} pases por acción "
              f"defensiva y tiene el {p0}% del balón.",
        "pt": f"Até aos {m}, o {team} permite {p1.replace('.', ',')} passes por ação defensiva "
              f"e tem {p0}% da posse.",
        "fr": f"À la {mm}e minute, {team} concède {p1.replace('.', ',')} passes par action "
              f"défensive et a {p0} % du ballon.",
        "ar": f"حتى الدقيقة {str(mm).translate(ARABIC)}، يسمح {team} بـ {p1.translate(ARABIC)} "
              f"تمريرة لكل إجراء دفاعي ويستحوذ على {p0.translate(ARABIC)}٪ من الكرة.",
    }[lang]  # fmt: skip
    return Item(item.facts, ins, lang, text)


def _off_minute(item: Item) -> int:
    e = item.facts.events(item.insight.event_ids)[0]
    return next(
        n for n in range(match_minute(e.period, e.t) + 3, 200) if n not in item.facts.minutes
    )


def plant(items: dict[str, list[Item]]) -> list[tuple[str, str, Item]]:
    """20 planted errors: (kind, stage, item). Each starts from a correct item."""
    pr, gl, rd, ch, rg = (items[k] for k in ("press", "goal", "red", "chance", "regain"))
    out: list[tuple[str, str, Item]] = []

    def add(kind: str, stage: str, item: Item) -> None:
        out.append((kind, stage, item))

    def edit_why(item: Item, f: Callable[[str], str]) -> Item:
        return item.mutate(why=f(item.insight.why))

    # --- caught by the deterministic number check -------------------------------------
    p = pr[0]
    c = p.insight.claims[0]
    wrong = round(c.value * 1.3 + 0.7, 1)
    add("wrong_value", "numbers", p.mutate(
        claims=[c.model_copy(update={"value": wrong}), p.insight.claims[1]],
        why=p.insight.why.replace(f"{c.value:.1f}", f"{wrong:.1f}"),
    ))  # fmt: skip
    add("invented_number", "numbers", edit_why(pr[1], lambda w: w + " They also won 47 duels."))
    p = pr[2]
    other = next(t for t in (p.facts.meta.home.club_id, p.facts.meta.away.club_id)
                 if f"/team:{t}" not in p.insight.claims[0].ref)  # fmt: skip
    swapped = [c.model_copy(update={"ref": c.ref.rsplit("/team:", 1)[0] + f"/team:{other}"})
               for c in p.insight.claims]  # fmt: skip
    add("other_team_stat", "numbers", p.mutate(claims=swapped))
    p = pr[3]
    e = p.facts.events(p.insight.event_ids)[0]
    add("wrong_minute", "numbers", edit_why(
        p, lambda w: w.replace(minute_label(e.period, e.t), f"{_off_minute(p)}'")))  # fmt: skip
    add("wrong_score", "numbers", edit_why(gl[0], lambda w: w + " That made it 4-0."))
    p = pr[0]
    rest = 100 - p.insight.claims[1].value * 100
    add("derived_number", "numbers",
        edit_why(p, lambda w: w + f" Their opponents had {rest:.1f}% of it."))  # fmt: skip
    add("wrong_formation", "numbers",
        edit_why(pr[1], lambda w: w + " They then switched to a 3-4-3."))  # fmt: skip
    p = pr[2]
    bad_ref = p.insight.claims[0].model_copy(
        update={"ref": "metric:ppda_10min@1:5999.0/team:nobody"}
    )
    add("unverifiable_ref", "numbers", p.mutate(claims=[bad_ref, p.insight.claims[1]]))
    es = localized(pr[3], "es")
    ppda = es.insight.claims[0].value
    add("es_wrong_value", "numbers", Item(es.facts, es.insight, "es", es.text.replace(
        f"{ppda:.1f}".replace(".", ","), f"{ppda + 3.4:.1f}".replace(".", ","))))  # fmt: skip
    ar = localized(pr[1], "ar")
    ppda = ar.insight.claims[0].value
    add("ar_wrong_value", "numbers", Item(ar.facts, ar.insight, "ar", ar.text.replace(
        f"{ppda:.1f}".translate(ARABIC), f"{ppda + 2.8:.1f}".translate(ARABIC))))  # fmt: skip
    p = ch[0]
    xg = p.insight.claims[0].value
    add("wrong_precision", "numbers",
        edit_why(p, lambda w: w.replace(f"{xg:.2f} xG", f"{xg + 0.21:.2f} xG")))  # fmt: skip
    add(
        "number_word",
        "numbers",
        edit_why(rd[0], lambda w: w + " It was his third card in twelve games."),
    )

    # --- caught only by the Verifier agent (numbers are right, words are wrong) --------
    g = gl[1]
    e = g.facts.events(g.insight.event_ids)[0]
    team, rival = (
        g.facts.names[e.team_id],
        g.facts.names[
            g.facts.meta.away.club_id
            if e.team_id == g.facts.meta.home.club_id
            else g.facts.meta.home.club_id
        ],
    )
    add("wrong_team", "wording", edit_why(g, lambda w: w.replace(f"for {team}", f"for {rival}", 1)))
    r = rd[0]
    e = r.facts.events(r.insight.event_ids)[0]
    squad = (
        r.facts.meta.home_squad
        if e.team_id == r.facts.meta.home.club_id
        else r.facts.meta.away_squad
    )
    other_player = next(p.name for p in squad if p.player_id != e.player_id and p.position == "FW")
    add(
        "wrong_player",
        "wording",
        edit_why(r, lambda w: w.replace(r.facts.names[e.player_id or ""], other_player)),
    )
    deep = next(i for i in rg if "deep in their own half" in i.insight.why)
    add(
        "wrong_place",
        "wording",
        edit_why(deep, lambda w: w.replace("deep in their own half", "high up the pitch")),
    )
    c0 = ch[1]
    add("wrong_outcome", "wording",
        edit_why(c0, lambda w: w.replace(", and did not score.", ", and scored.")))  # fmt: skip
    g = gl[0]
    redcard = rd[0].facts.events(rd[0].insight.event_ids)[0]
    if g.facts.match_id == rd[0].facts.match_id:
        both = g.insight.event_ids + [redcard.event_id]
        after = g.mutate(
            event_ids=both,
            why=g.insight.why.replace(
                " at ", f", after {rd[0].facts.names[redcard.team_id]}'s red card, at ", 1
            ),
        )
        add("wrong_order", "wording", after)
    r = rd[1] if len(rd) > 1 else rd[0]
    e = r.facts.events(r.insight.event_ids)[0]
    rival = r.facts.names[r.facts.meta.away.club_id if e.team_id == r.facts.meta.home.club_id
                          else r.facts.meta.home.club_id]  # fmt: skip
    add(
        "wrong_team_red",
        "wording",
        edit_why(r, lambda w: w.replace(f"leaving {r.facts.names[e.team_id]}", f"leaving {rival}")),
    )
    p = pr[1]
    e = p.facts.events(p.insight.event_ids)[0]
    rival = p.facts.names[p.facts.meta.away.club_id if e.team_id == p.facts.meta.home.club_id
                          else p.facts.meta.home.club_id]  # fmt: skip
    add("wrong_team_press", "wording",
        edit_why(p, lambda w: w.replace(p.facts.names[e.team_id], rival, 1)))  # fmt: skip
    mid = next(i for i in rg if "deep in their own half" not in i.insight.why)
    add(
        "invented_cause",
        "wording",
        edit_why(
            mid, lambda w: w.replace(" at ", " straight after a goalkeeper's long kick at ", 1)
        ),
    )
    return out


def main() -> None:
    settings = get_settings()
    repo = Repo(settings.db_url)
    stats = StatsService(repo, tracking_store(settings))
    items: dict[str, list[Item]] = {k: [] for k in ("press", "goal", "red", "chance", "regain")}
    for match_id in MATCHES:
        facts = StatsFacts(stats, match_id)
        events = sorted(facts._events.values(), key=lambda e: (e.period, e.t))
        home, away = facts.meta.home.club_id, facts.meta.away.club_id
        for team in (home, away):
            presses = [
                e for e in _team_events(facts, team, ("tackle", "interception")) if e.outcome
            ]
            items["press"] += [press(facts, presses[len(presses) // 3])]
            by_third = {facts.third(e): e for e in presses}
            wanted = ("defensive", "middle", "attacking")[len(items["regain"]) % 3]
            if wanted in by_third:
                items["regain"].append(regain(facts, by_third[wanted]))
        items["goal"] += [goal(facts, e) for e in events if e.type == "goal"][:2]
        items["red"] += [red(facts, e) for e in events
                         if e.type == "card" and e.extras.get("card") != "yellow"]  # fmt: skip
        goals = [(g.period, g.t, g.team_id) for g in events if g.type == "goal"]
        missed = [
            e for e in events
            if e.type == "shot" and float(e.extras.get("xg", 0)) > 0.2
            and not any(p == e.period and tm == e.team_id and 0 <= t - e.t <= 5.0
                        for p, t, tm in goals)  # a goal right after this shot: it went in
        ]  # fmt: skip
        items["chance"] += [chance(facts, e) for e in missed][:2]

    regains = items["regain"]
    if not any("deep in their own half" in i.insight.why for i in regains):
        raise SystemExit("no defensive-third regain found")
    correct = (items["press"][:4] + items["goal"][:3] + items["red"][:2] + items["chance"][:3]
               + regains[:3])  # fmt: skip
    correct += [localized(items["press"][4], "es"), localized(items["press"][5], "pt"),
                localized(items["press"][4], "fr"), localized(items["press"][5], "ar"),
                localized(items["press"][0], "es")]  # fmt: skip
    planted = plant(items)
    assert len(correct) == 20, len(correct)
    assert len(planted) == 20, len(planted)

    lines = [i.line(f"c{n:02d}", "correct", None) for n, i in enumerate(correct, 1)]
    lines += [i.line(f"e{n:02d}", kind, stage) for n, (kind, stage, i) in enumerate(planted, 1)]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines))
    print(f"wrote {OUT}: {len(correct)} correct, {len(planted)} planted "
          f"({sum(s == 'numbers' for _, s, _ in planted)} numbers, "
          f"{sum(s == 'wording' for _, s, _ in planted)} wording)")  # fmt: skip


if __name__ == "__main__":
    main()
