import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import morphio
import pytest
from bluepyemodel.model.mechanism_configuration import MechanismConfiguration
from bluepyemodel.model.model import define_morphology
from bluepyemodel.model.neuron_model_configuration import NeuronModelConfiguration
from bluepyemodel.preprocessing import (
    MorphologyCapabilities,
    build_optimization_recipe,
    build_params_definition,
    morphology_preflight,
    normalize_ion_channel_model,
)
from bluepyemodel.preprocessing.schemas import (
    DEFAULT_SECTION_LIST_CATALOG,
    AxonModifier,
    SectionListAvailability,
    SectionListCatalog,
    SectionListChoice,
    SectionListDefinition,
)

from obi_one.core.deserialize import deserialize_obi_object_from_json_data
from obi_one.core.schema import UIElement
from obi_one.core.single import SingleCoordinateScanParams
from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID
from obi_one.scientific.tasks.emodel_building import utils as emodel_building_utils
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization import (
    task as task_module,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.blocks import (
    CustomDistanceDependentDistribution,
    EModelOptimisationParameters,
    GlobalParameterSelection,
    MechanismRegionSelection,
    MechanismsBySectionList,
    MorphologySettings,
    OptimizationParams,
    OptimizationSettings,
    OptimizationValue,
    ParameterSelection,
    ParametersSelection,
    PhasePlotSettings,
    UniformDistanceDependentDistribution,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.config import (
    EModelOptimizationScanConfig,
    EModelOptimizationSingleConfig,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.task import (
    EModelOptimizationTask,
    _fresh_morph_modifiers,
    _tag_local_mechanisms,
    _validation_status_keyword,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.utils import (
    params_definition_input_from_config,
)
from obi_one.utils.filesystem import create_dir
from obi_one.utils.io import write_json


def _scan_config_data(**overrides):
    config_data = {
        "info": {"campaign_name": "test", "campaign_description": "test"},
        "initialize": {"emodel": "test", "etype": {"id_str": "etype"}},
        "inputs": {
            "target_efeatures": {"id_str": "target"},
            "morphology": {"id_str": "morphology"},
        },
        "emodel_optimisation_parameters": {
            "mechanisms": {"ion_channel_models": [{"id_str": "icm-1"}]}
        },
    }
    legacy = overrides.pop("parameters_selection", None)
    canonical = overrides.pop("emodel_optimisation_parameters", None)
    config_data.update(overrides)
    if canonical is not None:
        config_data["emodel_optimisation_parameters"] = canonical
    if legacy is not None:
        config_data.pop("emodel_optimisation_parameters", None)
        config_data["parameters_selection"] = legacy
    return config_data


def _model_entity(ion_names=("na",)):
    return SimpleNamespace(
        id="icm-1",
        name="Sodium channel",
        nmodl_suffix="NaTg",
        is_stochastic=False,
        is_ljp_corrected=False,
        temperature_celsius=34,
        neuron_block=SimpleNamespace(
            range=[{"gNa": "S/cm2"}, {"variable": "vshift", "units": "mV"}],
            global_=[{"variable": "ena", "units": "mV"}],
            useion=[SimpleNamespace(ion_name=ion_name) for ion_name in ion_names],
        ),
    )


def _compiler_fixture():
    reference = IonChannelModelFromID(id_str="icm-1")
    selection = ParametersSelection(
        ion_channel_models=(reference,),
        mechanism_regions={
            "apical": (
                MechanismRegionSelection(
                    ion_channel_model=reference,
                    parameters={
                        "gNa": ParameterSelection(
                            value=OptimizationValue(mode="bounds", bounds=(0.0, 1.0)),
                            distribution="decay",
                        ),
                        "vshift": ParameterSelection(
                            value=OptimizationValue(value=10.0),
                        ),
                    },
                ),
            ),
            "somatic": (
                MechanismRegionSelection(
                    ion_channel_model=reference,
                    parameters={
                        "gNa": ParameterSelection(
                            value=OptimizationValue(mode="bounds", bounds=(0.0, 1.0)),
                            distribution="decay",
                        ),
                    },
                ),
            ),
        },
        global_parameters={
            "v_init": GlobalParameterSelection(value=OptimizationValue(value=-80.0)),
            "ena": GlobalParameterSelection(
                value=OptimizationValue(value=50.0),
                ion_channel_model=reference,
            ),
        },
        base_parameters={
            "all": {
                "Ra": ParameterSelection(value=OptimizationValue(value=100.0)),
                "g_pas": ParameterSelection(value=OptimizationValue(mode="bounds")),
                "e_pas": ParameterSelection(value=OptimizationValue(mode="bounds")),
            }
        },
        distribution_parameters={
            "decay": {
                "constant": OptimizationValue(mode="bounds", bounds=(-0.1, 0.0)),
            }
        },
    )
    config = SimpleNamespace(
        morphology_settings=MorphologySettings(),
        parameters_selection=selection,
        distance_dependent_distributions={
            "uniform": UniformDistanceDependentDistribution(),
            "decay": CustomDistanceDependentDistribution(
                name="decay",
                function="math.exp({distance}*{constant})*{value}",
                parameters=["constant"],
            ),
        },
    )
    normalized = {"icm-1": normalize_ion_channel_model(_model_entity())}
    return config, reference, normalized


def _parameter_rows(params):
    return [
        {**parameter, "location": location, "value": parameter["val"]}
        for location, parameters in params["parameters"].items()
        for parameter in parameters
    ]


def test_parameter_selection_round_trips_and_serializes_axon_settings():
    config = EModelOptimizationScanConfig.model_validate(
        _scan_config_data(
            morphology_settings={"axon_modifier": "none"},
            parameters_selection=ParametersSelection(
                ion_channel_models=(IonChannelModelFromID(id_str="icm-1"),),
                base_parameters={},
            ),
        )
    )
    restored = EModelOptimizationScanConfig.model_validate(config.model_dump(mode="json"))

    assert restored.morphology_settings == MorphologySettings(axon_modifier="none")
    assert restored.morphology_settings.to_pipeline_settings() == {"morph_modifiers": []}
    assert restored.parameters_selection.global_parameters["v_init"].value.value == pytest.approx(
        -80.0
    )


def test_section_list_catalog_expands_aliases_and_emits_recipe_map():
    catalog = DEFAULT_SECTION_LIST_CATALOG

    assert catalog.expand("all") == ("apical", "basal", "somatic", "axonal")
    assert catalog.expand("alldend") == ("apical", "basal")
    assert catalog.expand("somadend") == ("apical", "basal", "somatic")
    assert catalog.expand("allnoaxon") == ("apical", "basal", "somatic")
    assert catalog.expand("somaxon") == ("axonal", "somatic")
    assert catalog.expand("allact") == ("apical", "basal", "somatic", "axonal")
    assert all(
        "myelinated" not in sections for sections in catalog.to_recipe_multiloc_map().values()
    )
    assert catalog.to_recipe_multiloc_map() == {
        "allact": ["apical", "basal", "somatic", "axonal"],
        "alldend": ["apical", "basal"],
        "allnoaxon": ["apical", "basal", "somatic"],
        "somadend": ["apical", "basal", "somatic"],
        "somaxon": ["axonal", "somatic"],
    }
    assert "all" not in catalog.to_recipe_multiloc_map()
    assert isinstance(catalog.definitions, tuple)
    assert isinstance(catalog.expand("all"), tuple)


def test_section_list_choices_follow_modifier_capabilities():
    expected = {
        "replace_axon_with_taper": (True, SectionListAvailability.available),
        "replace_axon_olfactory_bulb": (True, SectionListAvailability.available),
        "replace_axon_legacy": (False, SectionListAvailability.unavailable),
        "bluepyopt_replace_axon": (False, SectionListAvailability.unavailable),
        "none": (False, SectionListAvailability.unavailable),
    }

    for modifier, (available, availability) in expected.items():
        choices = {
            choice.name: choice
            for choice in MorphologySettings(axon_modifier=modifier).section_list_choices()
        }
        assert choices["myelinated"].available is available
        assert choices["myelinated"].availability == availability


def test_mechanisms_wizard_steps_are_mapped_in_figma_order():
    assert EModelOptimisationParameters.steps == (
        "Mechanism Selection",
        "Region assignment",
        "Distribution",
        "Parameters selection",
    )

    schema = EModelOptimizationScanConfig.model_json_schema()
    parameter_schema = schema["$defs"]["EModelOptimisationParameters"]["properties"]
    mechanisms_schema = schema["$defs"]["MechanismsBySectionList"]["properties"]

    assert mechanisms_schema["ion_channel_models"]["step"] == "Mechanism Selection"
    assert mechanisms_schema["ion_channel_models"]["step_order"] == 1
    assert mechanisms_schema["mechanism_regions"]["step"] == "Region assignment"
    assert mechanisms_schema["mechanism_regions"]["step_order"] == 2
    assert parameter_schema["global_parameters"]["step"] == "Parameters selection"
    assert parameter_schema["base_parameters"]["step"] == "Parameters selection"
    assert parameter_schema["distribution_parameters"]["step"] == "Parameters selection"

    top_level_schema = schema["properties"]
    assert top_level_schema["distance_dependent_distributions"]["step"] == "Distribution"
    assert top_level_schema["distance_dependent_distributions"]["step_order"] == 3
    assert (
        top_level_schema["distance_dependent_distributions"]["wizard"]
        == "emodel_optimisation_parameters"
    )


def test_schema_groups_match_figma_navigation():
    schema = EModelOptimizationScanConfig.model_json_schema()
    properties = schema["properties"]
    inputs_schema = schema["$defs"]["OptimizationInputs"]["properties"]

    assert properties["info"]["group"] == "Setup"
    assert properties["initialize"]["group"] == "Setup"
    assert properties["inputs"]["group"] == "Inputs"
    assert properties["inputs"]["title"] == "Inputs"
    assert inputs_schema["target_efeatures"]["title"] == "Target EFeatures"
    assert inputs_schema["target_efeatures"]["entity_query"] == {"type": "task_result"}
    assert inputs_schema["morphology"]["title"] == "Cell morphology"
    assert inputs_schema["morphology"]["entity_query"] == {"type": "cell_morphology"}
    assert properties["emodel_optimisation_parameters"]["group"] == "Inputs"
    assert properties["emodel_optimisation_parameters"]["title"] == "Mechanisms"
    assert properties["emodel_optimisation_parameters"]["ui_element"] == (
        UIElement.EMODEL_OPTIMISATION_PARAMETERS
    )
    mechanisms_schema = schema["$defs"]["MechanismsBySectionList"]["properties"]
    assert mechanisms_schema["ion_channel_models"]["entity_query"] == {"type": "ion_channel_model"}
    mechanism_region_schema = schema["$defs"]["MechanismRegionSelection"]["properties"]
    assert mechanism_region_schema["ion_channel_model"]["entity_query"] == {
        "type": "ion_channel_model"
    }
    global_parameter_schema = schema["$defs"]["GlobalParameterSelection"]["properties"]
    assert global_parameter_schema["ion_channel_model"]["entity_query"] == {
        "type": "ion_channel_model"
    }
    assert properties["distance_dependent_distributions"]["group"] == "Inputs"
    assert properties["morphology_settings"]["group"] == "Settings"
    assert properties["morphology_settings"]["title"] == "Morphology settings"
    assert properties["optimization_settings"]["group"] == "Settings"
    assert properties["optimization_params"]["group"] == "Settings"
    assert schema["group_order"] == ["Setup", "Inputs", "Settings"]


def test_section_list_schema_exposes_typed_choices_and_aliases():
    schema = EModelOptimizationScanConfig.model_json_schema()
    parameter_schema = schema["$defs"]["EModelOptimisationParameters"]
    mechanisms_schema = schema["$defs"]["MechanismsBySectionList"]
    base_schema = parameter_schema["properties"]["base_parameters"]
    mechanism_schema = mechanisms_schema["properties"]["mechanism_regions"]

    assert base_schema["propertyNames"] == {"$ref": "#/$defs/SectionListName"}
    assert schema["$defs"]["SectionListName"]["enum"] == [
        "all",
        "alldend",
        "somadend",
        "allnoaxon",
        "somaxon",
        "allact",
        "somatic",
        "basal",
        "apical",
        "axonal",
        "myelinated",
    ]
    assert base_schema["alias_expansions"]["all"] == [
        "apical",
        "basal",
        "somatic",
        "axonal",
    ]
    assert any(choice["name"] == "myelinated" for choice in base_schema["choices"])
    legacy_choices = {
        choice["name"]: choice
        for choice in base_schema["availability_by_axon_modifier"]["replace_axon_legacy"]
    }
    no_replacement_choices = {
        choice["name"]: choice for choice in base_schema["availability_by_axon_modifier"]["none"]
    }
    assert legacy_choices["myelinated"]["available"] is False
    assert no_replacement_choices["myelinated"]["available"] is False
    assert no_replacement_choices["myelinated"]["availability"] == "unavailable"
    assert mechanism_schema["alias_expansions"] == base_schema["alias_expansions"]
    assert set(schema["$defs"]["AxonModifier"]["enum"]) == {
        "replace_axon_with_taper",
        "replace_axon_legacy",
        "replace_axon_olfactory_bulb",
        "bluepyopt_replace_axon",
        "none",
    }


def test_modifier_validation_rejects_stale_myelinated_rows_with_path():
    reference = IonChannelModelFromID(id_str="icm-1")
    stale_selection = ParametersSelection(
        ion_channel_models=(reference,),
        base_parameters={
            "myelinated": {
                "cm": ParameterSelection(value=OptimizationValue(value=0.02)),
            }
        },
    )

    with pytest.raises(
        ValueError,
        match=r"emodel_optimisation_parameters\.base_parameters\.myelinated.*unavailable",
    ):
        EModelOptimizationScanConfig.model_validate(
            _scan_config_data(
                morphology_settings={"axon_modifier": "replace_axon_legacy"},
                parameters_selection=stale_selection,
            )
        )


def test_recipe_contains_multiloc_map_without_all_alias():
    recipes = build_optimization_recipe("test", "L5", "morphology.swc", "params.json")

    assert recipes["test"]["multiloc_map"] == DEFAULT_SECTION_LIST_CATALOG.to_recipe_multiloc_map()
    assert "all" not in recipes["test"]["multiloc_map"]
    assert recipes["test"]["params"] == "config/params/params.json"


def test_optimization_settings_serialize_bluepyemodel_recipe_fields():
    settings = OptimizationSettings(
        optimiser="MO-CMA",
        optimisation_checkpoint_period=30.0,
        use_stagnation_criterion=False,
        threshold_efeature_std=0.2,
        minimum_protocol_delay=0.5,
        stochasticity=("idrest",),
        validation_function="mean_score",
        validation_protocols=("APWaveform_300",),
        neuron_dt=0.025,
        cvode_minstep=0.001,
        use_params_for_seed=False,
        current_precision=0.001,
        max_threshold_voltage=-20.0,
        strict_holding_bounds=False,
        max_depth_holding_search=8,
        max_depth_threshold_search=11,
        spikecount_timeout=25.0,
        plot_currentscape=False,
        plot_traces=False,
        phase_plot_settings=PhasePlotSettings(
            prot_names=("idrest",),
            amplitude=150.0,
            amp_window=2.0,
            relative_amp=False,
        ),
    )
    params = OptimizationParams(offspring_size=30, sigma=0.3, weight_hv=0.7)

    recipe_settings = settings.to_dict(params)

    assert recipe_settings["optimiser"] == "MO-CMA"
    assert recipe_settings["optimisation_params"] == {
        "offspring_size": 30,
        "sigma": 0.3,
        "weight_hv": 0.7,
    }
    assert recipe_settings["optimisation_checkpoint_period"] == pytest.approx(30.0)
    assert recipe_settings["use_stagnation_criterion"] is False
    assert recipe_settings["threshold_efeature_std"] == pytest.approx(0.2)
    assert recipe_settings["stochasticity"] == ["idrest"]
    assert recipe_settings["validation_function"] == "mean_score"
    assert recipe_settings["validation_protocols"] == ["APWaveform_300"]
    assert recipe_settings["plot_currentscape"] is False
    assert recipe_settings["plot_traces"] is False
    assert recipe_settings["phase_plot_settings"]["prot_names"] == ["idrest"]
    assert "seed" not in recipe_settings


def test_optimization_params_reject_incompatible_algorithm_fields():
    with pytest.raises(ValueError, match="only valid for SO-CMA or MO-CMA"):
        OptimizationParams(sigma=0.4).to_dict("IBEA")
    with pytest.raises(ValueError, match="only valid for IBEA"):
        OptimizationParams(eta=10.0).to_dict("MO-CMA")
    with pytest.raises(ValueError, match="only valid for MO-CMA"):
        OptimizationParams(weight_hv=0.5).to_dict("SO-CMA")


def test_optimization_params_reject_single_member_cma_population():
    with pytest.raises(ValueError, match="at least 2"):
        OptimizationParams(offspring_size=1).to_dict("SO-CMA")
    with pytest.raises(ValueError, match="at least 2"):
        OptimizationParams(offspring_size=[1, 20]).to_dict("MO-CMA")


@pytest.mark.parametrize(
    ("optimiser", "optimization_params", "message"),
    [
        ("IBEA", {"sigma": 0.4}, "only valid for SO-CMA or MO-CMA"),
        ("MO-CMA", {"eta": 10.0}, "only valid for IBEA"),
        ("SO-CMA", {"weight_hv": 0.5}, "only valid for MO-CMA"),
    ],
)
def test_config_rejects_incompatible_optimizer_fields(optimiser, optimization_params, message):
    with pytest.raises(ValueError, match=message):
        EModelOptimizationScanConfig.model_validate(
            _scan_config_data(
                optimization_settings={"optimiser": optimiser},
                optimization_params=optimization_params,
            )
        )


def test_recipe_file_contains_artifact_paths_and_pipeline_settings(tmp_path):
    settings = OptimizationSettings(plot_currentscape=False)
    recipes = build_optimization_recipe("test", "L5", "morphology.swc", "params.json")
    recipes = emodel_building_utils.update_pipeline_settings(
        recipes,
        emodel="test",
        overrides=settings.to_dict(OptimizationParams()),
    )
    recipe_path = tmp_path / "config" / "recipes.json"
    create_dir(recipe_path.parent)
    write_json(recipes, recipe_path, indent=4)

    written = json.loads(recipe_path.read_text(encoding="utf-8"))["test"]
    assert written["features"] == "config/features/test.json"
    assert written["params"] == "config/params/params.json"
    assert written["morph_path"] == "./morphologies/"
    assert written["pipeline_settings"]["plot_currentscape"] is False
    assert written["pipeline_settings"]["optimisation_params"] == {"offspring_size": 20}


def test_feature_and_morphology_staging_write_expected_paths(tmp_path):
    class FakeExtractionTaskResult:
        def download_asset_by_label(self, asset_label, *, dest_dir, db_client):
            del asset_label, db_client
            path = dest_dir / "downloaded-features.json"
            path.write_text('{"features": []}', encoding="utf-8")
            return path

    class FakeMorphology:
        id_str = "morphology-1"

        def swc_file_content(self, *, db_client):
            del db_client
            return "1  soma  0 0 0 1 -1\\n"

    config = SimpleNamespace(
        initialize=SimpleNamespace(emodel="test"),
        inputs=SimpleNamespace(morphology=FakeMorphology()),
    )
    task = EModelOptimizationTask.model_construct(config=config)

    features_path = task._download_extraction_features(
        FakeExtractionTaskResult(),
        tmp_path,
        object(),
    )
    morphology_filename = task._stage_morphology(tmp_path, object())

    assert features_path == tmp_path / "config" / "features" / "test.json"
    assert features_path.read_text(encoding="utf-8") == '{"features": []}'
    assert morphology_filename == "morphology-1.swc"
    assert (tmp_path / "morphologies" / morphology_filename).read_text(encoding="utf-8") == (
        "1  soma  0 0 0 1 -1\\n"
    )


def test_overlapping_rows_warn_and_preserve_broad_to_narrow_order(caplog):
    selection = ParametersSelection(
        base_parameters={
            "all": {"cm": ParameterSelection(value=OptimizationValue(value=1.0))},
            "apical": {"cm": ParameterSelection(value=OptimizationValue(value=2.0))},
        }
    )
    config = SimpleNamespace(
        parameters_selection=selection,
        distance_dependent_distributions={"uniform": UniformDistanceDependentDistribution()},
    )

    params = build_params_definition(params_definition_input_from_config(config), {})

    cm_rows = [parameter for parameter in _parameter_rows(params) if parameter["name"] == "cm"]
    assert [parameter["location"] for parameter in cm_rows] == ["all", "apical"]
    assert len(cm_rows) == 2
    assert "Overlapping parameter rows" in caplog.text


def test_optimization_value_validates_fixed_and_bounds_modes():
    assert OptimizationValue(value=3.0).model_dump()["value"] == pytest.approx(3.0)
    assert OptimizationValue(mode="bounds", bounds=(1.0, 2.0)).model_dump()["bounds"] == (
        1.0,
        2.0,
    )

    with pytest.raises(ValueError, match="fixed optimization value"):
        OptimizationValue()
    with pytest.raises(ValueError, match="must not exceed"):
        OptimizationValue(mode="bounds", bounds=(2.0, 1.0))
    with pytest.raises(ValueError, match="cannot be provided"):
        OptimizationValue(mode="bounds", value=1.0)


def test_legacy_base_defaults_are_prepopulated_but_editable():
    selection = ParametersSelection()

    assert selection.global_parameters["v_init"].value.value == pytest.approx(-80.0)
    assert selection.global_parameters["celsius"].value.value == pytest.approx(34.0)
    assert selection.base_parameters["all"]["Ra"].value.value == pytest.approx(100.0)
    assert selection.base_parameters["all"]["g_pas"].value.bounds == (1e-5, 6e-5)
    assert selection.base_parameters["all"]["e_pas"].value.bounds == (-95.0, -60.0)
    assert selection.base_parameters["myelinated"]["cm"].value.value == pytest.approx(0.02)

    edited = selection.model_copy(
        update={
            "global_parameters": {
                **selection.global_parameters,
                "v_init": GlobalParameterSelection(value=OptimizationValue(value=-75.0)),
            }
        }
    )
    assert edited.global_parameters["v_init"].value.value == pytest.approx(-75.0)


def test_ion_channel_metadata_normalizes_mapping_entries_and_units():
    normalized = normalize_ion_channel_model(_model_entity())

    assert normalized.nmodl_suffix == "NaTg"
    assert normalized.find_variable("gNa").name == "gNa_NaTg"
    assert normalized.find_variable("gNa").units == "S/cm2"
    assert normalized.find_variable("ena").variable_type == "GLOBAL"
    assert normalized.ion_names == frozenset({"na"})
    assert [variable.name for variable in normalized.variables] == [
        "gNa_NaTg",
        "vshift_NaTg",
        "ena_NaTg",
    ]


def test_params_builder_emits_complete_deterministic_definition():
    config, _, normalized = _compiler_fixture()
    params = build_params_definition(params_definition_input_from_config(config), normalized)

    assert "morphology" not in params
    assert params["mechanisms"] == {
        "apical": {"mech": ["NaTg"]},
        "somatic": {"mech": ["NaTg"]},
        "all": {"mech": ["pas"]},
    }
    assert params["distributions"] == {
        "decay": {
            "fun": "math.exp({distance}*{constant})*{value}",
            "parameters": ["constant"],
        }
    }
    parameter_rows = _parameter_rows(params)
    assert [(parameter["name"], parameter["location"]) for parameter in parameter_rows] == [
        ("ena_NaTg", "global"),
        ("v_init", "global"),
        ("constant", "distribution_decay"),
        ("Ra", "all"),
        ("e_pas", "all"),
        ("g_pas", "all"),
        ("gNa_NaTg", "apical"),
        ("vshift_NaTg", "apical"),
        ("gNa_NaTg", "somatic"),
    ]
    assert parameter_rows[2]["value"] == [-0.1, 0.0]
    assert parameter_rows[4]["value"] == [-95.0, -60.0]
    assert parameter_rows[5]["value"] == [1e-5, 6e-5]
    assert parameter_rows[8]["dist"] == "decay"
    assert "distribution" not in parameter_rows[8]
    assert "distribution" not in parameter_rows[7]


def test_params_builder_omits_reversal_potential_without_assigned_ion():
    reference = IonChannelModelFromID(id_str="icm-1")
    selection = ParametersSelection(
        ion_channel_models=(reference,),
        mechanism_regions={
            "apical": (
                MechanismRegionSelection(
                    ion_channel_model=reference,
                    parameters={
                        "gNa": ParameterSelection(
                            value=OptimizationValue(mode="bounds", bounds=(0.0, 1.0)),
                        ),
                    },
                ),
            ),
        },
    )
    config = SimpleNamespace(
        parameters_selection=selection,
        distance_dependent_distributions={"uniform": UniformDistanceDependentDistribution()},
    )
    normalized = {"icm-1": normalize_ion_channel_model(_model_entity())}

    params = build_params_definition(params_definition_input_from_config(config), normalized)

    parameter_rows = _parameter_rows(params)
    regional_names = {
        parameter["name"]
        for parameter in parameter_rows
        if parameter["location"] in {"apical", "axonal", "basal", "somatic"}
    }
    ena_locations = {
        parameter["location"] for parameter in parameter_rows if parameter["name"] == "ena"
    }
    assert "ena" in regional_names
    assert ena_locations == {"apical"}
    assert "ek" not in regional_names


def test_params_definition_is_accepted_by_bluepyemodel_parser():
    config, _, normalized = _compiler_fixture()
    params = build_params_definition(params_definition_input_from_config(config), normalized)

    neuron_configuration = NeuronModelConfiguration()
    neuron_configuration.init_from_legacy_dict(params, {"name": "test-morphology"})

    assert neuron_configuration.morphology.name == "test-morphology"
    assert neuron_configuration.mechanism_names == {"NaTg", "pas"}
    assert neuron_configuration.distribution_names == {"decay", "uniform"}
    assert any(
        parameter.name == "gNa_NaTg" and parameter.distribution == "decay"
        for parameter in neuron_configuration.parameters
    )


def test_params_builder_rejects_missing_bounds_distribution_and_myelin():
    config, reference, normalized = _compiler_fixture()

    config.parameters_selection.base_parameters = {
        "all": {"Ra": ParameterSelection(value=OptimizationValue(mode="bounds"))}
    }
    with pytest.raises(ValueError, match="no bounds"):
        build_params_definition(
            params_definition_input_from_config(config), normalized, bounds_fallbacks={}
        )

    config, _, normalized = _compiler_fixture()
    config.parameters_selection.base_parameters["all"]["Ra"].distribution = "missing"
    with pytest.raises(ValueError, match="undeclared distribution"):
        build_params_definition(params_definition_input_from_config(config), normalized)

    myelinated_selection = ParametersSelection(
        ion_channel_models=(reference,),
        base_parameters={
            "myelinated": {"cm": ParameterSelection(value=OptimizationValue(value=0.02))}
        },
    )
    myelinated_config = SimpleNamespace(
        parameters_selection=myelinated_selection,
        distance_dependent_distributions={"uniform": UniformDistanceDependentDistribution()},
    )
    with pytest.raises(ValueError, match="no myelinated section list"):
        build_params_definition(
            params_definition_input_from_config(myelinated_config),
            normalized,
            morphology_capabilities=MorphologyCapabilities(has_myelinated=False),
        )
    with pytest.raises(ValueError, match="did not establish a myelinated section list"):
        build_params_definition(
            params_definition_input_from_config(myelinated_config),
            normalized,
            morphology_capabilities=MorphologyCapabilities(has_myelinated=None),
        )


def test_registration_error_names_the_missing_entitysdk_package():
    if importlib.util.find_spec("entitysdk.registration") is not None:
        pytest.skip("installed EntitySDK provides the registration helpers")

    with pytest.raises(RuntimeError, match=r"entitysdk\.registration"):
        EModelOptimizationTask.register_output_entities(None, Path(), None)


def test_morph_modifiers_survive_repeated_evaluator_builds():
    model_configuration = SimpleNamespace(morphology=SimpleNamespace(path="cell.swc"))

    # Sharing one list across builds is what broke the HOC export: BluePyEModel rewrites
    # the list in place, so the second build never resolves the HOC snippet again.
    shared = MorphologySettings().to_pipeline_settings()["morph_modifiers"]
    first = define_morphology(model_configuration, morph_modifiers=shared)
    second = define_morphology(model_configuration, morph_modifiers=shared)
    assert isinstance(first.morph_modifiers_hoc[0], str)
    assert second.morph_modifiers_hoc[0] is None

    # Copying per build keeps every HOC snippet that export_emodels_hoc concatenates, and
    # leaves the access point's own pipeline settings free of resolved callables.
    pipeline_settings = SimpleNamespace(**MorphologySettings().to_pipeline_settings())
    builds = [
        define_morphology(
            model_configuration,
            morph_modifiers=_fresh_morph_modifiers(pipeline_settings),
        )
        for _ in range(3)
    ]
    assert all(isinstance(build.morph_modifiers_hoc[0], str) for build in builds)
    assert pipeline_settings.morph_modifiers == ["replace_axon_with_taper"]


def test_fresh_morph_modifiers_preserves_empty_and_default_selections():
    without_replacement = MorphologySettings(axon_modifier="none").to_pipeline_settings()

    assert _fresh_morph_modifiers(SimpleNamespace(**without_replacement)) == []
    # None must stay None so BluePyEModel keeps applying its own default modifier.
    assert _fresh_morph_modifiers(SimpleNamespace(morph_modifiers=None)) is None


def test_local_mechanism_metadata_is_tagged_from_entitycore():
    normalized = {"icm-1": normalize_ion_channel_model(_model_entity())}
    mechanism = MechanismConfiguration(name="NaTg", location=None)

    tagged = _tag_local_mechanisms([mechanism], normalized)
    configuration = NeuronModelConfiguration(available_mechanisms=tagged)
    configuration.add_mechanism(
        "NaTg",
        "somatic",
        version=None,
        temperature=34,
        ljp_corrected=False,
    )

    assert tagged is not None
    assert tagged[0].temperature == 34
    assert tagged[0].ljp_corrected is False
    assert tagged[0].id == "icm-1"
    assert configuration.mechanism_names == {"NaTg"}


def test_stage_mechanisms_deduplicates_nested_models(tmp_path, monkeypatch):
    config, _, _ = _compiler_fixture()
    task = EModelOptimizationTask.model_construct(config=config)
    downloaded = []

    def download_asset(self, *, dest_dir, db_client):
        del dest_dir, db_client
        downloaded.append(self.id_str)

    monkeypatch.setattr(IonChannelModelFromID, "download_asset", download_asset)

    task._stage_mechanisms(tmp_path, object())

    assert downloaded == ["icm-1"]


def test_hand_authored_root_parameter_configuration_builds_and_stages_artifacts(tmp_path):
    root_payload = {
        "mechanisms": {
            "ion_channel_models": [{"id_str": "icm-1"}],
            "mechanism_regions": {
                "apical": [
                    {
                        "ion_channel_model": {"id_str": "icm-1"},
                        "parameters": {
                            "gNa": {
                                "value": {"mode": "bounds", "bounds": [0.0, 1.0]},
                                "distribution": "decay",
                            }
                        },
                    }
                ]
            },
        },
        "global_parameters": {
            "v_init": {"value": {"mode": "fixed", "value": -80.0}},
            "ena": {
                "value": {"mode": "fixed", "value": 50.0},
                "ion_channel_model": {"id_str": "icm-1"},
            },
        },
        "base_parameters": {
            "all": {
                "Ra": {"value": {"mode": "fixed", "value": 100.0}},
                "g_pas": {"value": {"mode": "bounds", "bounds": [1e-5, 6e-5]}},
                "e_pas": {"value": {"mode": "bounds", "bounds": [-95.0, -60.0]}},
            }
        },
        "distribution_parameters": {
            "decay": {
                "constant": {"mode": "bounds", "bounds": [-0.1, 0.0]},
            }
        },
    }
    data = _scan_config_data()
    data.pop("emodel_optimisation_parameters")
    data["emodel_optimisation_parameters"] = root_payload
    data["distance_dependent_distributions"] = {
        "decay": {
            "name": "decay",
            "function": "math.exp({distance}*{constant})*{value}",
            "parameters": ["constant"],
        }
    }
    config = EModelOptimizationScanConfig.model_validate(data)
    normalized = {"icm-1": normalize_ion_channel_model(_model_entity())}
    capabilities = MorphologyCapabilities(
        has_myelinated=True,
        available_physical_sections=("somatic", "basal", "apical", "axonal"),
    )
    task = EModelOptimizationTask.model_construct(config=config)
    artifacts = task._build_artifacts(
        db_client=object(),
        mtype="L5",
        morph_filename="morphology.swc",
        morphology_capabilities=capabilities,
        normalized_models=normalized,
    )
    params_path = tmp_path / "config" / "params" / "params.json"
    params_path.parent.mkdir(parents=True)
    params_path.write_text(json.dumps({"parameters": ["stale"]}), encoding="utf-8")

    artifacts.write(tmp_path)

    assert json.loads(params_path.read_text(encoding="utf-8")) == build_params_definition(
        params_definition_input_from_config(config),
        normalized,
        morphology_capabilities=capabilities,
    )
    assert json.loads((tmp_path / "config" / "recipes.json").read_text(encoding="utf-8"))["test"][
        "morphology"
    ] == [["L5", "morphology.swc"]]


def test_parameter_group_view_matches_figma_card_order():
    config, _, _ = _compiler_fixture()

    groups = config.parameters_selection.parameter_group_view

    # Global, Distribution parameters, then configured regions in display order:
    # "all" (base_parameters) and "apical"/"somatic" (mechanism_regions).
    assert [group.key for group in groups] == ["global", "distribution", "all", "somatic", "apical"]
    assert [group.kind for group in groups] == [
        "global",
        "distribution",
        "region",
        "region",
        "region",
    ]
    global_group, distribution_group, all_group, somatic_group, apical_group = groups
    assert global_group.count_label == "2 parameters"
    assert distribution_group.count_label == "1 parameters"
    assert all_group.count_label == "0 channels assigned"
    assert apical_group.count_label == "1 channels assigned"
    assert somatic_group.count_label == "1 channels assigned"
    assert "parameter_group_view" not in config.parameters_selection.model_dump(mode="json")


def test_distribution_group_rows_are_editable_not_read_only():
    config, _, _ = _compiler_fixture()

    rows = config.parameters_selection.parameter_rows("distribution")

    assert [(row.key, row.location, row.editable) for row in rows] == [
        ("distribution_decay.constant", "distribution_decay", True)
    ]
    assert rows[0].name == "constant"
    assert rows[0].distribution == "decay"
    assert rows[0].value.bounds == (-0.1, 0.0)


def test_global_group_rows_list_ordinary_globals_only():
    config, _, _ = _compiler_fixture()

    rows = config.parameters_selection.parameter_rows("global")

    assert [row.key for row in rows] == ["ena", "v_init"]
    assert all(row.kind == "global" for row in rows)


def test_region_group_rows_include_base_and_mechanism_parameters():
    config, _, _ = _compiler_fixture()

    apical_rows = config.parameters_selection.parameter_rows("apical")

    assert {row.name for row in apical_rows} == {"gNa", "vshift"}
    assert all(row.kind == "region" for row in apical_rows)
    assert all(row.mechanism == "icm-1" for row in apical_rows)


def test_parameter_group_view_omits_unconfigured_regions():
    selection = ParametersSelection()

    groups = selection.parameter_group_view

    # Defaults configure base parameters under all, myelinated, somatic, axonal,
    # apical, and basal; region order follows the catalog's display order.
    assert [group.key for group in groups] == [
        "global",
        "distribution",
        "all",
        "myelinated",
        "somatic",
        "axonal",
        "apical",
        "basal",
    ]


def test_build_params_definition_unchanged_by_parameter_group_view():
    """The Figma-shaped projection must never influence the compiled params."""
    config, _, normalized = _compiler_fixture()

    before = build_params_definition(params_definition_input_from_config(config), normalized)
    # Touch the projection to ensure it has no side effects on the config.
    _ = config.parameters_selection.parameter_group_view
    _ = config.parameters_selection.parameter_rows("global")
    after = build_params_definition(params_definition_input_from_config(config), normalized)

    assert before == after


def test_fallback_bounds_resolve_context_specific_parameter_names():
    config, _, normalized = _compiler_fixture()
    config.parameters_selection.mechanism_regions["apical"][0].parameters[
        "gNa"
    ].value = OptimizationValue(mode="bounds")
    config.parameters_selection.distribution_parameters["decay"]["constant"] = OptimizationValue(
        mode="bounds"
    )

    params = build_params_definition(
        params_definition_input_from_config(config),
        normalized,
        bounds_fallbacks={
            "g_pas": (1e-5, 6e-5),
            "e_pas": (-95.0, -60.0),
            "gNa_NaTg": (0.0, 1.0),
            "distribution_decay.constant": (-0.2, 0.0),
        },
    )

    by_name_and_location = {
        (parameter["name"], parameter["location"]): parameter["value"]
        for parameter in _parameter_rows(params)
    }
    assert by_name_and_location["gNa_NaTg", "apical"] == [0.0, 1.0]
    assert by_name_and_location["constant", "distribution_decay"] == [-0.2, 0.0]


def _fake_section(section_type):
    section = SimpleNamespace()
    section.type = section_type
    return section


def test_morphology_preflight_applies_modifier_capabilities(tmp_path, monkeypatch):
    morphio_type = morphio.SectionType
    axon_sections = [_fake_section(morphio_type.axon) for _ in range(3)]

    class FakeMorphology:
        sections = (*axon_sections, _fake_section(morphio_type.soma))

    morphology_path = tmp_path / "morphology.swc"
    morphology_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        morphology_preflight,
        "load_morphology_nrn_order",
        lambda _path: FakeMorphology(),
    )

    tapered = morphology_preflight.preflight_morphology(
        morphology_path,
        "replace_axon_with_taper",
    )
    no_replacement = morphology_preflight.preflight_morphology(
        morphology_path,
        "none",
    )

    assert tapered == MorphologyCapabilities(
        has_myelinated=True,
        axonal_section_count=3,
        available_physical_sections=("somatic", "axonal"),
    )
    assert no_replacement == MorphologyCapabilities(
        has_myelinated=None,
        axonal_section_count=3,
        available_physical_sections=("somatic", "axonal"),
    )


def test_morphology_preflight_detects_soma_points_without_soma_section(tmp_path, monkeypatch):
    morphio_type = morphio.SectionType
    axon_sections = [_fake_section(morphio_type.axon) for _ in range(3)]

    class FakeMorphology:
        sections = tuple(axon_sections)
        soma = SimpleNamespace(points=((0.0, 0.0, 0.0),))

    morphology_path = tmp_path / "morphology.swc"
    morphology_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        morphology_preflight,
        "load_morphology_nrn_order",
        lambda _path: FakeMorphology(),
    )

    capabilities = morphology_preflight.preflight_morphology(
        morphology_path,
        "replace_axon_with_taper",
    )

    assert capabilities.available_physical_sections == ("somatic", "axonal")


def test_morphology_preflight_reports_available_physical_sections_in_catalog_order(
    tmp_path, monkeypatch
):
    morphio_type = morphio.SectionType
    axon_sections = [_fake_section(morphio_type.axon) for _ in range(3)]

    class FakeMorphology:
        sections = (
            _fake_section(morphio_type.apical_dendrite),
            *axon_sections,
            _fake_section(morphio_type.soma),
            _fake_section(morphio_type.basal_dendrite),
        )

    morphology_path = tmp_path / "morphology.swc"
    morphology_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        morphology_preflight,
        "load_morphology_nrn_order",
        lambda _path: FakeMorphology(),
    )

    capabilities = morphology_preflight.preflight_morphology(
        morphology_path,
        "replace_axon_with_taper",
    )

    assert capabilities.available_physical_sections == ("somatic", "basal", "apical", "axonal")


def test_params_builder_rejects_region_the_morphology_does_not_provide():
    config, _, normalized = _compiler_fixture()

    axon_only_capabilities = MorphologyCapabilities(
        has_myelinated=True,
        axonal_section_count=3,
        available_physical_sections=("somatic", "axonal"),
    )

    with pytest.raises(ValueError, match=r"no source sections for \['apical', 'basal'\]"):
        build_params_definition(
            params_definition_input_from_config(config),
            normalized,
            morphology_capabilities=axon_only_capabilities,
        )


def test_morphology_capabilities_without_preflight_skips_region_check():
    """Direct construction (no preflight) must not spuriously reject configured regions."""
    config, _, normalized = _compiler_fixture()

    # available_physical_sections defaults to (): "not inspected".
    params = build_params_definition(
        params_definition_input_from_config(config),
        normalized,
        morphology_capabilities=MorphologyCapabilities(has_myelinated=True),
    )

    assert params["parameters"]


def test_morphology_preflight_rejects_insufficient_source_axon_sections(tmp_path, monkeypatch):
    class FakeSection:
        type = morphio.SectionType.axon

    class FakeMorphology:
        sections = (FakeSection(), FakeSection())

    morphology_path = tmp_path / "morphology.swc"
    morphology_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        morphology_preflight,
        "load_morphology_nrn_order",
        lambda _path: FakeMorphology(),
    )

    with pytest.raises(ValueError, match="requires at least 3"):
        morphology_preflight.preflight_morphology(
            morphology_path,
            "replace_axon_with_taper",
        )


