"""Task that resolves EM connectivity and writes a Brian2 point-neuron SONATA circuit."""

import logging
import os
from pathlib import Path

import pandas  # NOQA: ICN001
from entitysdk import Client
from entitysdk.models import EMDenseReconstructionDataset
from pydantic import PrivateAttr

from obi_one.config import settings
from obi_one.core.task import Task
from obi_one.scientific.from_id.em_dataset_from_id import EMDataSetFromID
from obi_one.scientific.tasks.point_neuron_circuit_from_em.brian2_sonata import (
    write_brian2_sonata_circuit,
)
from obi_one.scientific.tasks.point_neuron_circuit_from_em.config import (
    PointNeuronCircuitFromEMSingleConfig,
)
from obi_one.scientific.tasks.point_neuron_circuit_from_em.connectivity import (
    ResolvedConnectivity,
    resolve_connectivity,
)
from obi_one.scientific.tasks.point_neuron_circuit_from_em.register import (
    register_point_neuron_circuit,
)

L = logging.getLogger(__name__)


class PointNeuronCircuitFromEMTask(Task):
    """Build a Brian2 point-neuron SONATA circuit from a set of EM cell meshes.

    The afferent connectivity among the input EM cell meshes is resolved directly from the EM
    dense reconstruction (no morphologies or ME models are required), split into internal
    (between the modelled neurons) and external (from outside the set) connections, and written
    as a Brian2 SONATA circuit: a ``brian2_point`` population for the modelled neurons, a
    ``virtual`` population for the external presynaptic neurons, and ``brian2_synapse`` edge
    populations between them. The connectivity is also printed. Neuronal and synaptic parameters
    are borrowed from the Drosophila brain model as placeholders for now.
    """

    config: PointNeuronCircuitFromEMSingleConfig

    _internal_connectivity: pandas.DataFrame | None = PrivateAttr(default=None)
    _neuron_summary: pandas.DataFrame | None = PrivateAttr(default=None)
    _circuit_config_path: Path | None = PrivateAttr(default=None)
    _registered_circuit_id: str | None = PrivateAttr(default=None)

    @property
    def internal_connectivity(self) -> pandas.DataFrame | None:
        """Synapse-count matrix (rows = presynaptic, columns = postsynaptic), set on execute."""
        return self._internal_connectivity

    @property
    def neuron_summary(self) -> pandas.DataFrame | None:
        """Per-neuron afferent synapse summary, set on execute."""
        return self._neuron_summary

    @property
    def circuit_config_path(self) -> Path | None:
        """Path to the written Brian2 SONATA ``circuit_config.json``, set on execute."""
        return self._circuit_config_path

    @property
    def registered_circuit_id(self) -> str | None:
        """Id of the registered Circuit entity, set on execute."""
        return self._registered_circuit_id

    def execute(
        self,
        *,
        db_client: Client = None,  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,
    ) -> None:
        if db_client is None:
            err_str = "Resolving EM connectivity requires a working db_client"
            raise ValueError(err_str)

        execution_activity = PointNeuronCircuitFromEMTask._get_execution_activity(
            db_client=db_client, execution_activity_id=execution_activity_id
        )

        init = self.config.initialize

        # Resolve all EM cell meshes: pt_root_id, source dataset, CAVE version.
        L.info("Resolving EM cell meshes...")
        cell_meshes = list(init.cell_meshes.elements)
        pt_root_ids: list[int] = []
        for mesh in cell_meshes:
            pt_root_id = mesh.pt_root_id(db_client)
            if pt_root_id in pt_root_ids:
                err_str = (
                    f"Duplicate EM cell mesh: dense_reconstruction_cell_id "
                    f"{pt_root_id} appears more than once in the input."
                )
                raise ValueError(err_str)
            pt_root_ids.append(pt_root_id)

        # All meshes must come from the same EM dense reconstruction dataset.
        dataset_ids = {mesh.source_dataset(db_client).id for mesh in cell_meshes}
        if len(dataset_ids) != 1:
            err_str = (
                "All EM cell meshes must originate from the same EM dense reconstruction dataset."
            )
            raise ValueError(err_str)

        source_dataset = cell_meshes[0].source_dataset(db_client)
        cave_version = cell_meshes[0].cave_version(db_client)

        em_dataset = EMDataSetFromID(
            id_str=str(source_dataset.id),
            auth_token=os.environ[settings.cave_client_config.microns_api_key],
        )

        L.info("Resolving connectivity from the EM reconstruction...")
        connectivity = resolve_connectivity(em_dataset, pt_root_ids, cave_version, db_client)
        self._internal_connectivity = connectivity.internal_matrix
        self._neuron_summary = connectivity.neuron_summary

        L.info("Writing the Brian2 point-neuron SONATA circuit...")
        output_dir = Path(self.config.coordinate_output_root)
        self._circuit_config_path = write_brian2_sonata_circuit(output_dir, connectivity)

        L.info("Registering the circuit...")
        self._registered_circuit_id = register_point_neuron_circuit(
            db_client=db_client,
            circuit_path=self._circuit_config_path,
            source_dataset=source_dataset,
            point_pt_root_ids=connectivity.point_pt_root_ids,
            virtual_count=len(connectivity.virtual_pt_root_ids),
        )

        report = self._connectivity_report(source_dataset, cave_version, connectivity)
        print(report)  # noqa: T201

        generated = [self._registered_circuit_id] if self._registered_circuit_id else None
        PointNeuronCircuitFromEMTask._update_execution_activity(
            db_client=db_client,
            execution_activity=execution_activity,
            generated=generated,
        )

    def _connectivity_report(
        self,
        source_dataset: EMDenseReconstructionDataset,
        cave_version: int,
        connectivity: ResolvedConnectivity,
    ) -> str:
        internal_synapses = int(connectivity.internal_edges.synapse_count.sum())
        external_synapses = int(connectivity.external_edges.synapse_count.sum())
        lines = [
            "",
            "=== Point neuron circuit from EM: resolved connectivity ===",
            f"EM dense reconstruction dataset: {source_dataset.name} ({source_dataset.id})",  # ty:ignore[unresolved-attribute]
            f"CAVE materialization version: {cave_version}",
            f"Modelled (point) neurons: {len(connectivity.point_pt_root_ids)}",
            f"External (virtual) neurons: {len(connectivity.virtual_pt_root_ids)}",
            (
                f"Internal connections: {len(connectivity.internal_edges.source_node_id)} "
                f"({internal_synapses} synapses)"
            ),
            (
                f"External connections: {len(connectivity.external_edges.source_node_id)} "
                f"({external_synapses} synapses)"
            ),
            "",
            "Internal connectivity (synapse counts, rows = pre, cols = post):",
            connectivity.internal_matrix.to_string(),
            "",
            "Per-neuron afferent synapse summary:",
            connectivity.neuron_summary.to_string(),
            "",
            f"Brian2 SONATA circuit written to: {self._circuit_config_path}",
            f"Registered circuit id: {self._registered_circuit_id}",
        ]
        return "\n".join(lines)
