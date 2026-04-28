# tests/app/endpoints/test_morphology_analysis.py

import json

import pytest

from app.endpoints.morphology_metrics_calculation import _run_morphology_analysis

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
    actual_measurements = _run_morphology_analysis(str(DATA_DIR / "ch150801A1.swc"))

    expected_measurements = json.loads(
        (DATA_DIR / "measurement_kinds_ch150801A1_swc.json").read_text()
    )

    actual = _flatten_measurements(actual_measurements)
    expected = _flatten_measurements(expected_measurements)

    assert actual.keys() == expected.keys()

    for key, expected_value in expected.items():
        assert actual[key] == pytest.approx(expected_value), key
