"""Unit tests for electrical_cell_recording_properties library helpers."""

from unittest.mock import MagicMock

import entitysdk.client
import h5py
import numpy as np
import pytest

from obi_one.scientific.library.electrical_cell_recording_properties import (
    detect_ton_ms,
    read_amplitudes_from_nwb,
    read_protocols_from_nwb,
    read_timing_from_nwb,
    step_amplitude_na,
    stim_key_for_trace,
)
from obi_one.utils.db_sdk import get_recording_protocols


class TestStimKeyForTrace:
    def test_ccs_prefix(self):
        assert stim_key_for_trace("ccs__Step__1") == "ccss__Step__1"

    def test_ic_prefix(self):
        assert stim_key_for_trace("ic__Step__1") == "ics__Step__1"

    def test_no_match(self):
        assert stim_key_for_trace("abc__Step__1") is None


class TestStepAmplitudeNa:
    def test_empty(self):
        assert step_amplitude_na(np.array([])) == pytest.approx(0.0)

    def test_step(self):
        # 1000 samples: baseline 0 A, step 1e-10 A (0.1 nA)
        current = np.zeros(1000)
        current[300:700] = 1e-10
        amp = step_amplitude_na(current)
        assert pytest.approx(amp, abs=1e-6) == 0.1

    def test_negative_step(self):
        current = np.zeros(1000)
        current[300:700] = -5e-11
        amp = step_amplitude_na(current)
        assert pytest.approx(amp, abs=1e-6) == -0.05


class TestDetectTonMs:
    def test_too_short(self):
        assert detect_ton_ms(np.zeros(10), 0.1) is None

    def test_zero_dt(self):
        assert detect_ton_ms(np.zeros(1000), 0.0) is None

    def test_flat_trace(self):
        assert detect_ton_ms(np.zeros(1000), 0.1) is None

    def test_detect_onset(self):
        # 1000 samples at 0.1 ms dt, step at sample 500
        # Edges (first/last 50 samples) must be at baseline for noise estimation
        current = np.zeros(1000)
        current[500:950] = 0.1  # 0.1 nA step, baseline at both ends
        ton = detect_ton_ms(current, 0.1)
        assert ton is not None
        # Onset should be around 500 * 0.1 = 50 ms
        assert 45.0 <= ton <= 55.0


class TestGetRecordingProtocols:
    def test_extracts_stimuli_names(self):

        stimulus_1 = MagicMock()
        stimulus_1.name = "Step"
        stimulus_2 = MagicMock()
        stimulus_2.name = "IDRest"
        stimulus_3 = MagicMock()
        stimulus_3.name = "Step"  # duplicate

        entity = MagicMock()
        entity.stimuli = [stimulus_1, stimulus_2, stimulus_3]

        db_client = MagicMock(entitysdk.client.Client)
        db_client.get_entity.return_value = entity

        result = get_recording_protocols(["rec-1"], db_client)
        assert result == {"rec-1": ["IDRest", "Step"]}

    def test_empty_stimuli(self):

        entity = MagicMock()
        entity.stimuli = []

        db_client = MagicMock(entitysdk.client.Client)
        db_client.get_entity.return_value = entity

        result = get_recording_protocols(["rec-1"], db_client)
        assert result == {"rec-1": []}

    def test_none_stimuli(self):

        entity = MagicMock()
        entity.stimuli = None

        db_client = MagicMock(entitysdk.client.Client)
        db_client.get_entity.return_value = entity

        result = get_recording_protocols(["rec-1"], db_client)
        assert result == {"rec-1": []}

    def test_stimulus_with_none_name(self):

        stimulus_1 = MagicMock()
        stimulus_1.name = "Step"
        stimulus_2 = MagicMock()
        stimulus_2.name = None

        entity = MagicMock()
        entity.stimuli = [stimulus_1, stimulus_2]

        db_client = MagicMock(entitysdk.client.Client)
        db_client.get_entity.return_value = entity

        result = get_recording_protocols(["rec-1"], db_client)
        assert result == {"rec-1": ["Step"]}


