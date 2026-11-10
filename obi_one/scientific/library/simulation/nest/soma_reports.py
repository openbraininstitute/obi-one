"""SONATA soma reports of the membrane potential recorded by NEST multimeters.

A report has frames at the steps ``first + k * every``, ``k = 0, 1, ...``, up to its end. The
multimeter of a population samples ``V_m`` at those steps, except at step 0, which it cannot
record: that frame is the potential at the start of the simulation.
"""

from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np

UNIT_MV = "mV"


@dataclass(frozen=True)
class Frames:
    """The frames of a report, in units of the simulation step ``dt``."""

    first: int
    every: int
    count: int
    dt: float

    @classmethod
    def of(cls, name: str, start: float, end: float, dt: float, run_dt: float) -> "Frames":
        """The frames of the report *name*, with *start*, *end* and *dt* in ms."""
        every = round(max(dt, run_dt) / run_dt)
        if not np.isclose(every * run_dt, max(dt, run_dt)):
            msg = f"Report '{name}': dt {dt} ms is not a multiple of run.dt {run_dt} ms."
            raise ValueError(msg)
        first = round(start / run_dt)
        last = round(end / run_dt)
        return cls(first, every, max(0, -(-(last - first) // every)), run_dt)

    @property
    def step_ms(self) -> float:
        return self.every * self.dt

    @property
    def start_ms(self) -> float:
        return self.first * self.dt

    @property
    def end_ms(self) -> float:
        return (self.first + self.count * self.every) * self.dt

    @property
    def has_initial_frame(self) -> bool:
        """Whether the first frame is the state before the first step, which NEST cannot record."""
        return self.first == 0 and self.count > 0

    @property
    def sampled(self) -> int:
        """The number of frames that the multimeter records."""
        return self.count - int(self.has_initial_frame)

    def multimeter(self) -> dict:
        """The multimeter parameters that sample the frames after the initial one.

        The multimeter records at ``offset + m * interval`` in ``(start, stop]``.
        """
        first = self.first + (self.every if self.has_initial_frame else 0)
        return {
            "interval": round(self.step_ms, 6),
            "offset": round((first % self.every) * self.dt, 6),
            "start": round((first - 1) * self.dt, 6),
            "stop": round((self.first + (self.count - 1) * self.every) * self.dt, 6),
        }


def frames_matrix(
    events: dict, node_ids: np.ndarray, initial: np.ndarray | None, frames: Frames
) -> np.ndarray:
    """The ``(nodes, frames)`` potentials in mV from multimeter *events* and the *initial* frame.

    *node_ids* are the NEST ids of the recorded nodes, which are the rows. *initial* holds their
    potentials at the start, and is the first frame if the report has one.
    """
    nodes = len(node_ids)
    sampled = np.empty((nodes, 0))
    if frames.sampled:
        senders = np.asarray(events["senders"], dtype=np.int64)
        times = np.round(np.asarray(events["times"], dtype=np.float64), 6)
        values = np.asarray(events["V_m"], dtype=np.float64)
        order = np.lexsort((senders, times))
        senders, values = senders[order], values[order]
        if len(values) != frames.sampled * nodes:
            msg = f"The multimeter recorded {len(values)} samples, not {frames.sampled} of {nodes}."
            raise ValueError(msg)
        if not np.array_equal(senders[:nodes], np.sort(node_ids)):
            msg = "The multimeter did not record every node of the report."
            raise ValueError(msg)
        sampled = values.reshape(frames.sampled, nodes).T[np.argsort(np.argsort(node_ids))]
    if frames.has_initial_frame:
        return np.column_stack([initial, sampled])
    return sampled


def write_soma_report(
    path: Path, populations: dict[str, tuple[np.ndarray, np.ndarray]], frames: Frames
) -> None:
    """Write *populations* ``{name: (SONATA node ids, (nodes, frames) potentials in mV)}``.

    The file has one group per population, as libsonata's ``SomaReportReader`` reads it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = h5py.string_dtype()
    with h5py.File(path, "w") as handle:
        for name, (node_ids, values) in populations.items():
            if values.shape[1] != frames.count:
                msg = (
                    f"Report population '{name}' has {values.shape[1]} frames, not {frames.count}."
                )
                raise ValueError(msg)
            group = handle.create_group(f"report/{name}")
            data = group.create_dataset("data", data=values.T.astype(np.float32))
            data.attrs.create("units", UNIT_MV, dtype=text)
            mapping = group.create_group("mapping")
            mapping.create_dataset("node_ids", data=node_ids, dtype=np.uint64)
            mapping.create_dataset(
                "index_pointers", data=np.arange(len(node_ids) + 1), dtype=np.uint64
            )
            mapping.create_dataset("element_ids", data=np.zeros(len(node_ids)), dtype=np.uint32)
            time = mapping.create_dataset(
                "time", data=(frames.start_ms, frames.end_ms, frames.step_ms), dtype=np.float64
            )
            time.attrs.create("units", "ms", dtype=text)
