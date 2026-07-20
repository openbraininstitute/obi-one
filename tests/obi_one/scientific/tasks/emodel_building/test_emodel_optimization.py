"""Tests for the emodel optimization workflow (stages 02 + 03)."""

# ruff: noqa: PLC0415, RUF069, E501, PT012

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from entitysdk.models import TaskConfig
from entitysdk.types import TaskActivityType, TaskConfigType

try:
    import bluepyemodel  # noqa: F401

    _has_bluepyemodel = True
except ImportError:
    _has_bluepyemodel = False

from obi_one.core.exception import OBIONEError
from obi_one.scientific.from_id.brain_region_from_id import BrainRegionFromID
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.etype_class_from_id import ETypeClassFromID
from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.from_id.species_from_id import SpeciesFromID
from obi_one.scientific.from_id.task_config_from_id import TaskConfigFromID
from obi_one.scientific.from_id.task_result_from_id import TaskResultFromID
from obi_one.scientific.tasks.emodel_building._shared import determine_core_count
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks.settings import (
    Settings as ExtractionSettings,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
    _build_extraction_recipes,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.blocks import (
    MorphologySelection,
    OptimizationInitialize,
    ParametersSelection,
    ParamsFileSelection,
    validate_params_file,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.config import (
    EModelOptimizationScanConfig,
    EModelOptimizationSingleConfig,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.task import (
    EModelOptimizationTask,
)
from obi_one.scientific.tasks.emodel_building.task3_export_and_validation.blocks import (
    ExportAndValidationInitialize,
)
from obi_one.scientific.tasks.emodel_building.task3_export_and_validation.config import (
    EModelExportAndValidationScanConfig,
    EModelExportAndValidationSingleConfig,
)
from obi_one.scientific.tasks.emodel_building.task3_export_and_validation.task import (
    EModelExportAndValidationTask,
)

# ─── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def morph_id():
    return "492bdec5-2dce-4ae0-8b85-f020a1ad1d92"


@pytest.fixture
def extraction_tr_id():
    return "812a8721-1681-49a2-a155-59ab30981079"


@pytest.fixture
def opt_scan_config(morph_id, extraction_tr_id):
    return EModelOptimizationScanConfig(
        info=EModelOptimizationScanConfig.model_fields["info"].annotation(
            campaign_name="Test Opt Campaign",
            campaign_description="Test optimization campaign",
        ),
        initialize=OptimizationInitialize(
            extraction_task_result=TaskResultFromID(id_str=extraction_tr_id),
            emodel="TestEModel",
            species=SpeciesFromID(id_str="11111111-2222-3333-4444-555566667777"),
            brain_region=BrainRegionFromID(id_str="22222222-3333-4444-5555-666677778888"),
            etype=ETypeClassFromID(id_str="33333333-4444-5555-6666-777788889999"),
        ),
        morphology_selection=MorphologySelection(
            morphology=CellMorphologyFromID(id_str=morph_id),
        ),
        parameters_selection=ParametersSelection(
            ion_channel_models=(
                IonChannelModelFromID(id_str="55555555-6666-7777-8888-999900001111"),
            ),
        ),
    )


@pytest.fixture
def export_val_scan_config(extraction_tr_id):
    return EModelExportAndValidationScanConfig(
        info=EModelExportAndValidationScanConfig.model_fields["info"].annotation(
            campaign_name="Test Export+Val Campaign",
            campaign_description="Test export and validation campaign",
        ),
        initialize=ExportAndValidationInitialize(
            optimization_task_result=TaskResultFromID(id_str=extraction_tr_id),
            memodel=MEModelFromID(id_str="aaa11111-2222-3333-4444-555566667777"),
        ),
    )


# ─── Step 3: Config defaults, JSON-schema metadata, UI group ordering, UI_ENABLED ─


class TestOptimizationConfigClassVars:
    def test_name(self):
        assert EModelOptimizationScanConfig.name == "EModel Optimization"

    def test_single_coord_class_name(self):
        assert (
            EModelOptimizationScanConfig.single_coord_class_name == "EModelOptimizationSingleConfig"
        )

    def test_ui_enabled(self):
        assert EModelOptimizationScanConfig.json_schema_extra_additions.get("ui_enabled") is True

    def test_group_order(self):
        groups = EModelOptimizationScanConfig.json_schema_extra_additions.get("group_order")
        assert groups == ["Setup", "Input", "Morphology", "Parameters", "Optimization Settings"]

    def test_campaign_task_config_type(self):
        assert (
            EModelOptimizationScanConfig._campaign_task_config_type
            == TaskConfigType.emodel_optimization__campaign
        )

    def test_campaign_generation_task_activity_type(self):
        assert (
            EModelOptimizationScanConfig._campaign_generation_task_activity_type
            == TaskActivityType.emodel_optimization__config_generation
        )


class TestExportAndValidationConfigClassVars:
    def test_name(self):
        assert EModelExportAndValidationScanConfig.name == "EModel Export and Validation"

    def test_single_coord_class_name(self):
        assert (
            EModelExportAndValidationScanConfig.single_coord_class_name
            == "EModelExportAndValidationSingleConfig"
        )

    def test_ui_enabled(self):
        assert (
            EModelExportAndValidationScanConfig.json_schema_extra_additions.get("ui_enabled")
            is True
        )

    def test_group_order(self):
        groups = EModelExportAndValidationScanConfig.json_schema_extra_additions.get("group_order")
        assert groups == ["Setup"]

    def test_campaign_task_config_type(self):
        assert (
            EModelExportAndValidationScanConfig._campaign_task_config_type
            == TaskConfigType.optimized_emodel_analysis_validation__campaign
        )


class TestOptimizationDefaults:
    def test_default_optimiser(self, opt_scan_config):
        assert opt_scan_config.optimization_settings.optimiser == "MO-CMA"

    def test_default_max_ngen(self, opt_scan_config):
        assert opt_scan_config.optimization_settings.max_ngen == 100

    def test_default_offspring_size(self, opt_scan_config):
        assert opt_scan_config.optimization_params.offspring_size == 20

    def test_default_validation_threshold(self, opt_scan_config):
        assert opt_scan_config.optimization_settings.validation_threshold == 5.0

    def test_default_seed(self, opt_scan_config):
        assert opt_scan_config.optimization_settings.seed == 1


class TestSerialization:
    def test_opt_round_trip(self, opt_scan_config):
        json_str = opt_scan_config.model_dump_json()
        restored = EModelOptimizationScanConfig.model_validate_json(json_str)
        assert restored.initialize.emodel == "TestEModel"
        assert restored.initialize.etype.id_str == "33333333-4444-5555-6666-777788889999"

    def test_opt_dump_contains_type(self, opt_scan_config):
        dump = opt_scan_config.model_dump()
        assert dump["type"] == "EModelOptimizationScanConfig"

    def test_export_val_round_trip(self, export_val_scan_config):
        json_str = export_val_scan_config.model_dump_json()
        restored = EModelExportAndValidationScanConfig.model_validate_json(json_str)
        assert restored.initialize.memodel.id_str == "aaa11111-2222-3333-4444-555566667777"

    def test_export_val_dump_contains_type(self, export_val_scan_config):
        dump = export_val_scan_config.model_dump()
        assert dump["type"] == "EModelExportAndValidationScanConfig"


# ─── Step 4: Optimisation settings to_dict() ───────────────────────────────


class TestOptimizationSettingsToDict:
    def test_includes_optimiser(self, opt_scan_config):
        d = opt_scan_config.optimization_settings.to_dict(opt_scan_config.optimization_params)
        assert d["optimiser"] == "MO-CMA"

    def test_includes_max_ngen(self, opt_scan_config):
        d = opt_scan_config.optimization_settings.to_dict(opt_scan_config.optimization_params)
        assert d["max_ngen"] == 100

    def test_includes_validation_threshold(self, opt_scan_config):
        d = opt_scan_config.optimization_settings.to_dict(opt_scan_config.optimization_params)
        assert d["validation_threshold"] == 5.0

    def test_includes_plot_currentscape(self, opt_scan_config):
        d = opt_scan_config.optimization_settings.to_dict(opt_scan_config.optimization_params)
        assert d["plot_currentscape"] is True

    def test_includes_optimisation_params(self, opt_scan_config):
        d = opt_scan_config.optimization_settings.to_dict(opt_scan_config.optimization_params)
        assert d["optimisation_params"]["offspring_size"] == 20

    def test_omits_currentscape_config(self, opt_scan_config):
        d = opt_scan_config.optimization_settings.to_dict(opt_scan_config.optimization_params)
        assert "currentscape_config" not in d

    def test_omits_validation_protocols(self, opt_scan_config):
        d = opt_scan_config.optimization_settings.to_dict(opt_scan_config.optimization_params)
        assert "validation_protocols" not in d

    def test_omits_export_hoc(self, opt_scan_config):
        d = opt_scan_config.optimization_settings.to_dict(opt_scan_config.optimization_params)
        assert "export_hoc" not in d

    def test_omits_seeds(self, opt_scan_config):
        d = opt_scan_config.optimization_settings.to_dict(opt_scan_config.optimization_params)
        assert "seeds" not in d


# ─── Step 5: Merged task calls correct pipeline methods (no validation) ────


@pytest.mark.skipif(not _has_bluepyemodel, reason="bluepyemodel not installed")
class TestOptimizationTaskPipelineCalls:
    def test_optimise_called(self, opt_scan_config):
        """Verify that execute() calls setup_and_run_optimisation() but NOT validate()."""
        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)
        task = EModelOptimizationTask(config=single)

        mock_ap = MagicMock()
        mock_ap.pipeline_settings = MagicMock()

        with (
            patch("bluepyemodel.access_point.local.LocalAccessPoint", return_value=mock_ap),
            patch("bluepyemodel.optimisation.setup_and_run_optimisation") as mock_optimise,
            patch("bluepyemodel.optimisation.store_best_model") as mock_store,
            patch("bluepyemodel.emodel_pipeline.plotting.plot_models") as mock_plot,
            patch("bluepyemodel.export_emodel.export_emodel.export_emodels_hoc"),
            patch("bluepyemodel.export_emodel.export_emodel.export_emodels_sonata"),
            patch("bluepyemodel.validation.validation.validate") as mock_validate,
            patch.object(
                task,
                "_download_extraction_features",
                return_value=Path("/tmp/features.json"),  # noqa: S108
            ),
            patch.object(task, "_stage_morphology", return_value="morph.swc"),
            patch.object(task, "_stage_mechanisms"),
            patch.object(task, "_stage_params", return_value=Path("config/params/params.json")),
            patch.object(task, "_stage_traces"),
            patch.object(task, "_derive_mtype", return_value="L5PC"),
            patch("obi_one.scientific.tasks.emodel_building._shared.compile_mechanisms"),
            patch("obi_one.scientific.tasks.emodel_building._shared.chdir"),
            patch("obi_one.scientific.tasks.emodel_building._shared.write_recipes"),
            patch(
                "obi_one.scientific.tasks.emodel_building._shared.update_pipeline_settings",
                return_value={},
            ),
        ):
            single.initialize.species._entity = MagicMock(id="species-1", name="rat")
            single.initialize.brain_region._entity = MagicMock(id="br-1", name="SSCX")
            single.initialize.etype._entity = MagicMock(id="etype-1", pref_label="cADpyr")
            task.execute(db_client=None)

        mock_optimise.assert_called_once()
        mock_store.assert_called_once()
        mock_plot.assert_called_once()
        mock_validate.assert_not_called()

    def test_export_hoc_called_when_enabled(self, opt_scan_config):
        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)
        task = EModelOptimizationTask(config=single)

        mock_ap = MagicMock()
        mock_ap.pipeline_settings = MagicMock()

        with (
            patch("bluepyemodel.access_point.local.LocalAccessPoint", return_value=mock_ap),
            patch("bluepyemodel.optimisation.setup_and_run_optimisation"),
            patch("bluepyemodel.optimisation.store_best_model"),
            patch("bluepyemodel.emodel_pipeline.plotting.plot_models"),
            patch("bluepyemodel.export_emodel.export_emodel.export_emodels_hoc") as mock_hoc,
            patch("bluepyemodel.export_emodel.export_emodel.export_emodels_sonata") as mock_sonata,
            patch.object(
                task,
                "_download_extraction_features",
                return_value=Path("/tmp/features.json"),  # noqa: S108
            ),
            patch.object(task, "_stage_morphology", return_value="morph.swc"),
            patch.object(task, "_stage_mechanisms"),
            patch.object(task, "_stage_params", return_value=Path("config/params/params.json")),
            patch.object(task, "_stage_traces"),
            patch.object(task, "_derive_mtype", return_value="L5PC"),
            patch("obi_one.scientific.tasks.emodel_building._shared.compile_mechanisms"),
            patch("obi_one.scientific.tasks.emodel_building._shared.chdir"),
            patch("obi_one.scientific.tasks.emodel_building._shared.write_recipes"),
            patch(
                "obi_one.scientific.tasks.emodel_building._shared.update_pipeline_settings",
                return_value={},
            ),
        ):
            single.initialize.species._entity = MagicMock(id="species-1", name="rat")
            single.initialize.brain_region._entity = MagicMock(id="br-1", name="SSCX")
            single.initialize.etype._entity = MagicMock(id="etype-1", pref_label="cADpyr")
            task.execute(db_client=None)

        mock_hoc.assert_called_once()
        mock_sonata.assert_called_once()

    def test_export_always_called(self, opt_scan_config):
        """Export is now unconditional — hoc and sonata are always called."""
        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)
        task = EModelOptimizationTask(config=single)

        mock_ap = MagicMock()
        mock_ap.pipeline_settings = MagicMock()

        with (
            patch("bluepyemodel.access_point.local.LocalAccessPoint", return_value=mock_ap),
            patch("bluepyemodel.optimisation.setup_and_run_optimisation"),
            patch("bluepyemodel.optimisation.store_best_model"),
            patch("bluepyemodel.emodel_pipeline.plotting.plot_models"),
            patch("bluepyemodel.export_emodel.export_emodel.export_emodels_hoc") as mock_hoc,
            patch("bluepyemodel.export_emodel.export_emodel.export_emodels_sonata") as mock_sonata,
            patch.object(
                task,
                "_download_extraction_features",
                return_value=Path("/tmp/features.json"),  # noqa: S108
            ),
            patch.object(task, "_stage_morphology", return_value="morph.swc"),
            patch.object(task, "_stage_mechanisms"),
            patch.object(task, "_stage_params", return_value=Path("config/params/params.json")),
            patch.object(task, "_stage_traces"),
            patch.object(task, "_derive_mtype", return_value="L5PC"),
            patch("obi_one.scientific.tasks.emodel_building._shared.compile_mechanisms"),
            patch("obi_one.scientific.tasks.emodel_building._shared.chdir"),
            patch("obi_one.scientific.tasks.emodel_building._shared.write_recipes"),
            patch(
                "obi_one.scientific.tasks.emodel_building._shared.update_pipeline_settings",
                return_value={},
            ),
        ):
            single.initialize.species._entity = MagicMock(id="species-1", name="rat")
            single.initialize.brain_region._entity = MagicMock(id="br-1", name="SSCX")
            single.initialize.etype._entity = MagicMock(id="etype-1", pref_label="cADpyr")
            task.execute(db_client=None)

        mock_hoc.assert_called_once()
        mock_sonata.assert_called_once()


