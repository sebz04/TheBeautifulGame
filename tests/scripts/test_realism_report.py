from realism_report import fixture_for_seed, render_markdown

from matchmind.engine.validate import Check, RealismReport
from matchmind.league.fixtures import build_fixtures
from matchmind.league.league import build_league


def test_render_markdown_marks_pass_and_fail() -> None:
    report = RealismReport(
        checks=[
            Check(name="passes", value=512.0, lo=350, hi=650, ok=True, in_range_share=0.9),
            Check(name="tackles", value=91.5, lo=10, hi=25, ok=False, in_range_share=0.0),
        ],
        ok=False,
    )
    md = render_markdown(report, level=1, seeds=20)
    assert "Level 1" in md and "20 seeds" in md
    assert "| passes | 512.00 | 350–650 | 90% | pass |" in md
    assert "| tackles | 91.50 | 10–25 | 0% | **FAIL** |" in md
    assert "1/2 checks pass" in md


def test_fixtures_vary_by_seed() -> None:
    fixtures = build_fixtures(build_league(), seed=2026)
    picked = {fixture_for_seed(fixtures, s).match_id for s in range(1, 21)}
    assert len(picked) == 20
