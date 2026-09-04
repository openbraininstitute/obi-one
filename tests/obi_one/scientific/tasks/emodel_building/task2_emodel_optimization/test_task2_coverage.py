import json
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import morphio
import pytest
from bluepyemodel.preprocessing import (
    artifacts,
    morphology_preflight,
    parameters as bpem_parameters,
)
from bluepyemodel.preprocessing.schemas import (
    MorphologyCapabilities,
    NormalizedIonChannelModel,
)
from entitysdk.types import EntityLifecycleStatus, ValidationStatus

from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization import utils
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.blocks import (
    CustomDistanceDependentDistribution,
    DistanceDependentDistribution,
    GlobalParameterSelection,
    MechanismRegionSelection,
    OptimizationParams,
    OptimizationSettings,
    OptimizationValue,
    ParameterSelection,
    ParametersSelection,
    _validate_base_parameter_locations,
    _validate_mechanism_region_references,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.config import (
    EModelOptimizationScanConfig,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.task import (
    EModelOptimizationTask,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.utils import (
    optimization_artifact_input_from_config,
    params_definition_input_from_config,
)

from .test_parameter_selection import _model_entity, _scan_config_data


def _reference() -> IonChannelModelFromID:
    return IonChannelModelFromID(id_str="icm-1")


def _selection(**overrides) -> ParametersSelection:
    values = {
        "ion_channel_models": (_reference(),),
        "mechanism_regions": {},
        "global_parameters": {},
        "base_parameters": {},
        "distribution_parameters": {},
    }
    values.update(overrides)
    return ParametersSelection(**values)


def _compiler_config(selection: ParametersSelection, custom=None) -> SimpleNamespace:
    return SimpleNamespace(
        parameters_selection=selection,
        distance_dependent_distributions=custom or {},
    )


def _normalized_models() -> dict[str, NormalizedIonChannelModel]:
    return {"icm-1": bpem_parameters.normalize_ion_channel_model(_model_entity())}


def test_normalize_model_rejects_missing_required_metadata():
    with pytest.raises(ValueError, match="nmodl_suffix"):
        bpem_parameters.normalize_ion_channel_model(SimpleNamespace())
    with pytest.raises(ValueError, match="no entity ID"):
        bpem_parameters.normalize_ion_channel_model(SimpleNamespace(nmodl_suffix="NaTg"))
    with pytest.raises(ValueError, match="no neuron_block"):
        bpem_parameters.normalize_ion_channel_model(
            SimpleNamespace(nmodl_suffix="NaTg", id="icm-1")
        )


def test_normalize_model_accepts_mapping_global_metadata_and_ignores_empty_duplicates():
    entity = {
        "id": "icm-1",
        "nmodl_suffix": "NaTg",
        "neuron_block": {
            "range": [
                {"variable": "", "units": "mV"},
                {"variable": "gNa", "units": "S/cm2"},
                {"variable": "gNa", "units": "S/cm2"},
            ],
            "global": [{"variable": "ena", "units": "mV"}],
            "useion": [{"ion_name": " NA "}],
        },
    }

    normalized = bpem_parameters.normalize_ion_channel_model(entity)

    assert [variable.name for variable in normalized.range_variables] == ["gNa_NaTg"]
    assert [variable.name for variable in normalized.global_variables] == ["ena_NaTg"]
    assert normalized.ion_names == frozenset({"na"})


def test_resolve_and_fetch_ion_channel_models_preserve_reference_ids():
    entity = _model_entity()
    reference = SimpleNamespace(id_str="icm-1", entity=Mock(return_value=entity))
    reference_entity = reference.entity
    resolved = utils.resolve_ion_channel_models((reference,), object())

    assert resolved["icm-1"].entity_id == "icm-1"
    reference_entity.assert_called_once()

    client = SimpleNamespace(get_entity=Mock(return_value=entity))
    catalog = utils.fetch_variable_catalog(["icm-2"], client)

    assert catalog["icm-2"].entity_id == "icm-2"
    client.get_entity.assert_called_once()
    assert client.get_entity.call_args.kwargs["entity_id"] == "icm-2"


@pytest.mark.parametrize(
    ("bounds", "message"),
    [
        ((float("nan"), 1.0), "finite"),
        ((1.0, float("inf")), "finite"),
        ((2.0, 1.0), "Lower bound exceeds"),
    ],
)
def test_parameter_builder_rejects_invalid_fallback_bounds(bounds, message):
    with pytest.raises(ValueError, match=message):
        bpem_parameters._validate_bounds("g_pas", bounds)


def test_parameter_builder_rejects_fixed_without_value_and_invalid_locations():
    value = OptimizationValue.model_construct(mode="fixed", value=None, bounds=None)
    with pytest.raises(ValueError, match="has no value"):
        bpem_parameters._resolve_value("x", value, {})
    with pytest.raises(ValueError, match="Unsupported regional"):
        bpem_parameters._validate_location("not-a-region")


def test_parameter_builder_rejects_invalid_fallback_before_compilation():
    selection = _selection(
        base_parameters={"all": {"cm": ParameterSelection(value=OptimizationValue(value=1.0))}}
    )
    with pytest.raises(ValueError, match="finite"):
        bpem_parameters.build_params_definition(
            params_definition_input_from_config(_compiler_config(selection)),
            _normalized_models(),
            bounds_fallbacks={"g_pas": (float("nan"), 1.0)},
        )


def test_parameter_builder_rejects_missing_and_duplicate_mechanism_metadata():
    reference = _reference()
    assignment = MechanismRegionSelection(ion_channel_model=reference)
    selection = _selection(mechanism_regions={"somatic": (assignment,)})

    with pytest.raises(ValueError, match="No normalized metadata"):
        bpem_parameters._build_mechanisms(selection, {})

    duplicate_selection = _selection(mechanism_regions={"somatic": (assignment, assignment)})
    with pytest.raises(ValueError, match="assigned more than once"):
        bpem_parameters._build_mechanisms(duplicate_selection, _normalized_models())


def test_parameter_builder_rejects_invalid_global_parameter_sources():
    reference = _reference()
    model = _normalized_models()
    for name in ("missing", "gNa"):
        selection = _selection(
            global_parameters={
                name: GlobalParameterSelection(
                    value=OptimizationValue(value=1.0),
                    ion_channel_model=reference,
                )
            }
        )
        with pytest.raises(ValueError, match="not a GLOBAL"):
            bpem_parameters._build_global_parameters(selection, model, {})

    unknown_reference = IonChannelModelFromID(id_str="icm-2")
    selection = _selection(
        ion_channel_models=(unknown_reference,),
        global_parameters={
            "ena": GlobalParameterSelection(
                value=OptimizationValue(value=1.0),
                ion_channel_model=unknown_reference,
            )
        },
    )
    with pytest.raises(ValueError, match="No normalized metadata"):
        bpem_parameters._build_global_parameters(selection, model, {})


def test_parameter_builder_rejects_invalid_mechanism_parameter_sources():
    reference = _reference()
    model = _normalized_models()
    for name, message in (("missing", "not declared"), ("ena", "must be configured")):
        assignment = MechanismRegionSelection(
            ion_channel_model=reference,
            parameters={name: ParameterSelection(value=OptimizationValue(value=1.0))},
        )
        selection = _selection(mechanism_regions={"somatic": (assignment,)})
        with pytest.raises(ValueError, match=message):
            bpem_parameters._build_mechanism_parameters(selection, model, {"uniform": object()}, {})


def test_parameter_builder_rejects_invalid_distribution_rows():
    selection = _selection(
        distribution_parameters={
            "missing": {"constant": OptimizationValue(value=1.0)},
        }
    )
    with pytest.raises(ValueError, match="not declared"):
        bpem_parameters._build_distribution_parameters(selection, {}, {})

    selection = _selection(
        distribution_parameters={
            "decay": {"unknown": OptimizationValue(value=1.0)},
        }
    )
    distribution = SimpleNamespace(parameters=("constant",))
    with pytest.raises(ValueError, match="undeclared parameters"):
        bpem_parameters._build_distribution_parameters(selection, {"decay": distribution}, {})


def test_parameter_builder_legacy_conversions_preserve_optional_fields():
    mechanisms = bpem_parameters._to_legacy_mechanisms(
        [
            {"name": "NaTg", "location": "somatic"},
            {"name": "NaTg", "location": "somatic"},
        ]
    )
    distributions = bpem_parameters._to_legacy_distributions(
        [
            {
                "name": "decay",
                "function": "{value}*{distance}",
                "parameters": ["constant"],
                "soma_ref_location": 0.75,
            },
            {"name": "uniform", "function": None, "soma_ref_location": 0.5},
        ]
    )
    parameters = bpem_parameters._to_legacy_parameters(
        [{"name": "gNa_NaTg", "location": "somatic", "value": [0.0, 1.0], "dist": "decay"}]
    )

    assert mechanisms == {"somatic": {"mech": ["NaTg"]}}
    assert distributions["decay"]["soma_ref_location"] == pytest.approx(0.75)
    assert "parameters" not in distributions["uniform"]
    assert parameters == {"somatic": [{"name": "gNa_NaTg", "val": [0.0, 1.0], "dist": "decay"}]}


def test_parameter_builder_rejects_wrong_capability_type():
    selection = _selection()
    with pytest.raises(TypeError, match="MorphologyCapabilities"):
        bpem_parameters.build_params_definition(
            params_definition_input_from_config(_compiler_config(selection)),
            _normalized_models(),
            morphology_capabilities=object(),
        )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"parameters": ("constant",)}, "must define a function"),
        ({"function": "{distance}"}, "{value}"),
        ({"function": "{value}"}, "{distance}"),
        (
            {"function": "{value} * {distance}", "parameters": ("constant",)},
            "{constant}",
        ),
    ],
)
def test_distance_distribution_validates_function_placeholders(payload, message):
    with pytest.raises(ValueError, match=message):
        DistanceDependentDistribution(**payload)


