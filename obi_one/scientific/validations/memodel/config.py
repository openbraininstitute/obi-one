"""Shared simulator configuration for MEModel validation workflows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from math import isfinite
from pathlib import Path

_HOC_NUMERIC_LITERAL = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_HOC_PARAMETER_PATTERNS = {
    "celsius": re.compile(
        rf'check_parameter\(\s*"celsius"\s*,\s*({_HOC_NUMERIC_LITERAL})\s*,\s*celsius\s*\)'
    ),
    "v_init": re.compile(
        rf'check_parameter\(\s*"v_init"\s*,\s*({_HOC_NUMERIC_LITERAL})\s*,\s*v_init\s*\)'
    ),
}


@dataclass(frozen=True, slots=True)
class SimulatorConfig:
    """Global NEURON conditions used by a validation run.

    ``v_init`` is in mV and ``celsius`` is in degrees Celsius. NEURON stores
    both values as process-global state, so a validation workflow must apply a
    single configuration before constructing or running its tests.
    """

    celsius: float
    v_init: float

    def __post_init__(self) -> None:
        """Reject non-finite simulator conditions."""
        if not isfinite(self.celsius) or not isfinite(self.v_init):
            message = "Simulator configuration values must be finite."
            raise ValueError(message)


DEFAULT_SIMULATOR_CONFIG = SimulatorConfig(celsius=34.0, v_init=-80.0)
# Used only when a model HOC has no simulator declarations.
THALAMIC_SIMULATOR_CONFIG = SimulatorConfig(celsius=25.0, v_init=-70.0)


def _extract_hoc_parameter(source: str, parameter: str) -> float | None:
    """Extract one simulator parameter and reject conflicting declarations."""
    matches = _HOC_PARAMETER_PATTERNS[parameter].findall(source)
    if not matches:
        return None

    values = {float(value) for value in matches}
    if len(values) > 1:
        message = f"HOC declares conflicting {parameter} values: {sorted(values)}."
        raise ValueError(message)
    return values.pop()


def extract_simulator_config_from_hoc(hoc_path: str | Path) -> SimulatorConfig | None:
    """Extract the complete simulator contract declared by a model HOC.

    The generated HOCs declare expected values through
    ``check_parameter("celsius", ..., celsius)`` and
    ``check_parameter("v_init", ..., v_init)``. A HOC with no declarations
    returns ``None`` so the caller can apply an explicit profile fallback.
    Partial declarations and conflicting repeated declarations are rejected.
    """
    path = Path(hoc_path)
    source = path.read_text(encoding="utf-8")
    values = {
        parameter: _extract_hoc_parameter(source, parameter) for parameter in ("celsius", "v_init")
    }
    declared = {parameter for parameter, value in values.items() if value is not None}
    if not declared:
        return None
    if declared != set(values):
        missing = sorted(set(values) - declared)
        message = f"HOC file {path} has partial simulator declarations; missing {missing}."
        raise ValueError(message)

    celsius = values["celsius"]
    v_init = values["v_init"]
    if celsius is None or v_init is None:  # pragma: no cover - guarded above
        raise AssertionError
    return SimulatorConfig(celsius=celsius, v_init=v_init)


def load_simulator_config_from_hoc(
    hoc_path: str | Path,
    *,
    fallback: SimulatorConfig | None = None,
) -> SimulatorConfig:
    """Load a HOC simulator contract, using an explicit fallback if absent."""
    config = extract_simulator_config_from_hoc(hoc_path)
    if config is not None:
        return config
    if fallback is None:
        message = f"HOC file {hoc_path} has no simulator declarations and no fallback was provided."
        raise ValueError(message)
    return fallback
