"""Parity of ``estimate_matchable_amplitude`` with bluepyefe's own eCode classes.

For each amplitude-matched stimulus shape, a synthetic sweep is interpreted by the
bluepyefe eCode given its true timing; the timing-free estimate must agree, so that
the amplitudes offered to the user are the ones extraction matches targets against.
"""

import numpy as np
import pytest
from bluepyefe.ecode import eCodes

from obi_one.scientific.library.electrical_cell_recording_properties import (
    estimate_matchable_amplitude,
)

DT_MS = 0.1
HOLDING_NA = -0.05


def _trace(total_ms: float, segments: list[tuple[float, float, float]]) -> np.ndarray:
    """Holding current with ``(start_ms, end_ms, level_nA)`` plateaus on top."""
    current = np.full(int(total_ms / DT_MS), HOLDING_NA)
    for start, end, level in segments:
        current[int(start / DT_MS) : int(end / DT_MS)] = HOLDING_NA + level
    return current


def _ramp(total_ms: float, start_ms: float, end_ms: float, peak_na: float) -> np.ndarray:
    current = np.full(int(total_ms / DT_MS), HOLDING_NA)
    i0, i1 = int(start_ms / DT_MS), int(end_ms / DT_MS)
    current[i0:i1] += np.linspace(0.0, peak_na, i1 - i0)
    return current


def _triangles(total_ms: float, ramps: list[tuple[float, float, float]], peak_na: float):
    """Triangles rising from ``start`` to the peak at ``apex`` and back by ``end``."""
    current = np.full(int(total_ms / DT_MS), HOLDING_NA)
    for start, apex, end in ramps:
        i0, i1, i2 = (int(t / DT_MS) for t in (start, apex, end))
        current[i0:i1] += np.linspace(0.0, peak_na, i1 - i0)
        current[i1:i2] += np.linspace(peak_na, 0.0, i2 - i1)
    return current


def _chirp(total_ms: float, start_ms: float, end_ms: float, amplitude_na: float) -> np.ndarray:
    current = np.full(int(total_ms / DT_MS), HOLDING_NA)
    i0, i1 = int(start_ms / DT_MS), int(end_ms / DT_MS)
    t_s = np.arange(i1 - i0) * DT_MS / 1000.0
    current[i0:i1] += amplitude_na * np.sin(2 * np.pi * (1.0 + 5.0 * t_s) * t_s)
    return current


def _noise(total_ms: float, start_ms: float, end_ms: float, std_na: float) -> np.ndarray:
    current = np.full(int(total_ms / DT_MS), HOLDING_NA)
    i0, i1 = int(start_ms / DT_MS), int(end_ms / DT_MS)
    current[i0:i1] += np.random.default_rng(0).normal(0.0, std_na, i1 - i0)
    return current


def _pulses(total_ms: float, start_ms: float, end_ms: float, amplitude_na: float) -> np.ndarray:
    """Alternating 5 ms square pulses of +/- ``amplitude_na``."""
    current = np.full(int(total_ms / DT_MS), HOLDING_NA)
    width = int(5.0 / DT_MS)
    for k, i in enumerate(range(int(start_ms / DT_MS), int(end_ms / DT_MS), 2 * width)):
        current[i : i + width] += amplitude_na if k % 2 == 0 else -amplitude_na
    return current


_CHEOPS_RAMPS = [(250.0, 2250.0, 4250.0), (5250.0, 6250.0, 7250.0), (8250.0, 8750.0, 9250.0)]
_CHEOPS_TIMING = {"ton": 250.0, "t1": 4250.0, "t2": 5250.0, "t3": 7250.0, "t4": 8250.0}

