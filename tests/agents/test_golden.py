"""The Verifier's golden set (evals/verifier_golden.jsonl), deterministic stage only.

With a judge that passes everything, the number check alone must catch every error planted
for it, pass every correct insight, and let every wording error through (those are the
Verifier agent's job: `scripts/run_foundry_eval.py` measures it against the live model).
Since TASK-25.2 the deterministic stage also catches the two wording errors that give a team's
number to the other team (``owners.py``).
"""

import json
from pathlib import Path
from typing import Any

import pytest

from matchmind.agents.runtime import FakeChatClient
from matchmind.agents.verifier import DictFacts, verify
from matchmind.schemas import Insight

CAUGHT_BY_CODE = {"e18", "e19"}  # wrong-team numbers: "leaving Chapinero with 10 players"
GOLDEN = Path(__file__).parents[2] / "evals" / "verifier_golden.jsonl"
LINES: list[dict[str, Any]] = [json.loads(line) for line in GOLDEN.read_text().splitlines()]


def test_golden_set_shape() -> None:
    assert len(LINES) == 40
    assert sum(not x["planted"] for x in LINES) == 20
    assert sum(x["stage"] == "numbers" for x in LINES) == 12
    assert sum(x["stage"] == "wording" for x in LINES) == 8
    assert {x["lang"] for x in LINES} == {"en", "es", "pt", "fr", "ar"}


@pytest.mark.parametrize("line", LINES, ids=lambda x: f"{x['id']}-{x['kind']}")
async def test_number_stage_on_golden_set(line: dict[str, Any]) -> None:
    passes = {"checks": [{"statement": "all", "verdict": "supported", "reason": ""}]}
    judge = FakeChatClient({"*": json.dumps(passes)})
    insight = Insight(**line["insight"])
    verdict = await verify(insight, line["lang"], line["text"], DictFacts(line["facts"]), judge)
    caught = line["stage"] == "numbers" or line["id"] in CAUGHT_BY_CODE
    assert verdict.ok is not caught, verdict.failures
