import json
import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd
from bluepysnap import Circuit as SnapCircuit
from entitysdk import Client, models, types
from pydantic import PrivateAttr

from obi_one.core.exception import OBIONEError
from obi_one.core.task import Task
from obi_one.db_sdk.registration import circuit as circuit_registration
from obi_one.scientific.blocks.distributions.base import Distribution
from obi_one.scientific.blocks.morphology_locations.base import (
    GeneratedMorphologyLocationsBlock,
    MorphologyLocationsBlock,
)
from obi_one.scientific.blocks.neuron_sets.base import NeuronSet
from obi_one.scientific.blocks.structural_conn_models.base import (
    PathwayConnContext,
    PathwayStructuralConnModel,
)
from obi_one.scientific.blocks.synaptic_models.base import SynapticModelBase
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.build_synaptome import (
    _location_edge_properties,
    _preserve_numpy_random_state,
)
from obi_one.scientific.library.circuit import Circuit, ensure_mechanisms_dir
from obi_one.scientific.library.circuit_constants import TYPES_OF_BIOPHYS_NODES
from obi_one.scientific.library.map_em_synapses.constants import STR_POST_NODE, STR_PRE_NODE
from obi_one.scientific.library.map_em_synapses.write_sonata_edge_file import write_edges
from obi_one.scientific.tasks.circuit_rewiring.config import (
    CircuitConnectivityPathway,
    CircuitRewiringSingleConfig,
)
from obi_one.scientific.tasks.synapse_parameterization.utils import compatible_with

L = logging.getLogger(__name__)

# SONATA edge type for a plain chemical connectivity population.
_EDGE_TYPE = "chemical"

# SONATA node properties holding the soma position, used for distance-dependent connectivity.
_POSITION_PROPERTIES = ("x", "y", "z")


@dataclass(frozen=True)
class _ResolvedPathway:
    """A pathway with its references resolved to blocks and its neuron sets to node IDs."""

    index: int
    name: str
    conn_model: PathwayStructuralConnModel
    synapses_per_connection: Distribution
    locations_block: GeneratedMorphologyLocationsBlock
    synaptic_model: SynapticModelBase
    source_ids: dict[str, np.ndarray]
    target_ids: dict[str, np.ndarray]


