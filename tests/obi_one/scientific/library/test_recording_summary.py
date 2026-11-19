"""Tests for the recording summary: format, amplitudes, timing and rheobases."""

import json
import logging
from pathlib import Path
from types import SimpleNamespace

import h5py
import jsonschema
import numpy as np
import pytest
from pydantic import ValidationError

from obi_one.scientific.library import recording_summary as summary_module
from obi_one.scientific.library.recording_summary import (
    ProtocolSummary,
    RecordingSummary,
    compute_recording_summary,
    gives_rheobase,
    relative_amplitudes_by_class,
    rheobase_protocol_classes,
    step_protocols,
    timing_by_class,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.protocols import (  # ruff: ignore[line-too-long]
    IDRestProtocol,
    IVProtocol,
    SAHPProtocol,
    SpontaneousProtocol,
)

from tests.obi_one.scientific.library.spiking_nwb import (
    TOFF_MS,
    TON_MS,
    sweep_traces,
    write_spiking_nwb,
)

_SCHEMA = json.loads(
    (Path(__file__).parents[4] / "docs" / "recording-summary.schema.json").read_text()
)
_N_SAMPLES = 1000
# Sampling rate of the BBP-layout test files written with a rate: 0.1 ms per sample.
_RATE_HZ = 10000.0


def _step_trace(step_pa: float) -> np.ndarray:
    trace = np.zeros(_N_SAMPLES)
    trace[int(_N_SAMPLES * 0.3) : int(_N_SAMPLES * 0.7)] = step_pa
    return trace


def _sahp_trace(amp_pa: float, amp2_pa: float) -> np.ndarray:
    """sAHP two-step stimulus: long step → short middle step → long step."""
    trace = np.zeros(_N_SAMPLES)
    trace[int(_N_SAMPLES * 0.15) : int(_N_SAMPLES * 0.45)] = amp_pa
    trace[int(_N_SAMPLES * 0.45) : int(_N_SAMPLES * 0.55)] = amp2_pa
    trace[int(_N_SAMPLES * 0.55) : int(_N_SAMPLES * 0.8)] = amp_pa
    return trace


def _dehyperpol_trace(amp_pa: float, amp2_pa: float) -> np.ndarray:
    """DeHyperPol stimulus: depolarising first step → hyperpolarising second."""
    trace = np.zeros(_N_SAMPLES)
    trace[int(_N_SAMPLES * 0.15) : int(_N_SAMPLES * 0.5)] = amp_pa
    trace[int(_N_SAMPLES * 0.5) : int(_N_SAMPLES * 0.85)] = amp2_pa
    return trace


def _write_series(
    group, name, data, *, conversion=1e-12, unit="amperes", neurodata_type=None, rate=None
):
    series = group.create_group(name)
    if neurodata_type is not None:
        series.attrs["neurodata_type"] = neurodata_type
    ds = series.create_dataset("data", data=data)
    ds.attrs["conversion"] = conversion
    ds.attrs["unit"] = unit
    if rate is not None:
        series.create_dataset("starting_time", data=0.0).attrs["rate"] = rate


def _write_bbp_nwb(path, traces: list, *, ecode: str = "Step", neurodata_type=None, rate=None):
    """Minimal BBP NWB: ``data_organization/<cell>/<ecode>/rep/sweep`` + stimuli.

    ``traces`` are raw stimulus arrays (pA-scaled values, ``conversion=1e-12``). Without
    ``rate`` the stimuli have no sampling rate, so no timing is detected.
    """
    with h5py.File(path, "w") as f:
        cell = f.create_group("data_organization").create_group("cell_0")
        presentation = f.create_group("stimulus").create_group("presentation")
        f.create_group("acquisition")
        rep = cell.create_group(ecode).create_group("repetition 1")
        for i, trace in enumerate(traces):
            sweep = rep.create_group(f"sweep_{i}")
            sweep.create_dataset(f"ccs_{i}", data=np.zeros(10))
            _write_series(
                presentation,
                f"ccss_{i}",
                np.asarray(trace, dtype=float),
                neurodata_type=neurodata_type,
                rate=rate,
            )


def _summary() -> RecordingSummary:
    return RecordingSummary(
        protocols={
            "IDrest": ProtocolSummary(amp=[0.1, 0.3], ton=[200.0], toff=[800.0]),
            "sAHP": ProtocolSummary(
                amp=[0.3], long_amp=[0.08], ton=[25.0], tmid=[520.0], tmid2=[720.0], toff=[2720.0]
            ),
            "HyperDePol": ProtocolSummary(amp=[-0.16], amp2=[0.3]),
        },
        rheobase={"IDrest": 0.2, "IV": None},
    )


class TestRecordingSummary:
    def test_round_trip(self):
        summary = _summary()
        assert RecordingSummary.model_validate_json(summary.model_dump_json()) == summary

    def test_serialised_form_matches_the_schema(self):
        data = json.loads(_summary().model_dump_json())
        jsonschema.validate(data, _SCHEMA)
        assert data["units"] == {"current": "nA", "time": "ms"}
        assert data["protocols"]["IDrest"] == {"amp": [0.1, 0.3], "ton": [200.0], "toff": [800.0]}
        assert data["protocols"]["HyperDePol"] == {"amp": [-0.16], "amp2": [0.3]}
        assert data["rheobase"] == {"IDrest": 0.2, "IV": None}

    def test_empty_summary_keeps_required_keys(self):
        data = json.loads(RecordingSummary().model_dump_json())
        jsonschema.validate(data, _SCHEMA)
        assert data == {
            "version": 1,
            "units": {"current": "nA", "time": "ms"},
            "protocols": {},
            "rheobase": {},
        }

    @pytest.mark.parametrize(
        "data",
        [
            {"version": 1, "units": {"current": "pA"}, "protocols": {}},
            {"version": 1, "units": {"time": "s"}, "protocols": {}},
            {"version": 2, "protocols": {}},
            {"version": 1, "protocols": {"IDrest": {"amp": []}}},
            {"version": 1, "protocols": {"IDrest": {"amp": [0.1], "secondary": [0.2]}}},
            {"version": 1, "protocols": {"IDrest": {"amp": [0.1], "ton": []}}},
            {"version": 1, "protocols": {}, "rheobase": 0.2},
            {"version": 1, "protocols": {}, "rheobase_protocol": "IDthresh"},
        ],
    )
    def test_invalid_content_is_rejected(self, data):
        with pytest.raises(ValidationError):
            RecordingSummary.model_validate(data)


class TestSingleTiming:
    def test_one_value_per_key(self):
        protocol = ProtocolSummary(amp=[0.1], ton=[20.0], toff=[1020.0])
        assert protocol.single_timing() == {"ton": 20.0, "toff": 1020.0}

    def test_no_timing(self):
        assert ProtocolSummary(amp=[0.1]).single_timing() == {}

    def test_sweeps_that_differ_give_none(self):
        protocol = ProtocolSummary(amp=[0.1], ton=[520.0, 700.0], toff=[720.0, 2700.0])
        assert protocol.single_timing() is None


class TestRheobaseFor:
    def test_smallest_of_the_chosen_protocols(self):
        summary = RecordingSummary(rheobase={"IDThreshold": 0.1, "IDrest": 0.08, "IV": None})
        assert summary.rheobase_for({"IDThreshProtocol"}) == pytest.approx(0.1)
        assert summary.rheobase_for({"IDThreshProtocol", "IDRestProtocol"}) == pytest.approx(0.08)

    def test_protocols_that_do_not_fire_are_ignored(self):
        summary = RecordingSummary(rheobase={"IDthresh": 0.1, "IV": None})
        assert summary.rheobase_for({"IDThreshProtocol", "IVProtocol"}) == pytest.approx(0.1)
        assert summary.rheobase_for({"IVProtocol"}) is None

    def test_firing_without_current_makes_the_cell_unusable(self):
        """bluepyefe pools the protocols: a 0 nA firing sweep gives a 0 rheobase."""
        summary = RecordingSummary(rheobase={"IDthresh": 0.1, "GenericStep": 0.0})
        assert summary.rheobase_for({"IDThreshProtocol"}) == pytest.approx(0.1)
        assert summary.rheobase_for({"IDThreshProtocol", "GenericStepProtocol"}) is None

    def test_missing_protocol(self):
        assert RecordingSummary().rheobase_for({"IDThreshProtocol"}) is None


class TestRelativeAmplitudesByClass:
    def test_each_recording_uses_its_own_rheobase(self):
        """0.3 nA at 0.2 nA rheobase and 0.6 nA at 0.4 nA are both 150%."""
        summaries = {
            "a": RecordingSummary(
                protocols={"IDrest": ProtocolSummary(amp=[0.1, 0.3])}, rheobase={"IDthresh": 0.2}
            ),
            "b": RecordingSummary(
                protocols={"IDrest": ProtocolSummary(amp=[0.6])}, rheobase={"IDthresh": 0.4}
            ),
        }
        assert relative_amplitudes_by_class(summaries, ["IDThreshProtocol"]) == {
            "IDRestProtocol": [50.0, 150.0]
        }

    def test_rheobase_protocols_are_applied(self):
        summaries = {
            "a": RecordingSummary(
                protocols={"IDrest": ProtocolSummary(amp=[0.3])},
                rheobase={"IDthresh": 0.3, "IDrest": 0.15},
            )
        }
        assert relative_amplitudes_by_class(summaries, ["IDRestProtocol"]) == {
            "IDRestProtocol": [200.0]
        }

    def test_recordings_without_rheobase_are_skipped(self):
        summaries = {
            "without_rheobase": RecordingSummary(
                protocols={"IDrest": ProtocolSummary(amp=[0.3])}, rheobase={"IDthresh": None}
            ),
            "not_computed": None,
        }
        assert relative_amplitudes_by_class(summaries, ["IDThreshProtocol"]) == {}

    def test_unknown_protocols_are_dropped(self):
        summaries = {
            "a": RecordingSummary(
                protocols={"NotAProtocol": ProtocolSummary(amp=[0.3])}, rheobase={"IDthresh": 0.2}
            )
        }
        assert relative_amplitudes_by_class(summaries, ["IDThreshProtocol"]) == {}


def test_rheobase_protocol_classes_have_a_positive_rheobase_somewhere():
    summaries = {
        "a": RecordingSummary(rheobase={"IDThreshold": 0.1, "IV": None, "GenericStep": 0.0}),
        "b": RecordingSummary(rheobase={"IDrest": 0.2}),
        "c": None,
    }
    assert rheobase_protocol_classes(summaries) == ["IDRestProtocol", "IDThreshProtocol"]


def test_timing_by_class_unions_recordings():
    summaries = {
        "a": RecordingSummary(protocols={"IV": ProtocolSummary(amp=[0.1], ton=[20.0])}),
        "b": RecordingSummary(
            protocols={"IV": ProtocolSummary(amp=[0.1], ton=[25.0], toff=[1020.0])}
        ),
        "c": None,
    }
    assert timing_by_class(summaries) == {"IVProtocol": {"ton": [20.0, 25.0], "toff": [1020.0]}}


def test_step_protocols_are_those_with_a_current_step():
    names = ["IDrest", "IDthresh", "IV", "APWaveform", "GenericStep", "Spontaneous"]
    names += ["StartHold", "sAHP", "Ramp", "HyperDePol", "Unknown"]
    assert step_protocols(names) == ["APWaveform", "GenericStep", "IDrest", "IDthresh", "IV"]
    assert gives_rheobase(IDRestProtocol)
    assert gives_rheobase(IVProtocol)
    assert not gives_rheobase(SpontaneousProtocol)
    assert not gives_rheobase(SAHPProtocol)


class TestComputeRecordingSummary:
    def test_step_amplitudes(self, tmp_path):
        path = tmp_path / "cell.nwb"
        _write_bbp_nwb(path, [_step_trace(-400.0), _step_trace(400.0)])
        summary = compute_recording_summary(path)
        assert summary.protocols == {"Step": ProtocolSummary(amp=[-0.4, 0.4])}
        assert summary.rheobase == {"Step": None}
        jsonschema.validate(json.loads(summary.model_dump_json()), _SCHEMA)

    def test_step_timing_is_detected_from_the_sampling_rate(self, tmp_path):
        path = tmp_path / "cell.nwb"
        _write_bbp_nwb(path, [_step_trace(-400.0), _step_trace(400.0)], rate=_RATE_HZ)
        summary = compute_recording_summary(path)
        # Steps from sample 300 to 700 at 0.1 ms per sample.
        assert summary.protocols["Step"] == ProtocolSummary(
            amp=[-0.4, 0.4], ton=[30.0], toff=[70.0]
        )
        jsonschema.validate(json.loads(summary.model_dump_json()), _SCHEMA)

    def test_sahp_stores_short_step_as_amp_and_long_step_as_long_amp(self, tmp_path):
        """sAHP ``in_target`` matches the short middle step: it is ``amp``."""
        path = tmp_path / "cell.nwb"
        _write_bbp_nwb(
            path,
            [_sahp_trace(200.0, 600.0), _sahp_trace(200.0, 800.0)],
            ecode="sAHP",
        )
        sahp = compute_recording_summary(path).protocols["sAHP"]
        assert sahp.amp == pytest.approx([0.6, 0.8], abs=1e-3)
        assert sahp.long_amp == pytest.approx([0.2], abs=1e-3)
        assert sahp.amp2 is None

    def test_sahp_timing(self, tmp_path):
        path = tmp_path / "cell.nwb"
        _write_bbp_nwb(path, [_sahp_trace(200.0, 600.0)], ecode="sAHP", rate=_RATE_HZ)
        sahp = compute_recording_summary(path).protocols["sAHP"]
        assert sahp.amp == pytest.approx([0.6], abs=1e-3)
        assert sahp.long_amp == pytest.approx([0.2], abs=1e-3)
        assert sahp.timing() == {
            "ton": [15.0],
            "tmid": [45.0],
            "tmid2": [55.0],
            "toff": [80.0],
        }

    def test_idhyperpol_uses_sahp_semantics(self, tmp_path):
        path = tmp_path / "cell.nwb"
        _write_bbp_nwb(path, [_sahp_trace(300.0, 900.0)], ecode="IDhyperpol")
        idhyp = compute_recording_summary(path).protocols["IDhyperpol"]
        assert idhyp.amp == pytest.approx([0.9], abs=1e-3)
        assert idhyp.long_amp == pytest.approx([0.3], abs=1e-3)

    def test_dehyperpol_stores_first_step_as_amp_and_second_as_amp2(self, tmp_path):
        """DeHyperPol matches its depolarising first step; the second step is ``amp2``."""
        path = tmp_path / "cell.nwb"
        _write_bbp_nwb(path, [_dehyperpol_trace(500.0, -300.0)], ecode="DeHyperPol", rate=_RATE_HZ)
        dehyp = compute_recording_summary(path).protocols["DeHyperPol"]
        assert dehyp.amp == pytest.approx([0.5], abs=1e-3)
        assert dehyp.amp2 == pytest.approx([-0.3], abs=1e-3)
        assert dehyp.long_amp is None
        assert dehyp.timing() == {"ton": [15.0], "tmid": [50.0], "toff": [85.0]}

    def test_voltage_clamp_stimuli_are_skipped(self, tmp_path):
        path = tmp_path / "cell.nwb"
        _write_bbp_nwb(path, [_step_trace(400.0)], neurodata_type="VoltageClampStimulusSeries")
        assert compute_recording_summary(path).protocols == {}

    def test_typed_current_clamp_stimuli_are_kept(self, tmp_path):
        path = tmp_path / "cell.nwb"
        _write_bbp_nwb(path, [_step_trace(400.0)], neurodata_type="CurrentClampStimulusSeries")
        assert compute_recording_summary(path).protocols == {"Step": ProtocolSummary(amp=[0.4])}

    def test_rheobase_per_step_protocol(self, tmp_path):
        """Each step protocol's own lowest firing amplitude; IV never fires."""
        path = write_spiking_nwb(
            tmp_path / "cell.nwb",
            {"IDthresh": [0.25, 0.3], "IDrest": [0.2, 0.3], "IV": [-0.04, 0.0]},
            rheobase_na=0.2,
        )
        summary = compute_recording_summary(path)
        data = json.loads(summary.model_dump_json())
        # Rounded to 1 pA: bluepyefe reports 0.2 as the float32 0.20000000298023224.
        assert data["rheobase"] == {"IDrest": 0.2, "IDthresh": 0.25, "IV": None}
        assert summary.rheobase_for({"IDThreshProtocol"}) == pytest.approx(0.25)
        assert summary.rheobase_for({"IDThreshProtocol", "IDRestProtocol"}) == pytest.approx(0.2)
        jsonschema.validate(data, _SCHEMA)

    def test_timing_of_inspected_files(self, tmp_path):
        """Non-BBP layouts are read with bluepyefe's inspection, with its sampling rate."""
        path = write_spiking_nwb(tmp_path / "cell.nwb", {"IDthresh": [0.1, 0.25]}, rheobase_na=0.2)
        idthresh = compute_recording_summary(path).protocols["IDthresh"]
        assert idthresh.timing() == {"ton": [TON_MS], "toff": [TOFF_MS]}

    def test_firing_without_current_is_kept(self, tmp_path):
        """A sweep at 0 nA that fires (spontaneous activity) gives a 0 nA rheobase.

        bluepyefe would drop the cell when that protocol is a rheobase protocol, so it
        is kept as it is, and ``rheobase_for`` rejects it.
        """
        path = write_spiking_nwb(
            tmp_path / "cell.nwb",
            {"GenericStep": [0.0], "IDrest": [0.1, 0.2, 0.3]},
            rheobase_na=0.2,
        )
        _, firing_voltage = sweep_traces(0.3, rheobase_na=0.2)
        with h5py.File(path, "a") as f:
            f["acquisition/GenericStep__0/data"][:] = firing_voltage
        summary = compute_recording_summary(path)
        assert summary.rheobase == {"GenericStep": 0.0, "IDrest": pytest.approx(0.2)}
        assert summary.rheobase_for({"IDRestProtocol"}) == pytest.approx(0.2)
        assert summary.rheobase_for({"IDRestProtocol", "GenericStepProtocol"}) is None


class TestCheckAmplitudes:
    @staticmethod
    def _recording(amp: float):
        return SimpleNamespace(
            amp=amp,
            in_target=lambda target, tolerance, **_: abs(target - amp) < tolerance,
        )

    def test_warns_for_sweeps_away_from_every_amplitude(self, caplog):
        with caplog.at_level(logging.WARNING, logger=summary_module.__name__):
            summary_module._check_amplitudes(
                Path("cell.nwb"), "IV", [-0.1, 0.0], [self._recording(-0.1), self._recording(0.05)]
            )
        assert "1 IV sweeps" in caplog.text
        assert "[0.05]" in caplog.text

    def test_silent_when_every_sweep_matches(self, caplog):
        with caplog.at_level(logging.WARNING, logger=summary_module.__name__):
            summary_module._check_amplitudes(
                Path("cell.nwb"), "IV", [-0.1], [self._recording(-0.105)]
            )
        assert not caplog.text


def test_timing_by_class_drops_unknown_protocols():
    summaries = {
        "a": RecordingSummary(protocols={"Unknown": ProtocolSummary(amp=[0.1], ton=[1.0])})
    }
    assert timing_by_class(summaries) == {}


def test_unreadable_protocol_has_no_rheobase(tmp_path):
    path = tmp_path / "cell.nwb"
    path.write_text("not hdf5")
    assert summary_module._read_with_bluepyefe(path, "IDthresh", {}, {}) is None
