import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("bluepyemodel")

from bluepyemodel.evaluation import evaluation
from bluepyemodel.validation import validation as bpem_validation

from obi_one.scientific.tasks.emodel_building import validation_scoring
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization import task

SETTINGS = SimpleNamespace(
    optimization_settings=SimpleNamespace(
        validation_function="mean_score", validation_threshold=4.0
    )
)


def access_point(protocols):
    return SimpleNamespace(pipeline_settings=SimpleNamespace(validation_protocols=protocols))


def write_features(path, validation=()):
    protocols = [{"name": n, "validation": n in validation} for n in ("IDrest_150", "IDrest_250")]
    path.write_text(json.dumps({"protocols": protocols}), encoding="utf-8")


class TestResolveInlineValidationSettings:
    def test_uses_recipe_protocols(self, tmp_path):
        features = tmp_path / "f.json"
        write_features(features, validation=("IDrest_150",))
        settings = task.resolve_inline_validation_settings(
            SETTINGS, access_point(["IDrest_250"]), features
        )
        assert settings.validation_protocols == ["IDrest_250"]
        assert settings.validation_function == "mean_score"
        assert settings.validation_threshold == pytest.approx(4.0)
        assert settings.validation_protocols_only is False

    def test_falls_back_to_extraction_flags(self, tmp_path):
        features = tmp_path / "f.json"
        write_features(features, validation=("IDrest_150",))
        settings = task.resolve_inline_validation_settings(SETTINGS, access_point([]), features)
        assert settings.validation_protocols == ["IDrest_150"]

    def test_nothing_held_out(self, tmp_path):
        features = tmp_path / "f.json"
        write_features(features)
        assert (
            task.resolve_inline_validation_settings(SETTINGS, access_point(None), features) is None
        )


INLINE_CONFIG = SimpleNamespace(
    initialize=SimpleNamespace(emodel="L5PC"),
    optimization_settings=SETTINGS.optimization_settings,
)


def run_inline(tmp_path, validation=()):
    features = tmp_path / "config" / "features" / "L5PC.json"
    features.parent.mkdir(parents=True)
    write_features(features, validation=validation)
    return task.run_inline_validation(
        config=INLINE_CONFIG,
        access_point=access_point([]),
        access_point_kwargs={"emodel": "L5PC"},
        coord_root=tmp_path,
        seed=3,
    )


def test_run_inline_validation_skips_without_protocols(tmp_path, monkeypatch):
    score = MagicMock()
    monkeypatch.setattr(validation_scoring, "score_model_isolated", score)
    assert run_inline(tmp_path) is None
    score.assert_not_called()


def test_run_inline_validation_failure_is_not_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(
        validation_scoring, "score_model_isolated", MagicMock(side_effect=RuntimeError("boom"))
    )
    assert run_inline(tmp_path, validation=("IDrest_250",)) is None


def test_run_inline_validation_scores_in_isolated_process(tmp_path, monkeypatch):
    summary = {"passed": True}
    score = MagicMock(return_value=summary)
    monkeypatch.setattr(validation_scoring, "score_model_isolated", score)
    assert run_inline(tmp_path, validation=("IDrest_250",)) is summary
    kwargs = score.call_args.kwargs
    assert kwargs["seed"] == 3
    assert kwargs["working_dir"] == tmp_path
    assert kwargs["access_point_factory"] is task.create_entitycore_access_point
    assert kwargs["access_point_kwargs"] == {"emodel": "L5PC"}
    assert kwargs["settings"].validation_protocols == ["IDrest_250"]


def test_score_model_worker_builds_access_point_in_working_dir(tmp_path, monkeypatch):
    seen = {}

    def factory(**kwargs):
        seen["cwd"] = Path.cwd()
        seen["kwargs"] = kwargs
        return "access-point"

    monkeypatch.setattr(validation_scoring, "score_model", lambda ap, **_: ({"ap": ap}, None))
    settings = validation_scoring.ResolvedValidationSettings(
        validation_protocols=["p"],
        validation_protocols_only=False,
        validation_function="max_score",
        validation_threshold=5.0,
    )
    summary = validation_scoring.score_model_worker(
        factory, {"emodel": "L5PC"}, tmp_path, 1, settings
    )
    assert summary == {"ap": "access-point"}
    assert seen == {"cwd": tmp_path.resolve(), "kwargs": {"emodel": "L5PC"}}


def test_score_model_stores_verdict(monkeypatch):
    model = SimpleNamespace(
        scores={"IDrest_150.soma.v.Spikecount": 1.0},
        scores_validation={},
        features={},
        passed_validation=None,
    )

    def fake_compute_scores(m, validation_protocols):
        assert validation_protocols == ["IDrest_250"]
        m.scores_validation["IDrest_250.soma.v.Spikecount"] = 2.0

    monkeypatch.setattr(evaluation, "compute_responses", lambda *_, **__: [model])
    monkeypatch.setattr(bpem_validation, "compute_scores", fake_compute_scores)
    ap = MagicMock()
    settings = validation_scoring.ResolvedValidationSettings(
        validation_protocols=["IDrest_250"],
        validation_protocols_only=True,
        validation_function="max_score",
        validation_threshold=5.0,
    )
    summary, evaluator = validation_scoring.score_model(
        ap, seed=1, settings=settings, cell_evaluator="evaluator"
    )
    assert summary["passed"] is True
    assert summary["score"] == pytest.approx(2.0)
    assert evaluator == "evaluator"
    assert model.passed_validation is True
    ap.store_or_update_emodel.assert_called_once_with(model)


def test_score_model_requires_one_model(monkeypatch):
    monkeypatch.setattr(evaluation, "compute_responses", lambda *_, **__: [])
    settings = validation_scoring.ResolvedValidationSettings(
        validation_protocols=["p"],
        validation_protocols_only=False,
        validation_function="max_score",
        validation_threshold=5.0,
    )
    with pytest.raises(RuntimeError, match="Expected one optimised model"):
        validation_scoring.score_model(MagicMock(), seed=1, settings=settings, cell_evaluator="e")


def test_register_validation_results_without_suffix(monkeypatch):
    calls = []
    monkeypatch.setattr(
        validation_scoring,
        "register_validation_result",
        lambda **kw: calls.append(kw) or (None if len(calls) == 2 else SimpleNamespace(id="vr")),
    )
    summary = {
        "passed": False,
        "settings": {},
        "protocols": {"A_1": {"validation": True, "passed": False}, "B_1": {"validation": False}},
    }
    ids = validation_scoring.register_validation_results(
        client=MagicMock(), summary=summary, validated_entity_id="e", authorized_public=False
    )
    assert [c["name"] for c in calls] == ["E-feature score validation", "E-feature validation: A_1"]
    assert ids == ["vr"]