def test_entitysdk_validation_status_keyword_supports_both_spellings():
    def correct(*, validation_result_status):
        del validation_result_status

    def historical(*, validateion_result_status):
        del validateion_result_status

    assert _validation_status_keyword(correct) == "validation_result_status"
    assert _validation_status_keyword(historical) == "validateion_result_status"


def test_root_emodel_optimisation_parameters_normalizes_to_canonical_selection():
    reference = IonChannelModelFromID(id_str="icm-1")
    root = EModelOptimisationParameters(
        mechanisms=MechanismsBySectionList(
            ion_channel_models=(reference,),
            mechanism_regions={
                "apical": (
                    MechanismRegionSelection(
                        ion_channel_model=reference,
                        parameters={
                            "gNa": ParameterSelection(
                                value=OptimizationValue(mode="bounds", bounds=(0.0, 1.0)),
                            )
                        },
                    ),
                )
            },
        ),
        base_parameters={},
    )
    data = _scan_config_data()
    data.pop("emodel_optimisation_parameters")
    data["emodel_optimisation_parameters"] = root

    config = EModelOptimizationScanConfig.model_validate(data)
    canonical = config.parameters_selection

    assert canonical.ion_channel_models == (reference,)
    assert canonical.mechanism_regions["apical"][0].parameters["gNa"].value.bounds == (
        0.0,
        1.0,
    )
    serialized = config.model_dump(mode="json")
    assert "emodel_optimisation_parameters" in serialized
    assert "parameters_selection" not in serialized


