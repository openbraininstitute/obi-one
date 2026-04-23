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
        circuit = SimpleNamespace(id=uuid4())
        db_client.register_entity.side_effect = [circuit, "link-1"]

        compressed = tmp_path / "sonata.tar.gz"
        compressed.write_bytes(b"x" * 100)

        em_dataset = Mock()
        em_dataset.entity.return_value = SimpleNamespace(license=SimpleNamespace(id="lic"))

        with (
            patch(
                "obi_one.scientific.tasks.em_synapse_mapping.register.assemble_publication_links",
                return_value=[SimpleNamespace(id=uuid4())],
            ),
            patch(
                "obi_one.scientific.tasks.em_synapse_mapping.register.Circuit",
                return_value=SimpleNamespace(name="fake-circuit"),
            ),
            patch(
                "obi_one.scientific.tasks.em_synapse_mapping.register.ScientificArtifactPublicationLink",
                return_value=SimpleNamespace(id=uuid4()),
            ),
        ):
            result = register_output(
                db_client=db_client,
                resolved_neurons=[_resolved_neuron(111), _resolved_neuron(222)],
                source_dataset=_source_dataset(),
                em_dataset=em_dataset,
                all_notices=["notice-1"],
                total_synapses=50,
                total_connections=40,
                total_internal=30,
                total_external=20,
                file_paths={"a.txt": str(tmp_path / "a.txt")},
                compressed_path=compressed,
            )

        assert result == str(circuit.id)
        db_client.upload_directory.assert_called_once()
        db_client.upload_file.assert_called_once()

    def test_upload_large_compressed_with_multipart(self, tmp_path):
        db_client = Mock()
        circuit = SimpleNamespace(id=uuid4())
        db_client.register_entity.return_value = circuit

        compressed = tmp_path / "sonata.tar.gz"
        compressed.write_bytes(b"x" * 600_000_000)

        em_dataset = Mock()
        em_dataset.entity.return_value = SimpleNamespace(license=SimpleNamespace(id="lic"))

        with (
            patch(
                "obi_one.scientific.tasks.em_synapse_mapping.register.assemble_publication_links",
                return_value=[],
            ),
            patch(
                "obi_one.scientific.tasks.em_synapse_mapping.register.Circuit",
                return_value=SimpleNamespace(name="fake-circuit"),
            ),
        ):
            register_output(
                db_client=db_client,
                resolved_neurons=[_resolved_neuron(111), _resolved_neuron(222)],
                source_dataset=_source_dataset(),
                em_dataset=em_dataset,
                all_notices=[],
                total_synapses=0,
                total_connections=0,
                total_internal=0,
                total_external=0,
                file_paths={},
                compressed_path=compressed,
            )

        db_client.upload_file.assert_called_once()
        call_kwargs = db_client.upload_file.call_args.kwargs
        assert call_kwargs["transfer_config"] is not None

    def test_deduplicates_notices(self, tmp_path):
        db_client = Mock()
        circuit = SimpleNamespace(id=uuid4())
        db_client.register_entity.return_value = circuit

        compressed = tmp_path / "sonata.tar.gz"
        compressed.write_bytes(b"x" * 100)

        em_dataset = Mock()
        em_dataset.entity.return_value = SimpleNamespace(license=SimpleNamespace(id="lic"))

        captured_description = {}

        def fake_circuit(**kwargs):
            captured_description["desc"] = kwargs.get("description", "")
            return SimpleNamespace(name="fake")

        with (
            patch(
                "obi_one.scientific.tasks.em_synapse_mapping.register.assemble_publication_links",
                return_value=[],
            ),
            patch(
                "obi_one.scientific.tasks.em_synapse_mapping.register.Circuit",
                side_effect=fake_circuit,
            ),
        ):
            register_output(
                db_client=db_client,
                resolved_neurons=[_resolved_neuron(111), _resolved_neuron(222)],
                source_dataset=_source_dataset(),
                em_dataset=em_dataset,
                all_notices=["dup", "dup", "unique"],
                total_synapses=0,
                total_connections=0,
                total_internal=0,
                total_external=0,
                file_paths={},
                compressed_path=compressed,
            )

        desc = captured_description["desc"]
        assert desc.count("dup") == 1
        assert "unique" in desc
