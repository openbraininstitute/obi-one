"""Synthetic spiking NWB recordings for tests that run bluepyefe for real.

Writes the non-BBP ("Scala") layout bluepyefe's ``ScalaNWBReader`` reads: one
``acquisition`` voltage series and one ``stimulus/presentation`` current series per
sweep, sharing the sweep name, with the protocol in the voltage series'
``stimulus_description``. The cell is passive (100 MOhm) below ``rheobase_na`` and
fires regularly, faster with more current, at or above it.
"""

from pathlib import Path

import h5py
import numpy as np

RATE_HZ = 20000.0
DURATION_MS = 1000.0
TON_MS = 200.0
TOFF_MS = 800.0
RESTING_MV = -70.0
INPUT_RESISTANCE_MOHM = 100.0


def _spike(n_rise: int = 10, n_fall: int = 30) -> np.ndarray:
    """A 2 ms triangular action potential from rest to +30 mV and back below rest."""
    return np.concatenate((np.linspace(-40.0, 30.0, n_rise), np.linspace(30.0, -65.0, n_fall)))


def sweep_traces(amplitude_na: float, rheobase_na: float) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(current_pA, voltage_mV)`` of one step sweep."""
    n = int(DURATION_MS * RATE_HZ / 1000.0)
    ton, toff = (int(t * RATE_HZ / 1000.0) for t in (TON_MS, TOFF_MS))
    current = np.zeros(n)
    current[ton:toff] = amplitude_na * 1000.0
    voltage = np.full(n, RESTING_MV)
    voltage[ton:toff] += INPUT_RESISTANCE_MOHM * amplitude_na
    if amplitude_na >= rheobase_na:
        n_spikes = 1 + round(4.0 * (amplitude_na - rheobase_na) / rheobase_na)
        spike = _spike()
        margin = (toff - ton) // 10
        for start in np.linspace(ton + margin, toff - margin - len(spike), n_spikes).astype(int):
            voltage[start : start + len(spike)] = spike
    return current, voltage


def _write_series(group: h5py.Group, name: str, data: np.ndarray, conversion: float, unit: str):
    series = group.create_group(name)
    dataset = series.create_dataset("data", data=data)
    dataset.attrs["conversion"] = conversion
    dataset.attrs["unit"] = unit
    starting_time = series.create_dataset("starting_time", data=np.float64(0.0))
    starting_time.attrs["rate"] = RATE_HZ
    starting_time.attrs["unit"] = "seconds"
    return series


def write_spiking_nwb(
    path: Path,
    sweeps: dict[str, list[float]],
    *,
    rheobase_na: float,
) -> Path:
    """Write one sweep per ``(protocol, amplitude_nA)`` in ``sweeps`` to ``path``."""
    with h5py.File(path, "w") as f:
        acquisition = f.create_group("acquisition")
        presentation = f.create_group("stimulus").create_group("presentation")
        index = 0
        for protocol, amplitudes in sweeps.items():
            for amplitude in amplitudes:
                current, voltage = sweep_traces(amplitude, rheobase_na)
                name = f"{protocol}__{index}"
                _write_series(presentation, name, current, 1e-12, "amperes")
                series = _write_series(acquisition, name, voltage, 1e-3, "volts")
                series.attrs["stimulus_description"] = protocol
                index += 1
    return path