def test_single_config_asset_round_trips_plural_parameters_field(tmp_path):
    config = EModelOptimizationSingleConfig.model_validate(_scan_config_data())
    config.idx = 0
    config.single_coordinate_scan_params = SingleCoordinateScanParams()
    asset_path = tmp_path / "config.json"

    config.serialize(asset_path)
    payload = json.loads(asset_path.read_text(encoding="utf-8"))
    restored = deserialize_obi_object_from_json_data(payload)

    assert payload["emodel_optimisation_parameters"]["mechanisms"]["ion_channel_models"] == [
        {"id_str": "icm-1", "type": "IonChannelModelFromID"}
    ]
    assert "parameters_selection" not in payload
    assert isinstance(restored, EModelOptimizationSingleConfig)
    assert restored.emodel_optimisation_parameters.mechanisms.ion_channel_models == (
        IonChannelModelFromID(id_str="icm-1"),
    )


def test_legacy_parameters_selection_input_is_migrated_to_root_field():
    config = EModelOptimizationScanConfig.model_validate(
        _scan_config_data(
            parameters_selection=ParametersSelection(
                ion_channel_models=(IonChannelModelFromID(id_str="icm-1"),),
                base_parameters={},
            )
        )
    )

    assert config.emodel_optimisation_parameters.mechanisms.ion_channel_models == (
        IonChannelModelFromID(id_str="icm-1"),
    )
    assert "parameters_selection" not in config.model_dump(mode="json")


