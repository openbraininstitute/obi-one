from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from obi_one.scientific.tasks.em_synapse_mapping.register import register_output


def _resolved_neuron(pt_root_id, *, use_me_model=False):
    return SimpleNamespace(pt_root_id=pt_root_id, use_me_model=use_me_model)


def _source_dataset():
    return SimpleNamespace(
        name="dataset",
        subject=SimpleNamespace(name="mouse"),
        brain_region=SimpleNamespace(name="cortex"),
        experiment_date="2024-01-01",
    )


class TestRegisterOutputMultiple:
    def test_register_and_upload(self, tmp_path):
        db_client = Mock()
        circuit_path = tmp_path / "circuit_config.json"
        circuit_path.write_text("{}")

        registered_circuit = SimpleNamespace(id=uuid4(), name="multi-synaptome")

        em_dataset = Mock()
        em_dataset.entity.return_value = SimpleNamespace(license=SimpleNamespace(id="lic"))

        with (
            patch(
                "obi_one.scientific.tasks.em_synapse_mapping.register.assemble_publication_links",
                return_value={"10.1234/test": {"entity": Mock(), "type": "component_source"}},
            ),
            patch(
                "obi_one.scientific.tasks.em_synapse_mapping.register.circuit_registration.register_circuit",
                return_value=registered_circuit,
            ) as mock_register,
        ):
            result = register_output(
                db_client=db_client,
                circuit_path=circuit_path,
                resolved_neurons=[_resolved_neuron(111), _resolved_neuron(222)],
                source_dataset=_source_dataset(),
                em_dataset=em_dataset,
                all_notices=["notice-1"],
                total_internal=30,
                total_external=20,
            )

        assert result == str(registered_circuit.id)
        mock_register.assert_called_once()
        call_kwargs = mock_register.call_args.kwargs
        assert "Multi-synaptome" in call_kwargs["name"]
        assert call_kwargs["publications"] is not None

    def test_deduplicates_notices(self, tmp_path):
        db_client = Mock()
        circuit_path = tmp_path / "circuit_config.json"
        circuit_path.write_text("{}")

        registered_circuit = SimpleNamespace(id=uuid4(), name="multi-synaptome")

        em_dataset = Mock()
        em_dataset.entity.return_value = SimpleNamespace(license=SimpleNamespace(id="lic"))

        with (
            patch(
                "obi_one.scientific.tasks.em_synapse_mapping.register.assemble_publication_links",
                return_value={},
            ),
            patch(
                "obi_one.scientific.tasks.em_synapse_mapping.register.circuit_registration.register_circuit",
                return_value=registered_circuit,
            ) as mock_register,
        ):
            register_output(
                db_client=db_client,
                circuit_path=circuit_path,
                resolved_neurons=[_resolved_neuron(111), _resolved_neuron(222)],
                source_dataset=_source_dataset(),
                em_dataset=em_dataset,
                all_notices=["dup", "dup", "unique"],
                total_internal=0,
                total_external=0,
            )

        call_kwargs = mock_register.call_args.kwargs
        desc = call_kwargs["description"]
        assert desc.count("dup") == 1
        assert "unique" in desc