# ─── Step 6: Export+validation task calls validation() + export ────────────


@pytest.mark.skipif(not _has_bluepyemodel, reason="bluepyemodel not installed")
class TestExportAndValidationTaskPipelineCalls:
    def test_validation_called(self, export_val_scan_config):
        dump = export_val_scan_config.model_dump()
        dump["type"] = "EModelExportAndValidationSingleConfig"
        single = EModelExportAndValidationSingleConfig.model_validate(dump)
        task = EModelExportAndValidationTask(config=single)

        mock_ap = MagicMock()
        mock_ap.pipeline_settings = MagicMock()

        with (
            patch.object(MEModelFromID, "entity", return_value=MagicMock()),
            patch("bluepyemodel.access_point.local.LocalAccessPoint", return_value=mock_ap),
            patch("bluepyemodel.optimisation.store_best_model") as mock_store,
            patch("bluepyemodel.validation.validation.validate") as mock_validate,
            patch("bluepyemodel.emodel_pipeline.plotting.plot_models") as mock_plot,
            patch("bluepyemodel.export_emodel.export_emodel.export_emodels_hoc"),
            patch("bluepyemodel.export_emodel.export_emodel.export_emodels_sonata"),
            patch.object(task, "_download_opt_assets"),
            patch.object(task, "_stage_morphology"),
            patch.object(task, "_stage_mechanisms"),
            patch.object(task, "_derive_mtype", return_value="L5PC"),
            patch.object(
                task,
                "_derive_metadata",
                return_value={
                    "emodel": "TestEModel",
                    "etype": "cADpyr",
                    "species": "rat",
                    "brain_region": "SSCX",
                },
            ),
            patch("obi_one.scientific.tasks.emodel_building._shared.compile_mechanisms"),
            patch("obi_one.scientific.tasks.emodel_building._shared.chdir"),
            patch("obi_one.scientific.tasks.emodel_building._shared.write_recipes"),
            patch("obi_one.scientific.tasks.emodel_building._shared.load_recipes", return_value={}),
            patch(
                "obi_one.scientific.tasks.emodel_building._shared.update_pipeline_settings",
                return_value={},
            ),
        ):
            task.execute(db_client=None)

        mock_store.assert_called_once()
        mock_validate.assert_called_once()
        mock_plot.assert_called_once()


# ─── Step 7: Params-file validation success and failure ────────────────────


class TestParamsFileValidation:
    def test_valid_params_file(self):
        params = {
            "mechanisms": [{"name": "NaV"}],
            "distributions": {"uniform": {"type": "uniform"}},
            "parameters": [
                {"name": "gbar_NaV", "val": 0.1, "dist": "uniform"},
                {"name": "gbar_KV", "val": 0.05},
            ],
        }
        validate_params_file(params)  # should not raise

    def test_missing_required_key(self):
        params = {"mechanisms": [], "distributions": {}}
        with pytest.raises(OBIONEError, match="missing required top-level keys"):
            validate_params_file(params)

    def test_missing_all_keys(self):
        with pytest.raises(OBIONEError, match="missing required top-level keys"):
            validate_params_file({})

    def test_parameter_missing_name(self):
        params = {
            "mechanisms": [],
            "distributions": {},
            "parameters": [{"val": 0.1}],
        }
        with pytest.raises(OBIONEError, match="missing required key 'name'"):
            validate_params_file(params)

    def test_parameter_missing_val(self):
        params = {
            "mechanisms": [],
            "distributions": {},
            "parameters": [{"name": "gbar_NaV"}],
        }
        with pytest.raises(OBIONEError, match="missing required key 'val'"):
            validate_params_file(params)

    def test_invalid_dist_reference(self):
        params = {
            "mechanisms": [],
            "distributions": {"uniform": {"type": "uniform"}},
            "parameters": [
                {"name": "gbar_NaV", "val": 0.1, "dist": "nonexistent"},
            ],
        }
        with pytest.raises(OBIONEError, match="references distribution 'nonexistent'"):
            validate_params_file(params)

    def test_distributions_not_dict(self):
        params = {
            "mechanisms": [],
            "distributions": [],
            "parameters": [],
        }
        with pytest.raises(OBIONEError, match="'distributions' must be a dict"):
            validate_params_file(params)

    def test_parameters_not_list(self):
        params = {
            "mechanisms": [],
            "distributions": {},
            "parameters": "not_a_list",
        }
        with pytest.raises(OBIONEError, match="'parameters' must be a list"):
            validate_params_file(params)

    def test_parameter_not_dict(self):
        params = {
            "mechanisms": [],
            "distributions": {},
            "parameters": ["not_a_dict"],
        }
        with pytest.raises(OBIONEError, match="must be a dict"):
            validate_params_file(params)

    def test_null_dist_is_ok(self):
        params = {
            "mechanisms": [],
            "distributions": {},
            "parameters": [
                {"name": "gbar_NaV", "val": 0.1, "dist": None},
            ],
        }
        validate_params_file(params)  # should not raise


# ─── Step 8: mtype derived from morphology entity ──────────────────────────


class TestMtypeDerivation:
    def test_mtype_from_morphology_entity(self, opt_scan_config):
        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)
        task = EModelOptimizationTask(config=single)

        mock_client = MagicMock()
        mock_entity = MagicMock()
        mock_mtype = MagicMock()
        mock_mtype.pref_label = "L5PC"
        mock_entity.mtypes = [mock_mtype]
        mock_morph = MagicMock()
        mock_morph.entity.return_value = mock_entity
        task.config.morphology_selection.morphology = mock_morph

        result = task._derive_mtype(mock_client)
        assert result == "L5PC"

    def test_mtype_fallback_none(self, opt_scan_config):
        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)
        task = EModelOptimizationTask(config=single)

        mock_client = MagicMock()
        mock_entity = MagicMock()
        mock_entity.mtypes = []
        mock_morph = MagicMock()
        mock_morph.entity.return_value = mock_entity
        task.config.morphology_selection.morphology = mock_morph

        result = task._derive_mtype(mock_client)
        assert result is None


# ─── Step 9: Deterministic core count ──────────────────────────────────────


class TestDetermineCoreCount:
    def test_offspring_smaller_than_max_cpus(self):
        assert determine_core_count(4, 100, max_cpus=8) == 4

    def test_offspring_larger_than_max_cpus(self):
        assert determine_core_count(20, 100, max_cpus=8) == 8

    def test_offspring_equals_max_cpus(self):
        assert determine_core_count(8, 100, max_cpus=8) == 8

    def test_minimum_one(self):
        assert determine_core_count(1, 1) == 1

    def test_default_uses_cpu_count(self):
        expected = max(1, min(4, os.cpu_count() or 1))
        assert determine_core_count(4, 100) == expected

    def test_invalid_offspring_size(self):
        with pytest.raises(ValueError, match="offspring_size must be >= 1"):
            determine_core_count(0, 100)

    def test_invalid_max_ngen(self):
        with pytest.raises(ValueError, match="max_ngen must be >= 1"):
            determine_core_count(4, 0)

    def test_deterministic(self):
        """Same inputs always produce same output."""
        assert determine_core_count(10, 50, max_cpus=16) == determine_core_count(
            10, 50, max_cpus=16
        )


# ─── ParamsFileSelection config integration ────────────────────────────────


# ─── Extraction recipe validation_protocols ─────────────────────────────────


