"""Tests for the ElectricalCellRecording NWB helpers."""

import h5py
import numpy as np
import pytest

from obi_one.scientific.library.electrical_cell_recording_properties import (
    estimate_step_amplitude_na,
    read_amplitudes_from_nwb,
    read_protocols_from_nwb,
)

_N_SAMPLES = 52644
_STEP_ONSET = 1842  # ~3.5% of the trace — outside the middle-40% window
_STEP_OFFSET = 13841  # ~26.3%


def _step_trace(step_pa: float) -> np.ndarray:
    """Raw stimulus data in pA; step sits early in the trace like a Scala NWB."""
    data = np.zeros(_N_SAMPLES)
    data[_STEP_ONSET:_STEP_OFFSET] = step_pa
    return data


def _mid_step_trace(step_pa: float) -> np.ndarray:
    """Step covering the middle of the trace (BBP layout assumption)."""
    data = np.zeros(_N_SAMPLES)
    data[int(_N_SAMPLES * 0.3) : int(_N_SAMPLES * 0.7)] = step_pa
    return data


def _write_series(group, name: str, data: np.ndarray, *, description: str | None = None):
    series = group.create_group(name)
    ds = series.create_dataset("data", data=data)
    ds.attrs["conversion"] = 1e-12
    ds.attrs["unit"] = "amperes"
    st = series.create_dataset("starting_time", data=np.float64(0.0))
    st.attrs["rate"] = 20000.0
    st.attrs["unit"] = "seconds"
    if description is not None:
        series.attrs["stimulus_description"] = description


def _write_scala_nwb(path, sweeps: dict[str, float], *, description: str = "GenericStep"):
    """Minimal non-BBP NWB: shared sweep names in ``acquisition``/``presentation``."""
    with h5py.File(path, "w") as f:
        acquisition = f.create_group("acquisition")
        presentation = f.create_group("stimulus").create_group("presentation")
        for name, step_pa in sweeps.items():
            _write_series(presentation, name, _step_trace(step_pa))
            _write_series(acquisition, name, np.zeros(_N_SAMPLES), description=description)


def _write_bbp_nwb(path, steps_pa: list[float], *, ecode: str = "Step"):
    """Minimal BBP NWB: ``data_organization/<cell>/<ecode>/rep/sweep`` + stimuli."""
    with h5py.File(path, "w") as f:
        cell = f.create_group("data_organization").create_group("cell_0")
        presentation = f.create_group("stimulus").create_group("presentation")
        rep = cell.create_group(ecode).create_group("repetition 1")
        for i, step_pa in enumerate(steps_pa):
            sweep = rep.create_group(f"sweep_{i}")
            sweep.create_dataset(f"ccs_{i}", data=np.zeros(10))
            _write_series(presentation, f"ccss_{i}", _mid_step_trace(step_pa))


class TestEstimateStepAmplitudeNa:
    def test_early_step(self):
        """Step before the middle-40% window is still measured."""
        assert estimate_step_amplitude_na(_step_trace(250.0) * 1e-12) == pytest.approx(
            0.25, abs=1e-6
        )

    def test_negative_step(self):
        assert estimate_step_amplitude_na(_step_trace(-400.0) * 1e-12) == pytest.approx(
            -0.4, abs=1e-6
        )

    def test_zero_trace(self):
        assert estimate_step_amplitude_na(np.zeros(_N_SAMPLES) * 1e-12) == pytest.approx(0.0)

    def test_empty(self):
        assert estimate_step_amplitude_na(np.asarray([])) == pytest.approx(0.0)


class TestReadAmplitudesFromNwb:
    def test_bbp_layout(self, tmp_path):
        path = tmp_path / "cell.nwb"
        _write_bbp_nwb(path, [-400.0, 400.0])
        out = read_amplitudes_from_nwb(path, ["Step"])
        assert out["Step"] == [-0.4, 0.4]

    def test_scala_layout_falls_back_to_bluepyefe(self, tmp_path):
        """Non-BBP files are inspected with bluepyefe's own readers."""
        path = tmp_path / "cell.nwb"
        _write_scala_nwb(path, {"GenericStep__0": -400.0, "GenericStep__1": 400.0})
        out = read_amplitudes_from_nwb(path, ["GenericStep"])
        assert out["GenericStep"] == [-0.4, 0.4]

    def test_scala_layout_zero_step_included(self, tmp_path):
        path = tmp_path / "cell.nwb"
        _write_scala_nwb(path, {"GenericStep__0": 0.0, "GenericStep__1": 50.0})
        out = read_amplitudes_from_nwb(path, ["GenericStep"])
        assert out["GenericStep"] == [0.0, 0.05]

    def test_scala_reports_file_protocol_name(self, tmp_path):
        """Reported names not among the requested ones are still returned."""
        path = tmp_path / "cell.nwb"
        _write_scala_nwb(path, {"GenericStep__0": 100.0})
        out = read_amplitudes_from_nwb(path, ["Unrelated"])
        assert out["Unrelated"] == []
        assert out["GenericStep"] == [0.1]


class TestReadProtocolsFromNwb:
    def test_scala_layout_uses_stimulus_description(self, tmp_path):
        path = tmp_path / "cell.nwb"
        _write_scala_nwb(path, {"GenericStep__0": 0.0, "GenericStep__1": 50.0})
        assert read_protocols_from_nwb(path) == ["GenericStep"]