def test_supplying_both_legacy_and_root_parameter_fields_is_rejected():
    legacy_selection = ParametersSelection(
        ion_channel_models=(IonChannelModelFromID(id_str="icm-1"),),
        base_parameters={},
    )
    root_selection = EModelOptimisationParameters(
        mechanisms=MechanismsBySectionList(
            ion_channel_models=(IonChannelModelFromID(id_str="icm-1"),),
        ),
        base_parameters={},
    )
    data = _scan_config_data(
        parameters_selection=legacy_selection.model_dump(mode="json"),
    )
    data["emodel_optimisation_parameters"] = root_selection.model_dump(mode="json")

    with pytest.raises(ValueError, match="Use either emodel_optimisation_parameters or"):
        EModelOptimizationScanConfig.model_validate(data)


def test_root_parameter_configuration_preserves_compiler_output():
    legacy_config, _, normalized = _compiler_fixture()
    root = EModelOptimisationParameters.from_parameters_selection(
        legacy_config.parameters_selection
    )
    data = _scan_config_data()
    data.pop("emodel_optimisation_parameters")
    data["emodel_optimisation_parameters"] = root
    data["distance_dependent_distributions"] = {
        "decay": legacy_config.distance_dependent_distributions["decay"]
    }

    new_config = EModelOptimizationScanConfig.model_validate(data)

    assert build_params_definition(
        params_definition_input_from_config(new_config), normalized
    ) == build_params_definition(
        params_definition_input_from_config(legacy_config),
        normalized,
    )