class TestExtractionRecipeValidationProtocols:
    def test_build_extraction_recipes_includes_validation_protocols(self):
        """validation_protocols from settings are written to recipe pipeline_settings."""
        settings = ExtractionSettings(validation_protocols="sAHP_220,IDhyperpol_150")
        recipes = _build_extraction_recipes(settings)
        ps = recipes["emodel"]["pipeline_settings"]
        assert ps["validation_protocols"] == ["IDhyperpol_150", "sAHP_220"]

    def test_build_extraction_recipes_empty_validation_protocols(self):
        """Default empty validation_protocols results in empty list in recipe."""
        settings = ExtractionSettings()
        recipes = _build_extraction_recipes(settings)
        ps = recipes["emodel"]["pipeline_settings"]
        assert ps["validation_protocols"] == []

    def test_settings_field_exists_with_default(self):
        """Settings block has validation_protocols with empty string default."""
        s = ExtractionSettings()
        assert not s.validation_protocols

    def test_settings_serialization_round_trip(self):
        """validation_protocols survives JSON serialization."""
        s = ExtractionSettings(validation_protocols="sAHP_220")
        dumped = s.model_dump_json()
        restored = ExtractionSettings.model_validate_json(dumped)
        assert restored.validation_protocols == "sAHP_220"


class TestParamsFileMode:
    def test_use_params_file_false_by_default(self, opt_scan_config):
        assert opt_scan_config.use_params_file is False

    def test_use_params_file_true_when_set(self, morph_id, extraction_tr_id):
        config = EModelOptimizationScanConfig(
            info=EModelOptimizationScanConfig.model_fields["info"].annotation(
                campaign_name="T",
                campaign_description="T",
            ),
            initialize=OptimizationInitialize(
                extraction_task_result=TaskResultFromID(id_str=extraction_tr_id),
                emodel="Test",
                species=SpeciesFromID(id_str="11111111-2222-3333-4444-555566667777"),
                brain_region=BrainRegionFromID(id_str="22222222-3333-4444-5555-666677778888"),
                etype=ETypeClassFromID(id_str="33333333-4444-5555-6666-777788889999"),
            ),
            morphology_selection=MorphologySelection(
                morphology=CellMorphologyFromID(id_str=morph_id),
            ),
            params_file=ParamsFileSelection(
                params_template=TaskConfigFromID(id_str="44444444-5555-6666-7777-888899990000")
            ),
        )
        assert config.use_params_file is True

    def test_params_file_empty_by_default(self, opt_scan_config):
        assert opt_scan_config.params_file.params_template is None

    def test_rejects_config_with_no_params_source(self, morph_id, extraction_tr_id):
        with pytest.raises(ValueError, match="Either ion_channel_models or params_template"):
            EModelOptimizationScanConfig(
                info=EModelOptimizationScanConfig.model_fields["info"].annotation(
                    campaign_name="T",
                    campaign_description="T",
                ),
                initialize=OptimizationInitialize(
                    extraction_task_result=TaskResultFromID(id_str=extraction_tr_id),
                    emodel="Test",
                    species=SpeciesFromID(id_str="11111111-2222-3333-4444-555566667777"),
                    brain_region=BrainRegionFromID(id_str="22222222-3333-4444-5555-666677778888"),
                    etype=ETypeClassFromID(id_str="33333333-4444-5555-6666-777788889999"),
                ),
                morphology_selection=MorphologySelection(
                    morphology=CellMorphologyFromID(id_str=morph_id),
                ),
            )


# ─── Phase 2: _shared.py tests ─────────────────────────────────────────────


class TestSharedChdir:
    def test_chdir_changes_and_restores(self, tmp_path):

        from obi_one.scientific.tasks.emodel_building._shared import chdir

        original = Path.cwd()
        with chdir(tmp_path):
            assert Path.cwd() == tmp_path
        assert Path.cwd() == original

    def test_chdir_restores_on_exception(self, tmp_path):
        from obi_one.scientific.tasks.emodel_building._shared import chdir

        original = Path.cwd()
        with pytest.raises(RuntimeError), chdir(tmp_path):
            msg = "boom"
            raise RuntimeError(msg)
        assert Path.cwd() == original


class TestSharedCopyTree:
    def test_copy_file(self, tmp_path):
        from obi_one.scientific.tasks.emodel_building._shared import copy_tree

        src = tmp_path / "src.txt"
        src.write_text("hello")
        dst = tmp_path / "sub" / "dst.txt"
        copy_tree(src, dst)
        assert dst.read_text() == "hello"

    def test_copy_dir(self, tmp_path):
        from obi_one.scientific.tasks.emodel_building._shared import copy_tree

        src_dir = tmp_path / "srcdir"
        src_dir.mkdir()
        (src_dir / "a.txt").write_text("a")
        dst_dir = tmp_path / "dstdir"
        copy_tree(src_dir, dst_dir)
        assert (dst_dir / "a.txt").read_text() == "a"


class TestSharedSeedWorkingDir:
    def test_seeds_known_subpaths(self, tmp_path):
        from obi_one.scientific.tasks.emodel_building._shared import (
            seed_working_dir_from_previous,
        )

        prev = tmp_path / "prev"
        prev.mkdir()
        (prev / "config").mkdir()
        (prev / "config" / "recipes.json").write_text("{}")
        (prev / "final.json").write_text("[]")

        coord = tmp_path / "coord"
        seed_working_dir_from_previous(prev, coord)
        assert (coord / "config" / "recipes.json").exists()
        assert (coord / "final.json").exists()

    def test_raises_on_missing_previous(self, tmp_path):
        from obi_one.scientific.tasks.emodel_building._shared import (
            seed_working_dir_from_previous,
        )

        with pytest.raises(FileNotFoundError, match="previous_stage_output_path"):
            seed_working_dir_from_previous(tmp_path / "nonexistent", tmp_path / "coord")

    def test_skips_nonexistent_subpaths(self, tmp_path):
        from obi_one.scientific.tasks.emodel_building._shared import (
            seed_working_dir_from_previous,
        )

        prev = tmp_path / "prev"
        prev.mkdir()
        coord = tmp_path / "coord"
        coord.mkdir()
        seed_working_dir_from_previous(prev, coord)
        assert not any(coord.iterdir())


class TestSharedLoadWriteRecipes:
    def test_write_and_load_round_trip(self, tmp_path):
        from obi_one.scientific.tasks.emodel_building._shared import (
            load_recipes,
            write_recipes,
        )

        recipes = {"emodel": {"pipeline_settings": {"seed": 1}}}
        path = tmp_path / "config" / "recipes.json"
        write_recipes(recipes, path)
        assert path.exists()
        loaded = load_recipes(path)
        assert loaded == recipes

    def test_write_creates_parent_dirs(self, tmp_path):
        from obi_one.scientific.tasks.emodel_building._shared import write_recipes

        path = tmp_path / "a" / "b" / "c" / "recipes.json"
        write_recipes({}, path)
        assert path.exists()


class TestSharedUpdatePipelineSettings:
    def test_merges_overrides(self):
        from obi_one.scientific.tasks.emodel_building._shared import (
            update_pipeline_settings,
        )

        recipes = {"emodel": {"pipeline_settings": {"existing": True}}}
        result = update_pipeline_settings(recipes, "emodel", {"new": 42})
        assert result["emodel"]["pipeline_settings"]["existing"] is True
        assert result["emodel"]["pipeline_settings"]["new"] == 42

    def test_skips_none_values(self):
        from obi_one.scientific.tasks.emodel_building._shared import (
            update_pipeline_settings,
        )

        recipes = {"emodel": {"pipeline_settings": {}}}
        result = update_pipeline_settings(recipes, "emodel", {"skip": None, "keep": 1})
        assert "skip" not in result["emodel"]["pipeline_settings"]
        assert result["emodel"]["pipeline_settings"]["keep"] == 1

    def test_creates_pipeline_settings_if_missing(self):
        from obi_one.scientific.tasks.emodel_building._shared import (
            update_pipeline_settings,
        )

        recipes = {"emodel": {}}
        result = update_pipeline_settings(recipes, "emodel", {"seed": 1})
        assert result["emodel"]["pipeline_settings"]["seed"] == 1

    def test_raises_on_missing_emodel(self):
        from obi_one.scientific.tasks.emodel_building._shared import (
            update_pipeline_settings,
        )

        with pytest.raises(KeyError, match="not in recipes"):
            update_pipeline_settings({}, "missing", {})


class TestSharedCompileMechanisms:
    def test_raises_on_missing_dir(self, tmp_path):
        from obi_one.scientific.tasks.emodel_building._shared import (
            compile_mechanisms,
        )

        with pytest.raises(FileNotFoundError, match="not a directory"):
            compile_mechanisms(tmp_path / "nonexistent")

    def test_skips_if_already_compiled_x86_64(self, tmp_path):
        from obi_one.scientific.tasks.emodel_building._shared import (
            compile_mechanisms,
        )

        mech_dir = tmp_path / "mechanisms"
        mech_dir.mkdir()
        arch_dir = tmp_path / "x86_64"
        arch_dir.mkdir()
        (arch_dir / "special").write_text("")
        compile_mechanisms(mech_dir)

    def test_skips_if_already_compiled_arm64(self, tmp_path):
        from obi_one.scientific.tasks.emodel_building._shared import (
            compile_mechanisms,
        )

        mech_dir = tmp_path / "mechanisms"
        mech_dir.mkdir()
        arch_dir = tmp_path / "arm64"
        arch_dir.mkdir()
        (arch_dir / "special").write_text("")
        compile_mechanisms(mech_dir)


class TestSharedResolveNrnivmodl:
    def test_fallback_path(self, tmp_path, monkeypatch):
        from obi_one.scientific.tasks.emodel_building._shared import (
            _resolve_nrnivmodl,
        )

        monkeypatch.setattr("shutil.which", lambda _: None)
        monkeypatch.setattr("sys.prefix", str(tmp_path))
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "nrnivmodl").write_text("#!/bin/sh")
        result = _resolve_nrnivmodl()
        assert result.endswith("nrnivmodl")

    def test_raises_when_not_found(self, monkeypatch):
        from obi_one.scientific.tasks.emodel_building._shared import (
            _resolve_nrnivmodl,
        )

        monkeypatch.setattr("shutil.which", lambda _: None)
        monkeypatch.setattr("sys.prefix", "/nonexistent_prefix_12345")
        with pytest.raises(FileNotFoundError, match="Could not locate nrnivmodl"):
            _resolve_nrnivmodl()


# ─── Phase 3: Task2 helper tests ───────────────────────────────────────────


class TestTask2DownloadExtractionFeatures:
    def test_download_and_rename(self, opt_scan_config, tmp_path):
        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)
        task = EModelOptimizationTask(config=single)

        mock_tr = MagicMock()
        mock_path = tmp_path / "features" / "old.json"
        mock_path.parent.mkdir(parents=True)
        mock_path.write_text("{}")
        mock_tr.download_asset_by_label.return_value = mock_path

        result = task._download_extraction_features(mock_tr, tmp_path, MagicMock())
        assert result.name == "TestEModel.json"
        assert result.parent.name == "features"

    def test_download_no_rename_needed(self, opt_scan_config, tmp_path):
        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)
        task = EModelOptimizationTask(config=single)

        mock_tr = MagicMock()
        target = tmp_path / "config" / "features" / "TestEModel.json"
        target.parent.mkdir(parents=True)
        target.write_text("{}")
        mock_tr.download_asset_by_label.return_value = target

        result = task._download_extraction_features(mock_tr, tmp_path, MagicMock())
        assert result == target


