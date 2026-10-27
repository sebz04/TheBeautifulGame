from pathlib import Path

from seed_cloud import copy_tables, grant_sql, upload_tracking

from matchmind.schemas import Recap
from matchmind.store.blob import LocalBackend
from matchmind.store.db import Repo


def test_copy_tables_replaces_the_target_with_the_source(tmp_path: Path) -> None:
    src, dst = f"sqlite:///{tmp_path}/a.db", f"sqlite:///{tmp_path}/b.db"
    Repo(src).save_recap(Recap(match_id="m1", title="T", paragraphs=["p"], key_numbers=[],
                               verified=True, source="agent"))  # fmt: skip
    Repo(dst).save_recap(Recap(match_id="old", title="Old", paragraphs=["x"], key_numbers=[],
                               verified=True, source="template"))  # fmt: skip
    counts = copy_tables(src, dst, chunk=1)
    assert counts["narratives"] == 1
    assert Repo(dst).get_recap("m1") is not None and Repo(dst).get_recap("old") is None


def test_upload_tracking_copies_every_match_file(tmp_path: Path) -> None:
    local = tmp_path / "tracking"
    (local / "m1").mkdir(parents=True)
    (local / "m1" / "frames.parquet").write_bytes(b"parquet")
    target = LocalBackend(tmp_path / "cloud")
    assert upload_tracking(local, target) == ["m1/frames.parquet"]
    assert target.get("m1/frames.parquet") == b"parquet"


def test_grant_sql_names_the_app_identity() -> None:
    sql = grant_sql("ca-matchmind-api")
    assert "CREATE USER [ca-matchmind-api] FROM EXTERNAL PROVIDER" in sql[0]
    assert any("db_datareader" in s for s in sql) and any("db_datawriter" in s for s in sql)


def test_copy_tables_rebuilds_the_target_schema(tmp_path: Path) -> None:
    """A target created by an older schema (a narrower column, say) is dropped and rebuilt."""
    from sqlalchemy import create_engine, inspect, text

    dst = f"sqlite:///{tmp_path}/b.db"
    with create_engine(dst).begin() as c:
        c.execute(text("CREATE TABLE agent_runs (run_id VARCHAR(5) PRIMARY KEY)"))
    copy_tables(f"sqlite:///{tmp_path}/a.db", dst)
    cols = {c["name"] for c in inspect(create_engine(dst)).get_columns("agent_runs")}
    assert {"moment_id", "tokens_in"} <= cols


def _source(tmp_path: Path) -> str:
    src = f"sqlite:///{tmp_path}/src.db"
    repo = Repo(src)
    for lang in ("en", "es", "pt", "fr", "ar"):
        repo.save_recap(Recap(match_id="m1", title=lang, paragraphs=["p"], key_numbers=[],
                              verified=True, source="agent", lang=lang))  # fmt: skip
    repo.save_live_line("m1", "m1-m001-ins", "line")
    return src


def test_resume_finishes_a_partial_copy_without_duplicates(tmp_path: Path) -> None:
    from sqlalchemy import delete, func, select

    from matchmind.store.db import narratives

    src, dst = _source(tmp_path), f"sqlite:///{tmp_path}/dst.db"
    copy_tables(src, dst, chunk=2)
    with Repo(dst).engine.begin() as c:  # a dropped connection after the first 2 rows
        keep = [k for (k,) in c.execute(select(narratives.c.key).order_by(narratives.c.key))][:2]
        c.execute(delete(narratives).where(narratives.c.key.not_in(keep)))
    counts = copy_tables(src, dst, chunk=2, resume=True)
    assert counts["narratives"] == 6
    with Repo(dst).engine.connect() as c:
        assert c.execute(select(func.count()).select_from(narratives)).scalar() == 6
    assert Repo(dst).get_recap("m1", "ar") is not None


def test_resume_skips_tables_already_copied(tmp_path: Path) -> None:
    src, dst = _source(tmp_path), f"sqlite:///{tmp_path}/dst.db"
    copy_tables(src, dst)
    assert copy_tables(src, dst, resume=True)["narratives"] == 6  # no duplicate-key error


def test_a_chunk_is_retried_after_a_dropped_connection(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import seed_cloud
    from sqlalchemy.exc import OperationalError

    calls = {"n": 0}
    real = seed_cloud._insert_chunk

    def flaky(engine, table, rows):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 1:
            raise OperationalError("INSERT", {}, Exception("TCP Provider: Error code 0x274C"))
        return real(engine, table, rows)

    monkeypatch.setattr(seed_cloud, "_insert_chunk", flaky)
    monkeypatch.setattr(seed_cloud, "RETRY_WAIT_S", 0.0)
    src, dst = _source(tmp_path), f"sqlite:///{tmp_path}/dst.db"
    assert copy_tables(src, dst)["narratives"] == 6