def test_mechanism_filing_validates_duplicates_and_unselected_models_directly():
    selected = IonChannelModelFromID(id_str="icm-1")

    with pytest.raises(ValueError, match="must not contain duplicate entity IDs"):
        MechanismsBySectionList(ion_channel_models=(selected, selected))

    with pytest.raises(ValueError, match="must also be listed in ion_channel_models"):
        MechanismsBySectionList(
            ion_channel_models=(selected,),
            mechanism_regions={
                "somatic": (
                    MechanismRegionSelection(
                        ion_channel_model=IonChannelModelFromID(id_str="icm-2"),
                    ),
                )
            },
        )


def test_root_parameter_block_validates_global_model_reference_directly():
    selected = IonChannelModelFromID(id_str="icm-1")

    with pytest.raises(ValueError, match="Global parameter 'ena' source must also be listed"):
        EModelOptimisationParameters(
            mechanisms=MechanismsBySectionList(ion_channel_models=(selected,)),
            global_parameters={
                "ena": GlobalParameterSelection(
                    value=OptimizationValue(value=50.0),
                    ion_channel_model=IonChannelModelFromID(id_str="icm-2"),
                )
            },
            base_parameters={},
        )


def test_no_replacement_keeps_myelinated_choice_unavailable():
    settings = MorphologySettings(axon_modifier=AxonModifier.none)
    myelinated_choice = {choice.name: choice for choice in settings.section_list_choices()}[
        "myelinated"
    ]

    assert settings.expected_myelinated is None
    assert "myelinated" not in settings.available_section_list_names()
    assert not myelinated_choice.available
    assert myelinated_choice.availability == SectionListAvailability.unavailable