class TestTask2StageMorphology:
    def test_writes_swc_file(self, opt_scan_config, tmp_path):
        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)
        task = EModelOptimizationTask(config=single)

        mock_morph = MagicMock()
        mock_morph.swc_file_content.return_value = "fake SWC content"
        mock_morph.id_str = "abc123"
        task.config.morphology_selection.morphology = mock_morph

        filename = task._stage_morphology(tmp_path, MagicMock())
        assert filename == "abc123.swc"
        assert (tmp_path / "morphologies" / "abc123.swc").read_text() == "fake SWC content"


class TestTask2StageMechanisms:
    def test_stages_mod_files(self, opt_scan_config, tmp_path):
        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)
        task = EModelOptimizationTask(config=single)

        mock_icm = MagicMock()
        task.config.parameters_selection.ion_channel_models = (mock_icm,)

        task._stage_mechanisms(tmp_path, MagicMock())
        mock_icm.download_asset.assert_called_once()
        call_kwargs = mock_icm.download_asset.call_args
        assert call_kwargs.kwargs["dest_dir"] == tmp_path / "mechanisms"


class TestTask2StageParams:
    def test_params_template_mode_downloads_asset(self, opt_scan_config, tmp_path):
        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)
        task = EModelOptimizationTask(config=single)

        params_data = {
            "mechanisms": [],
            "distributions": {},
            "parameters": [],
        }
        # Set up params_template mode
        single.params_file.params_template = TaskConfigFromID(
            id_str="44444444-5555-6666-7777-888899990000"
        )

        # Mock the download_asset_by_label to write a params.json file
        def mock_download(_asset_label, dest_dir, _db_client):
            params_path = dest_dir / "params.json"
            params_path.write_text(json.dumps(params_data, indent=4), encoding="utf-8")
            return params_path

        with patch.object(TaskConfigFromID, "download_asset_by_label", side_effect=mock_download):
            result_path = task._stage_params(tmp_path, MagicMock())
        assert result_path.name == "params.json"
        written = json.loads(result_path.read_text())
        assert written == params_data

    def test_dynamic_mode_writes_placeholder(self, opt_scan_config, tmp_path):
        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)
        task = EModelOptimizationTask(config=single)

        result_path = task._stage_params(tmp_path, MagicMock())
        assert result_path.name == "params.json"
        written = json.loads(result_path.read_text())
        assert written == {"mechanisms": [], "distributions": {}, "parameters": []}


class TestTask2RegisterOutputEntities:
    def test_register_calls_helpers(self, opt_scan_config, tmp_path):
        """Verify register_output_entities calls the entitysdk registration helpers."""
        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)
        task = EModelOptimizationTask(config=single)

        mock_client = MagicMock()
        mock_search_result = MagicMock()
        mock_search_result.one.return_value = MagicMock(id="license-1")
        mock_client.search_entity.return_value = mock_search_result

        with (
            patch.object(TaskResultFromID, "entity", return_value=MagicMock(id="tr-1")),
            patch.object(
                CellMorphologyFromID,
                "entity",
                return_value=MagicMock(id="morph-1", species=None, brain_region=None, mtypes=[]),
            ),
            patch.object(
                SpeciesFromID,
                "entity",
                return_value=MagicMock(id="species-1", name="rat"),
            ),
            patch.object(
                BrainRegionFromID,
                "entity",
                return_value=MagicMock(id="br-1", name="SSCX"),
            ),
            patch.object(
                ETypeClassFromID,
                "entity",
                return_value=MagicMock(id="etype-1", pref_label="cADpyr"),
            ),
            patch(
                "entitysdk.registration.task_result.emodel_optimization.register_emodel_optimization_result",
                return_value=MagicMock(id="tr-val"),
            ) as mock_reg_tr,
            patch(
                "entitysdk.registration.emodel.register_emodel",
                return_value=MagicMock(id="em-1"),
            ) as mock_reg_em,
            patch(
                "entitysdk.registration.memodel.register_memodel",
                return_value=MagicMock(id="me-1"),
            ) as mock_reg_me,
        ):
            task.register_output_entities(tmp_path, mock_client)

        mock_reg_tr.assert_called_once()
        mock_reg_em.assert_called_once()
        mock_reg_me.assert_called_once()
        # Verify registered entity IDs are stored on the task instance
        assert task._registered_task_result_id == "tr-val"
        assert task._registered_emodel_id == "em-1"
        assert task._registered_memodel_id == "me-1"
        # authorized_public defaults to False when no execution_activity_id
        assert mock_reg_tr.call_args.kwargs["authorized_public"] is False
        assert mock_reg_em.call_args.kwargs["authorized_public"] is False

    def test_register_with_execution_activity_id(self, opt_scan_config, tmp_path):
        """Verify TaskActivity is updated when execution_activity_id is provided."""
        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)
        task = EModelOptimizationTask(config=single)

        mock_client = MagicMock()
        mock_search_result = MagicMock()
        mock_search_result.one.return_value = MagicMock(id="license-1")
        mock_client.search_entity.return_value = mock_search_result
        mock_client.get_entity.return_value = MagicMock(authorized_public=True)

        with (
            patch.object(TaskResultFromID, "entity", return_value=MagicMock(id="tr-1")),
            patch.object(
                CellMorphologyFromID,
                "entity",
                return_value=MagicMock(id="morph-1", species=None, brain_region=None, mtypes=[]),
            ),
            patch.object(
                SpeciesFromID,
                "entity",
                return_value=MagicMock(id="species-1", name="rat"),
            ),
            patch.object(
                BrainRegionFromID,
                "entity",
                return_value=MagicMock(id="br-1", name="SSCX"),
            ),
            patch.object(
                ETypeClassFromID,
                "entity",
                return_value=MagicMock(id="etype-1", pref_label="cADpyr"),
            ),
            patch(
                "entitysdk.registration.task_result.emodel_optimization.register_emodel_optimization_result",
                return_value=MagicMock(id="tr-val"),
            ) as mock_reg_tr,
            patch(
                "entitysdk.registration.emodel.register_emodel",
                return_value=MagicMock(id="em-1"),
            ) as mock_reg_em,
            patch(
                "entitysdk.registration.memodel.register_memodel",
                return_value=MagicMock(id="me-1"),
            ),
        ):
            task.register_output_entities(tmp_path, mock_client, execution_activity_id="act-1")

        mock_client.update_entity.assert_called_once()
        # Verify registered entity IDs are stored on the task instance
        assert task._registered_task_result_id == "tr-val"
        assert task._registered_emodel_id == "em-1"
        assert task._registered_memodel_id == "me-1"
        # authorized_public is propagated from the execution activity
        assert mock_reg_tr.call_args.kwargs["authorized_public"] is True
        assert mock_reg_em.call_args.kwargs["authorized_public"] is True


class TestTask2UploadOptimizationAssets:
    def test_uploads_all_assets_when_files_exist(self, tmp_path):
        """Verify recipes, params, HOC, and SONATA are uploaded to TaskResult."""
        # Create dummy files
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "recipes.json").write_text('{"emodel": {}}')

        params_dir = config_dir / "params"
        params_dir.mkdir()
        (params_dir / "params.json").write_text('{"parameters": {}}')

        hoc_dir = tmp_path / "export_emodels_hoc"
        hoc_dir.mkdir()
        (hoc_dir / "model.hoc").write_text("// hoc")

        sonata_dir = tmp_path / "export_emodels_sonata"
        sonata_dir.mkdir()
        (sonata_dir / "model.json").write_text("{}")
        (sonata_dir / "nodes.h5").write_text("")

        mock_client = MagicMock()
        EModelOptimizationTask._upload_optimization_assets(tmp_path, mock_client, "tr-1")

        # recipes + params + hoc = 3 file uploads
        assert mock_client.upload_file.call_count == 3
        # sonata = 1 directory upload
        assert mock_client.upload_directory.call_count == 1

    def test_skips_uploads_when_files_missing(self, tmp_path):
        """Verify no uploads when output files don't exist."""
        mock_client = MagicMock()
        EModelOptimizationTask._upload_optimization_assets(tmp_path, mock_client, "tr-1")

        mock_client.upload_file.assert_not_called()
        mock_client.upload_directory.assert_not_called()


class TestTask2ParseFinalJson:
    def test_parses_score_and_currents(self, tmp_path):
        # final.json structure: {emodel_name: [{fitness, holding_current, ...}]}
        final_data = {
            "TestEModel": [
                {
                    "fitness": 4.0,
                    "holding_current": -0.1,
                    "threshold_current": 0.3,
                    "iteration": "3",
                },
            ],
        }
        final_path = tmp_path / "final.json"
        final_path.write_text(json.dumps(final_data))

        result = EModelOptimizationTask._parse_final_json(final_path, "TestEModel")
        assert result["total_score"] == 4.0
        assert result["holding_current"] == -0.1
        assert result["threshold_current"] == 0.3
        assert result["iteration"] == "3"
        assert result["name"] == "TestEModel"

    def test_defaults_when_no_matching_emodel(self, tmp_path):
        final_path = tmp_path / "final.json"
        final_path.write_text(json.dumps({"OtherEModel": [{"fitness": 1.0}]}))
        result = EModelOptimizationTask._parse_final_json(final_path, "TestEModel")
        assert result["total_score"] == 0.0
        assert result["holding_current"] is None
        assert result["threshold_current"] is None
        assert result["iteration"] == "0"

    def test_defaults_when_file_missing(self, tmp_path):
        result = EModelOptimizationTask._parse_final_json(
            tmp_path / "nonexistent.json", "TestEModel"
        )
        assert result["total_score"] == 0.0
        assert result["name"] == "TestEModel"

    def test_falls_back_to_emodel_key(self, tmp_path):
        # When the placeholder key "emodel" is used (from extraction stage)
        final_data = {"emodel": [{"fitness": 2.5, "iteration": "0"}]}
        final_path = tmp_path / "final.json"
        final_path.write_text(json.dumps(final_data))
        result = EModelOptimizationTask._parse_final_json(final_path, "TestEModel")
        assert result["total_score"] == 2.5
        assert result["iteration"] == "0"


class TestTask2StageTracesReturnIds:
    def test_returns_trace_ids(self, opt_scan_config, tmp_path):
        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)
        task = EModelOptimizationTask(config=single)

        mock_client = MagicMock()
        mock_tr = MagicMock()
        mock_tr.entity.return_value = MagicMock(id="tr-1")

        deriv1 = MagicMock()
        deriv1.used = MagicMock(id="trace-aaa")
        deriv2 = MagicMock()
        deriv2.used = MagicMock(id="trace-bbb")
        mock_client.search_entity.return_value = [deriv1, deriv2]

        with patch.object(TaskResultFromID, "entity", return_value=MagicMock(id="tr-1")):
            result = task._stage_traces(mock_tr, tmp_path, mock_client)

        assert result == ["trace-aaa", "trace-bbb"]
        assert not (tmp_path / "ephys_data").exists()

    def test_returns_empty_when_no_derivations(self, opt_scan_config, tmp_path):
        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)
        task = EModelOptimizationTask(config=single)

        mock_client = MagicMock()
        mock_tr = MagicMock()
        mock_tr.entity.return_value = MagicMock(id="tr-1")
        mock_client.search_entity.return_value = []

        with patch.object(TaskResultFromID, "entity", return_value=MagicMock(id="tr-1")):
            result = task._stage_traces(mock_tr, tmp_path, mock_client)

        assert result == []


# ─── Phase 4: Task3 helper tests ───────────────────────────────────────────