def test_distance_distribution_serializes_legacy_fields():
    distribution = DistanceDependentDistribution(
        name="custom",
        function="{value} * {distance} * {constant}",
        soma_ref_location=0.75,
        parameters=("constant",),
    )

    assert distribution.to_emc_dict() == {
        "name": "custom",
        "function": "{value} * {distance} * {constant}",
        "soma_ref_location": 0.75,
        "parameters": ["constant"],
    }


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"value": float("nan")}, "finite"),
        ({"value": float("inf")}, "finite"),
        ({"mode": "bounds", "bounds": (float("nan"), 1.0)}, "finite"),
    ],
)
def test_optimization_value_rejects_nonfinite_values(kwargs, message):
    with pytest.raises(ValueError, match=message):
        OptimizationValue(**kwargs)


def test_optimization_params_validates_limits_and_serializes_all_algorithms():
    with pytest.raises(ValueError, match="centroids"):
        OptimizationParams(centroids=(float("nan"),))
    with pytest.raises(ValueError, match="at most 200"):
        OptimizationParams(offspring_size=201)
    with pytest.raises(ValueError, match="at most 200"):
        OptimizationParams(offspring_size=[20, 201])

    cma = OptimizationParams(offspring_size=[2, 4], sigma=[0.1, 0.2], centroids=(1.0, 2.0))
    assert cma.to_dict("SO-CMA") == {
        "offspring_size": [2, 4],
        "sigma": [0.1, 0.2],
        "centroids": [1.0, 2.0],
    }
    ibea = OptimizationParams(offspring_size=10, eta=2.0, mutpb=0.2, cxpb=[0.3, 0.4])
    assert ibea.to_dict("IBEA") == {
        "offspring_size": 10,
        "eta": 2.0,
        "mutpb": 0.2,
        "cxpb": [0.3, 0.4],
    }


