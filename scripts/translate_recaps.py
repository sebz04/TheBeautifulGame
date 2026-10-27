"""Translate every stored English recap into es, pt, fr, and ar (TASK-25.2).

Only the recap step of the precompute (``orchestrator.translate_recaps``): an agent recap is
translated by the Narrative agent and checked again in its language; a template recap gets
its template in that language. Languages already stored are skipped.

Usage:
    uv run python scripts/translate_recaps.py            # all matches, local database
    uv run python scripts/translate_recaps.py --match r01-chapinero-v-laureles
"""

from __future__ import annotations

import argparse
import asyncio

from azure.identity.aio import DefaultAzureCredential

from matchmind.agents.orchestrator import Deps, translate_recaps
from matchmind.agents.runtime import configure_tracing, make_chat_client
from matchmind.config import get_settings
from matchmind.store.db import Repo


async def run(match_ids: list[str] | None) -> None:
    settings = get_settings()
    configure_tracing(settings)
    repo = Repo(settings.db_url)
    async with DefaultAzureCredential() as credential:
        client = make_chat_client(settings, credential)
        deps = Deps(repo=repo, client=client, tools=None, facts_for=lambda _: None)  # type: ignore[arg-type,return-value]
        for match_id in match_ids or repo.list_matches():
            runs = await translate_recaps(match_id, deps)
            sources = {lang: (r.source if (r := repo.get_recap(match_id, lang)) else None)
                       for lang in ("es", "pt", "fr", "ar")}  # fmt: skip
            print(f"{match_id}: {len(runs)} agent runs, {sources}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--match", action="append", help="match id (repeatable; default all)")
    asyncio.run(run(parser.parse_args().match))


if __name__ == "__main__":
    main()
