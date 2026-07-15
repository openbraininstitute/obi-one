"""Tests for the emodel optimization workflow (stages 02 + 03)."""

# ruff: noqa: PLC0415, RUF069, E501, PT012

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from entitysdk.types import TaskActivityType, TaskConfigType

try:
    import bluepyemodel  # noqa: F401

    _has_bluepyemodel = True
except ImportError:
    _has_bluepyemodel = False

from obi_one.core.exception import OBIONEError
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.from_id.task_result_from_id import TaskResultFromID
from obi_one.scientific.tasks.emodel_optimization._shared import determine_core_count
from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.blocks.settings import (
    Settings as ExtractionSettings,
)
from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task import (
    _build_extraction_recipes,
)
from obi_one.scientific.tasks.emodel_optimization.task2_emodel_optimization.blocks import (
    MorphologySelection,
    OptimizationInitialize,
    ParamsFileSelection,
    validate_params_file,
)
from obi_one.scientific.tasks.emodel_optimization.task2_emodel_optimization.config import (
    EModelOptimizationScanConfig,
    EModelOptimizationSingleConfig,
)
from obi_one.scientific.tasks.emodel_optimization.task2_emodel_optimization.task import (
    EModelOptimizationTask,
)
from obi_one.scientific.tasks.emodel_optimization.task3_export_and_validation.blocks import (
    ExportAndValidationInitialize,
)
from obi_one.scientific.tasks.emodel_optimization.task3_export_and_validation.config import (
    EModelExportAndValidationScanConfig,
    EModelExportAndValidationSingleConfig,
)
from obi_one.scientific.tasks.emodel_optimization.task3_export_and_validation.task import (
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
            etype="cADpyr",
        ),
        morphology_selection=MorphologySelection(
            morphology=CellMorphologyFromID(id_str=morph_id),
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
            emodel="TestEModel",
            etype="cADpyr",
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
        assert groups == ["Setup", "Settings"]

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

    def test_default_plot_currentscape(self, opt_scan_config):
        assert opt_scan_config.optimization_settings.plot_currentscape is True


class TestExportAndValidationDefaults:
    def test_default_validation_threshold(self, export_val_scan_config):
        assert export_val_scan_config.settings.validation_threshold == 5.0

    def test_default_export_hoc(self, export_val_scan_config):
        assert export_val_scan_config.settings.export_hoc is True

    def test_default_export_sonata(self, export_val_scan_config):
        assert export_val_scan_config.settings.export_sonata is True

    def test_default_only_validated(self, export_val_scan_config):
        assert export_val_scan_config.settings.only_validated is True

    def test_default_only_best(self, export_val_scan_config):
        assert export_val_scan_config.settings.only_best is True

    def test_default_only_validated_plots(self, export_val_scan_config):
        assert export_val_scan_config.settings.only_validated_plots is True

    def test_default_validation_protocols(self, export_val_scan_config):
        assert export_val_scan_config.settings.validation_protocols == "sAHP_220"


class TestSerialization:
    def test_opt_round_trip(self, opt_scan_config):
        json_str = opt_scan_config.model_dump_json()
        restored = EModelOptimizationScanConfig.model_validate_json(json_str)
        assert restored.initialize.emodel == "TestEModel"
        assert restored.initialize.etype == "cADpyr"

    def test_opt_dump_contains_type(self, opt_scan_config):
        dump = opt_scan_config.model_dump()
        assert dump["type"] == "EModelOptimizationScanConfig"

    def test_export_val_round_trip(self, export_val_scan_config):
        json_str = export_val_scan_config.model_dump_json()
        restored = EModelExportAndValidationScanConfig.model_validate_json(json_str)
        assert restored.initialize.emodel == "TestEModel"

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

    def test_includes_currentscape_config_when_title_set(self, opt_scan_config):
        opt_scan_config.optimization_settings.currentscape_title = "Test Title"
        d = opt_scan_config.optimization_settings.to_dict(opt_scan_config.optimization_params)
        assert d["currentscape_config"]["title"] == "Test Title"

    def test_omits_currentscape_config_when_empty(self, opt_scan_config):
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
            patch.object(task, "_download_extraction_recipes", return_value={}),
            patch.object(task, "_download_extraction_targets"),
            patch.object(task, "_stage_morphology", return_value="morph.swc"),
            patch.object(task, "_stage_mechanisms"),
            patch.object(task, "_stage_params", return_value="params.json"),
            patch.object(task, "_stage_traces"),
            patch.object(task, "_derive_mtype", return_value="L5PC"),
            patch("obi_one.scientific.tasks.emodel_optimization._shared.compile_mechanisms"),
            patch("obi_one.scientific.tasks.emodel_optimization._shared.chdir"),
            patch("obi_one.scientific.tasks.emodel_optimization._shared.write_recipes"),
            patch(
                "obi_one.scientific.tasks.emodel_optimization._shared.update_pipeline_settings",
                return_value={},
            ),
        ):
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
            patch.object(task, "_download_extraction_recipes", return_value={}),
            patch.object(task, "_download_extraction_targets"),
            patch.object(task, "_stage_morphology", return_value="morph.swc"),
            patch.object(task, "_stage_mechanisms"),
            patch.object(task, "_stage_params", return_value="params.json"),
            patch.object(task, "_stage_traces"),
            patch.object(task, "_derive_mtype", return_value="L5PC"),
            patch("obi_one.scientific.tasks.emodel_optimization._shared.compile_mechanisms"),
            patch("obi_one.scientific.tasks.emodel_optimization._shared.chdir"),
            patch("obi_one.scientific.tasks.emodel_optimization._shared.write_recipes"),
            patch(
                "obi_one.scientific.tasks.emodel_optimization._shared.update_pipeline_settings",
                return_value={},
            ),
        ):
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
            patch.object(task, "_download_extraction_recipes", return_value={}),
            patch.object(task, "_download_extraction_targets"),
            patch.object(task, "_stage_morphology", return_value="morph.swc"),
            patch.object(task, "_stage_mechanisms"),
            patch.object(task, "_stage_params", return_value="params.json"),
            patch.object(task, "_stage_traces"),
            patch.object(task, "_derive_mtype", return_value="L5PC"),
            patch("obi_one.scientific.tasks.emodel_optimization._shared.compile_mechanisms"),
            patch("obi_one.scientific.tasks.emodel_optimization._shared.chdir"),
            patch("obi_one.scientific.tasks.emodel_optimization._shared.write_recipes"),
            patch(
                "obi_one.scientific.tasks.emodel_optimization._shared.update_pipeline_settings",
                return_value={},
            ),
        ):
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
            patch("bluepyemodel.access_point.local.LocalAccessPoint", return_value=mock_ap),
            patch("bluepyemodel.optimisation.store_best_model") as mock_store,
            patch("bluepyemodel.validation.validation.validate") as mock_validate,
            patch("bluepyemodel.emodel_pipeline.plotting.plot_models") as mock_plot,
            patch("bluepyemodel.export_emodel.export_emodel.export_emodels_hoc"),
            patch("bluepyemodel.export_emodel.export_emodel.export_emodels_sonata"),
            patch.object(task, "_download_opt_assets"),
            patch.object(task, "_stage_morphology_from_memodel"),
            patch.object(task, "_stage_mechanisms_from_memodel"),
            patch.object(task, "_derive_mtype_from_memodel", return_value="L5PC"),
            patch("obi_one.scientific.tasks.emodel_optimization._shared.compile_mechanisms"),
            patch("obi_one.scientific.tasks.emodel_optimization._shared.chdir"),
            patch("obi_one.scientific.tasks.emodel_optimization._shared.write_recipes"),
            patch(
                "obi_one.scientific.tasks.emodel_optimization._shared.load_recipes", return_value={}
            ),
            patch(
                "obi_one.scientific.tasks.emodel_optimization._shared.update_pipeline_settings",
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
        mock_entity.mtype = "L5PC"
        mock_morph = MagicMock()
        mock_morph.entity.return_value = mock_entity
        task.config.morphology_selection.morphology = mock_morph

        result = task._derive_mtype(mock_client)
        assert result == "L5PC"

    def test_mtype_fallback_unknown(self, opt_scan_config):
        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)
        task = EModelOptimizationTask(config=single)

        mock_client = MagicMock()
        mock_entity = MagicMock()
        mock_entity.mtype = None
        mock_morph = MagicMock()
        mock_morph.entity.return_value = mock_entity
        task.config.morphology_selection.morphology = mock_morph

        result = task._derive_mtype(mock_client)
        assert result == "unknown"


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
                etype="cADpyr",
            ),
            morphology_selection=MorphologySelection(
                morphology=CellMorphologyFromID(id_str=morph_id),
            ),
            params_file=ParamsFileSelection(
                params_content={"mechanisms": [], "distributions": {}, "parameters": []}
            ),
        )
        assert config.use_params_file is True

    def test_params_file_empty_by_default(self, opt_scan_config):
        assert not opt_scan_config.params_file.params_content


