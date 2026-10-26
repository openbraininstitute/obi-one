import json
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from entitysdk.exception import IteratorResultError
from pydantic import ValidationError

pytest.importorskip("bluepyemodel")

from obi_one.scientific.tasks.emodel_building import validation_scoring
from obi_one.scientific.tasks.emodel_building.task3_emodel_validation import (
    registration,
    staging,
)
from obi_one.scientific.tasks.emodel_building.task3_emodel_validation.config import (
    EModelValidationSingleConfig,
)

INFO = {"campaign_name": "c", "campaign_description": "d"}


OPTIMISATION_TARGETS = "opt-extraction-id"


def make_config(targets=OPTIMISATION_TARGETS, **kwargs) -> EModelValidationSingleConfig:
    return EModelValidationSingleConfig(
        info=INFO,
        emodel={"emodel": {"id_str": "emodel-id"}},
        target_efeatures={"task_result": {"id_str": targets}},
        **kwargs,
    )


def write_features(path, names, validation=()):
    protocols = [{"name": n, "stimuli": [], "validation": n in validation} for n in names]
    path.write_text(json.dumps({"efeatures": [], "protocols": protocols}), encoding="utf-8")


def optimisation_config(validation_protocols=("IDrest_250",)):
    return SimpleNamespace(
        target_efeatures=SimpleNamespace(task_result=SimpleNamespace(id_str=OPTIMISATION_TARGETS)),
        optimization_settings=SimpleNamespace(
            validation_protocols=validation_protocols,
            validation_function="max_score",
            validation_threshold=5.0,
        ),
    )


class TestResolveSettings:
    def test_defaults_come_from_optimisation(self, tmp_path):
        features = tmp_path / "f.json"
        write_features(features, ["IDrest_150", "IDrest_250"])
        settings = staging.resolve_settings(make_config(), optimisation_config(), features)
        assert settings.validation_protocols == ["IDrest_250"]
        assert settings.validation_function == "max_score"
        assert settings.validation_threshold == pytest.approx(5.0)
        assert settings.validation_protocols_only is False

    def test_falls_back_to_protocols_flagged_by_extraction(self, tmp_path):
        features = tmp_path / "f.json"
        write_features(features, ["IDrest_150", "IDrest_250"], validation=("IDrest_250",))
        settings = staging.resolve_settings(make_config(), optimisation_config(()), features)
        assert settings.validation_protocols == ["IDrest_250"]

    def test_fresh_extraction_defaults_to_all_protocols(self, tmp_path):
        features = tmp_path / "f.json"
        write_features(features, ["IDrest_150", "IV_-40"])
        config = make_config(targets="fresh-extraction-id")
        settings = staging.resolve_settings(config, optimisation_config(), features)
        assert settings.validation_protocols == ["IDrest_150", "IV_-40"]

    def test_validation_only_without_protocols_raises(self, tmp_path):
        features = tmp_path / "f.json"
        write_features(features, ["IDrest_150"])
        config = make_config(settings={"validation_protocols_only": True})
        with pytest.raises(ValueError, match="no validation protocols"):
            staging.resolve_settings(config, optimisation_config(()), features)


def test_mark_validation_protocols(tmp_path):
    features = tmp_path / "f.json"
    write_features(features, ["IDrest_150", "IDrest_250"], validation=("IDrest_150",))
    staging.mark_validation_protocols(features, ["IDrest_250.0"])
    flags = {p["name"]: p["validation"] for p in json.loads(features.read_text())["protocols"]}
    assert flags == {"IDrest_150": False, "IDrest_250": True}


def test_stage_final_entry_keeps_only_the_seed(tmp_path, monkeypatch):
    final = {
        "L5PC__1": {"emodel": "L5PC", "seed": 1, "validated": True, "validation_fitness": {"a": 1}},
        "L5PC__2": {"emodel": "L5PC", "seed": 2},
    }
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps(final), encoding="utf-8")
    monkeypatch.setattr(staging.db_sdk, "fetch_asset_by_label", lambda **_: summary)
    provenance = SimpleNamespace(
        emodel=SimpleNamespace(seed=1),
        config=SimpleNamespace(initialize=SimpleNamespace(emodel="L5PC")),
        task_result=SimpleNamespace(id="tr-id"),
    )
    entry = staging.stage_final_entry(provenance, tmp_path, MagicMock())
    written = json.loads((tmp_path / "final.json").read_text())
    assert list(written) == ["L5PC__1"]
    assert entry["validated"] is None
    assert entry["validation_fitness"] == {}


