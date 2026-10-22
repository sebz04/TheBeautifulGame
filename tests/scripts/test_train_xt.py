import json
from pathlib import Path

import numpy as np
from train_xt import write_grid


def test_write_grid_saves_grid_and_provenance(tmp_path: Path) -> None:
    grid = np.full((12, 16), 0.1)
    out = tmp_path / "models" / "xt_grid.npy"
    write_grid(grid, out, {"level": 1, "seeds": 3, "events": 99, "engine_version": "l1-0.1"})
    assert np.array_equal(np.load(out), grid)
    meta = json.loads(out.with_suffix(".json").read_text())
    assert meta == {"level": 1, "seeds": 3, "events": 99, "engine_version": "l1-0.1",
                    "shape": [12, 16]}  # fmt: skip