@pytest.mark.parametrize("field_name", ["base_parameters", "mechanism_regions"])
def test_no_replacement_rejects_myelinated_configuration_rows(field_name):
    reference = IonChannelModelFromID(id_str="icm-1")
    if field_name == "base_parameters":
        selection = ParametersSelection(
            ion_channel_models=(reference,),
            base_parameters={
                "myelinated": {
                    "cm": ParameterSelection(value=OptimizationValue(value=0.02)),
                }
            },
        )
    else:
        selection = ParametersSelection(
            ion_channel_models=(reference,),
            mechanism_regions={
                "myelinated": (MechanismRegionSelection(ion_channel_model=reference),)
            },
            base_parameters={},
        )
    data = _scan_config_data()
    data.pop("emodel_optimisation_parameters")
    data["morphology_settings"] = {"axon_modifier": AxonModifier.none.value}
    data["emodel_optimisation_parameters"] = EModelOptimisationParameters.from_parameters_selection(
        selection
    ).model_dump(mode="json")

    with pytest.raises(
        ValueError,
        match=rf"emodel_optimisation_parameters\.{field_name}\.myelinated.*unavailable",
    ):
        EModelOptimizationScanConfig.model_validate(data)


def test_morphology_settings_rejects_removed_source_myelinated_override():
    with pytest.raises(ValueError, match="source_has_myelinated"):
        EModelOptimizationScanConfig.model_validate(
            _scan_config_data(
                morphology_settings={
                    "axon_modifier": AxonModifier.none.value,
                    "source_has_myelinated": True,
                }
            )
        )


