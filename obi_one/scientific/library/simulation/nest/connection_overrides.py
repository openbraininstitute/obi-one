"""The ``connection_overrides`` of a NEST simulation: parsing, validation and the timed schedule."""

import logging
from dataclasses import dataclass

import numpy as np

L = logging.getLogger(__name__)

NEURON_ONLY = (
    "spont_minis",
    "synapse_configure",
    "modoverride",
    "neuromodulation_dtc",
    "neuromodulation_strength",
)


@dataclass(frozen=True)
class Override:
    """A connection override, with its ``delay`` as a step of the simulation."""

    index: int
    name: str
    source: str
    target: str
    step: int
    weight: float | None
    synapse_delay: float | None


def parse_overrides(raw: list[dict], dt: float) -> list[Override]:
    """The overrides in *raw*, the ``connection_overrides`` of the config; *dt* is ``run.dt``."""
    overrides = []
    for index, entry in enumerate(raw):
        name = entry.get("name", f"#{index}")
        unsupported = sorted(key for key in NEURON_ONLY if key in entry)
        if unsupported:
            msg = f"connection_overrides '{name}': {unsupported} are not supported for NEST."
            raise ValueError(msg)
        missing = sorted({"source", "target"} - set(entry))
        if missing:
            msg = f"connection_overrides '{name}': {missing} are missing."
            raise ValueError(msg)
        delay = float(entry.get("delay", 0.0))
        step = round(delay / dt)
        if not np.isclose(step * dt, delay, rtol=0.0, atol=1e-9):
            msg = f"connection_overrides '{name}': delay {delay} ms is not a multiple of {dt} ms."
            raise ValueError(msg)
        synapse_delay = entry.get("synapse_delay_override")
        weight = entry.get("weight")
        if weight is None and synapse_delay is None:
            L.warning(
                "connection_overrides '%s' sets neither weight nor synapse_delay_override.", name
            )
        overrides.append(
            Override(
                index=index,
                name=name,
                source=entry["source"],
                target=entry["target"],
                step=step,
                weight=None if weight is None else float(weight),
                synapse_delay=None if synapse_delay is None else max(float(synapse_delay), dt),
            )
        )
    return overrides


def schedule(overrides: list[Override], last_step: int) -> list[tuple[int, list[Override]]]:
    """The overrides grouped by the step they take effect, in time order, then in file order.

    An override that takes effect at or after *last_step* is dropped with a warning.
    """
    groups: dict[int, list[Override]] = {}
    for override in overrides:
        if override.step >= last_step:
            L.warning(
                "connection_overrides '%s' takes effect after the simulation ends.", override.name
            )
            continue
        groups.setdefault(override.step, []).append(override)
    return sorted(groups.items())
