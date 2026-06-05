# ruff: noqa: INP001
"""Isolated subprocess helper that runs one reference `model.run_trial`.

Invoked by `brian2_simulation_from_sonata.ipynb` so each reference trial runs in
a fresh Python interpreter — Brian2's global state (magic network, device,
compiled cython modules, RNG bookkeeping) cannot be fully cleared in-process,
and trials that share a process drift from the bitwise-identical result a
fresh process produces.

Usage::

    python _reference_trial.py <drosophila_repo> <sim_len_ms> <dt_ms>
                               <rate_hz> <seed> <sugar_indices_json>
                               <out_pickle>
"""
from __future__ import annotations

import json
import pickle  # noqa: S403
import sys
from pathlib import Path

import brian2
import numpy as np
from brian2 import Hz, ms


def main() -> None:
    repo = Path(sys.argv[1])
    sim_len_ms = float(sys.argv[2])
    dt_ms = float(sys.argv[3])
    rate_hz = float(sys.argv[4])
    seed = int(sys.argv[5])
    sugar = json.loads(sys.argv[6])
    out_path = Path(sys.argv[7])

    sys.path.insert(0, str(repo))
    from model import default_params, run_trial  # noqa: PLC0415

    params = dict(default_params)
    params["t_run"] = sim_len_ms * ms
    params["r_poi"] = rate_hz * Hz

    brian2.start_scope()
    brian2.defaultclock.dt = dt_ms * ms
    brian2.seed(seed)

    trains = run_trial(
        exc=sugar,
        exc2=[],
        slnc=[],
        path_comp=repo / "2023_03_23_completeness_630_final.csv",
        path_con=repo / "2023_03_23_connectivity_630_final.parquet",
        params=params,
    )
    ids: list[int] = []
    times: list[float] = []
    for idx, ts in trains.items():
        arr = np.asarray(ts / brian2.second)
        ids.extend([int(idx)] * len(arr))
        times.extend(arr.tolist())

    with out_path.open("wb") as f:
        pickle.dump(
            {
                "node_ids": np.asarray(ids, dtype=np.int64),
                "times_s": np.asarray(times, dtype=np.float64),
            },
            f,
        )


if __name__ == "__main__":
    main()