def test_legacy_parameters_selection_json_payload_is_migrated():
    legacy = ParametersSelection(
        ion_channel_models=(IonChannelModelFromID(id_str="icm-1"),),
        base_parameters={},
    ).model_dump(mode="json")

    config = EModelOptimizationScanConfig.model_validate(
        _scan_config_data(parameters_selection=legacy)
    )

    assert config.emodel_optimisation_parameters.mechanisms.ion_channel_models == (
        IonChannelModelFromID(id_str="icm-1"),
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"expanded_sections": ()}, "must expand"),
        ({"expanded_sections": ("apical", "apical")}, "duplicate"),
        ({"expanded_sections": ("apical",), "is_composite": True}, "multiple"),
        (
            {"name": "myelinated", "expanded_sections": ("apical",)},
            "may only expand",
        ),
        (
            {
                "name": "somatic",
                "expanded_sections": ("somatic",),
                "requires_myelinated": True,
            },
            "marked as requiring",
        ),
        (
            {
                "expanded_sections": ("apical", "myelinated"),
                "is_composite": True,
            },
            "must not contain myelinated",
        ),
    ],
)
def test_section_list_definition_rejects_invalid_expansions(overrides, message):
    values = {
        "name": "all",
        "label": "All sections",
        "description": "All sections",
        "expanded_sections": ("apical", "basal"),
    }
    values.update(overrides)

    with pytest.raises(ValueError, match=message):
        SectionListDefinition(**values)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"available": True, "availability": SectionListAvailability.unavailable},
            "cannot have unavailable status",
        ),
        (
            {"available": False, "availability": SectionListAvailability.available},
            "must have unavailable status",
        ),
        ({"available": True, "disabled_reason": "not selectable"}, "cannot have a disabled reason"),
        (
            {"available": False, "availability": SectionListAvailability.unavailable},
            "needs a disabled reason",
        ),
    ],
)
def test_section_list_choice_rejects_inconsistent_availability(overrides, message):
    values = {
        "name": "somatic",
        "label": "Somatic",
        "description": "Somatic sections",
    }
    values.update(overrides)

    with pytest.raises(ValueError, match=message):
        SectionListChoice(**values)


def test_section_list_catalog_validates_and_exposes_form_metadata():
    catalog = DEFAULT_SECTION_LIST_CATALOG
    definitions = catalog.definitions

    assert catalog.available("somatic")
    assert not catalog.available("myelinated", axon_modifier=AxonModifier.none)
    assert catalog.schema_choices()[0]["display_order"] == 0
    assert set(catalog.schema_availability_by_modifier()) == {
        modifier.value for modifier in AxonModifier
    }
    assert catalog.to_alias_expansions()["all"] == [
        "apical",
        "basal",
        "somatic",
        "axonal",
    ]

    no_replacement = catalog.choice("myelinated", axon_modifier=AxonModifier.none)
    assert "staged SWC path" in no_replacement.description
    assert "cannot establish" in no_replacement.disabled_reason

    with pytest.raises(ValueError, match="unique names"):
        SectionListCatalog(definitions=(*definitions, definitions[0]))
    with pytest.raises(ValueError, match="missing definitions"):
        SectionListCatalog(definitions=definitions[:-1])
    with pytest.raises(ValueError, match="Unsupported section-list name"):
        catalog.definition("not-a-section-list")


def test_input_entities_resolves_nested_root_mechanism_references(monkeypatch):
    config = EModelOptimizationScanConfig.model_validate(_scan_config_data())

    def fake_entity(self, db_client):
        del db_client
        return self.id_str

    monkeypatch.setattr("obi_one.core.entity_from_id.EntityFromID.entity", fake_entity)

    assert config.input_entities(object()) == ["target", "morphology", "icm-1"]


def test_legacy_migration_preserves_non_mapping_input():
    assert EModelOptimizationScanConfig.migrate_legacy_parameters_selection(None) is None


def test_section_list_choice_exposes_enabled_alias():
    assert DEFAULT_SECTION_LIST_CATALOG.choice("somatic").enabled


def test_stage_traces_returns_only_derivation_trace_ids(tmp_path):
    extraction = SimpleNamespace(
        entity=lambda **_: SimpleNamespace(id="extraction-1"),
    )
    derivations = [
        SimpleNamespace(used=SimpleNamespace(id="trace-1")),
        SimpleNamespace(used=None),
        SimpleNamespace(used=SimpleNamespace(id=None)),
        SimpleNamespace(used=SimpleNamespace(id="trace-2")),
    ]
    search_entity = Mock(return_value=derivations)
    db_client = SimpleNamespace(search_entity=search_entity)
    task = EModelOptimizationTask.model_construct(config=SimpleNamespace())

    assert task._stage_traces(extraction, tmp_path, db_client) == ["trace-1", "trace-2"]
    assert search_entity.call_args.kwargs["query"] == {"generated__id": "extraction-1"}


def test_derive_mtype_uses_first_label_and_handles_empty_mtypes():
    morphology_entity = SimpleNamespace(mtypes=[SimpleNamespace(pref_label="L5_TTPC")])
    morphology = SimpleNamespace(entity=lambda **_: morphology_entity)
    task = EModelOptimizationTask.model_construct(
        config=SimpleNamespace(inputs=SimpleNamespace(morphology=morphology))
    )

    assert task._derive_mtype(object()) == "L5_TTPC"

    morphology.entity = lambda **_: SimpleNamespace(mtypes=[])
    assert task._derive_mtype(object()) is None

    morphology.entity = lambda **_: SimpleNamespace()
    assert task._derive_mtype(object()) is None