def test_optimization_settings_serializes_optional_recipe_paths():
    settings = OptimizationSettings(
        name_rin_protocol="rin",
        name_rmp_protocol="rmp",
        custom_bluepyefe_cells_pklpath="cells.pkl",
        custom_bluepyefe_protocols_pklpath="protocols.pkl",
        stochasticity=True,
    )

    recipe = settings.to_dict(OptimizationParams(offspring_size=2))

    assert recipe["name_Rin_protocol"] == "rin"
    assert recipe["name_rmp_protocol"] == "rmp"
    assert recipe["custom_bluepyefe_cells_pklpath"] == "cells.pkl"
    assert recipe["custom_bluepyefe_protocols_pklpath"] == "protocols.pkl"
    assert recipe["stochasticity"] is True


@pytest.mark.parametrize(
    ("morphology_filename", "params_filename", "message"),
    [
        ("/absolute/path/morphology.swc", "params.json", "morph_filename"),
        ("nested/morphology.swc", "params.json", "morph_filename"),
        ("../morphology.swc", "params.json", "morph_filename"),
        ("morphology.swc", "other.json", "params_filename"),
    ],
)
def test_recipe_rejects_nonportable_paths(morphology_filename, params_filename, message):
    with pytest.raises(ValueError, match=message):
        artifacts.build_optimization_recipe(
            "test",
            "L5",
            morphology_filename,
            params_filename,
        )


