"""Tests for the EModelEFeatureExtractionScanConfig and SingleConfig."""

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from obi_one.scientific.from_id.electrical_cell_recording_from_id import (
    ElectricalCellRecordingFromID,
)
from obi_one.scientific.tasks.emodel_optimization._01_efeature_extraction.blocks import (
    AbsoluteRheobase,
    ExtractionInitialize,
    FlushRheobase,
    InterpolationRheobase,
    ProtocolAndFeatureSelection,
    Settings,
)
from obi_one.scientific.tasks.emodel_optimization._01_efeature_extraction.config import (
    EModelEFeatureExtractionScanConfig,
    EModelEFeatureExtractionSingleConfig,
)


@pytest.fixture
def recording_ids():
    return ("492bdec5-2dce-4ae0-8b85-f020a1ad1d92", "812a8721-1681-49a2-a155-59ab30981079")


@pytest.fixture
def scan_config(recording_ids):
    return EModelEFeatureExtractionScanConfig(
        info=EModelEFeatureExtractionScanConfig.model_fields["info"].annotation(
            campaign_name="Test Campaign",
            campaign_description="Test extraction campaign",
        ),
        initialize=ExtractionInitialize(
            electrical_cell_recording=tuple(
                ElectricalCellRecordingFromID(id_str=rid) for rid in recording_ids
            ),
        ),
    )


class TestScanConfigClassVars:
    def test_name(self):
        assert EModelEFeatureExtractionScanConfig.name == "EModel EFeature Extraction"

    def test_single_coord_class_name(self):
        assert (
            EModelEFeatureExtractionScanConfig.single_coord_class_name
            == "EModelEFeatureExtractionSingleConfig"
        )

    def test_campaign_task_config_type(self):
        from entitysdk.types import TaskConfigType

        assert (
            EModelEFeatureExtractionScanConfig._campaign_task_config_type
            == TaskConfigType.efeature_extraction__campaign
        )

    def test_campaign_generation_task_activity_type(self):
        from entitysdk.types import TaskActivityType

        assert (
            EModelEFeatureExtractionScanConfig._campaign_generation_task_activity_type
            == TaskActivityType.efeature_extraction__config_generation
        )


class TestScanConfigCreation:
    def test_minimal_creation(self, scan_config):
        assert scan_config.campaign_name == "Test Campaign"
        assert scan_config.campaign_description == "Test extraction campaign"
        assert len(scan_config.initialize.electrical_cell_recording) == 2

    def test_default_settings(self, scan_config):
        assert scan_config.settings.threshold == -20.0
        assert scan_config.settings.plot_extraction is True
        assert scan_config.settings.interp_step == 0.025

    def test_default_rheobase(self, scan_config):
        assert isinstance(scan_config.rheobase, AbsoluteRheobase)
        assert scan_config.rheobase.protocols == ("IDthresh",)
        assert scan_config.rheobase.spike_threshold == 1

    def test_default_efeatures_by_protocol(self, scan_config):
        assert scan_config.efeatures_by_protocol.autoselect is False
        assert len(scan_config.efeatures_by_protocol.protocols) == 5

    def test_custom_rheobase_strategy(self, recording_ids):
        config = EModelEFeatureExtractionScanConfig(
            info=EModelEFeatureExtractionScanConfig.model_fields["info"].annotation(
                campaign_name="Test",
                campaign_description="Test",
            ),
            initialize=ExtractionInitialize(
                electrical_cell_recording=(
                    ElectricalCellRecordingFromID(id_str=recording_ids[0]),
                ),
            ),
            rheobase=FlushRheobase(flush_length=2, protocols=("IDthresh", "IDrest")),
        )
        assert isinstance(config.rheobase, FlushRheobase)
        assert config.rheobase.flush_length == 2
        assert config.rheobase.protocols == ("IDthresh", "IDrest")


