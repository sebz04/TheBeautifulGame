from pathlib import Path

from seed_demo import seed

from matchmind.store.db import Repo


def test_seed_builds_an_offline_demo_match(tmp_path: Path) -> None:
    """One built match with template insights (each with a real, checked number), fan texts
    in all five languages, live lines, and a recap: no model needed."""
    db = f"sqlite:///{tmp_path}/demo.db"
    match_id = seed(db, tmp_path, "comeback_red_card")
    repo = Repo(db)
    insights = repo.list_insights(match_id)
    assert len(insights) == len(repo.list_moments(match_id)) > 5
    assert all(i.verified and i.source == "template" for i in insights)
    assert sum(bool(i.claims) for i in insights) >= len(insights) // 2
    for lang in ("en", "es", "pt", "fr", "ar"):
        assert len(repo.list_personalized(match_id, lang=lang)) >= len(insights) * 4
    assert set(repo.list_live_lines(match_id)) == {i.insight_id for i in insights}
    assert repo.get_recap(match_id) is not None
    assert all(repo.get_recap(match_id, lang) is not None for lang in ("es", "pt", "fr", "ar"))
    assert (tmp_path / "tracking" / match_id / "frames.parquet").exists()


def test_all_scenarios_are_the_eight_showcase_matches() -> None:
    from seed_demo import all_scenarios

    names = all_scenarios()
    assert len(names) == 8 and "comeback_red_card" in names


def test_if_missing_skips_a_database_that_already_has_matches(tmp_path: Path) -> None:
    from seed_demo import main_args

    db = f"sqlite:///{tmp_path}/demo.db"
    seed(db, tmp_path, "comeback_red_card")
    assert main_args(["--db", db, "--data-dir", str(tmp_path), "--all", "--if-missing"]) == []