def test_artifact_builder_rejects_unknown_contract_before_compilation():
    config = EModelOptimizationScanConfig.model_validate(_scan_config_data())
    artifact_input = optimization_artifact_input_from_config(
        config,
        mtype=None,
        morphology_filename="morphology.swc",
    ).model_copy(update={"config_contract_version": "task2-config-v0"})

    with pytest.raises(ValueError, match="contract version"):
        artifacts.build_optimization_artifacts(artifact_input, {})


@pytest.mark.parametrize(
    ("modifier", "axon_count", "has_myelinated"),
    [
        ("replace_axon_legacy", 2, False),
        ("replace_axon_olfactory_bulb", 3, True),
        ("bluepyopt_replace_axon", 0, False),
    ],
)
def test_preflight_reports_modifier_capabilities(
    tmp_path, monkeypatch, modifier, axon_count, has_myelinated
):
    class FakeMorphology:
        sections = tuple(SimpleNamespace(type=morphio.SectionType.axon) for _ in range(axon_count))

    path = tmp_path / "morphology.swc"
    path.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        morphology_preflight, "load_morphology_nrn_order", lambda _: FakeMorphology()
    )

    capabilities = morphology_preflight.preflight_morphology(path, modifier)

    assert capabilities.has_myelinated is has_myelinated
    assert capabilities.axonal_section_count == axon_count


