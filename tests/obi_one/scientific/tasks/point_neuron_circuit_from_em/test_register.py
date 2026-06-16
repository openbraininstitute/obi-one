from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from entitysdk.types import CircuitBuildCategory, TargetSimulator

from obi_one.scientific.tasks.point_neuron_circuit_from_em.register import (
    circuit_metadata,
    register_point_neuron_circuit,
)

_REGISTER_MODULE = "obi_one.scientific.tasks.point_neuron_circuit_from_em.register"


def _source_dataset():
    return SimpleNamespace(
        name="FlyWire FAFB",
        subject=SimpleNamespace(
            name="FlyWire subject",
            species=SimpleNamespace(name="Drosophila melanogaster"),
        ),
        brain_region=SimpleNamespace(name="root", hierarchy_id=uuid4()),
        license=SimpleNamespace(label="MIT"),
        experiment_date=datetime(2024, 10, 2),  # noqa: DTZ001
    )


def _db_with_hierarchy(name="FlyWire hierarchy"):
    db = Mock()
    db.get_entity.return_value = SimpleNamespace(name=name)
    return db


class TestCircuitMetadata:
    def test_linked_entities_come_from_em_dataset(self):
        md = circuit_metadata(_db_with_hierarchy(), _source_dataset(), [111, 222], 3)
        assert md["species"] == "Drosophila melanogaster"
        assert md["subject"] == "FlyWire subject"
        assert md["brain_region"] == "root"
        assert md["brain_region_hierarchy"] == "FlyWire hierarchy"
        assert md["license"] == "MIT"
        assert md["experiment_date"] == "02.10.2024"
        assert md["build_category"] == CircuitBuildCategory.computational_model
        assert md["target_simulator"] == TargetSimulator.Brian2
        assert md["scale_override"] is None
        # Keys the resolvers access directly (not via .get) must be present.
        for key in ("root", "parent", "derivation_type"):
            assert key in md

    def test_handles_missing_license_and_date(self):
        ds = _source_dataset()
        ds.license = None
        ds.experiment_date = None
        md = circuit_metadata(_db_with_hierarchy(), ds, [111], 0)
        assert md["license"] is None
        assert md["experiment_date"] is None


class TestRegisterPointNeuronCircuit:
    def test_skips_when_circuit_already_exists(self):
        db = Mock()
        db.search_entity.return_value.all.return_value = [SimpleNamespace(id="existing-id")]
        db.get_entity.return_value = SimpleNamespace(name="H")
        with patch(f"{_REGISTER_MODULE}.register_circuit_from_metadata") as mock_register:
            cid = register_point_neuron_circuit(
                db, Path("out/circuit_config.json"), _source_dataset(), [111], 0
            )
        mock_register.assert_not_called()
        assert cid == "existing-id"

    def test_registers_with_metadata_from_dataset(self):
        db = Mock()
        db.search_entity.return_value.all.return_value = []
        db.get_entity.return_value = SimpleNamespace(name="FlyWire hierarchy")
        with patch(
            f"{_REGISTER_MODULE}.register_circuit_from_metadata",
            return_value=SimpleNamespace(id="new-id"),
        ) as mock_register:
            cid = register_point_neuron_circuit(
                db, Path("out/circuit_config.json"), _source_dataset(), [111, 222], 1
            )
        mock_register.assert_called_once()
        kwargs = mock_register.call_args.kwargs
        assert kwargs["circuit_path"] == "out/circuit_config.json"
        assert kwargs["circuit_metadata"]["subject"] == "FlyWire subject"
        assert kwargs["circuit_metadata"]["brain_region_hierarchy"] == "FlyWire hierarchy"
        assert cid == "new-id"
