from unittest.mock import Mock

import pytest

from obi_one.core.exception import OBIONEError
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.library.morphology_metrics import MorphologyMetricsOutput
from obi_one.scientific.tasks.morphology_metrics.config import (
    MorphologyMetricsScanConfig,
    MorphologyMetricsSingleConfig,
)
from obi_one.scientific.tasks.morphology_metrics.task import MorphologyMetricsTask


def test_morphology_metrics_scan_config_accepts_morphology_from_id():
    morph = CellMorphologyFromID(id_str="morphology-id")
    config = MorphologyMetricsScanConfig(
        initialize=MorphologyMetricsScanConfig.Initialize(morphology=morph)
    )
    assert config.initialize.morphology.id_str == "morphology-id"


def test_morphology_metrics_task_execute_returns_metrics(monkeypatch):
    morph = CellMorphologyFromID(id_str="morphology-id")
    config = MorphologyMetricsSingleConfig(
        initialize=MorphologyMetricsScanConfig.Initialize(morphology=morph)
    )
    expected = MorphologyMetricsOutput(soma_radius=1.0)
    monkeypatch.setattr(
        CellMorphologyFromID,
        "neurom_morphology",
        Mock(return_value=Mock(name="neurom_morphology")),
    )
    monkeypatch.setattr(
        MorphologyMetricsOutput,
        "from_morphology",
        Mock(return_value=expected),
    )

    result = MorphologyMetricsTask(config=config).execute(db_client=Mock())

    assert result is expected


def test_morphology_metrics_task_execute_wraps_errors(monkeypatch):
    morph = CellMorphologyFromID(id_str="morphology-id")
    config = MorphologyMetricsSingleConfig(
        initialize=MorphologyMetricsScanConfig.Initialize(morphology=morph)
    )
    monkeypatch.setattr(
        CellMorphologyFromID,
        "neurom_morphology",
        Mock(side_effect=RuntimeError("load failed")),
    )

    with pytest.raises(OBIONEError, match="Internal Server Error: load failed"):
        MorphologyMetricsTask(config=config).execute(db_client=Mock())
