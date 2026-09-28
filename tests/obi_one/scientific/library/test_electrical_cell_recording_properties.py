"""Tests for the ElectricalCellRecording NWB helpers."""

import bluepyefe.reader
import h5py
import numpy as np
import pytest

from obi_one.scientific.library.electrical_cell_recording_properties import (
    estimate_step_amplitude,
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


def _write_series(
    group,
    name: str,
    data: np.ndarray,
    *,
    description: str | None = None,
    conversion: float = 1e-12,
    unit: str = "amperes",
):
    series = group.create_group(name)
    ds = series.create_dataset("data", data=data)
    ds.attrs["conversion"] = conversion
    ds.attrs["unit"] = unit
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


def _write_bbp_nwb(
    path,
    steps: list[float],
    *,
    ecode: str = "Step",
    i_conversion: float = 1e-12,
    i_unit: str = "amperes",
    v_conversion: float | None = None,
    v_unit: str = "volts",
):
    """Minimal BBP NWB: ``data_organization/<cell>/<ecode>/rep/sweep`` + stimuli.

    ``steps`` are raw stored values; when ``v_conversion`` is set, matching
    voltage series are written under ``acquisition``.
    """
    with h5py.File(path, "w") as f:
        cell = f.create_group("data_organization").create_group("cell_0")
        presentation = f.create_group("stimulus").create_group("presentation")
        acquisition = f.create_group("acquisition")
        rep = cell.create_group(ecode).create_group("repetition 1")
        for i, step in enumerate(steps):
            sweep = rep.create_group(f"sweep_{i}")
            sweep.create_dataset(f"ccs_{i}", data=np.zeros(10))
            _write_series(
                presentation,
                f"ccss_{i}",
                _mid_step_trace(step),
                conversion=i_conversion,
                unit=i_unit,
            )
            if v_conversion is not None:
                _write_series(
                    acquisition,
                    f"ccs_{i}",
                    np.zeros(_N_SAMPLES),
                    conversion=v_conversion,
                    unit=v_unit,
                )


class TestEstimateStepAmplitude:
    def test_early_step(self):
        """Step before the middle-40% window is still measured."""
        assert estimate_step_amplitude(_step_trace(0.25)) == pytest.approx(0.25, abs=1e-6)

    def test_negative_step(self):
        assert estimate_step_amplitude(_step_trace(-0.4)) == pytest.approx(-0.4, abs=1e-6)

    def test_zero_trace(self):
        assert estimate_step_amplitude(np.zeros(_N_SAMPLES)) == pytest.approx(0.0)

    def test_empty(self):
        assert estimate_step_amplitude(np.asarray([])) == pytest.approx(0.0)


class TestReadAmplitudesFromNwb:
    def test_bbp_layout(self, tmp_path):
        path = tmp_path / "cell.nwb"
        _write_bbp_nwb(path, [-400.0, 400.0])
        out = read_amplitudes_from_nwb(path, ["Step"])
        assert out["Step"] == [-0.4, 0.4]

    def test_bbp_layout_pa_unit(self, tmp_path):
        """BBP series stored with unit ``pA`` (conversion 1) are converted to nA."""
        path = tmp_path / "cell.nwb"
        _write_bbp_nwb(path, [-400.0, 400.0], i_conversion=1.0, i_unit="pA")
        out = read_amplitudes_from_nwb(path, ["Step"])
        assert out["Step"] == [-0.4, 0.4]

    def test_bbp_layout_volts_mixup_is_repaired(self, tmp_path):
        """bluepyefe's volts/volts mislabel (i_conv 1e-3, v_conv 1e-12) is repaired."""
        path = tmp_path / "cell.nwb"
        _write_bbp_nwb(
            path,
            [-400.0, 400.0],
            i_conversion=0.001,
            i_unit="volts",
            v_conversion=1e-12,
        )
        out = read_amplitudes_from_nwb(path, ["Step"])
        assert out["Step"] == [-0.4, 0.4]

    def test_bbp_layout_unknown_unit_skipped(self, tmp_path):
        path = tmp_path / "cell.nwb"
        _write_bbp_nwb(path, [400.0], i_unit="volts", v_conversion=1e-3)
        out = read_amplitudes_from_nwb(path, ["Step"])
        assert out["Step"] == []

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

    def test_scala_filters_to_requested_protocol_class(self, tmp_path):
        """Unrelated file protocols are dropped; same-class names still match."""
        path = tmp_path / "cell.nwb"
        _write_scala_nwb(path, {"GenericStep__0": 100.0})
        assert read_amplitudes_from_nwb(path, ["step"]) == {"GenericStep": [0.1]}
        assert read_amplitudes_from_nwb(path, ["IDRest"]) == {}


def _fake_inspect_nwb(traces):
    """Replacement for bluepyefe.reader.inspect_nwb returning fixed traces."""

    def fake(_path, **_kwargs):
        return {"protocols": ["GenericStep"], "traces": traces}

    return fake


def _trace(step_value: float, i_unit: str) -> dict:
    """A trace dict as inspect_nwb returns it, with the step in `i_unit`."""
    current = np.zeros(_N_SAMPLES)
    current[_STEP_ONSET:_STEP_OFFSET] = step_value
    return {"id": "t0", "current": current, "i_unit": i_unit}


def _minimal_non_bbp_nwb(path):
    """An HDF5 file without ``data_organization`` so the fallback path is used."""
    with h5py.File(path, "w") as f:
        f.create_group("acquisition")
    return path


class TestReadAmplitudesViaInspectionUnits:
    @pytest.mark.parametrize(
        ("i_unit", "step_value"),
        [("amperes", 250e-12), ("nA", 0.25), ("pA", 250.0), ("uA", 0.00025)],
    )
    def test_i_unit_is_respected(self, tmp_path, monkeypatch, i_unit, step_value):
        """Same physical step in different units gives the same nA amplitude."""
        monkeypatch.setattr(
            bluepyefe.reader, "inspect_nwb", _fake_inspect_nwb([_trace(step_value, i_unit)])
        )
        path = _minimal_non_bbp_nwb(tmp_path / "cell.nwb")
        out = read_amplitudes_from_nwb(path, ["GenericStep"])
        assert out["GenericStep"] == pytest.approx([0.25])

    def test_unknown_unit_trace_is_skipped(self, tmp_path, monkeypatch):
        traces = [_trace(0.25, "mV"), _trace(0.25, "nA")]
        monkeypatch.setattr(bluepyefe.reader, "inspect_nwb", _fake_inspect_nwb(traces))
        path = _minimal_non_bbp_nwb(tmp_path / "cell.nwb")
        out = read_amplitudes_from_nwb(path, ["GenericStep"])
        assert out["GenericStep"] == pytest.approx([0.25])

    def test_missing_unit_defaults_to_amperes(self, tmp_path, monkeypatch):
        trace = _trace(250e-12, "nA")
        del trace["i_unit"]
        monkeypatch.setattr(bluepyefe.reader, "inspect_nwb", _fake_inspect_nwb([trace]))
        path = _minimal_non_bbp_nwb(tmp_path / "cell.nwb")
        out = read_amplitudes_from_nwb(path, ["GenericStep"])
        assert out["GenericStep"] == pytest.approx([0.25])


class TestReadProtocolsFromNwb:
    def test_scala_layout_uses_stimulus_description(self, tmp_path):
        path = tmp_path / "cell.nwb"
        _write_scala_nwb(path, {"GenericStep__0": 0.0, "GenericStep__1": 50.0})
        assert read_protocols_from_nwb(path) == ["GenericStep"]