# ─── Phase 2: _shared.py tests ─────────────────────────────────────────────


class TestSharedChdir:
    def test_chdir_changes_and_restores(self, tmp_path):

        from obi_one.scientific.tasks.emodel_optimization._shared import chdir

        original = Path.cwd()
        with chdir(tmp_path):
            assert Path.cwd() == tmp_path
        assert Path.cwd() == original

    def test_chdir_restores_on_exception(self, tmp_path):
        from obi_one.scientific.tasks.emodel_optimization._shared import chdir

        original = Path.cwd()
        with pytest.raises(RuntimeError), chdir(tmp_path):
            msg = "boom"
            raise RuntimeError(msg)
        assert Path.cwd() == original


class TestSharedCopyTree:
    def test_copy_file(self, tmp_path):
        from obi_one.scientific.tasks.emodel_optimization._shared import copy_tree

        src = tmp_path / "src.txt"
        src.write_text("hello")
        dst = tmp_path / "sub" / "dst.txt"
        copy_tree(src, dst)
        assert dst.read_text() == "hello"

    def test_copy_dir(self, tmp_path):
        from obi_one.scientific.tasks.emodel_optimization._shared import copy_tree

        src_dir = tmp_path / "srcdir"
        src_dir.mkdir()
        (src_dir / "a.txt").write_text("a")
        dst_dir = tmp_path / "dstdir"
        copy_tree(src_dir, dst_dir)
        assert (dst_dir / "a.txt").read_text() == "a"


