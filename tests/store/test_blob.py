from pathlib import Path

import pytest

from matchmind.config import Settings
from matchmind.schemas import PlayerPos, TrackingFrame
from matchmind.store.blob import AzureBackend, LocalBackend, TrackingStore, tracking_store


def _frames(match_id: str = "m1") -> list[TrackingFrame]:
    out = []
    for period in (1, 2):
        for k in range(1000):  # 100 s per period
            n = 22 if k < 500 else 21  # a red card halfway: rows per frame vary
            players = [PlayerPos(player_id=f"p{i}", team_id="h" if i < 11 else "a",
                                 x=float(i + k * 0.01), y=30.0, vx=0.1, vy=0.0)
                       for i in range(n)]  # fmt: skip
            out.append(TrackingFrame(match_id=match_id, frame=len(out), period=period,
                                     t=round(k * 0.1, 1), ball=(50.0, 34.0, 0.11),
                                     players=players))  # fmt: skip
    return out


def _expected(frames: list[TrackingFrame], period: int, a: float, b: float) -> list[TrackingFrame]:
    return [f for f in frames if f.period == period and a <= f.t <= b]


def test_read_window_returns_exactly_the_requested_frames(tmp_path: Path) -> None:
    store, frames = TrackingStore(LocalBackend(tmp_path)), _frames()
    store.write("m1", frames)
    for period, a, b in ((1, 10.0, 20.0), (2, 49.5, 50.5), (1, 0.0, 0.0), (2, 95.0, 1e9)):
        assert store.read_window("m1", period, a, b) == _expected(frames, period, a, b)
    assert store.read_window("m1", 1, 30.0, 20.0) == []  # empty window
    assert store.read_all("m1") == frames


def test_frame_times_reads_only_the_clock(tmp_path: Path) -> None:
    store, frames = TrackingStore(LocalBackend(tmp_path)), _frames()
    store.write("m1", frames)
    assert store.frame_times("m1") == [(f.frame, f.period, f.t) for f in frames]


def test_rewrite_replaces(tmp_path: Path) -> None:
    store = TrackingStore(LocalBackend(tmp_path))
    store.write("m1", _frames())
    shorter = [f for f in _frames() if f.period == 1]
    store.write("m1", shorter)
    assert store.read_window("m1", 2, 0.0, 1e9) == []


def test_missing_match(tmp_path: Path) -> None:
    with pytest.raises(LookupError):
        TrackingStore(LocalBackend(tmp_path)).read_window("nope", 1, 0.0, 10.0)
    assert not TrackingStore(LocalBackend(tmp_path)).exists("nope")


class _Blob:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def readall(self) -> bytes:
        return self.data


class _FakeContainer:
    """The few `ContainerClient` methods the backend uses."""

    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    def upload_blob(self, name: str, data: bytes, overwrite: bool = False) -> None:
        if name in self.blobs and not overwrite:
            raise ValueError("exists")
        self.blobs[name] = data

    def download_blob(self, name: str) -> _Blob:
        if name not in self.blobs:
            raise KeyError(name)
        return _Blob(self.blobs[name])

    def get_blob_client(self, name: str) -> "_FakeContainer":
        self._name = name
        return self

    def exists(self) -> bool:
        return self._name in self.blobs


def test_azure_backend_with_a_fake_container() -> None:
    container, frames = _FakeContainer(), _frames()
    store = TrackingStore(AzureBackend(container))
    store.write("m1", frames)
    assert list(container.blobs) == ["m1/frames.parquet"]
    assert store.read_window("m1", 2, 10.0, 12.0) == _expected(frames, 2, 10.0, 12.0)
    with pytest.raises(LookupError):
        store.read_window("nope", 1, 0.0, 1.0)


def test_store_from_settings(tmp_path: Path) -> None:
    store = tracking_store(Settings(data_dir=tmp_path, blob_account_url=None))
    assert isinstance(store.backend, LocalBackend)
    assert store.backend.root == tmp_path / "tracking"
