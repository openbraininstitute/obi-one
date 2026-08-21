import json
from types import SimpleNamespace

import pytest
from bluepyemodel.model.neuron_model_configuration import NeuronModelConfiguration

from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID
from obi_one.scientific.tasks.emodel_building import _shared
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization import morphology_preflight
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.blocks import (
    CustomDistanceDependentDistribution,
    GlobalParameterSelection,
    MechanismRegionSelection,
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
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.parameter_builder import (
    MorphologyCapabilities,
    build_params_definition,
    normalize_ion_channel_model,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.section_lists import (
    DEFAULT_SECTION_LIST_CATALOG,
    SectionListAvailability,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.task import (
    EModelOptimizationTask,
    _validation_status_keyword,
    build_optimization_recipe,
)


def _scan_config_data(**overrides):
    config_data = {
        "info": {"campaign_name": "test", "campaign_description": "test"},
        "initialize": {"emodel": "test", "etype": {"id_str": "etype"}},
        "target_efeatures": {"id_str": "target"},
        "morphology": {"id_str": "morphology"},
        "parameters_selection": {"ion_channel_models": [{"id_str": "icm-1"}]},
    }
    config_data.update(overrides)
    return config_data


def _model_entity():
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
        "all": ["apical", "basal", "somatic", "axonal"],
        "allact": ["apical", "basal", "somatic", "axonal"],
        "alldend": ["apical", "basal"],
        "allnoaxon": ["apical", "basal", "somatic"],
        "somadend": ["apical", "basal", "somatic"],
        "somaxon": ["axonal", "somatic"],
    }
    assert isinstance(catalog.definitions, tuple)
    assert isinstance(catalog.expand("all"), tuple)


def test_section_list_choices_follow_modifier_capabilities():
    expected = {
        "replace_axon_with_taper": (True, SectionListAvailability.AVAILABLE),
        "replace_axon_olfactory_bulb": (True, SectionListAvailability.AVAILABLE),
        "replace_axon_legacy": (False, SectionListAvailability.UNAVAILABLE),
        "bluepyopt_replace_axon": (False, SectionListAvailability.UNAVAILABLE),
        "none": (False, SectionListAvailability.UNAVAILABLE),
    }

    for modifier, (available, availability) in expected.items():
        choices = {
            choice.name: choice
            for choice in MorphologySettings(axon_modifier=modifier).section_list_choices()
        }
        assert choices["myelinated"].available is available
        assert choices["myelinated"].availability == availability


def test_mechanisms_wizard_steps_are_mapped_in_figma_order():
    assert ParametersSelection.steps == (
        "Mechanism Selection",
        "Region assignment",
        "Parameters selection",
    )

    schema = EModelOptimizationScanConfig.model_json_schema()
    parameters_schema = schema["$defs"]["ParametersSelection"]["properties"]

    assert parameters_schema["ion_channel_models"]["step"] == "Mechanism Selection"
    assert parameters_schema["ion_channel_models"]["step_order"] == 1
    assert parameters_schema["mechanism_regions"]["step"] == "Region assignment"
    assert parameters_schema["mechanism_regions"]["step_order"] == 2
    assert parameters_schema["global_parameters"]["step"] == "Parameters selection"
    assert parameters_schema["base_parameters"]["step"] == "Parameters selection"
    assert parameters_schema["distribution_parameters"]["step"] == "Parameters selection"

    # distance_dependent_distributions no longer belongs to the Mechanisms wizard: it is
    # a standalone Inputs-group field for user-defined distributions only.
    top_level_schema = schema["properties"]
    assert "step" not in top_level_schema["distance_dependent_distributions"]


def test_schema_groups_match_figma_navigation():
    schema = EModelOptimizationScanConfig.model_json_schema()
    properties = schema["properties"]

    assert properties["info"]["group"] == "Setup"
    assert properties["initialize"]["group"] == "Setup"
    assert properties["target_efeatures"]["group"] == "Inputs"
    assert properties["morphology"]["group"] == "Inputs"
    assert properties["parameters_selection"]["group"] == "Inputs"
    assert properties["parameters_selection"]["title"] == "Mechanisms"
    assert properties["distance_dependent_distributions"]["group"] == "Inputs"
    assert properties["morphology_settings"]["group"] == "Settings"
    assert properties["morphology_settings"]["title"] == "Morphology settings"
    assert properties["optimization_settings"]["group"] == "Settings"
    assert properties["optimization_params"]["group"] == "Settings"
    assert schema["group_order"] == ["Setup", "Inputs", "Settings"]


def test_section_list_schema_exposes_typed_choices_and_aliases():
    schema = EModelOptimizationScanConfig.model_json_schema()
    parameters_schema = schema["$defs"]["ParametersSelection"]
    base_schema = parameters_schema["properties"]["base_parameters"]
    mechanism_schema = parameters_schema["properties"]["mechanism_regions"]

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
        match=r"parameters_selection\.base_parameters\.myelinated.*unavailable",
    ):
        EModelOptimizationScanConfig.model_validate(
            _scan_config_data(
                morphology_settings={"axon_modifier": "replace_axon_legacy"},
                parameters_selection=stale_selection,
            )
        )


def test_recipe_contains_the_canonical_multiloc_map():
    recipes = build_optimization_recipe("test", "L5", "morphology.swc", "params.json")

    assert recipes["test"]["multiloc_map"] == DEFAULT_SECTION_LIST_CATALOG.to_recipe_multiloc_map()
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
    recipes = _shared.update_pipeline_settings(
        recipes,
        emodel="test",
        overrides=settings.to_dict(OptimizationParams()),
    )
    recipe_path = tmp_path / "config" / "recipes.json"
    _shared.write_recipes(recipes, recipe_path)

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
        morphology=FakeMorphology(),
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

    params = build_params_definition(config, {})

    cm_rows = [parameter for parameter in params["parameters"] if parameter["name"] == "cm"]
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
    assert [variable.name for variable in normalized.variables] == [
        "gNa_NaTg",
        "vshift_NaTg",
        "ena_NaTg",
    ]


def test_params_builder_emits_complete_deterministic_definition():
    config, _, normalized = _compiler_fixture()
    params = build_params_definition(config, normalized)

    assert params["morphology"] == {}
    assert [(mechanism["name"], mechanism["location"]) for mechanism in params["mechanisms"]] == [
        ("NaTg", "apical"),
        ("NaTg", "somatic"),
        ("pas", "all"),
    ]
    assert [distribution["name"] for distribution in params["distributions"]] == [
        "decay",
        "uniform",
    ]
    assert [(parameter["name"], parameter["location"]) for parameter in params["parameters"]] == [
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
    assert params["parameters"][2]["value"] == [-0.1, 0.0]
    assert params["parameters"][4]["value"] == [-95.0, -60.0]
    assert params["parameters"][5]["value"] == [1e-5, 6e-5]
    assert params["parameters"][8]["dist"] == "decay"
    assert "distribution" not in params["parameters"][8]
    assert "distribution" not in params["parameters"][7]


def test_params_definition_is_accepted_by_bluepyemodel_parser():
    config, _, normalized = _compiler_fixture()
    params = build_params_definition(config, normalized)

    neuron_configuration = NeuronModelConfiguration()
    neuron_configuration.init_from_dict(params, {"name": "test-morphology"})

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
        build_params_definition(config, normalized, bounds_fallbacks={})

    config, _, normalized = _compiler_fixture()
    config.parameters_selection.base_parameters["all"]["Ra"].distribution = "missing"
    with pytest.raises(ValueError, match="undeclared distribution"):
        build_params_definition(config, normalized)

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
            myelinated_config,
            normalized,
            morphology_capabilities=MorphologyCapabilities(has_myelinated=False),
        )


def test_stage_params_overwrites_stale_json_and_deduplicates_nested_models(tmp_path, monkeypatch):
    config, reference, normalized = _compiler_fixture()
    reference._entity = _model_entity()
    task = EModelOptimizationTask.model_construct(config=config)
    params_path = tmp_path / "config" / "params" / "params.json"
    params_path.parent.mkdir(parents=True)
    params_path.write_text(
        json.dumps({"mechanisms": ["stale"], "distributions": [], "parameters": ["stale"]}),
        encoding="utf-8",
    )

    downloaded = []

    def download_asset(self, *, dest_dir, db_client):
        del dest_dir, db_client
        downloaded.append(self.id_str)

    monkeypatch.setattr(IonChannelModelFromID, "download_asset", download_asset)
    task._stage_mechanisms(tmp_path, object())
    task._stage_params(tmp_path, object())

    assert downloaded == ["icm-1"]
    assert json.loads(params_path.read_text(encoding="utf-8")) == build_params_definition(
        config, normalized
    )


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

    before = build_params_definition(config, normalized)
    # Touch the projection to ensure it has no side effects on the config.
    _ = config.parameters_selection.parameter_group_view
    _ = config.parameters_selection.parameter_rows("global")
    after = build_params_definition(config, normalized)

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
        config,
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
        for parameter in params["parameters"]
    }
    assert by_name_and_location["gNa_NaTg", "apical"] == [0.0, 1.0]
    assert by_name_and_location["constant", "distribution_decay"] == [-0.2, 0.0]