class TestSharedSeedWorkingDir:
    def test_seeds_known_subpaths(self, tmp_path):
        from obi_one.scientific.tasks.emodel_optimization._shared import (
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
        from obi_one.scientific.tasks.emodel_optimization._shared import (
            seed_working_dir_from_previous,
        )

        with pytest.raises(FileNotFoundError, match="previous_stage_output_path"):
            seed_working_dir_from_previous(tmp_path / "nonexistent", tmp_path / "coord")

    def test_skips_nonexistent_subpaths(self, tmp_path):
        from obi_one.scientific.tasks.emodel_optimization._shared import (
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
        from obi_one.scientific.tasks.emodel_optimization._shared import (
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
        from obi_one.scientific.tasks.emodel_optimization._shared import write_recipes

        path = tmp_path / "a" / "b" / "c" / "recipes.json"
        write_recipes({}, path)
        assert path.exists()


class TestSharedUpdatePipelineSettings:
    def test_merges_overrides(self):
        from obi_one.scientific.tasks.emodel_optimization._shared import (
            update_pipeline_settings,
        )

        recipes = {"emodel": {"pipeline_settings": {"existing": True}}}
        result = update_pipeline_settings(recipes, "emodel", {"new": 42})
        assert result["emodel"]["pipeline_settings"]["existing"] is True
        assert result["emodel"]["pipeline_settings"]["new"] == 42

    def test_skips_none_values(self):
        from obi_one.scientific.tasks.emodel_optimization._shared import (
            update_pipeline_settings,
        )

        recipes = {"emodel": {"pipeline_settings": {}}}
        result = update_pipeline_settings(recipes, "emodel", {"skip": None, "keep": 1})
        assert "skip" not in result["emodel"]["pipeline_settings"]
        assert result["emodel"]["pipeline_settings"]["keep"] == 1

    def test_creates_pipeline_settings_if_missing(self):
        from obi_one.scientific.tasks.emodel_optimization._shared import (
            update_pipeline_settings,
        )

        recipes = {"emodel": {}}
        result = update_pipeline_settings(recipes, "emodel", {"seed": 1})
        assert result["emodel"]["pipeline_settings"]["seed"] == 1

    def test_raises_on_missing_emodel(self):
        from obi_one.scientific.tasks.emodel_optimization._shared import (
            update_pipeline_settings,
        )

        with pytest.raises(KeyError, match="not in recipes"):
            update_pipeline_settings({}, "missing", {})


class TestSharedCompileMechanisms:
    def test_raises_on_missing_dir(self, tmp_path):
        from obi_one.scientific.tasks.emodel_optimization._shared import (
            compile_mechanisms,
        )

        with pytest.raises(FileNotFoundError, match="not a directory"):
            compile_mechanisms(tmp_path / "nonexistent")

    def test_skips_if_already_compiled_x86_64(self, tmp_path):
        from obi_one.scientific.tasks.emodel_optimization._shared import (
            compile_mechanisms,
        )

        mech_dir = tmp_path / "mechanisms"
        mech_dir.mkdir()
        arch_dir = tmp_path / "x86_64"
        arch_dir.mkdir()
        (arch_dir / "special").write_text("")
        compile_mechanisms(mech_dir)

    def test_skips_if_already_compiled_arm64(self, tmp_path):
        from obi_one.scientific.tasks.emodel_optimization._shared import (
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
        from obi_one.scientific.tasks.emodel_optimization._shared import (
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
        from obi_one.scientific.tasks.emodel_optimization._shared import (
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


class TestTask2DownloadExtractionRecipes:
    def test_returns_dict_on_success(self, opt_scan_config, tmp_path):
        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)
        task = EModelOptimizationTask(config=single)

        mock_tr = MagicMock()
        mock_tr.download_json_asset_by_label.return_value = {"emodel": {}}
        result = task._download_extraction_recipes(mock_tr, tmp_path, MagicMock())
        assert result == {"emodel": {}}

    def test_returns_empty_on_failure(self, opt_scan_config, tmp_path):
        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)
        task = EModelOptimizationTask(config=single)

        mock_tr = MagicMock()
        mock_tr.download_json_asset_by_label.side_effect = Exception("fail")
        result = task._download_extraction_recipes(mock_tr, tmp_path, MagicMock())
        assert result == {}


class TestTask2DownloadExtractionTargets:
    def test_download_succeeds(self, opt_scan_config, tmp_path):
        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)
        task = EModelOptimizationTask(config=single)

        mock_tr = MagicMock()
        task._download_extraction_targets(mock_tr, tmp_path, MagicMock())
        mock_tr.download_asset_by_label.assert_called_once()

    def test_download_fails_gracefully(self, opt_scan_config, tmp_path):
        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)
        task = EModelOptimizationTask(config=single)

        mock_tr = MagicMock()
        mock_tr.download_asset_by_label.side_effect = Exception("fail")
        task._download_extraction_targets(mock_tr, tmp_path, MagicMock())


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
        task.config.parameters_selection.ion_channel_models = [mock_icm]

        task._stage_mechanisms(tmp_path, MagicMock())
        mock_icm.download_asset.assert_called_once()
        call_kwargs = mock_icm.download_asset.call_args
        assert call_kwargs.kwargs["dest_dir"] == tmp_path / "mechanisms"


class TestTask2StageParams:
    def test_params_file_mode_writes_content(self, opt_scan_config, tmp_path):
        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)
        task = EModelOptimizationTask(config=single)

        params_data = {
            "mechanisms": [],
            "distributions": {},
            "parameters": [],
        }
        task.config.params_file.params_content = params_data

        filename = task._stage_params(tmp_path, MagicMock())
        assert filename == "params.json"
        written = json.loads((tmp_path / "config" / "params" / "params.json").read_text())
        assert written == params_data

    def test_dynamic_mode_writes_placeholder(self, opt_scan_config, tmp_path):
        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)
        task = EModelOptimizationTask(config=single)

        filename = task._stage_params(tmp_path, MagicMock())
        assert filename == "params.json"
        written = json.loads((tmp_path / "config" / "params" / "params.json").read_text())
        assert written == {"mechanisms": [], "distributions": {}, "parameters": []}