def test_preflight_rejects_missing_asset(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        morphology_preflight.preflight_morphology(tmp_path / "missing.swc", "none")


def _install_registration_modules(monkeypatch, calls):
    registration = ModuleType("entitysdk.registration")
    registration.__path__ = []
    task_result_package = ModuleType("entitysdk.registration.task_result")
    task_result_package.__path__ = []
    emodel_module = ModuleType("entitysdk.registration.emodel")
    memodel_module = ModuleType("entitysdk.registration.memodel")
    result_module = ModuleType("entitysdk.registration.task_result.emodel_optimization")

    def register_emodel(**kwargs):
        calls["emodel"] = kwargs
        return SimpleNamespace(id="emodel-id")

    def register_memodel(**kwargs):
        calls["memodel"] = kwargs
        return SimpleNamespace(id="memodel-id")

    def register_result(**kwargs):
        calls["result"] = kwargs
        return SimpleNamespace(id="task-result-id")

    emodel_module.register_emodel = register_emodel
    memodel_module.register_memodel = register_memodel
    result_module.register_emodel_optimization_result = register_result
    for name, module in (
        ("entitysdk.registration", registration),
        ("entitysdk.registration.task_result", task_result_package),
        ("entitysdk.registration.emodel", emodel_module),
        ("entitysdk.registration.memodel", memodel_module),
        ("entitysdk.registration.task_result.emodel_optimization", result_module),
    ):
        monkeypatch.setitem(sys.modules, name, module)


def _registration_fixture(tmp_path, *, complete=True):
    species = SimpleNamespace(name="Mus musculus")
    brain_region = SimpleNamespace(name="Somatosensory cortex")
    morphology_entity = SimpleNamespace(id="morphology-id")
    morphology = SimpleNamespace(
        entity=Mock(return_value=morphology_entity),
        metadata_entities=Mock(return_value=(species, brain_region)),
    )
    reference = SimpleNamespace(
        id_str="icm-1", entity=Mock(return_value=SimpleNamespace(id="icm-1"))
    )
    etype = SimpleNamespace(entity=Mock(return_value=SimpleNamespace(id="etype-id")))
    config = SimpleNamespace(
        initialize=SimpleNamespace(emodel="test", etype=etype),
        inputs=SimpleNamespace(morphology=morphology),
        optimization_settings=SimpleNamespace(seed=7),
        parameters_selection=SimpleNamespace(ion_channel_model_references=(reference,)),
    )
    task = EModelOptimizationTask.model_construct(config=config)
    license_entity = SimpleNamespace(id="license-id")
    activity = SimpleNamespace(authorized_public=True)
    db_client = SimpleNamespace(
        search_entity=Mock(return_value=SimpleNamespace(one=Mock(return_value=license_entity))),
        get_entity=Mock(return_value=activity),
        upload_file=Mock(),
        upload_directory=Mock(),
        update_entity=Mock(),
    )

    if complete:
        (tmp_path / "config" / "params").mkdir(parents=True)
        (tmp_path / "config" / "recipes.json").write_text("{}", encoding="utf-8")
        (tmp_path / "config" / "params" / "params.json").write_text("{}", encoding="utf-8")
        (tmp_path / "checkpoints").mkdir()
        (tmp_path / "checkpoints" / "model.pkl").write_text("checkpoint", encoding="utf-8")
        (tmp_path / "figures").mkdir()
        (tmp_path / "figures" / "validation.pdf").write_text("pdf", encoding="utf-8")
        (tmp_path / "figures" / "validation.png").write_text("png", encoding="utf-8")
        (tmp_path / "figures" / "ignored.txt").write_text("txt", encoding="utf-8")
        (tmp_path / "export_emodels_sonata" / "nodes").mkdir(parents=True)
        (tmp_path / "export_emodels_sonata" / "nodes" / "nodes.h5").write_text(
            "h5", encoding="utf-8"
        )
        (tmp_path / "final.json").write_text(
            json.dumps(
                {
                    "test": [
                        {
                            "fitness": 2.5,
                            "holding_current": 0.1,
                            "threshold_current": 0.2,
                            "iteration": 4,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    return task, db_client, morphology, reference, etype


def test_register_output_entities_registers_all_outputs_and_updates_activity(tmp_path, monkeypatch):
    calls = {}
    _install_registration_modules(monkeypatch, calls)
    task, db_client, morphology, reference, etype = _registration_fixture(tmp_path)

    task.register_output_entities(
        tmp_path,
        db_client,
        trace_ids=["trace-1"],
        execution_activity_id="activity-id",
    )

    assert calls["result"]["authorized_public"] is True
    assert calls["result"]["hdf5_checkpoint_file"].name == "model.pkl"
    assert calls["result"]["summary_file"].name == "final.json"
    assert calls["emodel"]["species"].name == "Mus musculus"
    assert calls["emodel"]["brain_region"].name == "Somatosensory cortex"
    assert calls["emodel"]["score"] == pytest.approx(2.5)
    assert calls["emodel"]["iteration"] == "4"
    assert calls["emodel"]["electrical_cell_recording_ids"] == ["trace-1"]
    assert calls["emodel"]["validation_result_status"] is False
    assert calls["memodel"]["emodel"].id == "emodel-id"
    assert calls["memodel"]["validation_status"] == ValidationStatus.created
    assert calls["memodel"]["lifecycle_status"] == EntityLifecycleStatus.draft
    assert morphology.metadata_entities.call_count == 1
    assert reference.entity.call_count == 1
    assert etype.entity.call_count == 1
    assert db_client.upload_file.call_count == 2
    assert db_client.upload_directory.call_count == 1
    db_client.update_entity.assert_called_once_with(
        entity_id="activity-id",
        entity_type=pytest.importorskip("entitysdk.models").TaskActivity,
        attrs_or_entity={
            "generated_ids": ["task-result-id", "emodel-id", "memodel-id"],
        },
    )
    assert task._registered_task_result_id == "task-result-id"
    assert task._registered_emodel_id == "emodel-id"
    assert task._registered_memodel_id == "memodel-id"


def test_register_output_entities_handles_missing_optional_outputs(tmp_path, monkeypatch):
    calls = {}
    _install_registration_modules(monkeypatch, calls)
    task, db_client, _, _, _ = _registration_fixture(tmp_path, complete=False)

    task.register_output_entities(tmp_path, db_client)

    assert calls["result"]["authorized_public"] is False
    assert calls["result"]["hdf5_checkpoint_file"] is None
    assert calls["result"]["summary_file"] is None
    assert calls["emodel"]["electrical_cell_recording_ids"] == []
    assert calls["emodel"]["validation_result_figure_files"] == []
    db_client.update_entity.assert_not_called()


def _config_data_for_selection(selection, distributions=None, **overrides):
    data = _scan_config_data(parameters_selection=selection.model_dump(mode="json"))
    data["distance_dependent_distributions"] = distributions or {}
    data.update(overrides)
    return data


def _decay_distribution():
    return CustomDistanceDependentDistribution(
        name="decay",
        function="math.exp({distance}*{constant})*{value}",
        parameters=("constant",),
    )


def test_scan_config_rejects_distribution_declaration_and_usage_errors():
    undeclared = _selection(
        distribution_parameters={"missing": {"constant": OptimizationValue(value=1.0)}}
    )
    with pytest.raises(ValueError, match="reference undeclared distribution 'missing'"):
        EModelOptimizationScanConfig.model_validate(_config_data_for_selection(undeclared))

    unknown_parameter = _selection(
        distribution_parameters={"decay": {"unknown": OptimizationValue(value=1.0)}}
    )
    with pytest.raises(ValueError, match="undeclared parameters"):
        EModelOptimizationScanConfig.model_validate(
            _config_data_for_selection(unknown_parameter, {"decay": _decay_distribution()})
        )

    undeclared_usage = _selection(
        base_parameters={
            "all": {
                "cm": ParameterSelection(
                    value=OptimizationValue(value=1.0),
                    distribution="missing",
                )
            }
        }
    )
    with pytest.raises(ValueError, match="Parameters reference undeclared distributions"):
        EModelOptimizationScanConfig.model_validate(_config_data_for_selection(undeclared_usage))

    missing_value = _selection(
        base_parameters={
            "all": {
                "cm": ParameterSelection(
                    value=OptimizationValue(value=1.0),
                    distribution="decay",
                )
            }
        }
    )
    with pytest.raises(ValueError, match="Used distribution 'decay' is missing values"):
        EModelOptimizationScanConfig.model_validate(
            _config_data_for_selection(missing_value, {"decay": _decay_distribution()})
        )


def test_scan_config_rejects_empty_ion_channel_model_selection():
    selection = _selection(ion_channel_models=())

    with pytest.raises(ValueError, match="ion_channel_models must be set"):
        EModelOptimizationScanConfig.model_validate(_config_data_for_selection(selection))


def test_remaining_block_validation_and_serialization_paths():
    distribution = DistanceDependentDistribution(function="{value} * {distance}")
    assert distribution.to_emc_dict() == {
        "name": None,
        "function": "{value} * {distance}",
        "soma_ref_location": 0.5,
    }

    with pytest.raises(ValueError, match="Bounds cannot be provided"):
        OptimizationValue(mode="fixed", value=1.0, bounds=(0.0, 2.0))

    with pytest.raises(ValueError, match="Unsupported mechanism region"):
        _validate_mechanism_region_references((), {"unsupported": ()})
    with pytest.raises(ValueError, match="Unsupported base parameter region"):
        _validate_base_parameter_locations({"unsupported": {}})

    for modifier, expected in (
        ("replace_axon_with_taper", True),
        ("replace_axon_olfactory_bulb", True),
        ("replace_axon_legacy", False),
        ("bluepyopt_replace_axon", False),
    ):
        config = EModelOptimizationScanConfig.model_validate(
            _config_data_for_selection(
                _selection(base_parameters={}, global_parameters={}),
                morphology_settings={"axon_modifier": modifier},
            )
        )
        assert config.morphology_settings.expected_myelinated is expected

    assert OptimizationParams(offspring_size=2).to_dict("IBEA") == {"offspring_size": 2}


def test_remaining_parameter_builder_paths():
    model = _normalized_models()["icm-1"]
    assert model.find_variable("gNa_NaTg").name == "gNa_NaTg"

    variables = bpem_parameters._normalize_variables(
        (SimpleNamespace(name="h", units="mV"), SimpleNamespace(variable="q")),
        "NaTg",
        "RANGE",
    )
    assert [variable.name for variable in variables] == ["h_NaTg", "q_NaTg"]
    assert bpem_parameters._location_sort_key("not-a-region") == (0, "not-a-region")

    pas_reference = IonChannelModelFromID(id_str="pas-model")
    pas_selection = _selection(
        ion_channel_models=(pas_reference,),
        mechanism_regions={"somatic": (MechanismRegionSelection(ion_channel_model=pas_reference),)},
        base_parameters={
            "somatic": {"g_pas": ParameterSelection(value=OptimizationValue(value=0.001))}
        },
    )
    pas_model = NormalizedIonChannelModel(
        entity_id="pas-model",
        name="Passive",
        nmodl_suffix="pas",
        is_stochastic=False,
        is_ljp_corrected=False,
        temperature_celsius=None,
        range_variables=(),
        global_variables=(),
        ion_names=frozenset(),
    )
    mechanisms = bpem_parameters._build_mechanisms(pas_selection, {"pas-model": pas_model})
    assert [mechanism["name"] for mechanism in mechanisms] == ["pas"]

    missing_metadata_selection = _selection(
        mechanism_regions={"somatic": (MechanismRegionSelection(ion_channel_model=_reference()),)}
    )
    assert bpem_parameters._assigned_ion_names_by_section(missing_metadata_selection, {}) == {}

    no_myelinated = _selection(
        base_parameters={"somatic": {"cm": ParameterSelection(value=OptimizationValue(value=1.0))}}
    )
    params = bpem_parameters.build_params_definition(
        params_definition_input_from_config(_compiler_config(no_myelinated)),
        _normalized_models(),
        morphology_capabilities=MorphologyCapabilities(has_myelinated=False),
    )
    assert params["parameters"]

    missing_distribution_values = _selection(
        base_parameters={
            "all": {
                "cm": ParameterSelection(
                    value=OptimizationValue(value=1.0),
                    distribution="decay",
                )
            }
        }
    )
    with pytest.raises(ValueError, match="Used distribution 'decay' is missing values"):
        bpem_parameters.build_params_definition(
            params_definition_input_from_config(
                _compiler_config(missing_distribution_values, {"decay": _decay_distribution()})
            ),
            _normalized_models(),
        )


def test_morphology_preflight_ignores_unknown_section_types():
    morphology = SimpleNamespace(sections=(SimpleNamespace(type="unknown"),), soma=None)

    assert morphology_preflight._available_physical_sections(morphology) == ()


def test_execute_covers_local_access_point_hooks_and_registration_path(tmp_path, monkeypatch):
    access_points = []

    class FakeLocalAccessPoint:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.pipeline_settings = SimpleNamespace(morph_modifiers=["none"])
            access_points.append(self)

        def get_available_mechanisms(self):
            return [SimpleNamespace(name="NaTg")]

        def get_model_configuration(self, *args, **kwargs):
            del args, kwargs
            return SimpleNamespace()

    monkeypatch.setattr(
        "bluepyemodel.access_point.local.LocalAccessPoint",
        FakeLocalAccessPoint,
    )
    monkeypatch.setattr("bluepyemodel.optimisation.setup_and_run_optimisation", Mock())
    monkeypatch.setattr("bluepyemodel.optimisation.store_best_model", Mock())
    monkeypatch.setattr(
        "bluepyemodel.export_emodel.export_emodel.export_emodels_sonata",
        Mock(),
    )
    monkeypatch.setattr(
        "obi_one.scientific.tasks.emodel_building._shared.compile_mechanisms", Mock()
    )
    monkeypatch.setattr("obi_one.scientific.tasks.emodel_building._shared.run_plot_models", Mock())
    monkeypatch.setattr(
        "obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.task.preflight_morphology",
        Mock(return_value=object()),
    )
    monkeypatch.setattr(
        "obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.task.resolve_ion_channel_models",
        Mock(return_value=_normalized_models()),
    )
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
    registration = Mock()
    monkeypatch.setattr(EModelOptimizationTask, "register_output_entities", registration)

    species = SimpleNamespace(name="Mus musculus")
    brain_region = SimpleNamespace(name="Somatosensory cortex")
    morphology = SimpleNamespace(
        metadata_entities=Mock(return_value=(species, brain_region)),
    )
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
    db_client = object()

    result = task.execute(db_client=db_client)

    assert result == tmp_path.resolve()
    assert registration.call_args.args == (tmp_path.resolve(), db_client)
    assert registration.call_args.kwargs == {
        "trace_ids": ["trace-1"],
        "execution_activity_id": None,
    }
    mechanism = access_points[0].get_available_mechanisms()[0]
    assert mechanism.id == "icm-1"
    configuration = access_points[0].get_model_configuration()
    assert configuration.morph_modifiers == ["none"]


def test_register_output_entities_handles_empty_checkpoint_and_nested_figure_paths(
    tmp_path, monkeypatch
):
    calls = {}
    _install_registration_modules(monkeypatch, calls)
    task, db_client, _, _, _ = _registration_fixture(tmp_path, complete=False)
    (tmp_path / "checkpoints").mkdir()
    (tmp_path / "figures" / "nested").mkdir(parents=True)

    task.register_output_entities(tmp_path, db_client)

    assert calls["result"]["hdf5_checkpoint_file"] is None
    assert calls["emodel"]["validation_result_figure_files"] == []