def test_execute_uses_morphology_metadata_for_local_access_point(tmp_path, monkeypatch):
    access_points = []

    class FakeLocalAccessPoint:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            access_points.append(self)

    monkeypatch.setattr(
        "bluepyemodel.access_point.local.LocalAccessPoint",
        FakeLocalAccessPoint,
    )
    monkeypatch.setattr(
        "bluepyemodel.optimisation.setup_and_run_optimisation",
        Mock(),
    )
    monkeypatch.setattr(
        "bluepyemodel.optimisation.store_best_model",
        Mock(),
    )
    monkeypatch.setattr(
        "bluepyemodel.export_emodel.export_emodel.export_emodels_sonata",
        Mock(),
    )
    monkeypatch.setattr(task_module.emodel_building_utils, "compile_mechanisms", Mock())
    monkeypatch.setattr(task_module.emodel_building_utils, "run_plot_models", Mock())
    monkeypatch.setattr(task_module, "preflight_morphology", Mock(return_value=object()))
    monkeypatch.setattr(task_module, "resolve_ion_channel_models", Mock(return_value={}))
    monkeypatch.setattr(EModelOptimizationTask, "_derive_mtype", Mock(return_value="L5_TTPC"))
    monkeypatch.setattr(EModelOptimizationTask, "_download_extraction_features", Mock())
    monkeypatch.setattr(
        EModelOptimizationTask,
        "_stage_morphology",
        Mock(return_value="morphology.swc"),
    )
    monkeypatch.setattr(EModelOptimizationTask, "_stage_mechanisms", Mock())
    monkeypatch.setattr(EModelOptimizationTask, "_stage_traces", Mock(return_value=["trace-1"]))
    artifacts = Mock()
    monkeypatch.setattr(EModelOptimizationTask, "_build_artifacts", Mock(return_value=artifacts))

    species = SimpleNamespace(name="Mus musculus")
    brain_region = SimpleNamespace(name="Somatosensory cortex")
    metadata_entities = Mock(return_value=(species, brain_region))
    morphology = SimpleNamespace(metadata_entities=metadata_entities)
    etype = SimpleNamespace(entity=Mock(return_value=SimpleNamespace(pref_label="cADpyr")))
    config = SimpleNamespace(
        coordinate_output_root=tmp_path,
        initialize=SimpleNamespace(emodel="test", etype=etype),
        inputs=SimpleNamespace(target_efeatures=object(), morphology=morphology),
        morphology_settings=SimpleNamespace(axon_modifier="none"),
        parameters_selection=SimpleNamespace(ion_channel_model_references=()),
        optimization_settings=SimpleNamespace(seed=7),
    )
    task = EModelOptimizationTask.model_construct(config=config)

    result = task.execute(db_client=None)

    assert result == tmp_path.resolve()
    assert len(access_points) == 1
    assert access_points[0].kwargs["species"] == "Mus musculus"
    assert access_points[0].kwargs["brain_region"] == "Somatosensory cortex"
    metadata_entities.assert_called_once_with(db_client=None)
    artifacts.write.assert_called_once_with(tmp_path.resolve())


def test_parse_final_json_handles_defaults_placeholder_and_direct_model(tmp_path):
    final_path = tmp_path / "final.json"
    defaults = {
        "name": "test",
        "total_score": 0.0,
        "holding_current": None,
        "threshold_current": None,
        "iteration": "0",
    }
    assert EModelOptimizationTask._parse_final_json(final_path, "test") == defaults

    final_path.write_text("[]", encoding="utf-8")
    assert EModelOptimizationTask._parse_final_json(final_path, "test") == defaults

    final_path.write_text(json.dumps({"other": []}), encoding="utf-8")
    assert EModelOptimizationTask._parse_final_json(final_path, "test") == defaults

    final_path.write_text(
        json.dumps(
            {
                "emodel": [
                    {
                        "score": 2.5,
                        "holding_current": 0.1,
                        "threshold_current": 0.2,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    assert EModelOptimizationTask._parse_final_json(final_path, "test") == {
        "name": "test",
        "total_score": 2.5,
        "holding_current": 0.1,
        "threshold_current": 0.2,
        "iteration": "0",
    }

    final_path.write_text(
        json.dumps({"test": {"fitness": 3.5, "iteration": 7}}),
        encoding="utf-8",
    )
    assert EModelOptimizationTask._parse_final_json(final_path, "test") == {
        "name": "test",
        "total_score": 3.5,
        "holding_current": None,
        "threshold_current": None,
        "iteration": "7",
    }


def test_upload_optimization_assets_uploads_existing_files_and_skips_empty_root(tmp_path):
    recipes_path = tmp_path / "config" / "recipes.json"
    params_path = tmp_path / "config" / "params" / "params.json"
    recipes_path.parent.mkdir(parents=True)
    params_path.parent.mkdir(parents=True)
    recipes_path.write_text("{}", encoding="utf-8")
    params_path.write_text("{}", encoding="utf-8")
    sonata_dir = tmp_path / "export_emodels_sonata"
    sonata_dir.mkdir()
    sonata_file = sonata_dir / "emodel" / "morphology.hoc"
    sonata_file.parent.mkdir()
    sonata_file.write_text("hoc", encoding="utf-8")

    db_client = SimpleNamespace(upload_file=Mock(), upload_directory=Mock())
    EModelOptimizationTask._upload_optimization_assets(tmp_path, db_client, "task-result-1")

    assert db_client.upload_file.call_count == 2
    assert db_client.upload_directory.call_args.kwargs["paths"] == {
        sonata_file.relative_to(sonata_dir): sonata_file
    }

    empty_root = tmp_path / "empty"
    (empty_root / "export_emodels_sonata").mkdir(parents=True)
    EModelOptimizationTask._upload_optimization_assets(empty_root, db_client, "task-result-2")
    assert db_client.upload_file.call_count == 2
    assert db_client.upload_directory.call_count == 1


def test_tag_local_mechanisms_handles_missing_and_unknown_mechanisms():
    normalized = {"icm-1": normalize_ion_channel_model(_model_entity())}
    unknown = MechanismConfiguration(name="Unknown", location=None)

    assert _tag_local_mechanisms(None, normalized) is None
    assert _tag_local_mechanisms([unknown], normalized) == [unknown]


def test_validation_status_keyword_handles_variadic_unsupported_and_uninspectable_callables():
    def variadic(**kwargs):
        del kwargs

    def unsupported(*, unrelated):
        del unrelated

    assert _validation_status_keyword(variadic) == "validation_result_status"
    with pytest.raises(TypeError, match="does not expose"):
        _validation_status_keyword(unsupported)
    assert _validation_status_keyword(object()) == "validation_result_status"


def test_download_extraction_features_keeps_already_named_target(tmp_path):
    class AlreadyNamedExtraction:
        def download_asset_by_label(self, asset_label, *, dest_dir, db_client):
            del asset_label, db_client
            path = dest_dir / "test.json"
            path.write_text("{}", encoding="utf-8")
            return path

    config = SimpleNamespace(initialize=SimpleNamespace(emodel="test"))
    task = EModelOptimizationTask.model_construct(config=config)

    result = task._download_extraction_features(AlreadyNamedExtraction(), tmp_path, object())

    assert result == tmp_path / "config" / "features" / "test.json"
    assert result.read_text(encoding="utf-8") == "{}"


def test_build_artifacts_resolves_models_when_not_supplied(monkeypatch):
    config, reference, normalized = _compiler_fixture()
    task = EModelOptimizationTask.model_construct(config=config)
    db_client = object()
    sentinel = object()
    resolved_calls = []
    build_calls = []

    def resolve(references, client):
        resolved_calls.append((references, client))
        return normalized

    def build(artifact_input, normalized_models):
        build_calls.append((artifact_input, normalized_models))
        return sentinel

    artifact_input_calls = []
    artifact_input = object()

    def to_artifact_input(config_arg, **kwargs):
        artifact_input_calls.append((config_arg, kwargs))
        return artifact_input

    monkeypatch.setattr(task_module, "resolve_ion_channel_models", resolve)
    monkeypatch.setattr(task_module, "build_optimization_artifacts", build)
    monkeypatch.setattr(task_module, "optimization_artifact_input_from_config", to_artifact_input)

    result = task._build_artifacts(
        db_client=db_client,
        mtype="L5",
        morph_filename="morphology.swc",
        morphology_capabilities=None,
    )

    assert result is sentinel
    assert resolved_calls == [((reference,), db_client)]
    assert artifact_input_calls == [
        (
            config,
            {
                "mtype": "L5",
                "morphology_filename": "morphology.swc",
                "morphology_capabilities": None,
            },
        )
    ]
    assert build_calls == [(artifact_input, normalized)]


def test_default_section_list_catalog_is_the_canonical_catalog():
    assert DEFAULT_SECTION_LIST_CATALOG.definitions
    assert DEFAULT_SECTION_LIST_CATALOG.expand("all") == (
        "apical",
        "basal",
        "somatic",
        "axonal",
    )