class TestTask2RegisterOutputEntities:
    def test_register_calls_db_client(self, opt_scan_config, tmp_path):
        dump = opt_scan_config.model_dump()
        dump["type"] = "EModelOptimizationSingleConfig"
        single = EModelOptimizationSingleConfig.model_validate(dump)
        task = EModelOptimizationTask(config=single)

        mock_client = MagicMock()

        # Patch all entity() calls and the entitysdk model constructors
        # to avoid pydantic validation on MagicMock attributes (memory blowup)
        with (
            patch.object(TaskResultFromID, "entity", return_value=MagicMock(id="tr-1")),
            patch.object(CellMorphologyFromID, "entity", return_value=MagicMock(id="morph-1", species=None, brain_region=None)),
            patch("entitysdk.models.EModel", return_value=MagicMock(id="em-1")),
            patch("entitysdk.models.MEModel", return_value=MagicMock(id="me-1")),
            patch("entitysdk.models.Derivation", return_value=MagicMock()),
            patch("entitysdk.models.TaskResult", return_value=MagicMock(id="tr-val")),
        ):
            task._register_output_entities(tmp_path, mock_client)
        assert mock_client.register_entity.call_count >= 5


# ─── Phase 4: Task3 helper tests ───────────────────────────────────────────


class TestTask3DownloadOptAssets:
    def test_downloads_all_asset_types(self, export_val_scan_config, tmp_path):
        dump = export_val_scan_config.model_dump()
        dump["type"] = "EModelExportAndValidationSingleConfig"
        single = EModelExportAndValidationSingleConfig.model_validate(dump)
        task = EModelExportAndValidationTask(config=single)

        mock_tr = MagicMock()
        mock_tr.download_json_asset_by_label.side_effect = [{"emodel": {}}, {"final": []}]
        task._download_opt_assets(mock_tr, tmp_path, MagicMock())

        assert (tmp_path / "checkpoints").exists()
        assert (tmp_path / "config").exists()
        assert (tmp_path / "config" / "params").exists()
        assert (tmp_path / "figures").exists()
        assert (tmp_path / "export_emodels_hoc").exists()
        assert (tmp_path / "export_emodels_sonata").exists()

    def test_handles_download_failures(self, export_val_scan_config, tmp_path):
        dump = export_val_scan_config.model_dump()
        dump["type"] = "EModelExportAndValidationSingleConfig"
        single = EModelExportAndValidationSingleConfig.model_validate(dump)
        task = EModelExportAndValidationTask(config=single)

        mock_tr = MagicMock()
        mock_tr.download_asset_by_label.side_effect = Exception("fail")
        mock_tr.download_json_asset_by_label.side_effect = Exception("fail")
        mock_tr.download_directory_asset_by_label.side_effect = Exception("fail")
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
        mock_mtype.name = "L5PC"
        mock_morph.mtypes = [mock_mtype]
        with patch.object(MEModelFromID, "entity", return_value=mock_memodel):
            mock_client.get_entity.return_value = mock_morph
            result = task._derive_mtype_from_memodel(mock_client)
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
        with patch.object(MEModelFromID, "entity", return_value=mock_memodel):
            mock_client.get_entity.return_value = mock_morph
            result = task._derive_mtype_from_memodel(mock_client)
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

        with (
            patch.object(MEModelFromID, "entity", return_value=mock_memodel),
            patch(
                "obi_one.scientific.from_id.cell_morphology_from_id.CellMorphologyFromID"
            ) as mock_morph_cls,
        ):
            mock_morph_instance = mock_morph_cls.return_value
            mock_morph_instance.swc_file_content.return_value = "fake SWC"
            task._stage_morphology_from_memodel(tmp_path, mock_client)

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

        with (
            patch.object(MEModelFromID, "entity", return_value=mock_memodel),
            patch(
                "obi_one.scientific.from_id.ion_channel_model_from_id.IonChannelModelFromID"
            ) as mock_icm_cls,
        ):
            mock_icm_instance = mock_icm_cls.return_value
            task._stage_mechanisms_from_memodel(tmp_path, mock_client)
            assert mock_icm_instance.download_asset.call_count == 2