class TestTask3DownloadOptAssets:
    def test_downloads_all_asset_types(self, export_val_scan_config, tmp_path):
        dump = export_val_scan_config.model_dump()
        dump["type"] = "EModelExportAndValidationSingleConfig"
        single = EModelExportAndValidationSingleConfig.model_validate(dump)
        task = EModelExportAndValidationTask(config=single)

        mock_tr = MagicMock()
        with patch(
            "obi_one.utils.db_sdk.select_json_asset_content",
            side_effect=[{"emodel": {}}, {"final": []}],
        ):
            task._download_opt_assets(mock_tr, tmp_path, MagicMock())

        assert (tmp_path / "checkpoints").exists()
        assert (tmp_path / "config").exists()
        assert (tmp_path / "config" / "params").exists()
        assert (tmp_path / "figures").exists()
        assert (tmp_path / "export_emodels_hoc").exists()
        assert (tmp_path / "export_emodels_sonata").exists()

    def test_raises_on_required_asset_failure(self, export_val_scan_config, tmp_path):
        """Required assets (checkpoint, recipes, params) must raise on failure."""
        dump = export_val_scan_config.model_dump()
        dump["type"] = "EModelExportAndValidationSingleConfig"
        single = EModelExportAndValidationSingleConfig.model_validate(dump)
        task = EModelExportAndValidationTask(config=single)

        mock_tr = MagicMock()
        mock_tr.download_asset_by_label.side_effect = Exception("checkpoint fail")
        mock_tr.download_directory_asset_by_label.side_effect = Exception("fail")
        with (
            patch("obi_one.utils.db_sdk.select_json_asset_content", side_effect=Exception("fail")),
            pytest.raises(Exception, match="checkpoint fail"),
        ):
            task._download_opt_assets(mock_tr, tmp_path, MagicMock())

    def test_suppresses_optional_asset_failure(self, export_val_scan_config, tmp_path):
        """Optional assets (figures, HOC, SONATA) are suppressed on failure."""
        dump = export_val_scan_config.model_dump()
        dump["type"] = "EModelExportAndValidationSingleConfig"
        single = EModelExportAndValidationSingleConfig.model_validate(dump)
        task = EModelExportAndValidationTask(config=single)

        mock_tr = MagicMock()
        # Required downloads succeed
        mock_tr.download_asset_by_label.return_value = tmp_path / "dummy.pkl"
        # But directory downloads (optional) fail
        mock_tr.download_directory_asset_by_label.side_effect = Exception("optional fail")

        recipes_dict = {"emodel": {"pipeline_settings": {}}}
        with patch(
            "obi_one.utils.db_sdk.select_json_asset_content",
            side_effect=[recipes_dict, Exception("final.json fail")],
        ):
            # Should NOT raise — optional assets are suppressed
            task._download_opt_assets(mock_tr, tmp_path, MagicMock())


class TestTask3DeriveMtypeFromMemodel:
    def test_derives_mtype_success(self, export_val_scan_config):
        dump = export_val_scan_config.model_dump()
        dump["type"] = "EModelExportAndValidationSingleConfig"
        single = EModelExportAndValidationSingleConfig.model_validate(dump)
        task = EModelExportAndValidationTask(config=single)

        mock_client = MagicMock()
        mock_memodel = MagicMock()
        mock_memodel.morphology.id = "morph-123"
        mock_morph = MagicMock()
        mock_mtype = MagicMock()
        mock_mtype.pref_label = "L5PC"
        mock_morph.mtypes = [mock_mtype]
        mock_client.get_entity.return_value = mock_morph
        result = task._derive_mtype(mock_memodel, mock_client)
        assert result == "L5PC"

    def test_fallback_unknown(self, export_val_scan_config):
        dump = export_val_scan_config.model_dump()
        dump["type"] = "EModelExportAndValidationSingleConfig"
        single = EModelExportAndValidationSingleConfig.model_validate(dump)
        task = EModelExportAndValidationTask(config=single)

        mock_client = MagicMock()
        mock_memodel = MagicMock()
        mock_memodel.morphology.id = "morph-123"
        mock_morph = MagicMock()
        mock_morph.mtypes = []
        mock_client.get_entity.return_value = mock_morph
        result = task._derive_mtype(mock_memodel, mock_client)
        assert result == "unknown"


class TestTask3StageMorphologyFromMemodel:
    def test_stages_swc(self, export_val_scan_config, tmp_path):
        dump = export_val_scan_config.model_dump()
        dump["type"] = "EModelExportAndValidationSingleConfig"
        single = EModelExportAndValidationSingleConfig.model_validate(dump)
        task = EModelExportAndValidationTask(config=single)

        mock_client = MagicMock()
        mock_memodel = MagicMock()
        mock_memodel.morphology.id = "morph-456"

        with patch(
            "obi_one.scientific.from_id.cell_morphology_from_id.CellMorphologyFromID"
        ) as mock_morph_cls:
            mock_morph_instance = mock_morph_cls.return_value
            mock_morph_instance.swc_file_content.return_value = "fake SWC"
            task._stage_morphology(mock_memodel, tmp_path, mock_client)

        assert (tmp_path / "morphologies" / "morph-456.swc").exists()


class TestTask3StageMechanismsFromMemodel:
    def test_stages_mod_files(self, export_val_scan_config, tmp_path):
        dump = export_val_scan_config.model_dump()
        dump["type"] = "EModelExportAndValidationSingleConfig"
        single = EModelExportAndValidationSingleConfig.model_validate(dump)
        task = EModelExportAndValidationTask(config=single)

        mock_client = MagicMock()
        mock_memodel = MagicMock()
        mock_memodel.emodel.id = "em-789"
        mock_emodel = MagicMock()
        mock_icm1 = MagicMock(id="icm-1")
        mock_icm2 = MagicMock(id="icm-2")
        mock_emodel.ion_channel_models = [mock_icm1, mock_icm2]
        mock_client.get_entity.return_value = mock_emodel

        with patch(
            "obi_one.scientific.from_id.ion_channel_model_from_id.IonChannelModelFromID"
        ) as mock_icm_cls:
            mock_icm_instance = mock_icm_cls.return_value
            task._stage_mechanisms(mock_memodel, tmp_path, mock_client)
            assert mock_icm_instance.download_asset.call_count == 2


class TestTask3RegisterAndUpdate:
    def test_register_and_update_calls_db(self, export_val_scan_config, tmp_path):
        dump = export_val_scan_config.model_dump()
        dump["type"] = "EModelExportAndValidationSingleConfig"
        single = EModelExportAndValidationSingleConfig.model_validate(dump)
        task = EModelExportAndValidationTask(config=single)

        mock_client = MagicMock()
        mock_client.register_entity.side_effect = [
            MagicMock(id="tr-val"),  # TaskResult
            MagicMock(id="cal-1"),  # MEModelCalibrationResult
        ]

        mock_memodel = MagicMock(
            id="me-1",
            name="test",
            description="desc",
            species=None,
            brain_region=None,
            morphology=None,
            emodel=MagicMock(id="em-1"),
            iteration="0",
        )

        task._register_and_update(tmp_path, mock_client, memodel_entity=mock_memodel)
        assert mock_client.register_entity.call_count >= 1
        # MEModel update + EModel lifecycle update = at least 2 update calls
        assert mock_client.update_entity.call_count >= 2
        # Verify registered entity IDs are stored on the task instance
        assert task._registered_task_result_id == "tr-val"
        assert task._registered_emodel_id == "em-1"
        assert task._registered_memodel_id == "me-1"

    def test_register_and_update_with_execution_activity_id(self, export_val_scan_config, tmp_path):
        """Verify TaskActivity is updated when execution_activity_id is provided."""
        dump = export_val_scan_config.model_dump()
        dump["type"] = "EModelExportAndValidationSingleConfig"
        single = EModelExportAndValidationSingleConfig.model_validate(dump)
        task = EModelExportAndValidationTask(config=single)

        mock_client = MagicMock()
        mock_client.register_entity.side_effect = [
            MagicMock(id="tr-val"),  # TaskResult
            MagicMock(id="cal-1"),  # MEModelCalibrationResult
        ]

        mock_memodel = MagicMock(
            id="me-1",
            name="test",
            description="desc",
            species=None,
            brain_region=None,
            morphology=None,
            emodel=MagicMock(id="em-1"),
            iteration="0",
        )

        task._register_and_update(
            tmp_path, mock_client, memodel_entity=mock_memodel, execution_activity_id="act-1"
        )
        # At least 3 update calls: MEModel update, EModel lifecycle, TaskActivity
        assert mock_client.update_entity.call_count >= 3
        # Verify registered entity IDs are stored on the task instance
        assert task._registered_task_result_id == "tr-val"
        assert task._registered_emodel_id == "em-1"
        assert task._registered_memodel_id == "me-1"

    def test_register_and_update_with_files(self, export_val_scan_config, tmp_path):
        """Verify file uploads happen when output files exist."""
        dump = export_val_scan_config.model_dump()
        dump["type"] = "EModelExportAndValidationSingleConfig"
        single = EModelExportAndValidationSingleConfig.model_validate(dump)
        task = EModelExportAndValidationTask(config=single)

        # Create dummy output files
        figures_dir = tmp_path / "figures"
        figures_dir.mkdir(parents=True)
        (figures_dir / "plot1.pdf").write_text("")

        recipes_dir = tmp_path / "config"
        recipes_dir.mkdir(parents=True)
        (recipes_dir / "recipes.json").write_text('{"emodel": {}}')

        hoc_dir = tmp_path / "export_emodels_hoc"
        hoc_dir.mkdir(parents=True)
        (hoc_dir / "model.hoc").write_text("")

        sonata_dir = tmp_path / "export_emodels_sonata"
        sonata_dir.mkdir(parents=True)
        (sonata_dir / "model.json").write_text("{}")

        final_path = tmp_path / "final.json"
        final_path.write_text(
            json.dumps(
                {
                    "TestEModel": [
                        {"fitness": 1.5, "holding_current": -0.1, "threshold_current": 0.3}
                    ]
                },
            )
        )

        mock_client = MagicMock()
        mock_memodel = MagicMock(
            id="me-1",
            name="test",
            description="desc",
            species=None,
            brain_region=None,
            morphology=None,
            emodel=MagicMock(id="em-1"),
            iteration="0",
        )

        task._register_and_update(tmp_path, mock_client, memodel_entity=mock_memodel)

        # Verify file uploads were called
        assert mock_client.upload_file.call_count >= 3  # recipe, hoc, validation_details
        assert mock_client.upload_directory.call_count >= 2  # figures, sonata
        # Verify EModel lifecycle update
        update_calls = mock_client.update_entity.call_args_list
        assert any("lifecycle_status" in str(c) for c in update_calls)


# ─── Phase 5: Blocks/config additional tests ───────────────────────────────


class TestOptimizationParamsToDict:
    def test_to_dict_default(self):
        from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.blocks import (
            OptimizationParams,
        )

        params = OptimizationParams()
        assert params.to_dict() == {"offspring_size": 20}

    def test_to_dict_custom(self):
        from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.blocks import (
            OptimizationParams,
        )

        params = OptimizationParams(offspring_size=50)
        assert params.to_dict() == {"offspring_size": 50}


class TestExportAndValidationConfigClassVarsAdditional:
    def test_campaign_generation_task_activity_type(self):
        assert (
            EModelExportAndValidationScanConfig._campaign_generation_task_activity_type
            == TaskActivityType.optimized_emodel_analysis_validation__config_generation
        )


