"""Sweep stored insights and fan texts with the Verifier's newer checks.

- Lead wording the score contradicts (TASK-24.4), team numbers given to the other team
  (TASK-25.2, ``agents/owners.py``), and PPDA read as pressure faced
  (``agents/meaning.py``): an insight that fails becomes its template (and so do all its
  fan texts and its live line); a fan text that fails becomes its template for that fan.
  Templates are built from the checked claims only, so they're right by construction.
- Template texts are rendered again, so template fixes (French elision, headlines without
  a subject; TASK-25.2) reach texts stored before them.

Usage:
    uv run python scripts/fix_scoreline.py                       # dry run, local database
    uv run python scripts/fix_scoreline.py --apply               # fix the local database
    uv run --extra azure python scripts/fix_scoreline.py --apply \\
        --db "$(azd env get-value MATCHMIND_SQL_URL)"
"""

from __future__ import annotations

import argparse

from matchmind.agents.context import match_names
from matchmind.agents.meaning import ppda_slips
from matchmind.agents.orchestrator import ALL_LANGS, template_insight
from matchmind.agents.owners import owner_failures
from matchmind.agents.personalizer import variants_for
from matchmind.agents.scoreline import lead_failures, team_variants
from matchmind.agents.templates import render
from matchmind.config import get_settings
from matchmind.schemas import Claim, Event, Lang, Moment, Variant
from matchmind.store.db import Repo


def _score_at(moment: Moment, goals: list[Event], home: str, away: str) -> dict[str, int]:
    """Goals by club at the moment's end."""
    scored = [g.team_id for g in goals if (g.period, g.t) <= (moment.period, moment.t_end)]
    return {home: scored.count(home), away: scored.count(away)}


def _fails(text: str, lang: Lang, claims: list[Claim], teams: dict[str, list[str]],
           score: dict[str, int]) -> bool:  # fmt: skip
    return bool(
        lead_failures(text, lang, teams, score)
        or owner_failures(text, lang, claims, teams)
        or ppda_slips(text, lang)
    )


def sweep(repo: Repo, apply: bool) -> dict[str, int]:
    """Count (and with ``apply``, replace) the insights and texts that fail the lead or team
    number checks, and the template texts a fresh render would change."""
    counts = {"insights": 0, "texts": 0, "templates": 0}
    for match_id in repo.list_matches():
        meta = repo.get_match_meta(match_id)
        assert meta is not None
        home, away = meta.home.club_id, meta.away.club_id
        teams = team_variants({home: meta.home.name, away: meta.away.name})
        names = match_names(meta)
        goals = repo.get_events(match_id, types=("goal",))
        moments = {m.moment_id: m for m in repo.list_moments(match_id)}

        insights = {i.insight_id: i for i in repo.list_insights(match_id)}
        replaced: set[str] = set()
        for ins in insights.values():
            text = f"{ins.headline}. {ins.why} {ins.recommendation}"
            if ins.moment_id in moments and _fails(
                text, "en", ins.claims, teams, _score_at(moments[ins.moment_id], goals, home, away)
            ):
                counts["insights"] += 1
                replaced.add(ins.insight_id)
                if apply:
                    moment = moments[ins.moment_id]
                    fixed = template_insight(moment, ins.level, names)
                    repo.save_insight(fixed)
                    repo.save_live_line(match_id, fixed.insight_id, fixed.headline)
                    for lang in ALL_LANGS:
                        repo.save_personalized(
                            [render(fixed, v, lang, names) for v in variants_for(fixed, meta)]
                        )
        for t in repo.list_personalized(match_id):
            ins = insights.get(t.insight_id)
            if ins is None or t.insight_id in replaced or ins.moment_id not in moments:
                continue
            v = Variant(persona=t.persona, club_id=t.club_id, player_id=t.player_id)
            if t.source == "template":
                fresh = render(ins, v, t.lang, names)
                if (fresh.headline, fresh.body) != (t.headline, t.body):
                    counts["templates"] += 1
                    if apply:
                        repo.save_personalized([fresh])
                continue
            score = _score_at(moments[ins.moment_id], goals, home, away)
            if _fails(f"{t.headline}. {t.body}", t.lang, ins.claims, teams, score):
                counts["texts"] += 1
                if apply:
                    repo.save_personalized([render(ins, v, t.lang, names)])
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", help="database URL (default: MATCHMIND_DB_URL)")
    parser.add_argument("--apply", action="store_true", help="replace them (default: dry run)")
    args = parser.parse_args()
    repo = Repo(args.db or get_settings().db_url)
    counts = sweep(repo, apply=args.apply)
    print(("replaced" if args.apply else "would replace"), counts)
    if args.apply:
        print("left after the sweep:", sweep(repo, apply=False))


if __name__ == "__main__":
    main()