class TestTask3RegisterAndUpdate:
    def test_register_and_update_calls_db(self, export_val_scan_config, tmp_path):
        dump = export_val_scan_config.model_dump()
        dump["type"] = "EModelExportAndValidationSingleConfig"
        single = EModelExportAndValidationSingleConfig.model_validate(dump)
        task = EModelExportAndValidationTask(config=single)

        mock_client = MagicMock()

        with (
            patch.object(MEModelFromID, "entity", return_value=MagicMock(
                id="me-1", name="test", description="desc", species=None,
                brain_region=None, morphology=None,
                emodel=MagicMock(id="em-1"), iteration="0",
            )),
            patch.object(TaskResultFromID, "entity", return_value=MagicMock(id="tr-1")),
            patch("entitysdk.models.TaskResult", return_value=MagicMock(id="tr-val")),
            patch("entitysdk.models.Derivation", return_value=MagicMock()),
            patch("entitysdk.models.MEModel", return_value=MagicMock(id="me-1")),
            patch("entitysdk.models.MEModelCalibrationResult", return_value=MagicMock(id="cal-1")),
        ):
            task._register_and_update(tmp_path, mock_client)
        assert mock_client.register_entity.call_count >= 2
        mock_client.update_entity.assert_called_once()


# ─── Phase 5: Blocks/config additional tests ───────────────────────────────