def test_stage_final_entry_missing_seed_raises(tmp_path, monkeypatch):
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"L5PC__2": {"emodel": "L5PC", "seed": 2}}), encoding="utf-8")
    monkeypatch.setattr(staging.db_sdk, "fetch_asset_by_label", lambda **_: summary)
    provenance = SimpleNamespace(
        emodel=SimpleNamespace(seed=1),
        config=SimpleNamespace(initialize=SimpleNamespace(emodel="L5PC")),
        task_result=SimpleNamespace(id="tr-id"),
    )
    with pytest.raises(ValueError, match="seed=1"):
        staging.stage_final_entry(provenance, tmp_path, MagicMock())


def synthesized_provenance(task_result=None):
    return SimpleNamespace(
        emodel=SimpleNamespace(
            id="emodel-id",
            seed=7,
            iteration="thalamoreticular",
            score=3.5,
            species=SimpleNamespace(name="Mus musculus"),
            brain_region=SimpleNamespace(name="TH"),
            etypes=[SimpleNamespace(pref_label="dNAD_ltb")],
            mtypes=[SimpleNamespace(pref_label="VPM_TC")],
        ),
        config=SimpleNamespace(initialize=SimpleNamespace(emodel="EM__test__0")),
        task_result=task_result,
    )


def test_stage_final_entry_synthesized_from_emodel_output(tmp_path, monkeypatch):
    output = {
        "parameter": [{"name": "g_pas.all", "value": 4e-5}],
        "fitness": 3.5,
        "score": [{"name": "Step_150.soma.v.AP_amplitude", "value": 0.2}],
        "features": [{"name": "Step_150.soma.v.AP_amplitude", "value": 45.0}],
        "seed": 7,
    }
    monkeypatch.setattr(staging.db_sdk, "select_json_asset_content", lambda **_: output)
    entry = staging.stage_final_entry(synthesized_provenance(), tmp_path, MagicMock())
    written = json.loads((tmp_path / "final.json").read_text())
    assert list(written) == ["EM__test__0__7"]
    assert entry["parameters"] == {"g_pas.all": 4e-5}
    assert entry["etype"] == "dNAD_ltb"
    assert entry["mtype"] == "VPM_TC"
    assert entry["species"] == "Mus musculus"
    assert entry["brain_region"] == "TH"
    assert entry["iteration"] == "thalamoreticular"
    assert entry["fitness"] == {"Step_150.soma.v.AP_amplitude": 0.2}
    assert entry["features"] == {"Step_150.soma.v.AP_amplitude": 45.0}
    assert entry["validated"] is None
    assert entry["validation_fitness"] == {}


def test_stage_final_entry_synthesized_requires_parameters(tmp_path, monkeypatch):
    monkeypatch.setattr(staging.db_sdk, "select_json_asset_content", lambda **_: {"parameter": []})
    with pytest.raises(ValueError, match="no parameters"):
        staging.stage_final_entry(synthesized_provenance(), tmp_path, MagicMock())


def test_stage_final_entry_synthesized_requires_optimisation_output(tmp_path, monkeypatch):
    def raise_empty(**_):
        raise IteratorResultError

    monkeypatch.setattr(staging.db_sdk, "select_json_asset_content", raise_empty)
    with pytest.raises(ValueError, match="no emodel_optimization_output asset"):
        staging.stage_final_entry(synthesized_provenance(), tmp_path, MagicMock())


def test_resolve_provenance_without_activity_raises():
    client = MagicMock()
    client.search_entity.return_value.first.return_value = None
    with pytest.raises(ValueError, match="only e-models optimised on the platform"):
        staging.resolve_optimisation_provenance(str(uuid4()), client)