class TestOptimizationConfigInputEntities:
    def test_input_entities_returns_list(self, opt_scan_config):
        mock_client = MagicMock()
        mock_tr = MagicMock(id="tr-1")
        mock_morph = MagicMock(id="morph-1")
        mock_species = MagicMock(id="species-1", name="rat")
        mock_br = MagicMock(id="br-1", name="SSCX")
        mock_etype = MagicMock(id="etype-1", pref_label="cADpyr")
        mock_icm = MagicMock(id="icm-1")
        with (
            patch.object(TaskResultFromID, "entity", return_value=mock_tr),
            patch.object(CellMorphologyFromID, "entity", return_value=mock_morph),
            patch.object(SpeciesFromID, "entity", return_value=mock_species),
            patch.object(BrainRegionFromID, "entity", return_value=mock_br),
            patch.object(ETypeClassFromID, "entity", return_value=mock_etype),
            patch.object(IonChannelModelFromID, "entity", return_value=mock_icm),
        ):
            entities = opt_scan_config.input_entities(mock_client)
        assert len(entities) == 6
        assert entities[0] == mock_tr
        assert entities[1] == mock_morph
        assert entities[2] == mock_species
        assert entities[3] == mock_br
        assert entities[4] == mock_etype
        assert entities[5] == mock_icm


# ─── Phase 6: Task1 pure function tests ────────────────────────────────────


class TestEcodeClassName:
    def test_matches_idrest(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
            _ecode_class_name,
        )

        ecodes = {"IDrest": type("IDrest", (), {}), "IV": type("IV", (), {})}
        assert _ecode_class_name("IDrest_150", ecodes) == "IDrest"

    def test_matches_iv_case_insensitive(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
            _ecode_class_name,
        )

        ecodes = {"IV": type("IV", (), {})}
        assert _ecode_class_name("iv_-20", ecodes) == "IV"

    def test_no_match_returns_none(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
            _ecode_class_name,
        )

        ecodes = {"IDrest": type("IDrest", (), {})}
        assert _ecode_class_name("unknown_protocol", ecodes) is None


class TestDiscoverTiming:
    def test_returns_median_per_protocol(self, tmp_path):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
            _discover_timing,
        )

        nwb1 = tmp_path / "cell1.nwb"
        nwb2 = tmp_path / "cell2.nwb"
        nwb1.write_text("")
        nwb2.write_text("")

        with patch(
            "obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task.read_timing_from_nwb"
        ) as mock_read:
            mock_read.side_effect = [
                {"IDrest": 100.0},
                {"IDrest": 200.0},
            ]
            result = _discover_timing([nwb1, nwb2], ["IDrest"])
            assert result == {"IDrest": 150.0}

    def test_omits_protocols_with_no_data(self, tmp_path):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
            _discover_timing,
        )

        nwb1 = tmp_path / "cell1.nwb"
        nwb1.write_text("")

        with patch(
            "obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task.read_timing_from_nwb"
        ) as mock_read:
            mock_read.return_value = {}
            result = _discover_timing([nwb1], ["IDrest", "IV"])
            assert result == {}


class TestPartitionProtocols:
    def test_standard_protocol_extractable(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
            _partition_protocols,
        )

        mock_protocol = MagicMock()
        mock_protocol.name = "IDrest_150"
        mock_protocol.timing_override.return_value = {"ton": 100.0, "toff": 1100.0}

        ecodes = {"IDrest": type("IDrest", (), {})}
        result = _partition_protocols((mock_protocol,), ecodes, {})
        assert len(result[0]) == 1
        assert "IDrest_150" in result[1]
        assert result[2] == []

    def test_ramp_protocol_with_ton(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
            _partition_protocols,
        )

        mock_protocol = MagicMock()
        mock_protocol.name = "Ramp_100"
        mock_protocol.timing_override.return_value = {}

        ecodes = {"Ramp": type("Ramp", (), {})}
        result = _partition_protocols((mock_protocol,), ecodes, {"Ramp_100": 50.0})
        assert len(result[0]) == 1
        assert result[1]["Ramp_100"]["ton"] == 50.0

    def test_ramp_protocol_without_ton_skipped(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
            _partition_protocols,
        )

        mock_protocol = MagicMock()
        mock_protocol.name = "Ramp_100"
        mock_protocol.timing_override.return_value = {}

        ecodes = {"Ramp": type("Ramp", (), {})}
        result = _partition_protocols((mock_protocol,), ecodes, {})
        assert len(result[0]) == 0
        assert "Ramp_100" in result[2]

    def test_dehyperpol_skipped(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
            _partition_protocols,
        )

        mock_protocol = MagicMock()
        mock_protocol.name = "DeHyperPol_100"
        mock_protocol.timing_override.return_value = {}

        ecodes = {"DeHyperPol": type("DeHyperPol", (), {})}
        result = _partition_protocols((mock_protocol,), ecodes, {})
        assert len(result[0]) == 0
        assert "DeHyperPol_100" in result[2]


class TestBuildFilesMetadata:
    def test_builds_rows_with_ljp(self, tmp_path):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
            _build_files_metadata,
        )

        nwb = tmp_path / "cell1.nwb"
        nwb.write_text("")
        ecodes_meta = {"IDrest": {"ton": 100.0}}
        result = _build_files_metadata(
            nwb_paths_with_ljp=[(nwb, 15.0)],
            ecodes_metadata_dict=ecodes_meta,
        )
        assert len(result) == 1
        assert result[0]["cell_name"] == "cell1"
        assert result[0]["ecodes"]["IDrest"]["ljp"] == 15.0

    def test_user_ljp_overrides_recording_ljp(self, tmp_path):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
            _build_files_metadata,
        )

        nwb = tmp_path / "cell1.nwb"
        nwb.write_text("")
        ecodes_meta = {"IDrest": {"ton": 100.0, "ljp": 5.0}}
        result = _build_files_metadata(
            nwb_paths_with_ljp=[(nwb, 15.0)],
            ecodes_metadata_dict=ecodes_meta,
        )
        assert result[0]["ecodes"]["IDrest"]["ljp"] == 5.0


class TestDiscoverAmplitudes:
    def test_unions_amplitudes_across_nwbs(self, tmp_path):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
            _discover_amplitudes,
        )

        nwb1 = tmp_path / "cell1.nwb"
        nwb2 = tmp_path / "cell2.nwb"
        nwb1.write_text("")
        nwb2.write_text("")

        with patch(
            "obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task.read_amplitudes_from_nwb"
        ) as mock_read:
            mock_read.side_effect = [
                {"IDrest": [0.1, 0.2]},
                {"IDrest": [0.2, 0.3]},
            ]
            result = _discover_amplitudes([nwb1, nwb2], ["IDrest"])
            assert result == {"IDrest": [0.1, 0.2, 0.3]}

    def test_empty_when_no_amplitudes(self, tmp_path):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
            _discover_amplitudes,
        )

        nwb1 = tmp_path / "cell1.nwb"
        nwb1.write_text("")

        with patch(
            "obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task.read_amplitudes_from_nwb"
        ) as mock_read:
            mock_read.return_value = {}
            result = _discover_amplitudes([nwb1], ["IDrest"])
            assert result == {"IDrest": []}


class TestBuildTargetsFormatted:
    def test_builds_rows_for_each_amplitude_and_feature(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
            _build_targets_formatted,
        )

        mock_feature = MagicMock()
        mock_feature.efel_name = "Spikecount"
        mock_feature.efeature_name = "Spikecount"
        mock_feature.tolerance = 1e-5
        mock_feature.weight = 1.0
        mock_feature.efel_settings_override.return_value = {"Threshold": -30.0}

        mock_protocol = MagicMock()
        mock_protocol.name = "IDrest"
        mock_protocol.extraction_amplitudes = None
        mock_protocol.selected_efeatures.return_value = [mock_feature]
        mock_protocol.efel_settings_override.return_value = {"Threshold": -20.0}

        rows = _build_targets_formatted(
            [mock_protocol],
            {"IDrest": [0.1, 0.2]},
        )
        assert len(rows) == 2
        assert rows[0]["efeature"] == "Spikecount"
        assert rows[0]["amplitude"] == 0.1
        assert rows[1]["amplitude"] == 0.2

    def test_skips_ohmic_input_resistance_for_iv_zero(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
            _build_targets_formatted,
        )

        mock_feature = MagicMock()
        mock_feature.efel_name = "ohmic_input_resistance_vb_ssse"
        mock_feature.efeature_name = "ohmic_input_resistance_vb_ssse"
        mock_feature.tolerance = 1e-5
        mock_feature.weight = 1.0
        mock_feature.efel_settings_override.return_value = {}

        mock_protocol = MagicMock()
        mock_protocol.name = "IV"
        mock_protocol.extraction_amplitudes = None
        mock_protocol.selected_efeatures.return_value = [mock_feature]
        mock_protocol.efel_settings_override.return_value = {}

        rows = _build_targets_formatted(
            [mock_protocol],
            {"IV": [0, 0.1]},
        )
        assert len(rows) == 1
        assert rows[0]["amplitude"] == 0.1

    def test_threshold_based_with_extraction_amplitudes(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
            _build_targets_formatted,
        )

        mock_feature = MagicMock()
        mock_feature.efel_name = "Spikecount"
        mock_feature.efeature_name = "Spikecount"
        mock_feature.tolerance = 1e-5
        mock_feature.weight = 1.0
        mock_feature.efel_settings_override.return_value = {}

        mock_protocol = MagicMock()
        mock_protocol.name = "IDrest"
        mock_protocol.extraction_amplitudes = 50.0
        mock_protocol.selected_efeatures.return_value = [mock_feature]
        mock_protocol.efel_settings_override.return_value = {}

        rows = _build_targets_formatted(
            [mock_protocol],
            {"IDrest": [0.1]},
            threshold_based=True,
        )
        assert len(rows) == 1
        assert rows[0]["amplitude"] == 50.0

    def test_empty_amplitudes_yields_no_rows(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
            _build_targets_formatted,
        )

        mock_protocol = MagicMock()
        mock_protocol.name = "IDrest"
        mock_protocol.extraction_amplitudes = None
        mock_protocol.selected_efeatures.return_value = []
        mock_protocol.efel_settings_override.return_value = {}

        rows = _build_targets_formatted(
            [mock_protocol],
            {"IDrest": []},
        )
        assert rows == []