class TestAutoselect:
    def test_autoselect_default_false(self, scan_config):
        assert scan_config.efeatures_by_protocol.autoselect is False

    def test_autoselect_true(self, recording_ids):
        config = EModelEFeatureExtractionScanConfig(
            info=EModelEFeatureExtractionScanConfig.model_fields["info"].annotation(
                campaign_name="Auto Test",
                campaign_description="Auto",
            ),
            initialize=ExtractionInitialize(
                electrical_cell_recording=(
                    ElectricalCellRecordingFromID(id_str=recording_ids[0]),
                ),
            ),
            efeatures_by_protocol=ProtocolAndFeatureSelection(autoselect=True),
        )
        assert config.efeatures_by_protocol.autoselect is True

    def test_default_presets(self, scan_config):
        assert scan_config.efeatures_by_protocol.auto_targets_presets == (
            "firing_pattern",
            "ap_waveform",
            "iv",
        )

    def test_custom_presets(self, recording_ids):
        config = EModelEFeatureExtractionScanConfig(
            info=EModelEFeatureExtractionScanConfig.model_fields["info"].annotation(
                campaign_name="Custom",
                campaign_description="Custom",
            ),
            initialize=ExtractionInitialize(
                electrical_cell_recording=(
                    ElectricalCellRecordingFromID(id_str=recording_ids[0]),
                ),
            ),
            efeatures_by_protocol=ProtocolAndFeatureSelection(
                autoselect=True,
                auto_targets_presets=("firing_pattern", "iv", "validation"),
            ),
        )
        assert config.efeatures_by_protocol.auto_targets_presets == (
            "firing_pattern",
            "iv",
            "validation",
        )


class TestSerialization:
    def test_model_dump_json_round_trip(self, scan_config):
        json_str = scan_config.model_dump_json()
        restored = EModelEFeatureExtractionScanConfig.model_validate_json(json_str)
        assert restored.campaign_name == scan_config.campaign_name
        assert len(restored.initialize.electrical_cell_recording) == 2
        assert restored.settings.threshold == scan_config.settings.threshold

    def test_model_dump_contains_type(self, scan_config):
        dump = scan_config.model_dump()
        assert dump["type"] == "EModelEFeatureExtractionScanConfig"

    def test_autoselect_serializes(self, recording_ids):
        config = EModelEFeatureExtractionScanConfig(
            info=EModelEFeatureExtractionScanConfig.model_fields["info"].annotation(
                campaign_name="T",
                campaign_description="T",
            ),
            initialize=ExtractionInitialize(
                electrical_cell_recording=(
                    ElectricalCellRecordingFromID(id_str=recording_ids[0]),
                ),
            ),
            efeatures_by_protocol=ProtocolAndFeatureSelection(autoselect=True),
        )
        dump = config.model_dump()
        assert dump["efeatures_by_protocol"]["autoselect"] is True


class TestCreateCampaignEntity:
    def test_no_db_client_returns_none(self, scan_config):
        result = scan_config.create_campaign_entity_with_config(
            output_root="/tmp/test",
            db_client=None,
        )
        assert result is None

    def test_registers_entity_and_uploads_config(self, scan_config):
        mock_client = MagicMock()
        mock_entity = MagicMock()
        mock_entity.id = uuid4()
        mock_client.register_entity.return_value = mock_entity

        scan_config.create_campaign_entity_with_config(
            output_root="/tmp/test",
            db_client=mock_client,
        )

        # Should register a TaskConfig entity
        mock_client.register_entity.assert_called_once()
        call_args = mock_client.register_entity.call_args[0][0]
        assert call_args.name == "Test Campaign"
        assert call_args.description == "Test extraction campaign"

        # Should upload the scan config JSON
        mock_client.upload_content.assert_called_once()


class TestCreateSingleEntityWithConfig:
    def test_no_db_client_returns_none(self, scan_config):
        dump = scan_config.model_dump()
        dump["type"] = "EModelEFeatureExtractionSingleConfig"
        single = EModelEFeatureExtractionSingleConfig.model_validate(dump)
        result = single.create_single_entity_with_config(
            campaign=MagicMock(),
            db_client=None,
        )
        assert result is None

    def test_registers_and_uploads(self, scan_config):
        dump = scan_config.model_dump()
        dump["type"] = "EModelEFeatureExtractionSingleConfig"
        single = EModelEFeatureExtractionSingleConfig.model_validate(dump)

        mock_client = MagicMock()
        mock_entity = MagicMock()
        mock_entity.id = uuid4()
        mock_client.register_entity.return_value = mock_entity

        mock_campaign = MagicMock()
        mock_campaign.id = uuid4()

        single.create_single_entity_with_config(
            campaign=mock_campaign,
            db_client=mock_client,
        )

        mock_client.register_entity.assert_called_once()
        mock_client.upload_content.assert_called_once()