def _fake_section(section_type):
    section = SimpleNamespace()
    section.type = section_type
    return section


def test_morphology_preflight_applies_modifier_capabilities(tmp_path, monkeypatch):
    morphio_type = morphology_preflight.morphio.SectionType
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
    source_myelin = morphology_preflight.preflight_morphology(
        morphology_path,
        "none",
        source_has_myelinated=True,
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
    assert source_myelin.has_myelinated is True


def test_morphology_preflight_reports_available_physical_sections_in_catalog_order(
    tmp_path, monkeypatch
):
    morphio_type = morphology_preflight.morphio.SectionType
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
            config,
            normalized,
            morphology_capabilities=axon_only_capabilities,
        )


def test_morphology_capabilities_without_preflight_skips_region_check():
    """Direct construction (no preflight) must not spuriously reject configured regions."""
    config, _, normalized = _compiler_fixture()

    # available_physical_sections defaults to (): "not inspected".
    params = build_params_definition(
        config,
        normalized,
        morphology_capabilities=MorphologyCapabilities(has_myelinated=True),
    )

    assert params["parameters"]


def test_morphology_preflight_rejects_insufficient_source_axon_sections(tmp_path, monkeypatch):
    class FakeSection:
        type = morphology_preflight.morphio.SectionType.axon

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