class TestOptimizationParamsToDict:
    def test_to_dict_default(self):
        from obi_one.scientific.tasks.emodel_optimization.task2_emodel_optimization.blocks import (
            OptimizationParams,
        )

        params = OptimizationParams()
        assert params.to_dict() == {"offspring_size": 20}

    def test_to_dict_custom(self):
        from obi_one.scientific.tasks.emodel_optimization.task2_emodel_optimization.blocks import (
            OptimizationParams,
        )

        params = OptimizationParams(offspring_size=50)
        assert params.to_dict() == {"offspring_size": 50}


class TestExportAndValidationSettingsToDict:
    def test_to_dict_includes_validation_protocols(self, export_val_scan_config):
        d = export_val_scan_config.settings.to_dict(
            export_val_scan_config.currentscape_config
        )
        assert "validation_protocols" in d
        assert d["validation_protocols"] == ["sAHP_220"]

    def test_to_dict_includes_currentscape_config(self, export_val_scan_config):
        d = export_val_scan_config.settings.to_dict(
            export_val_scan_config.currentscape_config
        )
        assert "currentscape_config" in d
        assert d["currentscape_config"]["title"] == "EModel"

    def test_to_dict_includes_plot_currentscape(self, export_val_scan_config):
        d = export_val_scan_config.settings.to_dict(
            export_val_scan_config.currentscape_config
        )
        assert d["plot_currentscape"] is True


class TestCurrentscapeConfigToDict:
    def test_default_title(self):
        from obi_one.scientific.tasks.emodel_optimization.task3_export_and_validation.blocks import (
            CurrentscapeConfig,
        )

        cfg = CurrentscapeConfig()
        assert cfg.to_dict() == {"title": "EModel"}

    def test_custom_title(self):
        from obi_one.scientific.tasks.emodel_optimization.task3_export_and_validation.blocks import (
            CurrentscapeConfig,
        )

        cfg = CurrentscapeConfig(figure_title="Custom")
        assert cfg.to_dict() == {"title": "Custom"}


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
        with (
            patch.object(TaskResultFromID, "entity", return_value=mock_tr),
            patch.object(CellMorphologyFromID, "entity", return_value=mock_morph),
        ):
            entities = opt_scan_config.input_entities(mock_client)
        assert len(entities) == 2
        assert entities[0] == mock_tr
        assert entities[1] == mock_morph


# ─── Phase 6: Task1 pure function tests ────────────────────────────────────


class TestEcodeClassName:
    def test_matches_idrest(self):
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task import (
            _ecode_class_name,
        )

        ecodes = {"IDrest": type("IDrest", (), {}), "IV": type("IV", (), {})}
        assert _ecode_class_name("IDrest_150", ecodes) == "IDrest"

    def test_matches_iv_case_insensitive(self):
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task import (
            _ecode_class_name,
        )

        ecodes = {"IV": type("IV", (), {})}
        assert _ecode_class_name("iv_-20", ecodes) == "IV"

    def test_no_match_returns_none(self):
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task import (
            _ecode_class_name,
        )

        ecodes = {"IDrest": type("IDrest", (), {})}
        assert _ecode_class_name("unknown_protocol", ecodes) is None


class TestDiscoverTiming:
    def test_returns_median_per_protocol(self, tmp_path):
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task import (
            _discover_timing,
        )

        nwb1 = tmp_path / "cell1.nwb"
        nwb2 = tmp_path / "cell2.nwb"
        nwb1.write_text("")
        nwb2.write_text("")

        with patch(
            "obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task._read_timing_from_nwb"
        ) as mock_read:
            mock_read.side_effect = [
                {"IDrest": 100.0},
                {"IDrest": 200.0},
            ]
            result = _discover_timing([nwb1, nwb2], ["IDrest"])
            assert result == {"IDrest": 150.0}

    def test_omits_protocols_with_no_data(self, tmp_path):
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task import (
            _discover_timing,
        )

        nwb1 = tmp_path / "cell1.nwb"
        nwb1.write_text("")

        with patch(
            "obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task._read_timing_from_nwb"
        ) as mock_read:
            mock_read.return_value = {}
            result = _discover_timing([nwb1], ["IDrest", "IV"])
            assert result == {}