class TestBuildExtractionRecipesAdditional:
    def test_threshold_based_includes_rin_rmp(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features import (
            Protocol,
        )

        iv = Protocol.from_protocol_name("IV")
        iv.is_rin_protocol = True
        iv.rin_amplitude = -20.0
        iv.is_rmp_protocol = True
        iv.rmp_amplitude = 0.0

        settings = ExtractionSettings()
        recipes = _build_extraction_recipes(settings, threshold_based=True, protocols=(iv,))
        ps = recipes["emodel"]["pipeline_settings"]
        assert ps["name_Rin_protocol"] == ["IV", -20.0]
        assert ps["name_rmp_protocol"] == ["IV", None]

    def test_non_threshold_omits_rin_rmp(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features import (
            Protocol,
        )

        iv = Protocol.from_protocol_name("IV")
        iv.is_rin_protocol = True
        iv.rin_amplitude = -20.0

        settings = ExtractionSettings()
        recipes = _build_extraction_recipes(settings, threshold_based=False, protocols=(iv,))
        ps = recipes["emodel"]["pipeline_settings"]
        assert ps["name_Rin_protocol"] is None
        assert ps["name_rmp_protocol"] is None

    def test_rheobase_protocol_flag_adds_strategy(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features import (
            Protocol,
        )

        idthresh = Protocol.from_protocol_name("IDthresh")
        idthresh.is_rheobase_protocol = True

        settings = ExtractionSettings()
        recipes = _build_extraction_recipes(settings, protocols=(idthresh,))
        ps = recipes["emodel"]["pipeline_settings"]
        assert ps["rheobase_strategy_extraction"] == "absolute"
        assert "rheobase_settings_extraction" in ps

    def test_no_rheobase_flag_omits_strategy(self):
        settings = ExtractionSettings()
        recipes = _build_extraction_recipes(settings, protocols=())
        ps = recipes["emodel"]["pipeline_settings"]
        assert "rheobase_strategy_extraction" not in ps

    def test_extract_absolute_amplitudes_default(self):
        settings = ExtractionSettings()
        recipes = _build_extraction_recipes(settings)
        ps = recipes["emodel"]["pipeline_settings"]
        assert ps["extract_absolute_amplitudes"] is True

    def test_extract_absolute_amplitudes_threshold_based(self):
        settings = ExtractionSettings()
        recipes = _build_extraction_recipes(settings, threshold_based=True)
        ps = recipes["emodel"]["pipeline_settings"]
        assert ps["extract_absolute_amplitudes"] is False


# ─── Phase 7: Task1 task method tests ──────────────────────────────────────


class TestTask1DownloadRecordings:
    def test_downloads_recordings_with_ljp(self, tmp_path):
        from obi_one.scientific.from_id.electrical_cell_recording_from_id import (
            ElectricalCellRecordingFromID,
        )
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks import (
            ExtractionInitialize,
        )
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.config import (
            EModelEFeatureExtractionScanConfig,
        )
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
            EModelEFeatureExtractionTask,
        )

        config = EModelEFeatureExtractionScanConfig(
            info=EModelEFeatureExtractionScanConfig.model_fields["info"].annotation(
                campaign_name="T",
                campaign_description="T",
            ),
            initialize=ExtractionInitialize(
                electrical_cell_recording=[
                    ElectricalCellRecordingFromID(id_str="rec-1"),
                ],
            ),
        )
        dump = config.model_dump()
        dump["type"] = "EModelEFeatureExtractionSingleConfig"
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.config import (
            EModelEFeatureExtractionSingleConfig,
        )

        single_config = EModelEFeatureExtractionSingleConfig.model_validate(dump)
        task = EModelEFeatureExtractionTask(config=single_config)

        mock_client = MagicMock()
        mock_entity = MagicMock(ljp=12.5)
        mock_recording = task.config.initialize.electrical_cell_recording[0]

        with (
            patch.object(type(mock_recording), "entity", return_value=mock_entity),
            patch.object(
                type(mock_recording), "download_asset", return_value=tmp_path / "rec-1" / "rec.nwb"
            ),
        ):
            result = task._download_recordings(tmp_path / "ephys_data", mock_client)
        assert len(result) == 1
        assert result[0][1] == 12.5

    def test_raises_on_wrong_type(self, tmp_path):
        from obi_one.scientific.from_id.electrical_cell_recording_from_id import (
            ElectricalCellRecordingFromID,
        )
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks import (
            ExtractionInitialize,
        )
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.config import (
            EModelEFeatureExtractionScanConfig,
            EModelEFeatureExtractionSingleConfig,
        )
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
            EModelEFeatureExtractionTask,
        )

        config = EModelEFeatureExtractionScanConfig(
            info=EModelEFeatureExtractionScanConfig.model_fields["info"].annotation(
                campaign_name="T",
                campaign_description="T",
            ),
            initialize=ExtractionInitialize(
                electrical_cell_recording=[
                    ElectricalCellRecordingFromID(id_str="rec-1"),
                ],
            ),
        )
        dump = config.model_dump()
        dump["type"] = "EModelEFeatureExtractionSingleConfig"
        single = EModelEFeatureExtractionSingleConfig.model_validate(dump)
        task = EModelEFeatureExtractionTask(config=single)

        task.config.initialize.electrical_cell_recording = ["not_a_recording"]
        with pytest.raises(TypeError, match="Expected ElectricalCellRecordingFromID"):
            task._download_recordings(tmp_path, MagicMock())


class TestTask1BuildFiguresManifest:
    @staticmethod
    def _make_task1():
        from obi_one.scientific.from_id.electrical_cell_recording_from_id import (
            ElectricalCellRecordingFromID,
        )
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks import (
            ExtractionInitialize,
        )
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.config import (
            EModelEFeatureExtractionScanConfig,
            EModelEFeatureExtractionSingleConfig,
        )
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
            EModelEFeatureExtractionTask,
        )

        config = EModelEFeatureExtractionScanConfig(
            info=EModelEFeatureExtractionScanConfig.model_fields["info"].annotation(
                campaign_name="T",
                campaign_description="T",
            ),
            initialize=ExtractionInitialize(
                electrical_cell_recording=[
                    ElectricalCellRecordingFromID(id_str="rec-1"),
                ],
            ),
        )
        dump = config.model_dump()
        dump["type"] = "EModelEFeatureExtractionSingleConfig"
        single = EModelEFeatureExtractionSingleConfig.model_validate(dump)
        return EModelEFeatureExtractionTask(config=single)

    def test_legend_file(self, tmp_path):
        task = self._make_task1()

        fig_dir = tmp_path / "figures"
        fig_dir.mkdir()
        (fig_dir / "legend.pdf").write_text("")

        manifest = task._build_figures_manifest(fig_dir)
        assert manifest["files"][0]["type"] == "legend"

    def test_recordings_plot(self, tmp_path):
        task = self._make_task1()

        fig_dir = tmp_path / "figures"
        fig_dir.mkdir()
        (fig_dir / "cell1_IDrest_recordings.pdf").write_text("")

        manifest = task._build_figures_manifest(fig_dir)
        entry = manifest["files"][0]
        assert entry["type"] == "recordings_plot"
        assert entry["cell"] == "cell1"
        assert entry["protocol"] == "IDrest"

    def test_feature_plot(self, tmp_path):
        task = self._make_task1()

        fig_dir = tmp_path / "figures"
        fig_dir.mkdir()
        (fig_dir / "cell1_IDrest_MeanFrequency_amp.pdf").write_text("")

        manifest = task._build_figures_manifest(fig_dir)
        entry = manifest["files"][0]
        assert entry["type"] == "feature_plot"
        assert entry["cell"] == "cell1"
        assert entry["protocol"] == "IDrest"
        assert entry["feature"] == "MeanFrequency"

    def test_other_type(self, tmp_path):
        task = self._make_task1()

        fig_dir = tmp_path / "figures"
        fig_dir.mkdir()
        (fig_dir / "random_file.pdf").write_text("")

        manifest = task._build_figures_manifest(fig_dir)
        assert manifest["files"][0]["type"] == "other"


class TestTask1RegisterTaskResult:
    def test_register_task_result(self, tmp_path):
        task = TestTask1BuildFiguresManifest._make_task1()

        mock_client = MagicMock()
        mock_client.register_entity.return_value = MagicMock(id="tr-1")

        mock_recording = MagicMock()
        mock_recording.entity.return_value = MagicMock(id="rec-1")
        task.config.initialize.electrical_cell_recording = [mock_recording]

        with (
            patch("entitysdk.models.TaskResult", return_value=MagicMock(id="tr-1")),
            patch("entitysdk.models.Derivation", return_value=MagicMock()),
        ):
            task._register_task_result(tmp_path, mock_client)
        mock_client.register_entity.assert_called()
        # Verify registered entity ID is stored on the task instance
        assert task.registered_task_result_id == "tr-1"


# ─── Phase 8: Task1 blocks/protocols/efeatures tests ───────────────────────