class TestCampaignConfigJson:
    @staticmethod
    def task_config(**kwargs):
        defaults = {
            "id": "config-id",
            "meta": {"scan_parameters": {}},
            "task_config_generator_id": "campaign-id",
        }
        return SimpleNamespace(**(defaults | kwargs))

    def test_rebuilds_single_config_from_scan_form(self, monkeypatch):
        scan = {
            "type": "GridScanGenerationTask",
            "form": {"type": "EModelOptimizationScanConfig", "initialize": {"emodel": "L5PC"}},
        }
        monkeypatch.setattr(staging.db_sdk, "select_json_asset_content", lambda **_: scan)
        client = MagicMock()
        client.get_entity.return_value = SimpleNamespace(id="campaign-id")
        result = staging._campaign_config_json(self.task_config(), client)
        assert result["type"] == "EModelOptimizationSingleConfig"
        assert result["initialize"] == {"emodel": "L5PC"}

    def test_bare_scan_config_without_form(self, monkeypatch):
        scan = {"type": "EModelOptimizationScanConfig", "initialize": {"emodel": "L5PC"}}
        monkeypatch.setattr(staging.db_sdk, "select_json_asset_content", lambda **_: scan)
        client = MagicMock()
        client.get_entity.return_value = SimpleNamespace(id="campaign-id")
        result = staging._campaign_config_json(self.task_config(), client)
        assert result["type"] == "EModelOptimizationSingleConfig"

    def test_scan_parameters_raise(self):
        task_config = self.task_config(meta={"scan_parameters": {"seed": [1, 2]}})
        with pytest.raises(ValueError, match="cannot be reconstructed"):
            staging._campaign_config_json(task_config, MagicMock())

    def test_missing_campaign_raises(self):
        task_config = self.task_config(task_config_generator_id=None)
        with pytest.raises(ValueError, match="no task_config asset and no campaign"):
            staging._campaign_config_json(task_config, MagicMock())

    def test_missing_campaign_asset_raises(self, monkeypatch):
        def raise_empty(**_):
            raise IteratorResultError

        monkeypatch.setattr(staging.db_sdk, "select_json_asset_content", raise_empty)
        client = MagicMock()
        client.get_entity.return_value = SimpleNamespace(id="campaign-id")
        with pytest.raises(ValueError, match="no task_config asset either"):
            staging._campaign_config_json(self.task_config(), client)


class TestSummariseModel:
    @staticmethod
    def model():
        return SimpleNamespace(
            scores={"IDrest_150.soma.v.Spikecount": 1.0, "IDrest_150.soma.v.AP_amplitude": 2.0},
            scores_validation={"IDrest_250.soma.v.Spikecount": 6.0},
            features={"IDrest_250.soma.v.Spikecount": 12.0},
        )

    @staticmethod
    def settings(**kwargs):
        defaults = {
            "validation_protocols": ["IDrest_250"],
            "validation_protocols_only": False,
            "validation_function": "max_score",
            "validation_threshold": 5.0,
        }
        return validation_scoring.ResolvedValidationSettings(**(defaults | kwargs))

    def test_max_score(self):
        summary = validation_scoring.summarise_model(self.model(), self.settings())
        assert summary["passed"] is False
        assert summary["score"] == pytest.approx(6.0)
        assert summary["protocols"]["IDrest_150"] | {"features": None} == {
            "validation": False,
            "features": None,
            "score": 2.0,
            "passed": True,
        }
        protocol = summary["protocols"]["IDrest_250"]
        assert protocol["validation"] is True
        assert protocol["passed"] is False
        assert protocol["features"]["IDrest_250.soma.v.Spikecount"]["model_value"] == pytest.approx(
            12.0
        )

    def test_mean_score(self):
        summary = validation_scoring.summarise_model(
            self.model(), self.settings(validation_function="mean_score")
        )
        assert summary["score"] == pytest.approx(3.0)
        assert summary["passed"] is True

    def test_validation_protocols_only(self):
        summary = validation_scoring.summarise_model(
            self.model(),
            self.settings(validation_function="mean_score", validation_protocols_only=True),
        )
        assert summary["score"] == pytest.approx(6.0)


def test_aggregate_rejects_unknown_function():
    with pytest.raises(ValueError, match="Unknown validation function"):
        validation_scoring.aggregate([1.0], "median")


def test_morphology_cannot_be_overridden():
    with pytest.raises(ValidationError, match="morphology"):
        make_config(morphology={"type": "OtherMorphology", "cell_morphology": {"id_str": "m"}})


