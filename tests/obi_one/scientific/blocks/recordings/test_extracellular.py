import json
from pathlib import Path
from uuid import UUID

import libsonata
import pytest

import obi_one as obi
from obi_one.scientific.library.constants import SIMULATION_TIMESTEP_MILLISECONDS

ARRAY_ID = "9f8ac5a5-4b6c-4e57-9a2f-2e3f7d0b1c44"


class _ClientThatMustNotBeUsed:
    """Fails the test on any use: emitting the report must not touch the database."""

    def __getattr__(self, name):
        msg = f"the recording used the database client ({name})"
        raise AssertionError(msg)


def _recording(name="LFPRecording", dt=0.1):
    recording = obi.ExtracellularElectrodeArrayRecordingBlock(
        electrode_array=obi.SimulatableExtracellularRecordingArrayFromID(id_str=ARRAY_ID),
        dt=dt,
    )
    recording.set_block_name(name)
    return recording


class TestExtracellularElectrodeArrayRecordingBlock:
    def test_generates_sonata_lfp_report(self):
        reports = _recording().config(
            SIMULATION_TIMESTEP_MILLISECONDS, end_time=100.0, default_node_set="AllBiophysical"
        )

        assert reports == {
            "LFPRecording": {
                "cells": "AllBiophysical",
                "type": "lfp",
                "sections": "all",
                "dt": 0.1,
                "start_time": 0.0,
                "end_time": 100.0,
                "electrodes_file": f"{ARRAY_ID}.h5",
            }
        }

    def test_electrodes_file_is_named_after_the_array(self):
        """entitysdk's stage_simulation reads the array id back out of the file name's stem."""
        reports = _recording().config(SIMULATION_TIMESTEP_MILLISECONDS, end_time=100.0)

        electrodes_file = Path(reports["LFPRecording"]["electrodes_file"])
        assert UUID(electrodes_file.stem) == UUID(ARRAY_ID)

    def test_does_not_download_the_weight_matrix(self):
        """The matrix covers the whole circuit; it is staged when the simulation is run."""
        reports = _recording().config(
            SIMULATION_TIMESTEP_MILLISECONDS,
            end_time=100.0,
            db_client=_ClientThatMustNotBeUsed(),
        )

        assert reports["LFPRecording"]["electrodes_file"] == f"{ARRAY_ID}.h5"

    def test_report_is_accepted_by_libsonata(self, tmp_path):
        """`write_simulation_config` validates with libsonata, which is strict about lfp reports.

        Nothing exists at the path: libsonata does not need the file, only the simulation does.
        """
        reports = _recording().config(SIMULATION_TIMESTEP_MILLISECONDS, end_time=100.0)

        sonata_config = {
            "version": 1,
            "network": "circuit_config.json",
            "run": {"tstop": 100.0, "dt": 0.025, "random_seed": 1},
            "reports": reports,
        }
        parsed = libsonata.SimulationConfig(json.dumps(sonata_config), str(tmp_path))

        report = parsed.report("LFPRecording")
        assert report.type == libsonata.SimulationConfig.Report.Type.lfp
        assert report.electrodes_file == str(tmp_path / f"{ARRAY_ID}.h5")


class TestCircuitRecordingUnion:
    def test_extracellular_recording_offered_by_circuit_simulations(self):
        scan_config = obi.CircuitSimulationScanConfig.empty_config()
        scan_config.add(_recording(), name="LFPRecording")

        assert isinstance(
            scan_config.recordings["LFPRecording"],
            obi.ExtracellularElectrodeArrayRecordingBlock,
        )

    def test_extracellular_recording_rejected_by_single_cell_simulations(self):
        """MEModel simulations have no circuit-wide weight matrix, so cannot record LFP."""
        scan_config = obi.MEModelSimulationScanConfig.empty_config()

        # Not in the block mapping, because it is not part of that config's recordings union.
        with pytest.raises(KeyError, match="ExtracellularElectrodeArrayRecordingBlock"):
            scan_config.add(_recording(), name="LFPRecording")
