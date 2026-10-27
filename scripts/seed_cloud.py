"""Load the precomputed matches into Azure: the database into Azure SQL, the tracking files
into Blob Storage, and read access for the API's managed identity. Keyless throughout: it
signs in as you (`az login`), so run it as the SQL server's Entra admin (azd sets you).

Usage (values from `azd env get-values`):
    uv run --extra azure python scripts/seed_cloud.py \\
        --sql-url "$(azd env get-value MATCHMIND_SQL_URL)" \\
        --blob-url "$(azd env get-value MATCHMIND_BLOB_ACCOUNT_URL)" \\
        --app-name "$(azd env get-value AZURE_IDENTITY_NAME)"

Add ``--tables personalized,narratives`` to rebuild and copy just those tables (after a
column type change). Add ``--resume`` to finish a copy that stopped (a dropped
connection): tables already complete are skipped and only missing rows are copied.
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Collection
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, Table, insert, select, text
from sqlalchemy.exc import OperationalError

from matchmind.config import get_settings
from matchmind.store.blob import CONTAINER, Backend
from matchmind.store.db import Repo, make_engine, md

RETRIES = 5
RETRY_WAIT_S = 10.0


def _insert_chunk(engine: Engine, table: Table, rows: list[dict[str, Any]]) -> None:
    with engine.begin() as out:
        out.execute(insert(table), rows)


def _insert_with_retry(engine: Engine, table: Table, rows: list[dict[str, Any]]) -> None:
    """One chunk in its own transaction, retried after a dropped connection (a home network
    to Azure SQL drops now and then: "TCP Provider: Error code 0x274C")."""
    for attempt in range(1, RETRIES + 1):
        try:
            _insert_chunk(engine, table, rows)
            return
        except OperationalError as exc:
            if attempt == RETRIES:
                raise
            print(f"  {table.name}: connection dropped ({exc.orig}); retry {attempt}")
            engine.dispose()
            time.sleep(RETRY_WAIT_S * attempt)


def _keys(engine: Engine, table: Table) -> set[tuple[Any, ...]]:
    cols = list(table.primary_key.columns)
    with engine.connect() as c:
        return {tuple(r) for r in c.execute(select(*cols))}


def copy_tables(
    src_url: str,
    dst_url: str,
    chunk: int = 5000,
    *,
    resume: bool = False,
    only: Collection[str] | None = None,
) -> dict[str, int]:
    """Replace ``dst_url``'s tables with ``src_url``'s schema and rows; returns the counts.
    The target's tables are dropped first, so a schema change (a wider column) applies.
    Each chunk commits on its own and is retried after a dropped connection. ``resume``
    keeps the target and copies only the rows it lacks, to finish a copy that stopped.
    ``only`` drops, rebuilds, and copies just those tables (a column type change)."""
    src = Repo(src_url)
    if only is not None:
        target = make_engine(dst_url)
        md.drop_all(target, tables=[t for t in md.sorted_tables if t.name in only])
        target.dispose()
    elif not resume:
        target = make_engine(dst_url)
        md.drop_all(target)
        target.dispose()
    dst = Repo(dst_url)  # creates the current schema (missing tables only, on a resume)
    counts: dict[str, int] = {}
    for table in md.sorted_tables:
        if only is not None and table.name not in only:
            continue
        with src.engine.connect() as inp:
            rows = [dict(r) for r in inp.execute(select(table)).mappings()]
        counts[table.name] = len(rows)
        if resume:
            have = _keys(dst.engine, table)
            if len(have) == len(rows):
                print(f"  {table.name}: {len(rows)} rows already there")
                continue
            pk = [c.name for c in table.primary_key.columns]
            rows = [r for r in rows if tuple(r[k] for k in pk) not in have]
        for i in range(0, len(rows), chunk):
            _insert_with_retry(dst.engine, table, rows[i : i + chunk])
        print(f"  {table.name}: {len(rows)} rows copied")
    return counts


def upload_tracking(local_dir: Path, target: Backend) -> list[str]:
    """Upload every ``<match>/frames.parquet`` under ``local_dir``; returns the blob names."""
    names = []
    for path in sorted(Path(local_dir).glob("*/frames.parquet")):
        name = f"{path.parent.name}/{path.name}"
        target.put(name, path.read_bytes())
        names.append(name)
    return names


def grant_sql(app_name: str) -> list[str]:
    """T-SQL that lets the container app's managed identity read and write the database."""
    return [
        f"IF USER_ID('{app_name}') IS NULL CREATE USER [{app_name}] FROM EXTERNAL PROVIDER",
        f"ALTER ROLE db_datareader ADD MEMBER [{app_name}]",
        f"ALTER ROLE db_datawriter ADD MEMBER [{app_name}]",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sql-url", required=True)
    parser.add_argument("--blob-url", required=True)
    parser.add_argument("--app-name", required=True, help="the app's managed identity name")
    parser.add_argument(
        "--resume", action="store_true", help="finish a stopped copy: add only missing rows"
    )
    parser.add_argument("--tables", help="rebuild and copy only these tables (comma-separated)")
    args = parser.parse_args()
    settings = get_settings()

    from azure.identity import DefaultAzureCredential  # noqa: PLC0415
    from azure.storage.blob import BlobServiceClient  # noqa: PLC0415

    from matchmind.store.blob import AzureBackend  # noqa: PLC0415

    only = set(args.tables.split(",")) if args.tables else None
    counts = copy_tables(settings.db_url, args.sql_url, resume=args.resume, only=only)
    print("rows copied:", counts)
    with Repo(args.sql_url).engine.begin() as c:
        for statement in grant_sql(args.app_name):
            c.execute(text(statement))
    print("granted", args.app_name)
    service = BlobServiceClient(args.blob_url, credential=DefaultAzureCredential())
    container = service.get_container_client(CONTAINER)
    if not container.exists():
        container.create_container()
    names = upload_tracking(settings.data_dir / "tracking", AzureBackend(container))
    print("uploaded", len(names), "tracking files")


if __name__ == "__main__":
    main()