class TestReadProtocolsFromNwb:
    def test_no_data_organization_or_acquisition(self, tmp_path):

        nwb_path = tmp_path / "test.nwb"
        with h5py.File(str(nwb_path), "w") as f:
            f.create_group("some_other_group")
        result = read_protocols_from_nwb(nwb_path)
        assert result == []

    def test_data_organization(self, tmp_path):

        nwb_path = tmp_path / "test.nwb"
        with h5py.File(str(nwb_path), "w") as f:
            do = f.create_group("data_organization")
            cell = do.create_group("cell_1")
            cell.create_group("Step")
            cell.create_group("IDRest")
        result = read_protocols_from_nwb(nwb_path)
        assert result == ["IDRest", "Step"]

    def test_acquisition_fallback(self, tmp_path):

        nwb_path = tmp_path / "test.nwb"
        with h5py.File(str(nwb_path), "w") as f:
            acq = f.create_group("acquisition")
            acq.create_group("ccs__Step__1")
            acq.create_group("ccs__IDRest__2")
        result = read_protocols_from_nwb(nwb_path)
        assert result == ["IDRest", "Step"]


class TestReadAmplitudesFromNwb:
    def test_no_data_organization(self, tmp_path):

        nwb_path = tmp_path / "test.nwb"
        with h5py.File(str(nwb_path), "w") as f:
            f.create_group("other")
        result = read_amplitudes_from_nwb(nwb_path, ["Step"])
        assert result == {"Step": []}

    def test_with_stimulus(self, tmp_path):

        nwb_path = tmp_path / "test.nwb"
        with h5py.File(str(nwb_path), "w") as f:
            do = f.create_group("data_organization")
            cell = do.create_group("cell_1")
            proto = cell.create_group("Step")
            rep = proto.create_group("rep_1")
            sweep = rep.create_group("sweep_1")
            sweep.create_group("ccs__Step__1")

            stim = f.create_group("stimulus")
            pres = stim.create_group("presentation")
            ccss = pres.create_group("ccss__Step__1")
            data = ccss.create_dataset("data", data=np.zeros(1000, dtype=np.float64))
            data.attrs["conversion"] = 1.0
            # 0.1 nA step in amperes = 1e-10
            data[300:700] = 1e-10

        result = read_amplitudes_from_nwb(nwb_path, ["Step"])
        assert "Step" in result
        assert len(result["Step"]) == 1
        assert pytest.approx(result["Step"][0], abs=1e-3) == 0.1


class TestReadTimingFromNwb:
    def test_no_data_organization(self, tmp_path):

        nwb_path = tmp_path / "test.nwb"
        with h5py.File(str(nwb_path), "w") as f:
            f.create_group("other")
        result = read_timing_from_nwb(nwb_path, ["Step"])
        assert result == {}

    def test_with_stimulus(self, tmp_path):

        nwb_path = tmp_path / "test.nwb"
        with h5py.File(str(nwb_path), "w") as f:
            do = f.create_group("data_organization")
            cell = do.create_group("cell_1")
            proto = cell.create_group("Step")
            rep = proto.create_group("rep_1")
            sweep = rep.create_group("sweep_1")
            sweep.create_group("ccs__Step__1")

            stim = f.create_group("stimulus")
            pres = stim.create_group("presentation")
            ccss = pres.create_group("ccss__Step__1")
            st = ccss.create_group("starting_time")
            st.attrs["rate"] = 10000.0  # 10 kHz → dt = 0.1 ms
            data = ccss.create_dataset("data", data=np.zeros(1000, dtype=np.float64))
            data.attrs["conversion"] = 1.0
            # 0.1 nA step at sample 500, baseline at edges → ton ≈ 50 ms
            data[500:950] = 0.1

        result = read_timing_from_nwb(nwb_path, ["Step"])
        assert "Step" in result
        assert 45.0 <= result["Step"] <= 55.0
