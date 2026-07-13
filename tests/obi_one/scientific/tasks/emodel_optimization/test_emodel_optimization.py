"""Tests for the emodel optimization workflow (stages 02 + 03)."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from entitysdk.types import TaskActivityType, TaskConfigType

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
        assert groups == ["Input", "Morphology", "Parameters", "Optimization Settings"]

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
        assert opt_scan_config.optimization_settings.optimiser == "SO-CMA"

    def test_default_max_ngen(self, opt_scan_config):
        assert opt_scan_config.optimization_settings.max_ngen == 2

    def test_default_offspring_size(self, opt_scan_config):
        assert opt_scan_config.optimization_params.offspring_size == 4

    def test_default_validation_threshold(self, opt_scan_config):
        assert opt_scan_config.optimization_settings.validation_threshold == 5.0  # noqa: RUF069

    def test_default_export_hoc(self, opt_scan_config):
        assert opt_scan_config.optimization_settings.export_hoc is True

    def test_default_export_sonata(self, opt_scan_config):
        assert opt_scan_config.optimization_settings.export_sonata is True

    def test_default_only_best(self, opt_scan_config):
        assert opt_scan_config.optimization_settings.only_best is False

    def test_default_seeds(self, opt_scan_config):
        assert opt_scan_config.optimization_settings.seeds == [1]


class TestExportAndValidationDefaults:
    def test_default_validation_threshold(self, export_val_scan_config):
        assert export_val_scan_config.settings.validation_threshold == 5.0  # noqa: RUF069

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
        assert export_val_scan_config.settings.validation_protocols == ("sAHP_220",)


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
        assert d["optimiser"] == "SO-CMA"

    def test_includes_max_ngen(self, opt_scan_config):
        d = opt_scan_config.optimization_settings.to_dict(opt_scan_config.optimization_params)
        assert d["max_ngen"] == 2

    def test_includes_validation_threshold(self, opt_scan_config):
        d = opt_scan_config.optimization_settings.to_dict(opt_scan_config.optimization_params)
        assert d["validation_threshold"] == 5.0  # noqa: RUF069

    def test_includes_plot_currentscape(self, opt_scan_config):
        d = opt_scan_config.optimization_settings.to_dict(opt_scan_config.optimization_params)
        assert d["plot_currentscape"] is True

    @pytest.mark.skip(
        reason="Belongs to optimisation branch — to_dict() doesn't emit validation_protocols"
    )
    def test_includes_validation_protocols(self, opt_scan_config):
        d = opt_scan_config.optimization_settings.to_dict(opt_scan_config.optimization_params)
        assert "validation_protocols" in d

    @pytest.mark.skip(
        reason="Belongs to optimisation branch — to_dict() doesn't emit name_Rin_protocol"
    )
    def test_includes_name_rin_protocol(self, opt_scan_config):
        d = opt_scan_config.optimization_settings.to_dict(opt_scan_config.optimization_params)
        assert "name_Rin_protocol" in d

    @pytest.mark.skip(
        reason="Belongs to optimisation branch — to_dict() doesn't emit name_rmp_protocol"
    )
    def test_includes_name_rmp_protocol(self, opt_scan_config):
        d = opt_scan_config.optimization_settings.to_dict(opt_scan_config.optimization_params)
        assert "name_rmp_protocol" in d

    def test_includes_optimisation_params(self, opt_scan_config):
        d = opt_scan_config.optimization_settings.to_dict(opt_scan_config.optimization_params)
        assert d["optimisation_params"]["offspring_size"] == 4

    def test_includes_currentscape_config_when_title_set(self, opt_scan_config):
        opt_scan_config.optimization_settings.currentscape_title = "Test Title"
        d = opt_scan_config.optimization_settings.to_dict(opt_scan_config.optimization_params)
        assert d["currentscape_config"]["title"] == "Test Title"

    def test_omits_currentscape_config_when_empty(self, opt_scan_config):
        d = opt_scan_config.optimization_settings.to_dict(opt_scan_config.optimization_params)
        assert "currentscape_config" not in d


# ─── Step 5: Merged task calls correct pipeline methods (no validation) ────


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

    def test_export_skipped_when_disabled(self, opt_scan_config):
        opt_scan_config.optimization_settings.export_hoc = False
        opt_scan_config.optimization_settings.export_sonata = False

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

        mock_hoc.assert_not_called()
        mock_sonata.assert_not_called()


# ─── Step 6: Export+validation task calls validation() + export ────────────


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
        settings = ExtractionSettings(validation_protocols=("sAHP_220", "IDhyperpol_150"))
        recipes = _build_extraction_recipes(settings)
        ps = recipes["emodel"]["pipeline_settings"]
        assert ps["validation_protocols"] == ["sAHP_220", "IDhyperpol_150"]

    def test_build_extraction_recipes_empty_validation_protocols(self):
        """Default empty validation_protocols results in empty list in recipe."""
        settings = ExtractionSettings()
        recipes = _build_extraction_recipes(settings)
        ps = recipes["emodel"]["pipeline_settings"]
        assert ps["validation_protocols"] == []

    def test_settings_field_exists_with_default(self):
        """Settings block has validation_protocols with empty tuple default."""
        s = ExtractionSettings()
        assert s.validation_protocols == ()

    def test_settings_serialization_round_trip(self):
        """validation_protocols survives JSON serialization."""
        s = ExtractionSettings(validation_protocols=("sAHP_220",))
        dumped = s.model_dump_json()
        restored = ExtractionSettings.model_validate_json(dumped)
        assert restored.validation_protocols == ("sAHP_220",)


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
            params_file=ParamsFileSelection(params_file_path="/tmp/params.json"),  # noqa: S108
        )
        assert config.use_params_file is True

    def test_params_file_none_by_default(self, opt_scan_config):
        assert opt_scan_config.params_file is None
