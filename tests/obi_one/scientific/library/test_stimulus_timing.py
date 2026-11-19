"""Tests for the per-sweep stimulus timing detection."""

import numpy as np
import pytest

from obi_one.scientific.library.electrical_cell_recording_properties import (
    detect_stimulus_timing,
    distinct_times,
    estimate_matchable_amplitude,
)

_RNG_SEED = 0


def _trace(levels: list[tuple[float, float]], *, duration_ms: float, dt_ms: float, noise=0.0):
    """Piecewise-constant current (nA): ``levels`` are ``(start_ms, level)``, from rest 0."""
    t = np.arange(0.0, duration_ms, dt_ms)
    current = np.zeros_like(t)
    for start, level in levels:
        current[t >= start] = level
    if noise:
        current += np.random.default_rng(_RNG_SEED).normal(0.0, noise, len(t))
    return current


class TestDetectStimulusTiming:
    def test_step(self):
        current = _trace([(200.0, 0.3), (800.0, 0.0)], duration_ms=1000.0, dt_ms=0.1)
        assert detect_stimulus_timing(current, 0.1, "Step") == pytest.approx(
            {"ton": 200.0, "toff": 800.0}
        )

    def test_short_rest_with_noise_and_holding_current(self):
        """The BBP IV case: 20 ms rest at 0.25 ms sampling, holding current, noise.

        bluepyefe's 50-sample noise window and 300-sample rest window both run into the
        step here; the detection does not.
        """
        current = -0.05 + _trace(
            [(20.0, -0.066), (1020.0, 0.0)], duration_ms=1220.0, dt_ms=0.25, noise=0.003
        )
        timing = detect_stimulus_timing(current, 0.25, "Step")
        assert timing == pytest.approx({"ton": 20.0, "toff": 1020.0}, abs=0.5)

    def test_sahp_with_short_rest(self):
        """The BBP sAHP case: 20 ms rest at 0.5 ms sampling."""
        current = _trace(
            [(20.0, 0.05), (520.0, 0.1), (720.0, 0.05), (2720.0, 0.0)],
            duration_ms=2740.0,
            dt_ms=0.5,
            noise=0.003,
        )
        timing = detect_stimulus_timing(current, 0.5, "SAHP")
        assert timing == pytest.approx(
            {"ton": 20.0, "tmid": 520.0, "tmid2": 720.0, "toff": 2720.0}, abs=1.0
        )
        assert estimate_matchable_amplitude(current, "SAHP", 0.5) == pytest.approx(
            (0.1, 0.05), abs=0.003
        )

    def test_hyperdepol(self):
        current = _trace([(100.0, -0.2), (400.0, 0.3), (600.0, 0.0)], duration_ms=800.0, dt_ms=0.1)
        assert detect_stimulus_timing(current, 0.1, "HyperDePol") == pytest.approx(
            {"ton": 100.0, "tmid": 400.0, "toff": 600.0}
        )

    def test_ramp_onset_is_extrapolated(self):
        t = np.arange(0.0, 1040.0, 0.1)
        current = np.where((t >= 20.0) & (t < 1020.0), 0.0003 * (t - 20.0), 0.0)
        timing = detect_stimulus_timing(current, 0.1, "Ramp")
        assert timing == pytest.approx({"ton": 20.0}, abs=1.0)

    @pytest.mark.parametrize(
        ("levels", "shape"),
        [
            ([], "Step"),  # 0 nA sweep: no step
            ([(100.0, 0.2), (300.0, 0.0), (500.0, 0.2), (700.0, 0.0)], "Step"),  # two pulses
            ([(100.0, 0.2), (800.0, 0.0)], "SAHP"),  # one step where three are expected
        ],
    )
    def test_unexpected_shapes_give_no_timing(self, levels, shape):
        current = _trace(levels, duration_ms=1000.0, dt_ms=0.1)
        assert detect_stimulus_timing(current, 0.1, shape) is None

    @pytest.mark.parametrize("shape", ["PinkNoise", "SpikeRec", None])
    def test_other_ecodes_are_left_to_bluepyefe(self, shape):
        current = _trace([(200.0, 0.3), (800.0, 0.0)], duration_ms=1000.0, dt_ms=0.1)
        assert detect_stimulus_timing(current, 0.1, shape) is None


def test_distinct_times_merge_sample_jitter():
    values = [20.25, 20.5, 20.25, 700.25, 700.5, 700.25]
    assert distinct_times(values) == [20.25, 700.25]
    assert distinct_times([]) == []


@pytest.mark.parametrize(
    "current",
    [
        np.zeros(10),  # too short
        np.zeros(10000),  # no rise
        np.concatenate((np.zeros(5000), np.full(5000, 0.3))),  # a step, not a ramp
    ],
)
def test_ramp_without_a_rise_has_no_onset(current):
    assert detect_stimulus_timing(current, 0.1, "Ramp") is None