class TestExtractionConfigClassVars:
    def test_name(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.config import (
            EModelEFeatureExtractionScanConfig,
        )

        assert EModelEFeatureExtractionScanConfig.name == "EModel EFeature Extraction"

    def test_single_coord_class_name(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.config import (
            EModelEFeatureExtractionScanConfig,
        )

        assert (
            EModelEFeatureExtractionScanConfig.single_coord_class_name
            == "EModelEFeatureExtractionSingleConfig"
        )

    def test_ui_enabled(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.config import (
            EModelEFeatureExtractionScanConfig,
        )

        assert (
            EModelEFeatureExtractionScanConfig.json_schema_extra_additions.get("ui_enabled") is True
        )

    def test_campaign_task_config_type(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.config import (
            EModelEFeatureExtractionScanConfig,
        )

        assert (
            EModelEFeatureExtractionScanConfig._campaign_task_config_type
            == TaskConfigType.efeature_extraction__campaign
        )


class TestExtractionSettingsDefaults:
    def test_default_plot_extraction(self):
        s = ExtractionSettings()
        assert s.plot_extraction is True

    def test_default_validation_protocols_empty(self):
        s = ExtractionSettings()
        assert not s.validation_protocols

    def test_default_std_value(self):
        s = ExtractionSettings()
        assert s.default_std_value == 0.01


class TestProtocolAndFeatureSelectionDefaults:
    def test_default_autoselect(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks.protocol_and_feature_selection import (
            ProtocolAndFeatureSelection,
        )

        sel = ProtocolAndFeatureSelection()
        assert sel.autoselect is False

    def test_default_threshold_based(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks.protocol_and_feature_selection import (
            ProtocolAndFeatureSelection,
        )

        sel = ProtocolAndFeatureSelection()
        assert sel.threshold_based is False


class TestEFeatureDefaults:
    def test_spikecount_defaults(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.efeatures import (
            EFeature,
        )

        f = EFeature(efel_name="Spikecount", category="Spike event")
        assert f.extract is False
        assert f.weight == 1.0
        assert f.efel_name == "Spikecount"

    def test_meanfrequency_defaults(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.efeatures import (
            EFeature,
        )

        f = EFeature(efel_name="mean_frequency", category="Spike event")
        assert f.extract is False
        assert f.efel_name == "mean_frequency"

    def test_efeature_settings_override(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.efeatures import (
            EFeature,
        )

        f = EFeature(
            efel_name="Spikecount",
            category="Spike event",
            threshold=-30.0,
            strict_stiminterval=True,
            interp_step=0.1,
        )
        override = f.efel_settings_override()
        assert override["Threshold"] == -30.0
        assert override["strict_stiminterval"] is True
        assert override["interp_step"] == 0.1


class TestProtocolDefaults:
    def test_idrest_defaults(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features import (
            Protocol,
        )

        p = Protocol.from_protocol_name("IDrest")
        assert p.ton == 0.0
        assert p.toff == 0.0
        assert p.ljp == 0.0

    def test_iv_defaults(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features import (
            Protocol,
        )

        p = Protocol.from_protocol_name("IV")
        assert p.ton == 0.0
        assert p.toff == 0.0

    def test_protocol_selected_efeatures(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features import (
            Protocol,
        )

        p = Protocol.from_protocol_name("IDrest")
        # Default protocols have features with extract=False
        selected = p.selected_efeatures()
        assert isinstance(selected, list)
        assert len(selected) == 0  # No features selected by default

    def test_protocol_timing_override_defaults(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features import (
            Protocol,
        )

        p = Protocol.from_protocol_name("IDrest")
        timing = p.timing_override()
        # All defaults are 0.0 which are omitted
        assert timing == {}

    def test_protocol_timing_override_with_values(self):
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features import (
            Protocol,
        )

        p = Protocol.from_protocol_name("IDrest", ton=100.0, toff=500.0)
        timing = p.timing_override()
        assert timing["ton"] == 100.0
        assert timing["toff"] == 500.0


# ─── Phase 9: Coverage improvements — campaign entity registration & validate_params_file ──


class TestOptCampaignEntityRegistration:
    """Tests for task2 config create_campaign_entity_with_config and create_single_entity_with_config."""

    def test_create_campaign_entity_with_config_registers_and_uploads(self, opt_scan_config):
        """Verify register_entity is called with a TaskConfig and upload_content is called."""
        mock_client = MagicMock()
        mock_campaign_entity = MagicMock(id="campaign-123")
        mock_client.register_entity.return_value = mock_campaign_entity

        with patch.object(
            EModelOptimizationScanConfig,
            "input_entities",
            return_value=[MagicMock(id="e-1")],
        ):
            opt_scan_config.create_campaign_entity_with_config(
                output_root=Path("/tmp/out"),  # noqa: S108
                db_client=mock_client,
            )

        mock_client.register_entity.assert_called_once()
        registered_arg = mock_client.register_entity.call_args[0][0]
        assert isinstance(registered_arg, TaskConfig)
        assert registered_arg.task_config_type == TaskConfigType.emodel_optimization__campaign

        mock_client.upload_content.assert_called_once()
        upload_kwargs = mock_client.upload_content.call_args[1]
        assert upload_kwargs["entity_id"] == "campaign-123"
        assert upload_kwargs["file_name"] == "scan_config.json"

    def test_create_campaign_entity_with_config_skips_when_no_client(self, opt_scan_config):
        """Verify no-op when db_client is None."""
        opt_scan_config.create_campaign_entity_with_config(
            output_root=Path("/tmp/out"),  # noqa: S108
            db_client=None,
        )
        # No exception, method returns early

    def test_create_single_entity_with_config_registers_and_uploads(self, opt_scan_config):
        """Verify single config registration and upload happen."""
        mock_client = MagicMock()
        mock_single_entity = MagicMock(id="single-456")
        mock_client.register_entity.return_value = mock_single_entity

        mock_campaign = MagicMock(id="campaign-123")

        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)

        with patch.object(
            EModelOptimizationSingleConfig,
            "input_entities",
            return_value=[MagicMock(id="e-1")],
        ):
            single.create_single_entity_with_config(
                campaign=mock_campaign,
                db_client=mock_client,
            )

        mock_client.register_entity.assert_called_once()
        registered_arg = mock_client.register_entity.call_args[0][0]
        assert isinstance(registered_arg, TaskConfig)
        assert registered_arg.task_config_type == TaskConfigType.emodel_optimization__config
        assert registered_arg.task_config_generator_id == "campaign-123"

        mock_client.upload_content.assert_called_once()
        upload_kwargs = mock_client.upload_content.call_args[1]
        assert upload_kwargs["entity_id"] == "single-456"
        assert upload_kwargs["file_name"] == "single_config.json"

    def test_create_single_entity_with_config_skips_when_no_client(self, opt_scan_config):
        """Verify no-op when db_client is None."""
        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)

        single.create_single_entity_with_config(
            campaign=MagicMock(),
            db_client=None,
        )
        # No exception, method returns early


class TestExportValCampaignEntityRegistration:
    """Tests for task3 config create_campaign_entity_with_config and create_single_entity_with_config."""

    def test_create_campaign_entity_with_config_registers_and_uploads(self, export_val_scan_config):
        """Verify register_entity is called with a TaskConfig and upload_content is called."""
        mock_client = MagicMock()
        mock_campaign_entity = MagicMock(id="campaign-789")
        mock_client.register_entity.return_value = mock_campaign_entity

        with patch.object(
            EModelExportAndValidationScanConfig,
            "input_entities",
            return_value=[MagicMock(id="e-1")],
        ):
            export_val_scan_config.create_campaign_entity_with_config(
                output_root=Path("/tmp/out"),  # noqa: S108
                db_client=mock_client,
            )

        mock_client.register_entity.assert_called_once()
        registered_arg = mock_client.register_entity.call_args[0][0]
        assert isinstance(registered_arg, TaskConfig)
        assert (
            registered_arg.task_config_type
            == TaskConfigType.optimized_emodel_analysis_validation__campaign
        )

        mock_client.upload_content.assert_called_once()
        upload_kwargs = mock_client.upload_content.call_args[1]
        assert upload_kwargs["entity_id"] == "campaign-789"
        assert upload_kwargs["file_name"] == "scan_config.json"

    def test_create_campaign_entity_with_config_skips_when_no_client(self, export_val_scan_config):
        """Verify no-op when db_client is None."""
        export_val_scan_config.create_campaign_entity_with_config(
            output_root=Path("/tmp/out"),  # noqa: S108
            db_client=None,
        )

    def test_create_single_entity_with_config_registers_and_uploads(self, export_val_scan_config):
        """Verify single config registration and upload happen."""
        mock_client = MagicMock()
        mock_single_entity = MagicMock(id="single-abc")
        mock_client.register_entity.return_value = mock_single_entity

        mock_campaign = MagicMock(id="campaign-789")

        dump = export_val_scan_config.model_dump()
        dump["type"] = "EModelExportAndValidationSingleConfig"
        single = EModelExportAndValidationSingleConfig.model_validate(dump)

        with patch.object(
            EModelExportAndValidationSingleConfig,
            "input_entities",
            return_value=[MagicMock(id="e-1")],
        ):
            single.create_single_entity_with_config(
                campaign=mock_campaign,
                db_client=mock_client,
            )

        mock_client.register_entity.assert_called_once()
        registered_arg = mock_client.register_entity.call_args[0][0]
        assert isinstance(registered_arg, TaskConfig)
        assert (
            registered_arg.task_config_type
            == TaskConfigType.optimized_emodel_analysis_validation__config
        )
        assert registered_arg.task_config_generator_id == "campaign-789"

        mock_client.upload_content.assert_called_once()
        upload_kwargs = mock_client.upload_content.call_args[1]
        assert upload_kwargs["entity_id"] == "single-abc"
        assert upload_kwargs["file_name"] == "single_config.json"

    def test_create_single_entity_with_config_skips_when_no_client(self, export_val_scan_config):
        """Verify no-op when db_client is None."""
        dump = export_val_scan_config.model_dump()
        dump["type"] = "EModelExportAndValidationSingleConfig"
        single = EModelExportAndValidationSingleConfig.model_validate(dump)

        single.create_single_entity_with_config(
            campaign=MagicMock(),
            db_client=None,
        )


class TestValidateParamsFileDictSections:
    """Tests exercising dict-mode parameters with section-level and parameter-level validation."""

    def test_section_params_not_list_raises(self):
        """Line 148: section_params that is not a list raises OBIONEError."""
        params = {
            "mechanisms": [],
            "distributions": {},
            "parameters": {
                "soma": "not_a_list",
            },
        }
        with pytest.raises(OBIONEError, match="Parameter section 'soma' must be a list"):
            validate_params_file(params)

    def test_section_params_dict_instead_of_list_raises(self):
        """Section value is a dict instead of a list."""
        params = {
            "mechanisms": [],
            "distributions": {"uniform": {"type": "uniform"}},
            "parameters": {
                "axon": {"name": "gbar_NaV", "val": 0.1},
            },
        }
        with pytest.raises(OBIONEError, match="Parameter section 'axon' must be a list"):
            validate_params_file(params)

    def test_dict_mode_param_missing_name(self):
        """Parameter in a named section missing 'name' key."""
        params = {
            "mechanisms": [],
            "distributions": {},
            "parameters": {
                "soma": [{"val": 0.1}],
            },
        }
        with pytest.raises(OBIONEError, match="missing required key 'name'"):
            validate_params_file(params)

    def test_dict_mode_param_missing_val(self):
        """Parameter in a named section missing 'val' key."""
        params = {
            "mechanisms": [],
            "distributions": {},
            "parameters": {
                "soma": [{"name": "gbar_NaV"}],
            },
        }
        with pytest.raises(OBIONEError, match="missing required key 'val'"):
            validate_params_file(params)

    def test_dict_mode_invalid_dist_reference(self):
        """Parameter in a named section references an undefined distribution."""
        params = {
            "mechanisms": [],
            "distributions": {"uniform": {"type": "uniform"}},
            "parameters": {
                "soma": [{"name": "gbar_NaV", "val": 0.1, "dist": "bogus"}],
            },
        }
        with pytest.raises(OBIONEError, match="references distribution 'bogus'"):
            validate_params_file(params)

    def test_dict_mode_param_not_dict_raises(self):
        """Individual parameter entry that is not a dict raises."""
        params = {
            "mechanisms": [],
            "distributions": {},
            "parameters": {
                "soma": [42],
            },
        }
        with pytest.raises(OBIONEError, match="must be a dict"):
            validate_params_file(params)

    def test_dict_mode_valid_passes(self):
        """Valid dict-mode parameters pass without error."""
        params = {
            "mechanisms": [{"name": "NaV"}],
            "distributions": {"uniform": {"type": "uniform"}},
            "parameters": {
                "soma": [
                    {"name": "gbar_NaV", "val": 0.1, "dist": "uniform"},
                ],
                "axon": [
                    {"name": "gbar_KV", "val": 0.05},
                ],
            },
        }
        validate_params_file(params)  # should not raise

    def test_dunder_section_skipped(self):
        """Sections starting with __ are skipped (including __root__)."""
        params = {
            "mechanisms": [],
            "distributions": {},
            "parameters": {
                "__private": "anything_here_is_ignored",
                "soma": [{"name": "gbar_NaV", "val": 0.1}],
            },
        }
        validate_params_file(params)  # should not raise


class TestTask1DownloadRecordingsAdditional:
    """Additional tests for _download_recordings to cover more branches."""

    def test_downloads_multiple_recordings(self, tmp_path):
        """Verify multiple recordings are all downloaded with correct LJP values."""
        from obi_one.scientific.from_id.electrical_cell_recording_from_id import (
            ElectricalCellRecordingFromID,
        )
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks import (
            ExtractionInitialize,
        )
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.config import (
            EModelEFeatureExtractionScanConfig,
            EModelEFeatureExtractionSingleConfig,
        )
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
            EModelEFeatureExtractionTask,
        )

        config = EModelEFeatureExtractionScanConfig(
            info=EModelEFeatureExtractionScanConfig.model_fields["info"].annotation(
                campaign_name="T",
                campaign_description="T",
            ),
            initialize=ExtractionInitialize(
                electrical_cell_recording=[
                    ElectricalCellRecordingFromID(id_str="rec-1"),
                    ElectricalCellRecordingFromID(id_str="rec-2"),
                ],
            ),
        )
        dump = config.model_dump()
        dump["type"] = "EModelEFeatureExtractionSingleConfig"
        single = EModelEFeatureExtractionSingleConfig.model_validate(dump)
        task = EModelEFeatureExtractionTask(config=single)

        mock_client = MagicMock()
        mock_entity_1 = MagicMock(ljp=10.0)
        mock_entity_2 = MagicMock(ljp=14.0)

        rec1 = task.config.initialize.electrical_cell_recording[0]

        with (
            patch.object(
                type(rec1),
                "download_asset",
                side_effect=[
                    tmp_path / "rec-1" / "cell1.nwb",
                    tmp_path / "rec-2" / "cell2.nwb",
                ],
            ),
            patch.object(
                type(rec1),
                "entity",
                side_effect=[mock_entity_1, mock_entity_2],
            ),
        ):
            result = task._download_recordings(tmp_path / "ephys_data", mock_client)

        assert len(result) == 2
        assert result[0][1] == 10.0
        assert result[1][1] == 14.0
