from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from obi_one.scientific.tasks.em_synapse_mapping.register import register_output


def _resolved_neuron(pt_root_id, *, use_me_model=False, me_model_entity=None, phys_node_props=None):
    return SimpleNamespace(
        pt_root_id=pt_root_id,
        use_me_model=use_me_model,
        me_model_entity=me_model_entity,
        phys_node_props=phys_node_props or {},
    )


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

    def test_passes_unique_emodels_and_labels_to_register_circuit(self, tmp_path):
        """One emodel/label pair per unique EModel is forwarded to register_circuit."""
        db_client = Mock()
        circuit_path = tmp_path / "circuit_config.json"
        circuit_path.write_text("{}")

        registered_circuit = SimpleNamespace(id=uuid4(), name="multi-synaptome")

        em_dataset = Mock()
        em_dataset.entity.return_value = SimpleNamespace(license=SimpleNamespace(id="lic"))

        emodel_a = SimpleNamespace(id="emodel-a")
        emodel_b = SimpleNamespace(id="emodel-b")
        neurons = [
            _resolved_neuron(
                111,
                use_me_model=True,
                me_model_entity=SimpleNamespace(emodel=emodel_a),
                phys_node_props={"model_template": ["hoc:mdl_a"]},
            ),
            _resolved_neuron(
                222,
                use_me_model=True,
                me_model_entity=SimpleNamespace(emodel=emodel_b),
                phys_node_props={"model_template": ["hoc:mdl_b"]},
            ),
            _resolved_neuron(333),  # morphology-only neuron contributes no derivation
            _resolved_neuron(
                444,
                use_me_model=True,
                # Shares emodel_a and therefore its hoc:mdl_<emodel_id> template:
                # must not produce a second derivation on the same EModel.
                me_model_entity=SimpleNamespace(emodel=emodel_a),
                phys_node_props={"model_template": ["hoc:mdl_a"]},
            ),
        ]

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
                resolved_neurons=neurons,
                source_dataset=_source_dataset(),
                em_dataset=em_dataset,
                all_notices=["notice"],
                total_internal=0,
                total_external=0,
            )

        mock_register.assert_called_once()
        call_kwargs = mock_register.call_args.kwargs
        # Neuron 444 shares emodel_a's template, so it collapses to one pair;
        # neuron 333 has no ME-model and contributes nothing.
        assert call_kwargs["derived_from_emodel"] == [emodel_a, emodel_b]
        assert call_kwargs["derivation_label"] == ["hoc:mdl_a", "hoc:mdl_b"]
