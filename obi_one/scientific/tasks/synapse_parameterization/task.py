import logging
import shutil
from pathlib import Path

from connectome_manipulator.model_building import model_types
from entitysdk import Client, models, types
from pydantic import PrivateAttr

from obi_one.core.task import Task
from obi_one.scientific.library.memodel_circuit import MEModelWithSynapsesCircuit
from obi_one.scientific.library.synaptome_helpers import (
    compress_output,
    register_synaptome,
    synaptome_description_with_physiology,
    synaptome_name_with_physiology,
)
from obi_one.scientific.tasks.synapse_parameterization.config import (
    SynapseParameterizationSingleConfig,
)

L = logging.getLogger(__name__)


class SynapseParameterizationTask(Task):
    config: SynapseParameterizationSingleConfig

    _synaptome: MEModelWithSynapsesCircuit | None = PrivateAttr(default=None)
    _synaptome_entity: models.Circuit | None = PrivateAttr(default=None)
    _pathway_model: model_types.ConnPropsModel | None = PrivateAttr(default=None)

    def _stage_synaptome(self, *, db_client: Client, entity_cache: bool) -> Path:
        self._synaptome_entity = self.config.initialize.synaptome.entity(db_client=db_client)
        root_dir = self.config.scan_output_root.resolve()
        output_dir = self.config.coordinate_output_root.resolve()

        if entity_cache:
            # Use a cache directory at the campaign root --> Won't be deleted after extraction!
            L.info("Using entity cache")
            stage_dir = (
                root_dir / "entity_cache" / "sonata_circuit" / str(self._synaptome_entity.id)
            )
        else:
            # Stage circuit directly in output directory --> Modify in-place!
            stage_dir = output_dir

        synaptome = self.config.initialize.synaptome.stage_circuit(
            db_client=db_client, dest_dir=stage_dir, entity_cache=entity_cache
        )

        if output_dir != stage_dir:
            # Copy staged circuit into output directory
            shutil.copytree(stage_dir, output_dir, dirs_exist_ok=False)
            synaptome = MEModelWithSynapsesCircuit(
                name=synaptome.name, path=str(output_dir / "circuit_config.json")
            )

        self._synaptome = synaptome

        return output_dir

    def _register_derivation(
        self, db_client: Client, registered_synaptome: models.Circuit
    ) -> models.Derivation:
        derivation_model = models.Derivation(
            used=self._synaptome_entity,
            generated=registered_synaptome,
            derivation_type=types.DerivationType.circuit_rewiring,
        )
        registered_derivation = db_client.register_entity(derivation_model)
        return registered_derivation

    def execute(self, *, db_client: Client = None, entity_cache: bool = False) -> None:
        if db_client is None:
            msg = "The synapse parameterization task requires a working db_client!"
            raise ValueError(msg)

        # Stage synaptome
        output_dir = self._stage_synaptome(db_client=db_client, entity_cache=entity_cache)

        # Check parameters
        circ = self._synaptome.sonata_circuit

        for syn_model_assigner in self.config.synapse_model_assigners.values():
            syn_model_assigner.assign_synaptic_model(circ=circ)

        for syn_parameterization in self.config.synapse_parameterizations.values():
            syn_parameterization.go_for_it(circ=circ)

        # Register (re-)parameterized synaptome
        L.info("Registering the output...")
        file_paths = {
            str(path.relative_to(output_dir)): path
            for path in output_dir.rglob("*")
            if path.is_file()
        }
        compressed_path = compress_output(output_dir)

        registered_synaptome = register_synaptome(
            db_client=db_client,
            name=synaptome_name_with_physiology(self._synaptome_entity.name),
            description=synaptome_description_with_physiology(
                self._synaptome_entity.description, self._pathway_model.prop_names
            ),
            number_synapses=self._synaptome_entity.number_synapses,
            number_connections=self._synaptome_entity.number_connections,
            source_dataset=self._synaptome_entity,
            em_dataset=self._synaptome_entity,
            lst_notices=[],
            file_paths=file_paths,
            compressed_path=compressed_path,
        )

        # Register derivation link
        self._register_derivation(db_client=db_client, registered_synaptome=registered_synaptome)