class _NewEdgePopulation(NamedTuple):
    """A generated edge population: its node populations, edges file and synaptic models."""

    source_population: str
    target_population: str
    edges_file: Path  # relative to the circuit directory
    synaptic_models: list[SynapticModelBase]


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

    def _postsynaptic_location_properties(
        self,
        *,
        locations_block: MorphologyLocationsBlock,
        pathway_index: int,
        tgt_pop: str,
        post: np.ndarray,
        rng: np.random.Generator,
    ) -> pd.DataFrame:
        """Generate the per-edge postsynaptic location columns for one batch of edges.

        Following Build Synaptome, the number of locations equals the number of synapses: every
        target neuron gets as many locations as it receives edges, generated on its own
        morphology with ``locations_block`` (whose ``number_of_locations`` is therefore overridden
        per neuron). The locations are assigned to that
        neuron's edges in random order, so clustered locations are not tied to source-id order.

        The location seed is derived from the block's ``random_seed``, the pathway index and the
        target node id: neurons do not share a draw and the result is reproducible.

        Returns a frame with one row per entry of ``post`` (same order) holding the
        ``afferent_*`` columns written by Build Synaptome.
        """
        population = self._circuit.sonata_circuit.nodes[tgt_pop]  # ty:ignore[unresolved-attribute]
        if population.type not in TYPES_OF_BIOPHYS_NODES:
            msg = (
                f"Target population '{tgt_pop}' is of type '{population.type}' and has no"
                " morphologies, so connection locations cannot be generated on it. Morphology"
                " locations require a biophysical target population."
            )
            raise OBIONEError(msg)

        base_seed = int(getattr(locations_block, "random_seed", 0))
        order = np.argsort(post, kind="stable")  # groups the edges of each target together
        targets, starts, counts = np.unique(post[order], return_index=True, return_counts=True)

        frames: list[pd.DataFrame] = []
        edge_index: list[np.ndarray] = []
        for target, start, count in zip(targets, starts, counts, strict=True):
            seed = int(
                np.random.SeedSequence([base_seed, pathway_index, int(target)]).generate_state(1)[0]
            )
            placement = locations_block.model_copy(
                update={"number_of_locations": int(count), "random_seed": seed}
            )
            try:
                frames.append(
                    self._locations_on_target(placement, int(target), tgt_pop, int(count))
                )
            except (ValueError, KeyError, RuntimeError, OSError) as exc:
                msg = (
                    f"Could not generate {count} morphology locations with"
                    f" {type(locations_block).__name__} on neuron {int(target)} of population"
                    f" '{tgt_pop}': {exc}"
                )
                raise OBIONEError(msg) from exc
            edge_index.append(order[start : start + count][rng.permutation(count)])

        properties = pd.concat(frames, ignore_index=True)
        # Row i of `properties` belongs to edge edge_index[i]; reorder so row j belongs to edge j.
        return properties.iloc[np.argsort(np.concatenate(edge_index))].reset_index(drop=True)

    def _locations_on_target(
        self, placement: MorphologyLocationsBlock, target: int, tgt_pop: str, count: int
    ) -> pd.DataFrame:
        """Generate ``count`` locations on one target neuron's morphology as afferent columns."""
        morphology = self._circuit.load_morphology(target, population=tgt_pop)  # ty:ignore[unresolved-attribute]
        with _preserve_numpy_random_state():
            locations = placement.points_on(morphology).reset_index(drop=True)
        if len(locations) != count:
            msg = f"generated {len(locations)} locations, expected {count}"
            raise ValueError(msg)
        return _location_edge_properties(morphology, locations)

    @staticmethod
    def _check_synaptic_model(pathway_name: str, model: SynapticModelBase) -> None:
        """Check the pathway's synaptic model can be assigned to the new (chemical) population."""
        compatible_types = type(model).compatible_edge_population_types()
        if _EDGE_TYPE not in compatible_types:
            msg = (
                f"Pathway '{pathway_name}': {type(model).__name__} can only be assigned to edge"
                f" populations of type {sorted(compatible_types)}, but the new edge population"
                f" has type '{_EDGE_TYPE}'."
            )
            raise OBIONEError(msg)

    def _resolve_pathway(
        self, pathway_index: int, pathway_name: str, pathway: CircuitConnectivityPathway
    ) -> _ResolvedPathway:
        """Resolve a pathway's references and neuron sets, validating them on the way."""
        locations_block = pathway.morphology_locations.block
        if not isinstance(locations_block, GeneratedMorphologyLocationsBlock):
            msg = (
                f"Pathway '{pathway_name}' uses unsupported morphology locations"
                f" {type(locations_block).__name__}."
            )
            raise OBIONEError(msg)
        # The target neurons are defined by the neuron set of the morphology locations block.
        # NOTE: We may want to re-think this in the future, see the config validator
        # `require_target_neuron_set_in_morphology_locations`.
        if locations_block.neuron_set is None:
            msg = (
                f"Pathway '{pathway_name}': the morphology locations block must specify a"
                " neuron set, as it defines the target neurons of the pathway."
            )
            raise OBIONEError(msg)
        synaptic_model = pathway.synaptic_model.block
        self._check_synaptic_model(pathway_name, synaptic_model)
        return _ResolvedPathway(
            index=pathway_index,
            name=pathway_name,
            conn_model=pathway.conn_model.block,
            synapses_per_connection=pathway.synapses_per_connection.block,
            locations_block=locations_block,
            synaptic_model=synaptic_model,
            source_ids=self._resolve_pathway_ids(pathway.source_neuron_set.block),
            target_ids=self._resolve_pathway_ids(locations_block.neuron_set.block),
        )

    def _synaptic_parameters(
        self, pathway: _ResolvedPathway, pre: np.ndarray, post: np.ndarray
    ) -> pd.DataFrame:
        """Sample the synaptic model's parameters, one row per synapse (edge).

        Every synapse draws its own values; per-connection sharing of parameters
        (``*_shared_within``) is not implemented by the models yet and is rejected by them. The
        generator is derived from the task seed and the pathway index, so a pathway's parameters
        do not change when other pathways are added.
        """
        indices = pd.DataFrame({"@source_node": pre, "@target_node": post})
        rng = np.random.default_rng([int(self.config.initialize.seed), pathway.index])
        return pathway.synaptic_model.sample(indices, rng=rng)

    def _draw_pair_edges(
        self,
        pathway: _ResolvedPathway,
        source: tuple[str, np.ndarray],
        target: tuple[str, np.ndarray],
        rng: np.random.Generator,
    ) -> pd.DataFrame | None:
        """Draw the edges of one pathway between one source and one target population.

        Returns a frame with the pre/post node ids, the postsynaptic location columns and the
        synaptic parameter columns of every edge, or None if no connection was drawn.
        """
        (src_pop, src_ids), (tgt_pop, tgt_ids) = source, target
        context = PathwayConnContext(
            source_ids=src_ids,
            target_ids=tgt_ids,
            source_positions=self._population_positions(src_pop, src_ids),
            target_positions=self._population_positions(tgt_pop, tgt_ids),
            same_population=src_pop == tgt_pop,
        )
        pre, post = pathway.conn_model.draw_connections(context, rng)
        if pre.size == 0:
            return None
        pre, post = self._expand_by_synapse_count(pre, post, pathway.synapses_per_connection, rng)
        locations = self._postsynaptic_location_properties(
            locations_block=pathway.locations_block,
            pathway_index=pathway.index,
            tgt_pop=tgt_pop,
            post=post,
            rng=rng,
        )
        parameters = self._synaptic_parameters(pathway, pre, post)
        return pd.concat(
            [pd.DataFrame({STR_PRE_NODE: pre, STR_POST_NODE: post}), locations, parameters],
            axis=1,
        )

    def _collect_pathway_connections(
        self, rng: np.random.Generator
    ) -> dict[tuple[str, str], tuple[pd.DataFrame, list[SynapticModelBase]]]:
        """Draw connections for every pathway, grouped by (source pop, target pop) pair.

        A SONATA edge population connects exactly one source node population to one target node
        population, while a neuron set may span several populations. Connections are therefore
        collected per ordered (source population, target population) pair across all pathways,
        with each pathway's structural connectivity model deciding the connections. Each drawn
        connection is then replicated by an integer count sampled from the pathway's
        ``synapses_per_connection`` distribution, so a pair can be connected by several edges,
        and every edge gets a postsynaptic location and the physiological parameters of the
        pathway's synaptic model.

        Returns, per pair, a frame with the pre/post node ids and the edge property columns, and
        the synaptic models of the pathways that contributed edges to it.
        """
        frames: dict[tuple[str, str], list[pd.DataFrame]] = {}
        models_per_pair: dict[tuple[str, str], list[SynapticModelBase]] = {}

        for pathway_index, (pathway_name, config_pathway) in enumerate(
            self.config.pathways.items()
        ):
            pathway = self._resolve_pathway(pathway_index, pathway_name, config_pathway)
            L.info(
                "Pathway '%s': drawing connections with %s",
                pathway_name,
                type(pathway.conn_model).__name__,
            )
            for src_item in pathway.source_ids.items():
                for tgt_item in pathway.target_ids.items():
                    edges = self._draw_pair_edges(pathway, src_item, tgt_item, rng)
                    if edges is None:
                        continue
                    pair = (src_item[0], tgt_item[0])
                    self._check_consistent_synaptic_models(
                        pathway_name, pair, models_per_pair.get(pair, []), pathway.synaptic_model
                    )
                    frames.setdefault(pair, []).append(edges)
                    models_per_pair.setdefault(pair, []).append(pathway.synaptic_model)

        return {
            pair: (pd.concat(pair_frames, ignore_index=True), models_per_pair[pair])
            for pair, pair_frames in frames.items()
        }

    @staticmethod
    def _check_consistent_synaptic_models(
        pathway_name: str,
        pair: tuple[str, str],
        existing: list[SynapticModelBase],
        new: SynapticModelBase,
    ) -> None:
        """Check that pathways feeding one edge population use compatible synaptic models.

        All edges of a population share one set of property columns, so the models must provide
        the same parameters (they must belong to the same synapse model family).
        """
        if not existing:
            return
        try:
            compatible_with(existing[0], new)
        except ValueError as exc:
            msg = (
                f"Pathway '{pathway_name}' and earlier pathways both connect populations"
                f" {pair[0]} -> {pair[1]} but use incompatible synaptic models"
                f" ({type(existing[0]).__name__} and {type(new).__name__}): {exc}"
            )
            raise OBIONEError(msg) from exc

    @staticmethod
    def _write_edge_population(
        *,
        edge_population: str,
        src_pop: str,
        tgt_pop: str,
        edges: pd.DataFrame,
        output_dir: Path,
        sonata_circuit: SnapCircuit,
    ) -> Path:
        """Write one SONATA edge population; return its relative edges path.

        ``edges`` holds the pre/post node ids plus one column per edge property (the
        postsynaptic location columns), which are written as the population's edge properties.
        """
        # Sort by target then source so the SONATA target-node index is well-formed. A stable
        # sort keeps the order of identical (multi-synapse) edges deterministic.
        edges = edges.sort_values([STR_POST_NODE, STR_PRE_NODE], kind="stable").reset_index(
            drop=True
        )
        syn_pre_post = edges[[STR_PRE_NODE, STR_POST_NODE]]
        syn_data = edges.drop(columns=[STR_PRE_NODE, STR_POST_NODE])

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
            len(edges),
        )
        return edges_relative

    def _generate_edge_populations(
        self, *, output_dir: Path, rng: np.random.Generator
    ) -> dict[str, _NewEdgePopulation]:
        """Generate the edge population file(s).

        One edge population is written per ordered (source population, target population) pair.
        When a single pair is involved the edge population keeps the user-provided name;
        otherwise each pair is suffixed with its populations to keep the names unique.

        Returns a mapping of edge population name -> the generated population (its source and
        target node populations, its edges file path relative to ``output_dir`` and the synaptic
        models of the pathways that contributed to it).
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

        edge_populations: dict[str, _NewEdgePopulation] = {}
        for (src_pop, tgt_pop), (edges, synaptic_models) in connections.items():
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
                edges=edges,
                output_dir=output_dir,
                sonata_circuit=sonata_circuit,
            )
            edge_populations[edge_population] = _NewEdgePopulation(
                src_pop, tgt_pop, edges_relative, synaptic_models
            )

        return edge_populations

    @staticmethod
    def _add_edge_populations_to_config(
        circuit_config_path: Path, edge_populations: dict[str, _NewEdgePopulation]
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

        for edge_population, new_population in edge_populations.items():
            edges.append(
                {
                    "edges_file": f"{prefix}{new_population.edges_file.as_posix()}",
                    "populations": {edge_population: {"type": _EDGE_TYPE}},
                }
            )

        with circuit_config_path.open("w", encoding="utf-8") as config_file:
            json.dump(circuit_config, config_file, indent=2)

    @staticmethod
    def _write_mod_files(
        circuit_config_path: Path, edge_populations: dict[str, _NewEdgePopulation]
    ) -> None:
        """Copy the mechanism (``.mod``) files the synaptic models need into the circuit.

        Resolved per edge population, since the mechanisms directory can be set on an individual
        population. This needs the population to be declared in the circuit config already, and
        may declare the directory in the config if the circuit has none.
        """
        for edge_population, new_population in edge_populations.items():
            mechanisms_dir = ensure_mechanisms_dir(circuit_config_path, edge_population)
            for model_class in {type(model) for model in new_population.synaptic_models}:
                model_class.copy_mod_files(mechanisms_dir)

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
        self._write_mod_files(circuit_config_path, edge_populations)
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
