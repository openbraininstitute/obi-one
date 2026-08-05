import json
from dataclasses import dataclass
from pathlib import Path

import libsonata
import pytest
from entitysdk.result import IteratorResult
from entitysdk.types import AssetLabel

import obi_one as obi
from obi_one.core.exception import OBIONEError

ARRAY_ID = "9f8ac5a5-4b6c-4e57-9a2f-2e3f7d0b1c44"


@dataclass
class _FakeDownloadedAsset:
    path: Path


class _FakeClient:
    """Stands in for an entitysdk client, writing dummy weight-matrix files on download."""

    def __init__(self, asset_names=("weights.h5",)) -> None:
        self.asset_names = asset_names
        self.selections = []

    def get_entity(self, entity_id, entity_type):  # noqa: ARG002
        return object()

    def download_assets(self, entity, *, selection, output_path):  # noqa: ARG002
        self.selections.append(selection)
        downloaded = []
        for asset_name in self.asset_names:
            path = Path(output_path) / asset_name
            path.write_bytes(b"weights")
            downloaded.append(_FakeDownloadedAsset(path))
        return IteratorResult(downloaded)


def _recording(name="LFPRecording", dt=0.1):
    recording = obi.ExtracellularElectrodeArrayRecordingBlock(
        electrode_array=obi.SimulatableExtracellularRecordingArrayFromID(id_str=ARRAY_ID),
        dt=dt,
    )
    recording.set_block_name(name)
    return recording


class TestExtracellularElectrodeArrayRecordingBlock:
    def test_generates_sonata_lfp_report(self, tmp_path):
        recording = _recording()
        db_client = _FakeClient()

        reports = recording.config(
            end_time=100.0,
            default_node_set="AllBiophysical",
            db_client=db_client,
            sonata_simulation_config_directory=tmp_path,
        )

        assert reports == {
            "LFPRecording": {
                "cells": "AllBiophysical",
                "type": "lfp",
                "sections": "all",
                "dt": 0.1,
                "start_time": 0.0,
                "end_time": 100.0,
                "electrodes_file": "LFPRecording_electrodes.h5",
            }
        }

    def test_downloads_weight_matrix_next_to_simulation_config(self, tmp_path):
        recording = _recording(name="ProbeA")
        db_client = _FakeClient()

        recording.config(
            end_time=100.0,
            db_client=db_client,
            sonata_simulation_config_directory=tmp_path,
        )

        # Selected by asset label, and renamed after the block so two arrays cannot collide.
        assert db_client.selections == [{"label": AssetLabel.electrode_array_weight_matrix}]
        assert (tmp_path / "ProbeA_electrodes.h5").read_bytes() == b"weights"
        assert not (tmp_path / "weights.h5").exists()

    def test_report_is_accepted_by_libsonata(self, tmp_path):
        """`write_simulation_config` validates with libsonata, which is strict about lfp reports."""
        recording = _recording()
        reports = recording.config(
            end_time=100.0,
            db_client=_FakeClient(),
            sonata_simulation_config_directory=tmp_path,
        )

        sonata_config = {
            "version": 1,
            "network": "circuit_config.json",
            "run": {"tstop": 100.0, "dt": 0.025, "random_seed": 1},
            "reports": reports,
        }
        parsed = libsonata.SimulationConfig(json.dumps(sonata_config), str(tmp_path))

        report = parsed.report("LFPRecording")
        assert report.type == libsonata.SimulationConfig.Report.Type.lfp
        assert report.electrodes_file == str(tmp_path / "LFPRecording_electrodes.h5")

    def test_missing_db_client_raises(self, tmp_path):
        recording = _recording()

        with pytest.raises(OBIONEError, match="needs a database client"):
            recording.config(end_time=100.0, sonata_simulation_config_directory=tmp_path)

    def test_missing_config_directory_raises(self):
        recording = _recording()

        with pytest.raises(OBIONEError, match="needs the simulation config directory"):
            recording.config(end_time=100.0, db_client=_FakeClient())

    @pytest.mark.parametrize("asset_names", [(), ("a.h5", "b.h5")])
    def test_requires_exactly_one_weight_matrix_asset(self, tmp_path, asset_names):
        recording = _recording()

        with pytest.raises(OBIONEError, match="Expected exactly one"):
            recording.config(
                end_time=100.0,
                db_client=_FakeClient(asset_names=asset_names),
                sonata_simulation_config_directory=tmp_path,
            )


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
