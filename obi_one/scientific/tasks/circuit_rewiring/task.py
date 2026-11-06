import json
import logging
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from bluepysnap import Circuit as SnapCircuit
from entitysdk import Client, models, types
from pydantic import PrivateAttr

from obi_one.core.exception import OBIONEError
from obi_one.core.task import Task
from obi_one.db_sdk.registration import circuit as circuit_registration
from obi_one.scientific.blocks.distributions.base import Distribution
from obi_one.scientific.blocks.neuron_sets.base import NeuronSet
from obi_one.scientific.blocks.structural_conn_models.base import PathwayConnContext
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.circuit_constants import TYPES_OF_VIRTUAL_NODES
from obi_one.scientific.library.map_em_synapses.constants import STR_POST_NODE, STR_PRE_NODE
from obi_one.scientific.library.map_em_synapses.write_sonata_edge_file import write_edges
from obi_one.scientific.tasks.circuit_rewiring.config import CircuitRewiringSingleConfig

L = logging.getLogger(__name__)

# SONATA edge type for a plain chemical connectivity population.
_EDGE_TYPE = "chemical"

# SONATA node properties holding the soma position, used for distance-dependent connectivity.
_POSITION_PROPERTIES = ("x", "y", "z")


class CircuitRewiringTask(Task):
    """Adds a new connectivity edge population to a SONATA circuit and registers it."""

    config: CircuitRewiringSingleConfig
    _circuit: Circuit | None = PrivateAttr(default=None)
    _circuit_entity: models.Circuit | None = PrivateAttr(default=None)
    _temp_dir: tempfile.TemporaryDirectory | None = PrivateAttr(default=None)

    def __del__(self) -> None:
        """Destructor for automatic clean-up (if something goes wrong)."""
        self._cleanup_temp_dir()

    def _create_temp_dir(self) -> Path:
        """Creation of a new temporary directory."""
        self._cleanup_temp_dir()  # In case it exists already
        self._temp_dir = tempfile.TemporaryDirectory()
        return Path(self._temp_dir.name).resolve()

    def _cleanup_temp_dir(self) -> None:
        """Clean-up of temporary directory, if any."""
        if self._temp_dir is not None:
            self._temp_dir.cleanup()
            self._temp_dir = None

    def _stage_circuit(
        self, *, db_client: Client | None, entity_cache: bool, dest_dir: Path
    ) -> None:
        """Resolve the input circuit into a local, writable staged circuit at ``dest_dir``.

        The original circuit is never mutated: a local ``Circuit`` is copied into ``dest_dir``
        (so the new edge population and rewritten ``circuit_config.json`` are written next to a
        private copy of the existing files), and a ``CircuitFromID`` is staged from entitycore
        into ``dest_dir``. A local circuit has no entity, so nothing is registered at the end.
        """
        circuit = self.config.initialize.circuit
        if isinstance(circuit, Circuit):
            source_dir = Path(circuit.path).resolve().parent
            if dest_dir.exists():
                msg = f"Circuit staging directory '{dest_dir}' already exists."
                raise FileExistsError(msg)
            # copy_function=copy2 preserves metadata; symlinks are materialized into real files
            # so the copy is fully writable and self-contained.
            shutil.copytree(source_dir, dest_dir, symlinks=False)
            self._circuit = Circuit(
                name=circuit.name,
                path=str(dest_dir / Path(circuit.path).name),
            )
            self._circuit_entity = None
            return

        if isinstance(circuit, CircuitFromID):
            if db_client is None:
                msg = "db_client is required to stage a CircuitFromID."
                raise ValueError(msg)
            self._circuit = circuit.stage_circuit(
                db_client=db_client, dest_dir=dest_dir, entity_cache=entity_cache
            )
            self._circuit_entity = circuit.entity(db_client=db_client)
            return

        msg = f"Unsupported circuit type: {type(circuit)}"
        raise OBIONEError(msg)

    def _resolve_pathway_ids(self, neuron_set: NeuronSet) -> dict[str, np.ndarray]:
        """Resolve a neuron set to node IDs per node population."""
        neuron_set.check_populations_in_circuit(self._circuit)  # ty:ignore[invalid-argument-type]
        return {
            pop: np.asarray(ids, dtype=np.int64)
            for pop, ids in neuron_set.get_neuron_ids(self._circuit).items()  # ty:ignore[invalid-argument-type]
        }

    def _population_positions(self, population: str, node_ids: np.ndarray) -> np.ndarray | None:
        """Return the ``(len(node_ids), 3)`` x/y/z positions for ``node_ids``, or None.

        None when the population does not expose x/y/z properties (e.g. a point population
        without positions), in which case distance-dependent models cannot be used for it.
        """
        pop = self._circuit.sonata_circuit.nodes[population]  # ty:ignore[unresolved-attribute]
        if not all(prop in pop.property_names for prop in _POSITION_PROPERTIES):
            return None
        if node_ids.size == 0:
            return np.empty((0, 3), dtype=float)
        positions = pop.get(node_ids, properties=list(_POSITION_PROPERTIES))
        return positions.to_numpy(dtype=float)

    def _require_non_virtual_target_population(self, population: str) -> None:
        """Reject a virtual target population.

        A virtual population models spike sources with no dynamics, so a chemical edge whose
        target is virtual is physiologically meaningless. The target reference field already
        excludes virtual neuron sets at the type level; this guards the resolved population type
        as defense-in-depth (e.g. for a combined set that could span populations).
        """
        pop = self._circuit.sonata_circuit.nodes[population]  # ty:ignore[unresolved-attribute]
        if pop.type in TYPES_OF_VIRTUAL_NODES:
            msg = (
                f"Target population '{population}' is virtual. Connections cannot target a"
                " virtual population; use a non-virtual neuron set as the target."
            )
            raise OBIONEError(msg)

    @staticmethod
    def _expand_by_synapse_count(
        pre: np.ndarray,
        post: np.ndarray,
        synapses_per_connection: Distribution,
        rng: np.random.Generator,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Replicate each drawn connection by its sampled synapse count.

        For every connection in ``(pre, post)`` an integer is drawn from
        ``synapses_per_connection``; that connection is then repeated that many times, so the
        edge population can hold several identical edges between the same neuron pair. Samples
        are rounded to the nearest integer and clamped to a minimum of 1 (a connection that was
        drawn is kept at least once).
        """
        if pre.size == 0:
            return pre, post
        raw = np.asarray(synapses_per_connection.sample(n=pre.size, rng=rng), dtype=float)
        counts = np.clip(np.rint(raw).astype(np.int64), 1, None)
        return np.repeat(pre, counts), np.repeat(post, counts)

    def _collect_pathway_connections(
        self, rng: np.random.Generator
    ) -> dict[tuple[str, str], tuple[np.ndarray, np.ndarray]]:
        """Draw connections for every pathway, grouped by (source pop, target pop) pair.

        A SONATA edge population connects exactly one source node population to one target node
        population, while a neuron set may span several populations. Connections are therefore
        collected per ordered (source population, target population) pair across all pathways,
        with each pathway's structural connectivity model deciding the connections. Each drawn
        connection is then replicated by an integer count sampled from the pathway's
        ``synapses_per_connection`` distribution, so a pair can be connected by several edges.
        """
        per_pair_pre: dict[tuple[str, str], list[np.ndarray]] = {}
        per_pair_post: dict[tuple[str, str], list[np.ndarray]] = {}

        for pathway_name, pathway in self.config.pathways.items():
            conn_model = pathway.conn_model.block
            synapses_per_connection = pathway.synapses_per_connection.block
            source_ids_per_pop = self._resolve_pathway_ids(pathway.source_neuron_set.block)
            target_ids_per_pop = self._resolve_pathway_ids(pathway.target_neuron_set.block)

            L.info(
                "Pathway '%s': drawing connections with %s",
                pathway_name,
                type(conn_model).__name__,
            )

            for src_pop, src_ids in source_ids_per_pop.items():
                src_positions = self._population_positions(src_pop, src_ids)
                for tgt_pop, tgt_ids in target_ids_per_pop.items():
                    self._require_non_virtual_target_population(tgt_pop)
                    tgt_positions = self._population_positions(tgt_pop, tgt_ids)
                    context = PathwayConnContext(
                        source_ids=src_ids,
                        target_ids=tgt_ids,
                        source_positions=src_positions,
                        target_positions=tgt_positions,
                        same_population=src_pop == tgt_pop,
                    )
                    pre, post = conn_model.draw_connections(context, rng)
                    if pre.size == 0:
                        continue
                    pre, post = self._expand_by_synapse_count(
                        pre, post, synapses_per_connection, rng
                    )
                    per_pair_pre.setdefault((src_pop, tgt_pop), []).append(pre)
                    per_pair_post.setdefault((src_pop, tgt_pop), []).append(post)

        return {
            pair: (np.concatenate(per_pair_pre[pair]), np.concatenate(per_pair_post[pair]))
            for pair in per_pair_pre
        }

    @staticmethod
    def _write_edge_population(
        *,
        edge_population: str,
        src_pop: str,
        tgt_pop: str,
        pre: np.ndarray,
        post: np.ndarray,
        output_dir: Path,
        sonata_circuit: SnapCircuit,
    ) -> Path:
        """Write one connectivity-only SONATA edge population; return its relative edges path."""
        syn_pre_post = pd.DataFrame({STR_PRE_NODE: pre, STR_POST_NODE: post})
        # Sort by target then source so the SONATA target-node index is well-formed.
        syn_pre_post = syn_pre_post.sort_values([STR_POST_NODE, STR_PRE_NODE]).reset_index(
            drop=True
        )
        # Connectivity only: no per-edge properties.
        syn_data = pd.DataFrame(index=syn_pre_post.index)

        edges_relative = Path(edge_population) / "edges.h5"
        edges_path = output_dir / edges_relative
        edges_path.parent.mkdir(parents=True, exist_ok=True)

        write_edges(
            edges_path,
            edge_population,
            syn_pre_post,
            syn_data,
            src_pop,
            tgt_pop,
            n_src=int(sonata_circuit.nodes[src_pop].size),
            n_tgt=int(sonata_circuit.nodes[tgt_pop].size),
        )
        L.info(
            "Wrote edge population '%s' (%s -> %s) with %d connections",
            edge_population,
            src_pop,
            tgt_pop,
            len(syn_pre_post),
        )
        return edges_relative

    def _generate_edge_populations(
        self, *, output_dir: Path, rng: np.random.Generator
    ) -> dict[str, tuple[str, str, Path]]:
        """Generate the connectivity edge population file(s).

        One edge population is written per ordered (source population, target population) pair.
        When a single pair is involved the edge population keeps the user-provided name;
        otherwise each pair is suffixed with its populations to keep the names unique.

        Returns a mapping of edge population name -> (source population, target population,
        edges file path relative to ``output_dir``).
        """
        base_name = self.config.initialize.edge_population_name
        connections = self._collect_pathway_connections(rng)

        if not connections:
            msg = (
                "No connections were generated. Check that the pathways reference non-empty"
                " neuron sets and non-zero connection probabilities."
            )
            raise OBIONEError(msg)

        single_pair = len(connections) == 1
        sonata_circuit = self._circuit.sonata_circuit  # ty:ignore[unresolved-attribute]
        existing_edge_populations = set(sonata_circuit.edges.population_names)

        edge_populations: dict[str, tuple[str, str, Path]] = {}
        for (src_pop, tgt_pop), (pre, post) in connections.items():
            edge_population = base_name if single_pair else f"{base_name}__{src_pop}__{tgt_pop}"
            if edge_population in existing_edge_populations:
                msg = (
                    f"Edge population '{edge_population}' already exists in the circuit."
                    " Choose a different edge population name."
                )
                raise OBIONEError(msg)

            edges_relative = self._write_edge_population(
                edge_population=edge_population,
                src_pop=src_pop,
                tgt_pop=tgt_pop,
                pre=pre,
                post=post,
                output_dir=output_dir,
                sonata_circuit=sonata_circuit,
            )
            edge_populations[edge_population] = (src_pop, tgt_pop, edges_relative)

        return edge_populations

    @staticmethod
    def _add_edge_populations_to_config(
        circuit_config_path: Path, edge_populations: dict[str, tuple[str, str, Path]]
    ) -> None:
        """Register the new edge population(s) in circuit_config.json.

        The edge-file paths follow whatever base-directory convention the config already uses:
        ``$BASE_DIR/...`` when the manifest declares ``$BASE_DIR`` (the convention staged SONATA
        circuits use), otherwise a plain path relative to the config directory. This keeps the
        rewritten config loadable regardless of the circuit's manifest style.
        """
        with circuit_config_path.open(encoding="utf-8") as config_file:
            circuit_config = json.load(config_file)

        manifest = circuit_config.get("manifest", {})
        prefix = "$BASE_DIR/" if "$BASE_DIR" in manifest else ""

        networks = circuit_config.setdefault("networks", {})
        edges = networks.setdefault("edges", [])

        for edge_population, (_src_pop, _tgt_pop, edges_relative) in edge_populations.items():
            edges.append(
                {
                    "edges_file": f"{prefix}{edges_relative.as_posix()}",
                    "populations": {edge_population: {"type": _EDGE_TYPE}},
                }
            )

        with circuit_config_path.open("w", encoding="utf-8") as config_file:
            json.dump(circuit_config, config_file, indent=2)

    def _register_output(self, db_client: Client, circuit_path: Path) -> models.Circuit | None:
        """Register the rewired circuit entity with assets and a derivation link."""
        parent = self._circuit_entity

        campaign_str = self.config.info.campaign_name.replace(" ", "-")
        circuit_name = f"{parent.name}__{campaign_str}"  # ty:ignore[unresolved-attribute]
        params = self.config.single_coordinate_scan_params.scan_params
        if len(params) > 0:
            circuit_name = f"{circuit_name}-{self.config.idx}"
        circuit_descr = self.config.info.campaign_description

        return circuit_registration.register_circuit(
            client=db_client,
            circuit_path=circuit_path,
            name=circuit_name,
            description=circuit_descr,
            build_category=parent.build_category,  # ty:ignore[unresolved-attribute]
            brain_region=parent.brain_region,  # ty:ignore[unresolved-attribute, invalid-argument-type]
            subject=parent.subject,  # ty:ignore[unresolved-attribute, invalid-argument-type]
            target_simulator=parent.target_simulator,  # ty:ignore[unresolved-attribute]
            experiment_date=parent.experiment_date,  # ty:ignore[unresolved-attribute]
            license=parent.license,  # ty:ignore[unresolved-attribute]
            atlas=None,
            root=parent.root_circuit_id or parent.id,  # ty:ignore[unresolved-attribute]
            parent=parent,
            derivation_type=types.DerivationType.circuit_rewiring,
        )

    def execute(
        self,
        *,
        db_client: Client | None = None,
        entity_cache: bool = False,
        execution_activity_id: str | None = None,
    ) -> str | None:
        """Add a new connectivity edge population and (if staged from ID) register it.

        Returns the ID of the registered rewired circuit, or None when the input was a local
        circuit (nothing to register).
        """
        execution_activity = CircuitRewiringTask._get_execution_activity(
            db_client=db_client, execution_activity_id=execution_activity_id
        )

        if not self.config.pathways:
            msg = "At least one pathway must be provided to generate connections."
            raise OBIONEError(msg)

        # Stage the circuit into the (persistent) coordinate output root so the new edge
        # population and rewritten config are written next to the existing circuit files and
        # the whole folder can be registered as an asset.
        output_dir = Path(self.config.coordinate_output_root) / "SONATA"
        self._stage_circuit(db_client=db_client, entity_cache=entity_cache, dest_dir=output_dir)

        circuit_config_path = Path(self._circuit.path)  # ty:ignore[unresolved-attribute]

        rng = np.random.default_rng(self.config.initialize.seed)
        edge_populations = self._generate_edge_populations(
            output_dir=circuit_config_path.parent, rng=rng
        )

        self._add_edge_populations_to_config(circuit_config_path, edge_populations)
        L.info(
            "Added %d edge population(s) to '%s'",
            len(edge_populations),
            circuit_config_path,
        )

        new_circuit_entity = None
        if db_client and self._circuit_entity:
            new_circuit_entity = self._register_output(
                db_client=db_client, circuit_path=circuit_config_path
            )
            if new_circuit_entity is not None:
                CircuitRewiringTask._update_execution_activity(
                    db_client=db_client,
                    execution_activity=execution_activity,
                    generated=[str(new_circuit_entity.id)],
                )
            L.info("Registration DONE")

        self._cleanup_temp_dir()

        if new_circuit_entity:
            return str(new_circuit_entity.id)
        return None
