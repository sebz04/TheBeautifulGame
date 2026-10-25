"""The tracking store: each match's frames as one Parquet file, read back by time window.

The file is the long format of `engine.match_io` (one row per player per frame, zstd),
written in one-minute row groups, so a window read only decodes the row groups it
touches. It lives on the local disk (`<data_dir>/tracking/<match_id>/frames.parquet`) or
in an Azure Blob container (`<match_id>/frames.parquet`) when `Settings.blob_account_url`
is set; Azure uses managed identity (`DefaultAzureCredential`), never keys.
"""

import gc
import io
from pathlib import Path
from typing import Any, Protocol

import pyarrow as pa
import pyarrow.parquet as pq

from matchmind.config import Settings
from matchmind.engine.match_io import frames_from_table, frames_table
from matchmind.schemas import TrackingFrame

ROWS_PER_GROUP = 22 * 600  # about one minute of 10 Hz frames
CONTAINER = "tracking"


class Backend(Protocol):
    def put(self, name: str, data: bytes) -> None: ...
    def get(self, name: str) -> bytes: ...
    def has(self, name: str) -> bool: ...


class LocalBackend:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def put(self, name: str, data: bytes) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)  # atomic: readers never see half a file

    def get(self, name: str) -> bytes:
        path = self.root / name
        if not path.exists():
            raise LookupError(name)
        return path.read_bytes()

    def has(self, name: str) -> bool:
        return (self.root / name).exists()


class AzureBackend:
    """Wraps an `azure.storage.blob.ContainerClient` (or anything with its methods)."""

    def __init__(self, container: Any) -> None:
        self.container = container

    def put(self, name: str, data: bytes) -> None:
        self.container.upload_blob(name, data, overwrite=True)

    def get(self, name: str) -> bytes:
        try:
            return bytes(self.container.download_blob(name).readall())
        except Exception as exc:  # the SDK raises ResourceNotFoundError
            raise LookupError(name) from exc

    def has(self, name: str) -> bool:
        return bool(self.container.get_blob_client(name).exists())


class TrackingStore:
    def __init__(self, backend: Backend) -> None:
        self.backend = backend

    @staticmethod
    def _name(match_id: str) -> str:
        return f"{match_id}/frames.parquet"

    def write(self, match_id: str, frames: list[TrackingFrame]) -> None:
        """Replaces the match's frames."""
        buf = io.BytesIO()
        pq.write_table(frames_table(frames), buf, compression="zstd", store_schema=False,
                       row_group_size=ROWS_PER_GROUP)  # fmt: skip
        self.backend.put(self._name(match_id), buf.getvalue())

    def exists(self, match_id: str) -> bool:
        return self.backend.has(self._name(match_id))

    def _read(
        self, match_id: str, filters: list[tuple[str, str, Any]] | None
    ) -> list[TrackingFrame]:
        data = self.backend.get(self._name(match_id))
        table: pa.Table = pq.read_table(io.BytesIO(data), filters=filters)
        enabled = gc.isenabled()
        gc.disable()  # many small acyclic objects; see engine/baseline.flush_frames
        try:
            return frames_from_table(table, match_id)
        finally:
            if enabled:
                gc.enable()

    def read_window(
        self, match_id: str, period: int, t_from: float, t_to: float
    ) -> list[TrackingFrame]:
        """Frames of `period` with t_from <= t <= t_to, in order (empty if t_from > t_to)."""
        if t_from > t_to:
            if not self.exists(match_id):
                raise LookupError(match_id)
            return []
        return self._read(match_id, [("period", "=", period), ("t", ">=", t_from),
                                     ("t", "<=", t_to)])  # fmt: skip

    def read_all(self, match_id: str) -> list[TrackingFrame]:
        return self._read(match_id, None)


def tracking_store(settings: Settings) -> TrackingStore:
    """Local disk, or Azure Blob when `blob_account_url` is set (needs the `azure` extra)."""
    if settings.blob_account_url is None:
        return TrackingStore(LocalBackend(settings.data_dir / "tracking"))
    from azure.identity import DefaultAzureCredential  # noqa: PLC0415
    from azure.storage.blob import BlobServiceClient  # noqa: PLC0415

    service = BlobServiceClient(settings.blob_account_url, credential=DefaultAzureCredential())
    return TrackingStore(AzureBackend(service.get_container_client(CONTAINER)))