# (bluepyefe eCode key, obi-one ecode_class, sweep, true timing, matched attr, other attr)
CASES = {
    "step": (
        "idrest",
        "Step",
        _trace(2000.0, [(250.0, 1600.0, 0.3)]),
        {"ton": 250.0, "toff": 1600.0},
        "amp",
        None,
    ),
    "sahp": (
        "sahp",
        "SAHP",
        _trace(1425.0, [(250.0, 500.0, 0.08), (500.0, 725.0, 0.5), (725.0, 1175.0, 0.08)]),
        {"ton": 250.0, "tmid": 500.0, "tmid2": 725.0, "toff": 1175.0},
        "amp2",
        "amp",
    ),
    "hyperdepol": (
        "hyperdepol",
        "HyperDePol",
        _trace(1220.0, [(250.0, 700.0, -0.16), (700.0, 970.0, 0.3)]),
        {"ton": 250.0, "tmid": 700.0, "toff": 970.0},
        "amp",
        "amp2",
    ),
    "dehyperpol": (
        "dehyperpol",
        "DeHyperPol",
        _trace(1220.0, [(250.0, 520.0, 0.3), (520.0, 970.0, -0.16)]),
        {"ton": 250.0, "tmid": 520.0, "toff": 970.0},
        "amp",
        "amp2",
    ),
    # obi-one's Ramp protocol only exposes the onset, so bluepyefe finds the ramp's
    # end at the smoothed maximum, as the estimate does.
    "ramp": (
        "ramp",
        "Ramp",
        _ramp(2000.0, 250.0, 1600.0, 0.4),
        {"ton": 250.0},
        "amp",
        None,
    ),
    "poscheops": (
        "poscheops",
        "PosCheops",
        _triangles(10000.0, _CHEOPS_RAMPS, 0.6),
        {**_CHEOPS_TIMING, "toff": 9250.0},
        "amp",
        None,
    ),
    "negcheops": (
        "negcheops",
        "NegCheops",
        _triangles(10000.0, _CHEOPS_RAMPS, -0.3),
        {**_CHEOPS_TIMING, "toff": 9250.0},
        "amp",
        None,
    ),
    "sinespec": (
        "sinespec",
        "SineSpec",
        _chirp(5500.0, 300.0, 5300.0, 0.1),
        {"ton": 300.0, "toff": 5300.0},
        "amp",
        None,
    ),
    "pinknoise": (
        "pinknoise",
        "PinkNoise",
        _noise(2600.0, 300.0, 2300.0, 0.05),
        {"ton": 300.0, "toff": 2300.0},
        "amp",
        None,
    ),
    "capcheck": (
        "capcheck",
        "CapCheck",
        _pulses(1000.0, 300.0, 700.0, 0.1),
        {"ton": 300.0, "toff": 700.0},
        "amp",
        None,
    ),
}


def _bluepyefe_recording(ecode_key: str, current: np.ndarray, timing: dict):
    config = {"i_unit": "nA", "v_unit": "mV", "t_unit": "ms", "dt": DT_MS, **timing}
    reader = {
        "current": current,
        "voltage": np.full_like(current, -70.0),
        "dt": DT_MS,
        "i_unit": "nA",
        "v_unit": "mV",
        "t_unit": "ms",
    }
    return eCodes[ecode_key](config, reader, ecode_key, {})


@pytest.mark.parametrize("case", CASES.values(), ids=CASES.keys())
def test_estimate_matches_bluepyefe(case):
    ecode_key, ecode_class, current, timing, matched_attr, other_attr = case
    recording = _bluepyefe_recording(ecode_key, current, timing)

    matchable, secondary = estimate_matchable_amplitude(current, ecode_class)

    assert matchable == pytest.approx(getattr(recording, matched_attr), abs=1e-3)
    if other_attr is None:
        assert secondary is None
    else:
        assert secondary == pytest.approx(getattr(recording, other_attr), abs=1e-3)


def test_stimulus_starting_inside_baseline_window_keeps_holding_current():
    """A step starting within bluepyefe's 300-sample baseline window does not leak in."""
    current = _trace(500.0, [(10.0, 400.0, 0.3)])

    matchable, _ = estimate_matchable_amplitude(current, "Step")

    assert matchable == pytest.approx(0.3, abs=1e-3)


def test_spikerec_has_no_amplitude():
    assert estimate_matchable_amplitude(_trace(1000.0, [(250.0, 260.0, 1.0)]), "SpikeRec") == (
        None,
        None,
    )
