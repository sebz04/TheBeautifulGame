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
