"""Load the precomputed matches into Azure: the database into Azure SQL, the tracking files
into Blob Storage, and read access for the API's managed identity. Keyless throughout: it
signs in as you (`az login`), so run it as the SQL server's Entra admin (azd sets you).

Usage (values from `azd env get-values`):
    uv run --extra azure python scripts/seed_cloud.py \\
        --sql-url "$(azd env get-value MATCHMIND_SQL_URL)" \\
        --blob-url "$(azd env get-value MATCHMIND_BLOB_ACCOUNT_URL)" \\
        --app-name "$(azd env get-value AZURE_IDENTITY_NAME)"
"""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import insert, select, text

from matchmind.config import get_settings
from matchmind.store.blob import CONTAINER, Backend
from matchmind.store.db import Repo, make_engine, md


def copy_tables(src_url: str, dst_url: str, chunk: int = 5000) -> dict[str, int]:
    """Replace ``dst_url``'s tables with ``src_url``'s schema and rows; returns the counts.
    The target's tables are dropped first, so a schema change (a wider column) applies."""
    src = Repo(src_url)
    target = make_engine(dst_url)
    md.drop_all(target)
    target.dispose()
    dst = Repo(dst_url)  # creates the current schema
    counts: dict[str, int] = {}
    for table in md.sorted_tables:
        with src.engine.connect() as inp, dst.engine.begin() as out:
            rows = [dict(r) for r in inp.execute(select(table)).mappings()]
            for i in range(0, len(rows), chunk):
                out.execute(insert(table), rows[i : i + chunk])
        counts[table.name] = len(rows)
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
    args = parser.parse_args()
    settings = get_settings()

    from azure.identity import DefaultAzureCredential  # noqa: PLC0415
    from azure.storage.blob import BlobServiceClient  # noqa: PLC0415

    from matchmind.store.blob import AzureBackend  # noqa: PLC0415

    counts = copy_tables(settings.db_url, args.sql_url)
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
