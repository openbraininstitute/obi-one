from unittest.mock import MagicMock, patch

import pytest

from obi_one.core.exception import OBIONEError
from obi_one.scientific.from_id.circuit_from_id import (
    CircuitFromID,
    MEModelWithSynapsesCircuitFromID,
)

_MODULE = "obi_one.scientific.from_id.circuit_from_id"


def _sonata_asset():
    asset = MagicMock()
    asset.label = "sonata_circuit"
    return asset


def test_circuit_from_id_stage_circuit(tmp_path):
    dest_dir = tmp_path / "circuit_staging"
    circuit_from_id = CircuitFromID(id_str="circuit-1")
    entity = MagicMock()
    entity.assets = [_sonata_asset()]
    db_client = MagicMock()
    expected_circuit = MagicMock()

    with (
        patch.object(CircuitFromID, "entity", return_value=entity),
        patch(f"{_MODULE}.stage_circuit") as mock_stage,
        patch(f"{_MODULE}.Circuit", return_value=expected_circuit) as mock_circuit_cls,
    ):
        result = circuit_from_id.stage_circuit(
            dest_dir=dest_dir,
            db_client=db_client,
            entity_cache=False,
        )

    assert result is expected_circuit
    mock_stage.assert_called_once_with(
        client=db_client,
        model=entity,
        output_dir=dest_dir,
        max_concurrent=4,
    )
    mock_circuit_cls.assert_called_once_with(
        name=str(circuit_from_id),
        path=str(dest_dir / "circuit_config.json"),
    )


def test_circuit_from_id_stage_circuit_raises_when_dest_exists(tmp_path):
    circuit_from_id = CircuitFromID(id_str="circuit-1")
    entity = MagicMock()
    entity.assets = [_sonata_asset()]

    with (
        patch.object(CircuitFromID, "entity", return_value=entity),
        pytest.raises(FileExistsError, match="already exists"),
    ):
        circuit_from_id.stage_circuit(dest_dir=tmp_path, db_client=MagicMock())


def test_circuit_from_id_stage_circuit_skips_staging_with_cache(tmp_path):
    circuit_from_id = CircuitFromID(id_str="circuit-1")
    entity = MagicMock()
    entity.assets = [_sonata_asset()]

    with (
        patch.object(CircuitFromID, "entity", return_value=entity),
        patch(f"{_MODULE}.stage_circuit") as mock_stage,
        patch(f"{_MODULE}.Circuit", return_value=MagicMock()),
    ):
        circuit_from_id.stage_circuit(
            dest_dir=tmp_path,
            db_client=MagicMock(),
            entity_cache=True,
        )

    mock_stage.assert_not_called()


def test_circuit_from_id_stage_circuit_missing_asset():
    circuit_from_id = CircuitFromID(id_str="circuit-1")
    entity = MagicMock()
    entity.assets = [MagicMock(label="other")]

    with (
        patch.object(CircuitFromID, "entity", return_value=entity),
        pytest.raises(OBIONEError, match="No 'sonata_circuit' asset found"),
    ):
        circuit_from_id.stage_circuit(db_client=MagicMock())


def test_memodel_with_synapses_entity_requires_single_scale():
    circuit_from_id = MEModelWithSynapsesCircuitFromID(id_str="circuit-1")
    entity = MagicMock()
    entity.scale = "microcircuit"
    circuit_from_id._entity = entity

    with pytest.raises(OBIONEError, match="scale 'single'"):
        circuit_from_id.entity(db_client=MagicMock())


def test_memodel_with_synapses_stage_circuit(tmp_path):
    dest_dir = tmp_path / "circuit_staging"
    circuit_from_id = MEModelWithSynapsesCircuitFromID(id_str="circuit-1")
    entity = MagicMock()
    entity.scale = "single"
    entity.assets = [_sonata_asset()]
    expected_circuit = MagicMock()

    with (
        patch.object(MEModelWithSynapsesCircuitFromID, "entity", return_value=entity),
        patch(f"{_MODULE}.stage_circuit") as mock_stage,
        patch(f"{_MODULE}.MEModelWithSynapsesCircuit", return_value=expected_circuit) as mock_cls,
    ):
        result = circuit_from_id.stage_circuit(dest_dir=dest_dir, db_client=MagicMock())

    assert result is expected_circuit
    mock_stage.assert_called_once()
    mock_cls.assert_called_once_with(
        name=dest_dir.name,
        path=str(dest_dir / "circuit_config.json"),
    )
