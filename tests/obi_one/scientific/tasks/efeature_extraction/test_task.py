"""Tests for the EModelEFeatureExtractionTask."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from obi_one.scientific.tasks.emodel_optimization._01_efeature_extraction.task import (
    EModelEFeatureExtractionTask,
    _build_extraction_recipes,
    _build_figures_manifest,
    _build_files_metadata,
    _build_targets_formatted,
    _discover_amplitudes,
    _ecode_class_name,
    _partition_protocols,
)
from obi_one.scientific.tasks.emodel_optimization._01_efeature_extraction.blocks import (
    AbsoluteRheobase,
    Settings,
)


class TestBuildExtractionRecipes:
    def test_default_settings(self):
        settings = Settings()
        rheobase = AbsoluteRheobase()
        recipes = _build_extraction_recipes(settings, rheobase)

        assert "emodel" in recipes
        ps = recipes["emodel"]["pipeline_settings"]
        assert ps["extract_absolute_amplitudes"] is True
        assert ps["plot_extraction"] is True
        assert ps["default_std_value"] == 0.01
        assert ps["rheobase_strategy_extraction"] == "absolute"
        assert ps["rheobase_settings_extraction"] == {"spike_threshold": 1}
        assert ps["efel_settings"]["Threshold"] == -20.0
        assert ps["efel_settings"]["interp_step"] == 0.025

    def test_custom_settings(self):
        settings = Settings(
            threshold=-30.0,
            plot_extraction=False,
            pickle_cells=True,
            name_rin_protocol="IV_-20",
        )
        rheobase = AbsoluteRheobase(spike_threshold=3, protocols=("IDthresh", "IDrest"))
        recipes = _build_extraction_recipes(settings, rheobase)

        ps = recipes["emodel"]["pipeline_settings"]
        assert ps["efel_settings"]["Threshold"] == -30.0
        assert ps["plot_extraction"] is False
        assert ps["pickle_cells_extraction"] is True
        assert ps["name_Rin_protocol"] == "IV_-20"
        assert ps["rheobase_settings_extraction"] == {"spike_threshold": 3}


class TestBuildFilesMetadata:
    def test_basic(self, tmp_path):
        path1 = tmp_path / "cell1.nwb"
        path1.touch()
        path2 = tmp_path / "cell2.nwb"
        path2.touch()

        files = _build_files_metadata(
            nwb_paths_with_ljp=[(path1, 14.0), (path2, 12.0)],
            ecodes_metadata_dict={"IDrest": {}, "IV": {"ton": 20.0}},
        )

        assert len(files) == 2
        # Sorted by path
        assert files[0]["cell_name"] == "cell1"
        assert files[0]["ecodes"]["IDrest"] == {"ljp": 14.0}
        assert files[0]["ecodes"]["IV"] == {"ton": 20.0, "ljp": 14.0}
        assert files[1]["cell_name"] == "cell2"
        assert files[1]["ecodes"]["IDrest"] == {"ljp": 12.0}

    def test_empty_ecodes(self, tmp_path):
        path1 = tmp_path / "cell1.nwb"
        path1.touch()

        files = _build_files_metadata(
            nwb_paths_with_ljp=[(path1, 14.0)],
            ecodes_metadata_dict={},
        )
        assert len(files) == 1
        assert files[0]["ecodes"] == {}


class TestBuildFiguresManifest:
    def test_empty_directory(self, tmp_path):
        figures_dir = tmp_path / "figures"
        figures_dir.mkdir()

        task = EModelEFeatureExtractionTask.__new__(EModelEFeatureExtractionTask)
        manifest = task._build_figures_manifest(figures_dir)
        assert manifest == {"cells": [], "files": []}

    def test_legend_file(self, tmp_path):
        figures_dir = tmp_path / "figures"
        figures_dir.mkdir()
        (figures_dir / "legend.pdf").touch()

        task = EModelEFeatureExtractionTask.__new__(EModelEFeatureExtractionTask)
        manifest = task._build_figures_manifest(figures_dir)
        assert len(manifest["files"]) == 1
        assert manifest["files"][0]["type"] == "legend"
        assert manifest["files"][0]["path"] == "legend.pdf"

    def test_feature_plot(self, tmp_path):
        figures_dir = tmp_path / "figures"
        cell_dir = figures_dir / "CellA"
        cell_dir.mkdir(parents=True)
        (cell_dir / "CellA_IDRest_mean_frequency_amp.pdf").touch()

        task = EModelEFeatureExtractionTask.__new__(EModelEFeatureExtractionTask)
        manifest = task._build_figures_manifest(figures_dir)
        assert len(manifest["files"]) == 1
        entry = manifest["files"][0]
        assert entry["type"] == "feature_plot"
        assert entry["cell"] == "CellA"
        assert entry["protocol"] == "IDRest"
        assert entry["feature"] == "mean_frequency"

    def test_recordings_plot(self, tmp_path):
        figures_dir = tmp_path / "figures"
        cell_dir = figures_dir / "CellA"
        cell_dir.mkdir(parents=True)
        (cell_dir / "CellA_IDRest_recordings.pdf").touch()

        task = EModelEFeatureExtractionTask.__new__(EModelEFeatureExtractionTask)
        manifest = task._build_figures_manifest(figures_dir)
        assert len(manifest["files"]) == 1
        entry = manifest["files"][0]
        assert entry["type"] == "recordings_plot"

    def test_cells_list(self, tmp_path):
        figures_dir = tmp_path / "figures"
        for cell in ("CellA", "CellB"):
            cell_dir = figures_dir / cell
            cell_dir.mkdir(parents=True)
            (cell_dir / f"{cell}_IDRest_recordings.pdf").touch()

        task = EModelEFeatureExtractionTask.__new__(EModelEFeatureExtractionTask)
        manifest = task._build_figures_manifest(figures_dir)
        assert manifest["cells"] == ["CellA", "CellB"]


class TestAutoselect:
    """Test that autoselect mode invokes get_auto_target_from_presets."""

    def test_autoselect_calls_auto_targets(self):
        """When autoselect=True, _build_targets_configuration should use auto_targets."""
        from obi_one.scientific.tasks.emodel_optimization._01_efeature_extraction.blocks import (
            ExtractionInitialize,
            ProtocolAndFeatureSelection,
        )
        from obi_one.scientific.from_id.electrical_cell_recording_from_id import (
            ElectricalCellRecordingFromID,
        )
        from obi_one.scientific.tasks.emodel_optimization._01_efeature_extraction.config import (
            EModelEFeatureExtractionSingleConfig,
        )

        # Build a config with autoselect=True
        config_data = EModelEFeatureExtractionSingleConfig(
            info=EModelEFeatureExtractionSingleConfig.model_fields["info"].annotation(
                campaign_name="T",
                campaign_description="T",
            ),
            initialize=ExtractionInitialize(
                electrical_cell_recording=(
                    ElectricalCellRecordingFromID(id_str="fake-id"),
                ),
            ),
            efeatures_by_protocol=ProtocolAndFeatureSelection(
                autoselect=True,
                auto_targets_presets=("firing_pattern", "iv"),
            ),
        )

        task = EModelEFeatureExtractionTask(config=config_data)

        # Mock the imports that _build_targets_configuration uses
        mock_targets_config = MagicMock()
        fake_downloaded = [(Path("/tmp/fake.nwb"), 14.0)]

        with (
            patch(
                "obi_one.scientific.tasks.emodel_optimization._01_efeature_extraction.task._build_files_metadata",
                return_value=[{"cell_name": "fake", "filepath": "/tmp/fake.nwb", "ecodes": {}}],
            ),
            patch(
                "bluepyemodel.efeatures_extraction.auto_targets.get_auto_target_from_presets",
                return_value=[{"protocols": ["IDrest"], "efeatures": ["mean_frequency"]}],
            ) as mock_auto,
            patch(
                "bluepyemodel.efeatures_extraction.targets_configuration.TargetsConfiguration",
                return_value=mock_targets_config,
            ) as mock_tc,
        ):
            result = task._build_targets_configuration(fake_downloaded)

        mock_auto.assert_called_once_with(["firing_pattern", "iv"])
        # TargetsConfiguration should be called with auto_targets, not targets
        call_kwargs = mock_tc.call_args[1]
        assert "auto_targets" in call_kwargs
        assert "targets" not in call_kwargs
