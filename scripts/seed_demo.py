"""Build one match with template insights, offline: no model, no Azure.

The insights are the deterministic templates (Constitution II), each given one real number
(the team's possession at the moment's end, read through the stats service the Verifier
uses), so the cards, "Ask why", and every language have content. Used by the Playwright
smoke test in CI and for a local demo without Foundry.

Usage:
    uv run python scripts/seed_demo.py --db sqlite:///data/demo.db --data-dir data/demo
"""

from __future__ import annotations

import argparse
from pathlib import Path

from matchmind.agents.context import match_names
from matchmind.agents.narrative import recap_context, template_recap
from matchmind.agents.orchestrator import ALL_LANGS, template_insight
from matchmind.agents.personalizer import variants_for
from matchmind.agents.templates import render
from matchmind.engine.scenario import SCENARIO_DIR
from matchmind.mcp_server.server import StatsService
from matchmind.pipeline.build_match import build_scenario
from matchmind.schemas import Claim
from matchmind.store.blob import LocalBackend, TrackingStore
from matchmind.store.db import Repo


def seed(db_url: str, data_dir: Path, scenario: str) -> str:
    """Build ``scenario`` into ``db_url`` and ``data_dir/tracking``; returns the match id."""
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    if db_url.startswith("sqlite:///"):
        Path(db_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    repo = Repo(db_url)
    store = TrackingStore(LocalBackend(Path(data_dir) / "tracking"))
    match_id = build_scenario(SCENARIO_DIR / f"{scenario}.toml", repo, store).match_id
    meta = repo.get_match_meta(match_id)
    assert meta is not None
    names, stats = match_names(meta), StatsService(repo, store)
    insights = []
    for moment in repo.list_moments(match_id):
        insight = template_insight(moment, moment.level, names)
        team = moment.team_id or meta.home.club_id
        got = stats.get_metric(match_id, "possession", "team", team, moment.period, moment.t_end)
        if got.get("value") is not None:
            pct = round(100 * got["value"])
            claim = Claim(text=f"{pct}% possession for {names[team]}", metric="possession",
                          value=got["value"], unit="", ref=got["ref"])  # fmt: skip
            insight = insight.model_copy(update={"claims": [claim]})
        repo.save_insight(insight)
        repo.save_live_line(match_id, insight.insight_id, insight.headline)
        for lang in ALL_LANGS:
            repo.save_personalized(
                [render(insight, v, lang, names) for v in variants_for(insight, meta)]
            )
        insights.append(insight)
    repo.save_recap(template_recap(recap_context(repo, match_id), insights))
    return match_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", required=True, help="database URL, e.g. sqlite:///data/demo.db")
    parser.add_argument("--data-dir", type=Path, required=True, help="where tracking files go")
    parser.add_argument("--scenario", default="comeback_red_card")
    args = parser.parse_args()
    print(seed(args.db, args.data_dir, args.scenario))


if __name__ == "__main__":
    main()
