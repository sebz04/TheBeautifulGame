"""Match files: `meta.json`, `events.parquet`, and `frames.parquet` in one directory.

Frames are stored long (one row per player per frame, ball columns repeated), which is
the shape the stats engine reads. Same data in, byte-identical files out.
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from matchmind.schemas import Event, MatchData, MatchMeta, PlayerPos, TrackingFrame

_EVENT_SCHEMA = pa.schema(
    [
        ("event_id", pa.string()),
        ("match_id", pa.string()),
        ("period", pa.int8()),
        ("t", pa.float64()),
        ("type", pa.string()),
        ("team_id", pa.string()),
        ("player_id", pa.string()),
        ("x", pa.float64()),
        ("y", pa.float64()),
        ("end_x", pa.float64()),
        ("end_y", pa.float64()),
        ("outcome", pa.bool_()),
        ("receiver_id", pa.string()),
        ("ball_speed_ms", pa.float64()),
        ("extras", pa.string()),  # JSON
    ]
)

_FRAME_SCHEMA = pa.schema(
    [
        ("frame", pa.int32()),
        ("period", pa.int8()),
        ("t", pa.float64()),
        ("ball_x", pa.float64()),
        ("ball_y", pa.float64()),
        ("ball_z", pa.float64()),
        ("player_id", pa.string()),
        ("team_id", pa.string()),
        ("x", pa.float64()),
        ("y", pa.float64()),
        ("vx", pa.float64()),
        ("vy", pa.float64()),
    ]
)


def _write_table(table: pa.Table, path: Path) -> None:
    pq.write_table(table, path, compression="zstd", store_schema=False)


def write_match(data: MatchData, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "meta.json").write_text(
        json.dumps(data.meta.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )

    rows: dict[str, list[Any]] = {name: [] for name in _EVENT_SCHEMA.names}
    for ev in data.events:
        dumped = ev.model_dump()
        dumped["extras"] = json.dumps(ev.extras, sort_keys=True)
        for name in rows:
            rows[name].append(dumped[name])
    _write_table(pa.table(rows, schema=_EVENT_SCHEMA), out_dir / "events.parquet")

    cols: dict[str, list[Any]] = {name: [] for name in _FRAME_SCHEMA.names}
    for fr in data.frames:
        for p in fr.players:
            cols["frame"].append(fr.frame)
            cols["period"].append(fr.period)
            cols["t"].append(fr.t)
            cols["ball_x"].append(fr.ball[0])
            cols["ball_y"].append(fr.ball[1])
            cols["ball_z"].append(fr.ball[2])
            cols["player_id"].append(p.player_id)
            cols["team_id"].append(p.team_id)
            cols["x"].append(p.x)
            cols["y"].append(p.y)
            cols["vx"].append(p.vx)
            cols["vy"].append(p.vy)
    _write_table(pa.table(cols, schema=_FRAME_SCHEMA), out_dir / "frames.parquet")


def read_match(out_dir: Path) -> MatchData:
    meta = MatchMeta.model_validate_json((out_dir / "meta.json").read_text())

    events = []
    for row in pq.read_table(out_dir / "events.parquet").to_pylist():
        row["extras"] = json.loads(row["extras"])
        events.append(Event.model_validate(row))

    table = pq.read_table(out_dir / "frames.parquet")
    c = {name: table.column(name).to_pylist() for name in _FRAME_SCHEMA.names}
    frame_ids = np.asarray(c["frame"])
    # Rows are written grouped by frame; split at each change of frame number.
    starts = [0, *(np.flatnonzero(np.diff(frame_ids)) + 1).tolist(), len(frame_ids)]
    frames = []
    for a, b in zip(starts, starts[1:], strict=False):
        if a == b:
            continue
        players = [
            PlayerPos.model_construct(
                player_id=c["player_id"][i],
                team_id=c["team_id"][i],
                x=c["x"][i],
                y=c["y"][i],
                vx=c["vx"][i],
                vy=c["vy"][i],
            )
            for i in range(a, b)
        ]
        frames.append(
            TrackingFrame.model_construct(
                match_id=meta.match_id,
                frame=c["frame"][a],
                period=c["period"][a],
                t=c["t"][a],
                ball=(c["ball_x"][a], c["ball_y"][a], c["ball_z"][a]),
                players=players,
            )
        )
    return MatchData(meta=meta, events=events, frames=frames)
