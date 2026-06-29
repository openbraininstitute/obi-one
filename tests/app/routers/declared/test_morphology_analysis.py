# tests/app/endpoints/test_morphology_analysis.py

import json

import pytest

import obi_one.scientific.library.morphology_measurement_annotation as uf
from app.endpoints.morphology_metrics_calculation import run_morphology_analysis

from tests.utils import DATA_DIR


def _flatten_measurements(measurements):
    flattened = {}

    for measurement in measurements:
        domain = measurement["structural_domain"]
        pref_label = measurement["pref_label"]

        for item in measurement["measurement_items"]:
            key = (
                domain,
                pref_label,
                item["name"],
                item["unit"],
            )
            flattened[key] = item["value"]

    return flattened


def test_real_morphology_metrics_match_golden_values():
    actual_measurements = run_morphology_analysis(str(DATA_DIR / "ch150801A1.swc"))

    expected_measurements = json.loads(
        (DATA_DIR / "measurement_kinds_ch150801A1_swc.json").read_text()
    )

    actual = _flatten_measurements(actual_measurements)
    expected = _flatten_measurements(expected_measurements)

    assert actual.keys() == expected.keys()

    for key, expected_value in expected.items():
        assert actual[key] == pytest.approx(expected_value), key


def test_morphology_metrics_do_not_reuse_apical_values_from_cached_template():
    uf.get_morphology_template.cache_clear()
    uf.get_morphology_analysis_dict.cache_clear()

    with_apical = uf.compute_morphometrics(DATA_DIR / "ch150801A1.swc")
    without_apical = uf.compute_morphometrics(DATA_DIR / "cell_morphology.asc")

    assert any(m["structural_domain"] == "apical_dendrite" for m in with_apical)
    assert not any(m["structural_domain"] == "apical_dendrite" for m in without_apical)


def test_metric_with_nan_values_is_skipped(monkeypatch, caplog):
    monkeypatch.setattr(uf.nm, "get", lambda *_args, **_kwargs: [1.0, float("nan"), 3.0])

    result = uf._process_measurement("section_tortuosity", "dimensionless", object())

    assert result == ["section_tortuosity", None, "dimensionless"]
    assert "1 of 3 values are NaN" in caplog.text
    json.dumps(result, allow_nan=False)


def test_scalar_nan_metric_is_skipped(monkeypatch, caplog):
    monkeypatch.setattr(uf.nm, "get", lambda *_args, **_kwargs: float("nan"))

    result = uf._process_measurement("soma_radius", "um", object())

    assert result == ["soma_radius", None, "um"]
    assert "Skipping NaN value for morphology metric soma_radius" in caplog.text
    json.dumps(result, allow_nan=False)