def test_targets_are_required():
    with pytest.raises(ValidationError, match="target_efeatures"):
        EModelValidationSingleConfig(info=INFO, emodel={"emodel": {"id_str": "emodel-id"}})


def test_uses_optimisation_targets():
    assert staging.uses_optimisation_targets(make_config(), optimisation_config())
    assert not staging.uses_optimisation_targets(
        make_config(targets="fresh-extraction-id"), optimisation_config()
    )


def test_result_name_suffix():
    suffix = registration.result_name_suffix(make_config(), uses_optimisation_targets=True)
    assert suffix == " [validation]"
    config = make_config(
        targets="1234567890",
        settings={
            "validation_protocols_only": True,
            "validation_function": "mean_score",
            "validation_threshold": 3.0,
        },
    )
    assert registration.result_name_suffix(config, uses_optimisation_targets=False) == (
        " [validation, extraction 12345678, validation protocols only, mean_score, threshold 3]"
    )


def test_register_output_entities(tmp_path, monkeypatch):
    figures = tmp_path / "figures"
    figures.mkdir()
    (figures / "traces.pdf").write_bytes(b"%PDF")
    (figures / "ignored.txt").write_text("x")
    registered = []

    def fake_register(**kwargs):
        registered.append(kwargs)
        return SimpleNamespace(id=f"vr-{len(registered)}")

    monkeypatch.setattr(validation_scoring, "register_validation_result", fake_register)
    client = MagicMock()
    client.register_entity.return_value = SimpleNamespace(id="tr-id")
    staged = SimpleNamespace(
        provenance=SimpleNamespace(
            emodel=SimpleNamespace(id="emodel-id", name="L5PC"), config=optimisation_config()
        )
    )
    summary = {
        "passed": False,
        "score": 6.0,
        "settings": {},
        "protocols": {
            "IDrest_150": {"validation": False, "passed": True},
            "IDrest_250": {"validation": True, "passed": False},
        },
    }
    outputs = registration.register_output_entities(
        make_config(),
        tmp_path,
        client,
        staged=staged,
        summary=summary,
        figures_dir=figures,
    )
    assert outputs.generated_ids == ["tr-id", "vr-1", "vr-2"]
    assert [r["name"] for r in registered] == [
        "E-feature score validation [validation]",
        "E-feature validation: IDrest_250 [validation]",
    ]
    assert registered[0]["figure_files"] == [figures / "traces.pdf"]
    assert client.upload_file.call_count == 2


def write_typed_features(path, protocol_type, pre_protocols=()):
    protocols = [{"name": "IDrest_150", "protocol_type": protocol_type}]
    efeatures = [{"protocol_name": name} for name in ("IDrest_150", *pre_protocols)]
    path.write_text(json.dumps({"efeatures": efeatures, "protocols": protocols}), encoding="utf-8")


class TestCheckThresholdSearchTargets:
    def test_absolute_protocols_need_nothing(self, tmp_path):
        features = tmp_path / "f.json"
        write_typed_features(features, "Protocol")
        staging.check_threshold_search_targets(features)

    def test_threshold_based_with_targets(self, tmp_path):
        features = tmp_path / "f.json"
        write_typed_features(
            features,
            "ThresholdBasedProtocol",
            ("RMPProtocol", "RinProtocol", "SearchHoldingCurrent"),
        )
        staging.check_threshold_search_targets(features)

    def test_threshold_based_missing_targets(self, tmp_path):
        features = tmp_path / "f.json"
        write_typed_features(features, "ThresholdBasedProtocol", ("RMPProtocol",))
        with pytest.raises(ValueError, match=r"RinProtocol', 'SearchHoldingCurrent"):
            staging.check_threshold_search_targets(features)

    def test_no_holding_does_not_need_holding_search(self, tmp_path):
        features = tmp_path / "f.json"
        write_typed_features(
            features, "ThresholdBasedNoHoldingProtocol", ("RMPProtocol", "RinProtocol")
        )
        staging.check_threshold_search_targets(features)


def test_validation_protocols_cannot_be_set():
    with pytest.raises(ValidationError, match="validation_protocols"):
        make_config(settings={"validation_protocols": ["IDrest_250"]})