class TestPartitionProtocols:
    def test_standard_protocol_extractable(self):
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task import (
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
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task import (
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
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task import (
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
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task import (
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
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task import (
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
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task import (
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
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task import (
            _discover_amplitudes,
        )

        nwb1 = tmp_path / "cell1.nwb"
        nwb2 = tmp_path / "cell2.nwb"
        nwb1.write_text("")
        nwb2.write_text("")

        with patch(
            "obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task._read_amplitudes_from_nwb"
        ) as mock_read:
            mock_read.side_effect = [
                {"IDrest": [0.1, 0.2]},
                {"IDrest": [0.2, 0.3]},
            ]
            result = _discover_amplitudes([nwb1, nwb2], ["IDrest"])
            assert result == {"IDrest": [0.1, 0.2, 0.3]}

    def test_empty_when_no_amplitudes(self, tmp_path):
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task import (
            _discover_amplitudes,
        )

        nwb1 = tmp_path / "cell1.nwb"
        nwb1.write_text("")

        with patch(
            "obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task._read_amplitudes_from_nwb"
        ) as mock_read:
            mock_read.return_value = {}
            result = _discover_amplitudes([nwb1], ["IDrest"])
            assert result == {"IDrest": []}


class TestBuildTargetsFormatted:
    def test_builds_rows_for_each_amplitude_and_feature(self):
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task import (
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
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task import (
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
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task import (
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
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task import (
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
        settings = ExtractionSettings(
            rin_protocol_name="IV_-20",
            rin_protocol_amplitude=-0.2,
            rmp_protocol_name="IV_0",
            rmp_protocol_amplitude=0.0,
        )
        recipes = _build_extraction_recipes(settings, threshold_based=True)
        ps = recipes["emodel"]["pipeline_settings"]
        assert ps["name_Rin_protocol"] == ["IV_-20", -0.2]
        assert ps["name_rmp_protocol"] == ["IV_0", None]

    def test_non_threshold_omits_rin_rmp(self):
        settings = ExtractionSettings(
            rin_protocol_name="IV_-20",
            rmp_protocol_name="IV_0",
        )
        recipes = _build_extraction_recipes(settings, threshold_based=False)
        ps = recipes["emodel"]["pipeline_settings"]
        assert ps["name_Rin_protocol"] is None
        assert ps["name_rmp_protocol"] is None

    def test_compute_rheobase_adds_strategy(self):
        settings = ExtractionSettings(compute_rheobase=True)
        recipes = _build_extraction_recipes(settings)
        ps = recipes["emodel"]["pipeline_settings"]
        assert ps["rheobase_strategy_extraction"] == "absolute"
        assert "rheobase_settings_extraction" in ps

    def test_no_rheobase_omits_strategy(self):
        settings = ExtractionSettings(compute_rheobase=False)
        recipes = _build_extraction_recipes(settings)
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
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.blocks import (
            ExtractionInitialize,
        )
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.config import (
            EModelEFeatureExtractionScanConfig,
        )
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task import (
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
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.config import (
            EModelEFeatureExtractionSingleConfig,
        )
        single_config = EModelEFeatureExtractionSingleConfig.model_validate(dump)
        task = EModelEFeatureExtractionTask(config=single_config)

        mock_client = MagicMock()
        mock_entity = MagicMock(ljp=12.5)
        mock_recording = task.config.initialize.electrical_cell_recording[0]

        with (
            patch.object(type(mock_recording), "entity", return_value=mock_entity),
            patch.object(type(mock_recording), "download_asset", return_value=tmp_path / "rec-1" / "rec.nwb"),
        ):
            result = task._download_recordings(tmp_path / "ephys_data", mock_client)
        assert len(result) == 1
        assert result[0][1] == 12.5

    def test_raises_on_wrong_type(self, tmp_path):
        from obi_one.scientific.from_id.electrical_cell_recording_from_id import (
            ElectricalCellRecordingFromID,
        )
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.blocks import (
            ExtractionInitialize,
        )
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.config import (
            EModelEFeatureExtractionScanConfig,
            EModelEFeatureExtractionSingleConfig,
        )
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task import (
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
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.blocks import (
            ExtractionInitialize,
        )
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.config import (
            EModelEFeatureExtractionScanConfig,
            EModelEFeatureExtractionSingleConfig,
        )
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.task import (
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

        mock_recording = MagicMock()
        mock_recording.entity.return_value = MagicMock(id="rec-1")
        task.config.initialize.electrical_cell_recording = [mock_recording]

        with (
            patch("entitysdk.models.TaskResult", return_value=MagicMock(id="tr-1")),
            patch("entitysdk.models.Derivation", return_value=MagicMock()),
        ):
            task._register_task_result(tmp_path, mock_client)
        mock_client.register_entity.assert_called()


# ─── Phase 8: Task1 blocks/protocols/efeatures tests ───────────────────────


class TestExtractionConfigClassVars:
    def test_name(self):
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.config import (
            EModelEFeatureExtractionScanConfig,
        )

        assert EModelEFeatureExtractionScanConfig.name == "EModel EFeature Extraction"

    def test_single_coord_class_name(self):
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.config import (
            EModelEFeatureExtractionScanConfig,
        )

        assert (
            EModelEFeatureExtractionScanConfig.single_coord_class_name
            == "EModelEFeatureExtractionSingleConfig"
        )

    def test_ui_enabled(self):
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.config import (
            EModelEFeatureExtractionScanConfig,
        )

        assert EModelEFeatureExtractionScanConfig.json_schema_extra_additions.get("ui_enabled") is True

    def test_campaign_task_config_type(self):
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.config import (
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

    def test_default_compute_rheobase(self):
        s = ExtractionSettings()
        assert s.compute_rheobase is True

    def test_default_validation_protocols_empty(self):
        s = ExtractionSettings()
        assert not s.validation_protocols

    def test_default_std_value(self):
        s = ExtractionSettings()
        assert s.default_std_value == 0.01


class TestProtocolAndFeatureSelectionDefaults:
    def test_default_autoselect(self):
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.blocks.protocol_and_feature_selection import (
            ProtocolAndFeatureSelection,
        )

        sel = ProtocolAndFeatureSelection()
        assert sel.autoselect is False

    def test_default_threshold_based(self):
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.blocks.protocol_and_feature_selection import (
            ProtocolAndFeatureSelection,
        )

        sel = ProtocolAndFeatureSelection()
        assert sel.threshold_based is False


class TestEFeatureDefaults:
    def test_spikecount_defaults(self):
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.protocols_and_features.efeatures import (
            Spikecount,
        )

        f = Spikecount()
        assert f.extract is False
        assert f.weight == 1.0
        assert f.efel_name == "Spikecount"

    def test_meanfrequency_defaults(self):
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.protocols_and_features.efeatures import (
            MeanFrequency,
        )

        f = MeanFrequency()
        assert f.extract is False
        assert f.efel_name == "mean_frequency"

    def test_efeature_settings_override(self):
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.protocols_and_features.efeatures import (
            Spikecount,
        )

        f = Spikecount(threshold=-30.0, strict_stiminterval=True, interp_step=0.1)
        override = f.efel_settings_override()
        assert override["Threshold"] == -30.0
        assert override["strict_stiminterval"] is True
        assert override["interp_step"] == 0.1


class TestProtocolDefaults:
    def test_idrest_defaults(self):
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.protocols_and_features.protocols import (
            IDrest,
        )

        p = IDrest()
        assert p.ton == 0.0
        assert p.toff == 0.0
        assert p.ljp == 0.0

    def test_iv_defaults(self):
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.protocols_and_features.protocols import (
            IV,
        )

        p = IV()
        assert p.ton == 0.0
        assert p.toff == 0.0

    def test_protocol_selected_efeatures(self):
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.protocols_and_features.protocols import (
            IDrest,
        )

        p = IDrest()
        # Default protocols have features defined as fields
        selected = p.selected_efeatures()
        assert isinstance(selected, list)

    def test_protocol_timing_override_defaults(self):
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.protocols_and_features.protocols import (
            IDrest,
        )

        p = IDrest()
        timing = p.timing_override()
        # All defaults are 0.0 which are omitted
        assert timing == {}

    def test_protocol_timing_override_with_values(self):
        from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.protocols_and_features.protocols import (
            IDrest,
        )

        p = IDrest(ton=100.0, toff=500.0)
        timing = p.timing_override()
        assert timing["ton"] == 100.0
        assert timing["toff"] == 500.0
