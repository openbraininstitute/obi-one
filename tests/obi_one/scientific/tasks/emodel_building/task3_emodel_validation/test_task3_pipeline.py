import json
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

pytest.importorskip("bluepyemodel")

from bluepyemodel.emodel_pipeline import plotting
from bluepyemodel.evaluation import evaluation
from bluepyemodel.preprocessing import OptimizationArtifacts
from entitysdk.exception import IteratorResultError
from entitysdk.types import EntityType, TaskResultType

from obi_one.scientific.tasks.emodel_building import (
    utils as emodel_building_utils,
    validation_scoring,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.config import (
    EModelOptimizationSingleConfig,
)
from obi_one.scientific.tasks.emodel_building.task3_emodel_validation import (
    registration,
    staging,
    task,
)
from obi_one.scientific.tasks.emodel_building.task3_emodel_validation.config import (
    EModelValidationSingleConfig,
)

INFO = {"campaign_name": "c", "campaign_description": "d"}
OPT_TARGETS = "00000000-0000-4000-8000-000000000001"
SETTINGS = validation_scoring.ResolvedValidationSettings(
    validation_protocols=["IDrest_250"],
    validation_protocols_only=False,
    validation_function="max_score",
    validation_threshold=5.0,
)


def make_config(tmp_path=None, targets=OPT_TARGETS):
    extra = {"coordinate_output_root": tmp_path} if tmp_path is not None else {}
    return EModelValidationSingleConfig(
        info=INFO,
        emodel={"emodel": {"id_str": str(uuid4())}},
        target_efeatures={"task_result": {"id_str": targets}},
        **extra,
    )


def ref(entity_type, entity_id="x"):
    return SimpleNamespace(type=entity_type, id=entity_id)


def provenance_client(activity, task_results=()):
    client = MagicMock()
    client.search_entity.return_value.first.return_value = activity
    by_id = {tr.id: tr for tr in task_results}
    client.get_entity.side_effect = lambda entity_id, **_: by_id.get(
        entity_id, SimpleNamespace(id=entity_id)
    )
    return client


class TestResolveOptimisationProvenance:
    def test_success(self, monkeypatch):
        result = SimpleNamespace(
            id="tr", task_result_type=TaskResultType.emodel_optimization__result
        )
        activity = SimpleNamespace(
            id="act",
            used=[ref(EntityType.task_config, "cfg")],
            generated=[ref(EntityType.task_result, "tr"), ref(EntityType.emodel, "e")],
        )
        config = MagicMock(spec=EModelOptimizationSingleConfig)
        monkeypatch.setattr(staging.db_sdk, "select_json_asset_content", lambda **_: {})
        monkeypatch.setattr(staging, "deserialize_obi_object_from_json_data", lambda _: config)

        provenance = staging.resolve_optimisation_provenance(
            str(uuid4()), provenance_client(activity, [result])
        )

        assert provenance.config is config
        assert provenance.task_result is result

    def test_requires_single_task_config(self):
        activity = SimpleNamespace(id="act", used=[], generated=[])
        with pytest.raises(ValueError, match="Expected one TaskConfig"):
            staging.resolve_optimisation_provenance(str(uuid4()), provenance_client(activity))

    def test_requires_optimisation_config(self, monkeypatch):
        activity = SimpleNamespace(id="act", used=[ref(EntityType.task_config)], generated=[])
        monkeypatch.setattr(staging.db_sdk, "select_json_asset_content", lambda **_: {})
        monkeypatch.setattr(staging, "deserialize_obi_object_from_json_data", lambda _: object())
        with pytest.raises(TypeError, match="not an EModelOptimizationSingleConfig"):
            staging.resolve_optimisation_provenance(str(uuid4()), provenance_client(activity))

    def test_falls_back_to_campaign_config(self, monkeypatch):
        activity = SimpleNamespace(
            id="act", used=[ref(EntityType.task_config, "child")], generated=[]
        )
        scan = {"form": {"type": "EModelOptimizationScanConfig", "initialize": {}}}
        responses = iter([IteratorResultError(), scan])

        def select_or_raise(**_):
            result = next(responses)
            if isinstance(result, Exception):
                raise result
            return result

        seen = {}
        config = MagicMock(spec=EModelOptimizationSingleConfig)

        def fake_deserialize(data):
            seen["data"] = data
            return config

        monkeypatch.setattr(staging.db_sdk, "select_json_asset_content", select_or_raise)
        monkeypatch.setattr(staging, "deserialize_obi_object_from_json_data", fake_deserialize)
        client = provenance_client(activity)
        client.get_entity.side_effect = lambda entity_id, **_: SimpleNamespace(
            id=entity_id, meta={}, task_config_generator_id="campaign-id"
        )

        provenance = staging.resolve_optimisation_provenance(str(uuid4()), client)

        assert provenance.config is config
        assert seen["data"]["type"] == "EModelOptimizationSingleConfig"

    def test_missing_optimisation_result_is_allowed(self, monkeypatch):
        other = SimpleNamespace(id="tr", task_result_type="other")
        activity = SimpleNamespace(
            id="act",
            used=[ref(EntityType.task_config)],
            generated=[ref(EntityType.task_result, "tr")],
        )
        monkeypatch.setattr(staging.db_sdk, "select_json_asset_content", lambda **_: {})
        monkeypatch.setattr(
            staging,
            "deserialize_obi_object_from_json_data",
            lambda _: MagicMock(spec=EModelOptimizationSingleConfig),
        )
        provenance = staging.resolve_optimisation_provenance(
            str(uuid4()), provenance_client(activity, [other])
        )
        assert provenance.task_result is None


def test_stage_working_directory(tmp_path, monkeypatch):
    optimisation_config = SimpleNamespace(
        initialize=SimpleNamespace(emodel="L5PC"),
        target_efeatures=SimpleNamespace(task_result=SimpleNamespace(id_str=OPT_TARGETS)),
        morphology_settings=SimpleNamespace(axon_modifier=None),
        parameters_selection=SimpleNamespace(ion_channel_model_references=[]),
        optimization_settings=SimpleNamespace(
            validation_protocols=("IDrest_250",),
            validation_function="max_score",
            validation_threshold=5.0,
        ),
    )
    provenance = SimpleNamespace(config=optimisation_config)
    features = tmp_path / "features.json"
    features.write_text(
        json.dumps({"efeatures": [], "protocols": [{"name": "IDrest_250"}]}), encoding="utf-8"
    )
    artifacts = OptimizationArtifacts(
        config_contract_version="c", artifact_contract_version="a", params={}, recipes={"L5PC": {}}
    )
    opt_staging = staging.optimisation_staging
    monkeypatch.setattr(staging, "resolve_optimisation_provenance", lambda *_: provenance)
    monkeypatch.setattr(opt_staging, "download_extraction_features", lambda *_: features)
    monkeypatch.setattr(opt_staging, "stage_morphology", lambda *_: "m.swc")
    monkeypatch.setattr(opt_staging, "stage_mechanisms", lambda *_: None)
    monkeypatch.setattr(opt_staging, "derive_mtype", lambda *_: "L5_TPC")
    monkeypatch.setattr(opt_staging, "build_artifacts", lambda *_, **__: artifacts)
    monkeypatch.setattr(staging, "preflight_morphology", lambda *_: None)
    monkeypatch.setattr(staging, "resolve_ion_channel_models", lambda *_: {"m": 1})
    monkeypatch.setattr(staging, "stage_final_entry", lambda *_: {"emodel": "L5PC"})

    staged = staging.stage_working_directory(make_config(), tmp_path, MagicMock())

    recipe = json.loads((tmp_path / artifacts.recipes_path).read_text())["L5PC"]
    assert recipe["pipeline_settings"]["validation_protocols"] == ["IDrest_250"]
    assert recipe["pipeline_settings"]["validation_threshold"] == pytest.approx(5.0)
    assert json.loads(features.read_text())["protocols"][0]["validation"] is True
    assert staged.normalized_models == {"m": 1}
    assert staged.settings.validation_function == "max_score"


def test_run_validation_pipeline(tmp_path, monkeypatch):
    summary = {"passed": True}
    score = MagicMock(return_value=summary)
    plot = MagicMock()
    monkeypatch.setattr(task, "score_model_isolated", score)
    monkeypatch.setattr(task, "create_entitycore_access_point", lambda **_: "ap")
    monkeypatch.setattr(plotting, "plot_models", plot)
    staged = SimpleNamespace(
        final_entry={"emodel": "L5PC", "seed": 3}, normalized_models={}, settings=SETTINGS
    )

    assert task.run_validation_pipeline(coord_root=tmp_path, staged=staged) is summary
    assert score.call_args.kwargs["seed"] == 3
    assert plot.call_args.kwargs["access_point"] == "ap"
    assert json.loads((tmp_path / task.RESULTS_FILENAME).read_text()) == summary


def test_execute(tmp_path, monkeypatch):
    staged = object()
    register = MagicMock()
    monkeypatch.setattr(task.staging, "stage_working_directory", lambda *_: staged)
    monkeypatch.setattr(emodel_building_utils, "compile_mechanisms", lambda *_: None)
    monkeypatch.setattr(task, "run_validation_pipeline", lambda **_: {"passed": True})
    monkeypatch.setattr(task.registration, "register_output_entities", register)
    config = make_config(tmp_path)

    assert task.EModelValidationTask(config=config).execute(db_client="c") == tmp_path.resolve()
    assert register.call_args.kwargs["staged"] is staged
    assert register.call_args.kwargs["summary"] == {"passed": True}


def test_config_input_entities_and_campaign():
    client = MagicMock()
    client.get_entity.side_effect = lambda entity_type, **_: entity_type.__name__
    config = make_config()
    assert config.input_entities(client) == ["EModel", "TaskResult"]
    assert config.campaign_name == "c"
    assert config.campaign_description == "d"


def test_registration_uses_activity_visibility_and_updates_it(tmp_path, monkeypatch):
    update = MagicMock()
    monkeypatch.setattr(registration.db_sdk, "update_execution_activity_with_generated", update)
    monkeypatch.setattr(registration, "register_validation_results", lambda **_: ["vr"])
    client = MagicMock()
    client.get_entity.return_value = SimpleNamespace(authorized_public=True)
    client.register_entity.return_value = SimpleNamespace(id="tr")
    staged = SimpleNamespace(
        provenance=SimpleNamespace(
            emodel=SimpleNamespace(id="e", name="L5PC"),
            config=SimpleNamespace(
                target_efeatures=SimpleNamespace(task_result=SimpleNamespace(id_str=OPT_TARGETS))
            ),
        )
    )
    activity_id = str(uuid4())

    outputs = registration.register_output_entities(
        make_config(),
        tmp_path,
        client,
        staged=staged,
        summary={"passed": True},
        figures_dir=tmp_path / "missing",
        execution_activity_id=activity_id,
    )

    assert client.register_entity.call_args.args[0].authorized_public is True
    assert outputs.generated_ids == ["tr", "vr"]
    assert update.call_args.kwargs["generated_ids"] == ["tr", "vr"]


def test_aggregate_rejects_empty_scores():
    with pytest.raises(ValueError, match="empty"):
        validation_scoring.aggregate([], "max_score")


def test_score_model_builds_evaluator_when_not_given(monkeypatch):
    model = SimpleNamespace(scores={"A_1.soma.v.f": 1.0}, scores_validation={}, features={})
    build = MagicMock(return_value="evaluator")
    monkeypatch.setattr(evaluation, "get_evaluator_from_access_point", build)
    monkeypatch.setattr(evaluation, "compute_responses", lambda *_, **__: [model])
    monkeypatch.setattr("bluepyemodel.validation.validation.compute_scores", lambda *_: None)
    _, evaluator = validation_scoring.score_model(MagicMock(), seed=1, settings=SETTINGS)
    assert evaluator == "evaluator"
    build.assert_called_once()


class InlineExecutor:
    last_kwargs: ClassVar[dict] = {}

    def __init__(self, **kwargs):
        InlineExecutor.last_kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    @staticmethod
    def submit(fn, *args):
        return SimpleNamespace(result=lambda: fn(*args))


def test_score_model_isolated_runs_worker(monkeypatch, tmp_path):
    monkeypatch.setattr(validation_scoring, "ProcessPoolExecutor", InlineExecutor)
    worker = MagicMock(return_value={"passed": True})
    monkeypatch.setattr(validation_scoring, "score_model_worker", worker)
    summary = validation_scoring.score_model_isolated(
        access_point_factory=dict,
        access_point_kwargs={},
        working_dir=tmp_path,
        seed=1,
        settings=SETTINGS,
    )
    assert summary == {"passed": True}
    assert worker.call_args.args[2] == tmp_path
    assert InlineExecutor.last_kwargs["initargs"] == (str(tmp_path),)


def test_register_validation_results_when_overall_exists(monkeypatch):
    monkeypatch.setattr(validation_scoring, "register_validation_result", lambda **_: None)
    summary = {
        "passed": True,
        "settings": {},
        "protocols": {"A_1": {"validation": True, "passed": True}},
    }
    ids = validation_scoring.register_validation_results(
        client=MagicMock(), summary=summary, validated_entity_id="e", authorized_public=False
    )
    assert ids == []
