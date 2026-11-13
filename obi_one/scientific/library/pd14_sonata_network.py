"""SONATA network writer for point-neuron (PD14-style) networks, driven by an obi-one config.


Defines the ``SonataNetworkFromConfig`` class, a copy of ``SonataNetwork`` (see
``microcircuit.sonata_network``) which is parameterized by a single configuration
dictionary instead of ``net_dict`` / ``stim_dict`` / ``sonata_dict``.

The configuration is the dictionary representation of the obi-one
``PD14NetworkWriteSingleConfig`` (i.e. its ``model_dump()``). The populations,
pathways and global parameters are read directly from it, so the network
description is not constrained by the layout of ``net_dict`` and ``stim_dict``.
Given the same configuration, the written SONATA network is identical to the
one written by ``SonataNetwork`` for the equivalent ``net_dict`` / ``stim_dict``
(same files, same random numbers). The output layout is documented in
``microcircuit.sonata_network``.

Configuration format
~~~~~~~~~~~~~~~~~~~~

Only the following entries are read; all others (e.g. ``type``, ``info``, the
output roots of the obi-one task) are ignored::

    {
        "initialize": {
            "n_scaling", "k_scaling",          # neuron / indegree scaling factors
            "bg_rate",                         # background rate [spikes/s]
            "psp_ext",                         # PSP of the external (background) input [mV]
            "delay_exc_mean", "delay_inh_mean",  # mean delays [ms]
            "delay_rel_std",                   # relative std of the delays
            "rng_seed",
            "num_th_neurons",                  # 0 disables the thalamus
            "psp_th", "weight_th_rel_std",     # thalamic PSP [mV], relative std of the weights
            "delay_th_mean", "delay_th_rel_std",
            "c_m", "tau_m", "tau_syn",         # optional (defaults: 250 pF, 10 ms, 0.5 ms)
            "population_name",                 # name of the neuron node population
            "background_name",                 # prefix of the background populations (or None)
            "thalamus_name",                   # name of the thalamus population (or None)
            "write_indices",
        },
        "point_neuron_populations": {
            "<block name>": {
                "population_name", "num_neurons", "synapse_class",    # "EXC" or "INH"
                "k_ext", "mean_rate", "thalamic_connection_probability",
                "x_min", "x_max", "y_min", "y_max", "z_min", "z_max",
                "v0_mean", "v0_std",
                "e_l", "v_th", "v_reset", "t_ref",   # optional (defaults: -65, -50, -65, 2)
            },
            ...
        },
        "pathway_connection_probabilities": {
            "<block name>": {
                "source": {"block_name": "<population block name>"},
                "target": {"block_name": "<population block name>"},
                "connection_probability",
                "psp_mean",                    # PSP amplitude [mV], non-negative
                "weight_rel_std",              # relative std of the weights
            },
            ...
        },
    }

- Populations are ordered by their block name (the keys of
  ``point_neuron_populations``); this order defines the node ids and the
  indices of the connection-probability matrix.
- The connection-probability matrix is assembled from the pathways. Pathways
  that are not listed have no connections. Two pathways with the same
  source and target population raise an error. ``psp_mean`` is an unsigned
  amplitude; the weights are excitatory (positive) for sources of synapse class
  "EXC" and inhibitory (negative) for sources of class "INH".
- All parameters must be single values (no scan dimensions).

Parameters that are not part of the configuration are fixed here: the neuron
model (``iaf_psc_exp``), the (poisson) background input type, and the
background delay, which equals ``delay_exc_mean``.

"""

import json
import logging
import warnings
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pandas as pd
from microcircuit import helpers
from voxcell import CellCollection

L = logging.getLogger(__name__)

# String-valued node properties that are always stored as SONATA enumerations
# (``@library``), independent of how repetitive their values are.
_ENUMERATED_NODE_PROPERTIES = (
    "model_type",
    "model_template",
    "mtype",
    "etype",
    "layer",
    "synapse_class",
)

# Parameters that are not part of the configuration.
_NEURON_MODEL = "iaf_psc_exp"
# Neuron parameters that are optional in the configuration; the default is used if an entry is
# missing (e.g. in configurations written before the entry existed).
_POPULATION_NEURON_DEFAULTS = {
    "e_l": -65.0,  # leak / resting potential (mV)
    "v_th": -50.0,  # threshold potential (mV)
    "v_reset": -65.0,  # reset potential (mV)
    "t_ref": 2.0,  # refractory period (ms)
}
_GLOBAL_NEURON_DEFAULTS = {
    "c_m": 250.0,  # membrane capacitance (pF)
    "tau_m": 10.0,  # membrane time constant (ms)
    "tau_syn": 0.5,  # time constant of postsynaptic currents (ms)
}
_BG_INPUT_TYPE = "poisson"

_MIN_POP_NAME_LENGTH = 3  # shortest name following the L<digits><E|I> pattern

_SYNAPSE_CLASSES = ("EXC", "INH")

_POPULATION_KEYS = (
    "population_name",
    "num_neurons",
    "synapse_class",
    "k_ext",
    "mean_rate",
    "thalamic_connection_probability",
    "x_min",
    "x_max",
    "y_min",
    "y_max",
    "z_min",
    "z_max",
    "v0_mean",
    "v0_std",
)


def _require(mapping: Any, key: str, where: str) -> Any:
    """Returns ``mapping[key]`` or raises a ``ValueError`` naming the missing entry."""
    try:
        return mapping[key]
    except (KeyError, TypeError):
        msg = f"{where}: missing required entry '{key}'."
        raise ValueError(msg) from None


def _is_scan_dimension(value: Any) -> bool:
    return isinstance(value, (list, tuple, dict, set))


def _scalar(mapping: Any, key: str, where: str) -> Any:
    """Returns a required single value (not None, not a list)."""
    value = _require(mapping, key, where)
    if value is None or _is_scan_dimension(value):
        msg = f"{where}: '{key}' must be a single value, got {value!r}."
        raise ValueError(msg)
    return value


def _optional_name(mapping: Any, key: str, where: str) -> Any:
    """Returns a required name that may be None."""
    value = _require(mapping, key, where)
    if _is_scan_dimension(value):
        msg = f"{where}: '{key}' must be a single value or None, got {value!r}."
        raise ValueError(msg)
    return value


def _check_probability(value: float, where: str) -> None:
    if not 0.0 <= value < 1.0:
        msg = f"{where}: probability must be in [0, 1), got {value}."
        raise ValueError(msg)


class SonataNetworkFromConfig:
    """Writes the neurons and connections of a point-neuron network to SONATA files.

    Counterpart of ``SonataNetwork`` which is parameterized by the dictionary
    representation of the obi-one ``PD14NetworkWriteSingleConfig`` (see the
    module docstring for the format).

    ``create()`` creates the neuronal and the virtual input populations,
    ``connect()`` the connections.

    Parameters
    ----------
    config
        Dictionary representation of the network configuration, e.g.
        ``PD14NetworkWriteSingleConfig.model_dump()``.
    sonata_path
        Output directory for the SONATA files. Created if it does not exist;
        existing files are overwritten.
    max_batch_size
        Maximum number of connections generated at once (limits memory usage).

    """

    def __init__(
        self, config: dict, sonata_path: str | Path, max_batch_size: int = 10_000_000
    ) -> None:
        """Parses the configuration and prepares the output directory."""
        self.config = config
        self.max_batch_size = int(max_batch_size)

        self.__parse_config()

        # output directory
        self.sonata_path = Path(sonata_path)
        if self.sonata_path.is_dir():
            L.info("Output directory exists, old data will be overwritten: %s", self.sonata_path)
        else:
            self.sonata_path.mkdir(parents=True)
        L.info("SONATA files will be written to: %s", self.sonata_path)

        self.edges_file = self.sonata_path / "edges.h5"
        self.node_sets_file = self.sonata_path / "node_sets.json"
        self.circuit_config_file = self.sonata_path / "circuit_config.json"

        # node populations: name -> (SONATA type, number of nodes)
        self.node_populations = {}
        # nodes files: node population name -> path of the file containing it
        self.nodes_files = {}
        # edge populations: name -> (source population, target population)
        self.edge_populations = {}

        # random number generator
        self.rng = np.random.default_rng(self.rng_seed)

        # derive parameters from the configuration
        self.__derive_parameters()

    def create(self) -> None:
        """Creates all node populations and writes them to the nodes files.

        The neuronal populations and the virtual populations representing the
        background and thalamic input are created, each written to its own
        nodes file (``nodes_<population>.h5``). Also writes the node sets file.

        """
        self.__create_neuronal_populations()
        if self.background_name is not None:
            self.__create_background_population()
        if self.thalamus_name is not None:
            self.__create_thalamic_population()

        self.__write_node_sets()

    def connect(self) -> None:
        """Connects the network and writes the connections to the edge file.

        Recurrent connections among neurons of the neuronal populations and
        connections from the virtual input populations onto the neurons are
        created. Afterwards, the edge indices (if requested) and the circuit
        configuration file are written.

        """
        if not hasattr(self, "pops"):
            msg = "create() must be called before connect()."
            raise RuntimeError(msg)

        with h5py.File(self.edges_file, "w") as f:
            edges_grp = f.create_group("edges")
            self.__connect_neuronal_populations(edges_grp)
            if self.background_name is not None:
                self.__connect_background_population(edges_grp)
            if self.thalamus_name is not None:
                self.__connect_thalamic_population(edges_grp)

        if self.write_indices:
            self.__write_edge_indices()
        self.__write_circuit_config()

    def store_metadata(self) -> None:
        """Stores the configuration as ``config.json`` in ``sonata_path``."""
        L.info("Storing metadata to %s", self.sonata_path)
        helpers.dict2json(self.config, str(self.sonata_path / "config.json"))

    def __parse_config(self) -> None:  # ruff: ignore[complex-structure, too-many-locals, too-many-statements, too-many-branches]
        """Reads and validates the configuration and stores it as class attributes."""
        init = _require(self.config, "initialize", "config")
        where = "config['initialize']"

        # global parameters
        self.n_scaling = _scalar(init, "n_scaling", where)
        self.k_scaling = _scalar(init, "k_scaling", where)
        self.bg_rate = _scalar(init, "bg_rate", where)
        self.psp_ext = _scalar(init, "psp_ext", where)
        self.delay_exc_mean = _scalar(init, "delay_exc_mean", where)
        self.delay_inh_mean = _scalar(init, "delay_inh_mean", where)
        self.delay_rel_std = _scalar(init, "delay_rel_std", where)
        self.rng_seed = _scalar(init, "rng_seed", where)
        self.num_th_neurons = int(_scalar(init, "num_th_neurons", where))
        self.psp_th = _scalar(init, "psp_th", where)
        self.weight_th_rel_std = _scalar(init, "weight_th_rel_std", where)
        self.delay_th_mean = _scalar(init, "delay_th_mean", where)
        self.delay_th_rel_std = _scalar(init, "delay_th_rel_std", where)

        # names of the SONATA populations
        self.population_name = _scalar(init, "population_name", where)
        self.background_name = _optional_name(init, "background_name", where)
        # no thalamus population is written without thalamic neurons
        thalamus_name = _optional_name(init, "thalamus_name", where)
        self.thalamus_name = thalamus_name if self.num_th_neurons > 0 else None

        # neuron parameters shared by all populations (used for the PSP -> PSC conversion)
        for key, default in _GLOBAL_NEURON_DEFAULTS.items():
            value = _scalar({key: init.get(key, default)}, key, where)
            if value <= 0:
                msg = f"{where}: '{key}' must be positive, got {value}."
                raise ValueError(msg)
            setattr(self, key, value)
        self.write_indices = bool(_scalar(init, "write_indices", where))

        # neuronal populations, ordered by block name
        blocks = _require(self.config, "point_neuron_populations", "config")
        if not blocks:
            msg = "At least one point neuron population must be defined."
            raise ValueError(msg)
        block_names = sorted(blocks)
        index_by_block_name = {name: i for i, name in enumerate(block_names)}

        values = {key: [] for key in (*_POPULATION_KEYS, *_POPULATION_NEURON_DEFAULTS)}
        for block_name in block_names:
            block = blocks[block_name]
            block_where = f"config['point_neuron_populations']['{block_name}']"
            for key in _POPULATION_KEYS:
                values[key].append(_scalar(block, key, block_where))
            for key, default in _POPULATION_NEURON_DEFAULTS.items():
                values[key].append(_scalar({key: block.get(key, default)}, key, block_where))

        self.population_names = [str(name) for name in values["population_name"]]
        if len(set(self.population_names)) != len(self.population_names):
            msg = "Point neuron population names must be unique."
            raise ValueError(msg)
        for block_name, synapse_class in zip(block_names, values["synapse_class"], strict=False):
            if synapse_class not in _SYNAPSE_CLASSES:
                msg = (
                    f"Population '{block_name}': synapse_class must be one of"
                    f" {_SYNAPSE_CLASSES}, got {synapse_class!r}."
                )
                raise ValueError(msg)

        self.synapse_classes = [str(synapse_class) for synapse_class in values["synapse_class"]]
        self.full_num_neurons = np.array(values["num_neurons"])
        self.full_mean_rates = np.array(values["mean_rate"])
        self.K_ext = np.array(values["k_ext"])
        self.conn_probs_th = np.array(values["thalamic_connection_probability"])
        for block_name, probability in zip(block_names, self.conn_probs_th, strict=False):
            _check_probability(
                probability, f"Population '{block_name}' thalamic_connection_probability"
            )
        self.extents = [
            {
                coord: (values[coord + "_min"][i], values[coord + "_max"][i])
                for coord in ("x", "y", "z")
            }
            for i in range(len(block_names))
        ]
        self.v0_mean = np.array(values["v0_mean"])
        self.v0_std = np.array(values["v0_std"])
        self.e_l = np.array(values["e_l"], dtype=float)
        self.v_th = np.array(values["v_th"], dtype=float)
        self.v_reset = np.array(values["v_reset"], dtype=float)
        self.t_ref = np.array(values["t_ref"], dtype=float)
        for block_name, v_th, v_reset, t_ref in zip(
            block_names, self.v_th, self.v_reset, self.t_ref, strict=True
        ):
            if v_th <= v_reset:
                msg = f"Population '{block_name}': v_th ({v_th}) must exceed v_reset ({v_reset})."
                raise ValueError(msg)
            if t_ref < 0:
                msg = f"Population '{block_name}': t_ref must not be negative, got {t_ref}."
                raise ValueError(msg)

        # connection probabilities: conn_probs[target][source], 0 where no pathway is given
        num_pops = len(block_names)
        self.conn_probs = np.zeros((num_pops, num_pops))
        # mean PSPs and relative weight standard deviations of the pathways
        self.PSP_matrix_mean = np.zeros((num_pops, num_pops))
        self.weight_rel_std_matrix = np.zeros((num_pops, num_pops))
        seen = set()
        pathways = self.config.get("pathway_connection_probabilities") or {}
        for pathway_name, pathway in pathways.items():
            pathway_where = f"config['pathway_connection_probabilities']['{pathway_name}']"
            source_name = _require(
                _require(pathway, "source", pathway_where),
                "block_name",
                pathway_where + "['source']",
            )
            target_name = _require(
                _require(pathway, "target", pathway_where),
                "block_name",
                pathway_where + "['target']",
            )
            if source_name not in index_by_block_name:
                msg = (
                    f"Pathway source population '{source_name}' is not in point_neuron_populations."
                )
                raise ValueError(msg)
            if target_name not in index_by_block_name:
                msg = (
                    f"Pathway target population '{target_name}' is not in point_neuron_populations."
                )
                raise ValueError(msg)
            j = index_by_block_name[source_name]
            i = index_by_block_name[target_name]
            if (i, j) in seen:
                msg = (
                    f"Duplicate pathway connection probability for source '{source_name}'"
                    f" and target '{target_name}'."
                )
                raise ValueError(msg)
            seen.add((i, j))
            probability = _scalar(pathway, "connection_probability", pathway_where)
            _check_probability(probability, pathway_where)
            self.conn_probs[i][j] = probability

            psp_mean = _scalar(pathway, "psp_mean", pathway_where)
            if psp_mean < 0:
                msg = f"{pathway_where}: psp_mean must not be negative, got {psp_mean}."
                raise ValueError(msg)
            # the sign is given by the synapse class of the source population
            if self.synapse_classes[j] == "INH":
                psp_mean = -psp_mean
            weight_rel_std = _scalar(pathway, "weight_rel_std", pathway_where)
            if weight_rel_std < 0:
                msg = f"{pathway_where}: weight_rel_std must not be negative, got {weight_rel_std}."
                raise ValueError(msg)
            self.PSP_matrix_mean[i][j] = psp_mean
            self.weight_rel_std_matrix[i][j] = weight_rel_std

        # mean delays, set by the synapse class of the source population (column j)
        self.delay_matrix_mean = np.zeros((num_pops, num_pops))
        for j, synapse_class in enumerate(self.synapse_classes):
            is_exc = synapse_class == "EXC"
            self.delay_matrix_mean[:, j] = self.delay_exc_mean if is_exc else self.delay_inh_mean

    def __derive_parameters(self) -> None:
        """Derives and adjusts parameters and stores them as class attributes.

        Same as ``SonataNetwork.__derive_parameters()``, with the parameters
        taken from the parsed configuration.
        """
        self.num_pops = len(self.population_names)

        # total number of synapses between neuronal populations before scaling
        full_num_synapses = helpers.num_synapses_from_conn_probs(
            self.conn_probs, self.full_num_neurons, self.full_num_neurons
        )

        # scaled numbers of neurons and synapses
        self.num_neurons = np.round(self.full_num_neurons * self.n_scaling).astype(int)
        self.num_synapses = np.round(full_num_synapses * self.n_scaling * self.k_scaling).astype(
            int
        )
        self.ext_indegrees = np.round(self.K_ext * self.k_scaling).astype(int)

        # conversion from PSPs to PSCs
        psc_over_psp = helpers.postsynaptic_potential_to_current(self.c_m, self.tau_m, self.tau_syn)
        psc_matrix_mean = self.PSP_matrix_mean * psc_over_psp
        psc_ext = self.psp_ext * psc_over_psp

        # the background is represented by (virtual) poisson sources, so no compensating DC input
        dc_amp = np.zeros(self.num_pops)

        # adjust weights and DC amplitude if the indegree is scaled
        if self.k_scaling != 1:
            psc_matrix_mean, psc_ext, dc_amp = helpers.adjust_weights_and_input_to_synapse_scaling(
                self.full_num_neurons,
                full_num_synapses,
                self.k_scaling,
                psc_matrix_mean,
                psc_ext,
                self.tau_syn,
                self.full_mean_rates,
                dc_amp,
                _BG_INPUT_TYPE,
                self.bg_rate,
                self.K_ext,
            )

        # store final parameters as class attributes
        self.weight_matrix_mean = psc_matrix_mean
        self.weight_ext = psc_ext
        self.DC_amp = dc_amp
        self.delay_poisson = self.delay_exc_mean

        # thalamic input
        if self.num_th_neurons > 0:
            num_th_synapses = helpers.num_synapses_from_conn_probs(
                self.conn_probs_th, self.num_th_neurons, self.full_num_neurons
            )[0]
        else:
            num_th_synapses = np.zeros(self.num_pops)
        self.weight_th = self.psp_th * psc_over_psp
        if self.k_scaling != 1:
            num_th_synapses *= self.k_scaling
            self.weight_th /= np.sqrt(self.k_scaling)
        self.num_th_synapses = np.round(num_th_synapses).astype(int)

        if self.n_scaling != 1:
            L.info("Neuron numbers are scaled by a factor of %.3f.", self.n_scaling)
        if self.k_scaling != 1:
            L.info(
                "Indegrees are scaled by a factor of %.3f. "
                "Weights and DC input are adjusted to compensate.",
                self.k_scaling,
            )

    def __create_neuronal_populations(self) -> None:
        """Creates the neuronal populations and writes them to a nodes file.

        All neurons are stored in a single SONATA node population; the
        microcircuit populations are distinguished by the ``mtype`` attribute.
        The initial membrane potential of the neurons is drawn from normal
        distributions given by ``v0_mean`` and ``v0_std`` of each population.
        Neuron positions are drawn from uniform distributions within the
        intervals given by the ``x/y/z_min/max`` of each population.

        ``self.pops`` holds the (0-based) SONATA node ids of each population.
        """
        num_total = int(np.sum(self.num_neurons))
        pop_index = np.repeat(np.arange(self.num_pops), self.num_neurons)

        offsets = np.concatenate(([0], np.cumsum(self.num_neurons)))
        self.pops = [
            np.arange(offsets[i], offsets[i + 1], dtype=np.uint64) for i in range(self.num_pops)
        ]

        # initial membrane potentials
        v_m = np.empty(num_total)
        for i in range(self.num_pops):
            v_m[offsets[i] : offsets[i + 1]] = self.rng.normal(
                self.v0_mean[i], self.v0_std[i], self.num_neurons[i]
            )

        # positions, uniformly distributed within the population's intervals
        positions = {coord: np.empty(num_total) for coord in ("x", "y", "z")}
        for i in range(self.num_pops):
            for coord, values in positions.items():
                low, high = self.extents[i][coord]
                values[offsets[i] : offsets[i + 1]] = self.rng.uniform(
                    low, high, self.num_neurons[i]
                )

        # parameters of the neuron model (NEST names); C_m and tau_m are not
        # set explicitly in Network but match the NEST defaults of iaf_psc_exp
        dynamics_params = {
            "C_m": np.full(num_total, self.c_m),
            "tau_m": np.full(num_total, self.tau_m),
            "E_L": self.e_l[pop_index],
            "V_th": self.v_th[pop_index],
            "V_reset": self.v_reset[pop_index],
            "t_ref": self.t_ref[pop_index],
            "tau_syn_ex": np.full(num_total, self.tau_syn),
            "tau_syn_in": np.full(num_total, self.tau_syn),
            "I_e": np.asarray(self.DC_amp, dtype=float)[pop_index],
            "V_m": v_m,
        }

        # per-population string attributes
        layers = [self.__layer_of(name) for name in self.population_names]

        # Node properties as a voxcell CellCollection. String attributes are plain
        # per-node values here; they are stored as enumerations (@library) on saving.
        # Properties prefixed with SONATA_DYNAMIC_PROPERTY end up in dynamics_params.
        properties = {
            "model_type": np.full(num_total, "point_neuron", dtype=object),
            "model_template": np.full(num_total, f"nest:{_NEURON_MODEL}", dtype=object),
            "mtype": np.repeat(np.array(self.population_names, dtype=object), self.num_neurons),
            "etype": np.full(num_total, "N/A", dtype=object),
            "layer": np.array(layers, dtype=object)[pop_index],
            "synapse_class": np.array(self.synapse_classes, dtype=object)[pop_index],
        }
        for name, values in dynamics_params.items():
            properties[CellCollection.SONATA_DYNAMIC_PROPERTY + name] = np.asarray(
                values, dtype=np.float32
            )

        cells = CellCollection(population_name=self.population_name)
        cells.positions = np.column_stack([positions["x"], positions["y"], positions["z"]]).astype(
            np.float32
        )
        cells.properties = pd.DataFrame(properties)
        self.__save_node_population(cells, "point_neuron")

    def __background_population_names(self) -> list[str]:
        """Names of the background node populations, one per neuronal
        population.
        """
        return [f"{self.background_name}_{pop}" for pop in self.population_names]

    def __create_background_population(self) -> None:
        """Creates the virtual node populations representing the background
        input: one population per neuronal population, with one virtual node
        per targeted neuron.

        Each background node carries the external indegree ``ext_indegree`` of
        its target population (``k_ext`` scaled by ``k_scaling``) as a custom
        node property, i.e. the number of external inputs the corresponding
        cortical neuron receives.
        """
        for name, num_nodes, ext_indegree in zip(
            self.__background_population_names(), self.num_neurons, self.ext_indegrees, strict=False
        ):
            self.__create_virtual_population(
                name,
                int(num_nodes),
                extra_properties={"ext_indegree": np.full(int(num_nodes), int(ext_indegree))},
            )

    def __create_thalamic_population(self) -> None:
        """Creates the virtual node population representing the thalamus.

        Note that the number of thalamic neurons is not scaled with
        ``n_scaling``.
        """
        self.__create_virtual_population(self.thalamus_name, self.num_th_neurons)

    def __create_virtual_population(
        self, name: str, num_nodes: int, extra_properties: dict | None = None
    ) -> None:
        """Writes a node population of ``num_nodes`` virtual nodes to its own nodes file.

        ``extra_properties`` is an optional mapping of custom node property name
        to an array of ``num_nodes`` values, written as datasets under the node
        group (``/<population>/0/<name>``).
        """
        properties = {"model_type": np.full(num_nodes, "virtual", dtype=object)}
        properties.update(extra_properties or {})
        cells = CellCollection(population_name=name)
        cells.properties = pd.DataFrame(properties)
        self.__save_node_population(cells, "virtual")

    def __save_node_population(self, cells: CellCollection, population_type: str) -> None:
        """Saves a ``CellCollection`` as a SONATA nodes file containing only its
        population (``nodes_<population>.h5``) and registers the population.
        """
        path = self.sonata_path / f"nodes_{cells.population_name}.h5"
        cells.save_sonata(str(path), forced_library=_ENUMERATED_NODE_PROPERTIES)
        self.node_populations[cells.population_name] = (population_type, len(cells.properties))
        self.nodes_files[cells.population_name] = path

    def __connect_neuronal_populations(self, edges_grp: h5py.Group) -> None:
        """Creates the recurrent connections between neuronal populations."""

        def batches() -> Iterator[tuple]:
            for i, target_pop in enumerate(self.pops):
                for j, source_pop in enumerate(self.pops):
                    if self.weight_matrix_mean[i][j] < 0:
                        w_bounds = (-np.inf, 0.0)
                    else:
                        w_bounds = (0.0, np.inf)
                    yield from self.__fixed_total_number(
                        source_pop,
                        target_pop,
                        int(self.num_synapses[i][j]),
                        self.weight_matrix_mean[i][j],
                        abs(self.weight_matrix_mean[i][j] * self.weight_rel_std_matrix[i][j]),
                        w_bounds,
                        self.delay_matrix_mean[i][j],
                        self.delay_matrix_mean[i][j] * self.delay_rel_std,
                    )

        self.__write_edge_population(
            edges_grp, self.population_name, self.population_name, batches()
        )

    def __connect_background_population(self, edges_grp: h5py.Group) -> None:
        """Connects each background population to its neuronal population
        (one-to-one) with weight ``weight_ext`` and delay ``delay_poisson``.
        """

        def batches(target_pop: np.ndarray) -> Iterator[tuple]:
            for start in range(0, len(target_pop), self.max_batch_size):
                targets = target_pop[start : start + self.max_batch_size]
                sources = np.arange(start, start + len(targets), dtype=np.uint64)
                yield (
                    sources,
                    targets,
                    np.full(len(targets), self.weight_ext),
                    np.full(len(targets), self.delay_poisson),
                )

        for name, target_pop in zip(self.__background_population_names(), self.pops, strict=False):
            self.__write_edge_population(edges_grp, name, self.population_name, batches(target_pop))

    def __connect_thalamic_population(self, edges_grp: h5py.Group) -> None:
        """Connects the thalamic population to the neuronal populations."""

        def batches() -> Iterator[tuple]:
            thalamic_pop = np.arange(self.num_th_neurons, dtype=np.uint64)
            for i, target_pop in enumerate(self.pops):
                yield from self.__fixed_total_number(
                    thalamic_pop,
                    target_pop,
                    int(self.num_th_synapses[i]),
                    self.weight_th,
                    self.weight_th * self.weight_th_rel_std,
                    (0.0, np.inf),
                    self.delay_th_mean,
                    self.delay_th_mean * self.delay_th_rel_std,
                )

        self.__write_edge_population(edges_grp, self.thalamus_name, self.population_name, batches())

    def __fixed_total_number(
        self,
        source_pop: np.ndarray,
        target_pop: np.ndarray,
        num: int,
        w_mean: float,
        w_std: float,
        w_bounds: tuple[float, float],
        d_mean: float,
        d_std: float,
    ) -> Iterator[tuple]:
        """Generates ``num`` connections from ``source_pop`` to ``target_pop``
        (NEST rule ``fixed_total_number``, autapses and multapses allowed).

        Weights are normally distributed and redrawn until within
        ``w_bounds``. Delays are normally distributed and redrawn until
        positive (constant if ``d_std`` is 0); see ``sonata_network.py`` for
        the difference to NEST.

        Yields batches ``(sources, targets, weights, delays)``.
        """
        min_delay = np.nextafter(0.0, 1.0)  # smallest positive value
        remaining = num
        while remaining > 0:
            n = min(remaining, self.max_batch_size)
            remaining -= n
            sources = source_pop[self.rng.integers(0, len(source_pop), n)]
            targets = target_pop[self.rng.integers(0, len(target_pop), n)]
            weights = self.__redraw_normal(w_mean, w_std, n, *w_bounds)
            if d_std == 0:
                delays = np.full(n, d_mean)
            else:
                delays = self.__redraw_normal(d_mean, d_std, n, min_delay, np.inf)
            yield sources, targets, weights, delays

    def __write_edge_population(
        self, edges_grp: h5py.Group, source_name: str, target_name: str, batches: Iterator[tuple]
    ) -> None:
        """Writes an edge population from batches of connections.

        Each batch is sorted by target and then source node id.
        """
        name = f"{source_name}__{target_name}__chemical"
        chunk = min(self.max_batch_size, 1 << 20)

        pop_grp = edges_grp.create_group(name)
        grp = pop_grp.create_group("0")
        datasets = []
        for parent, ds_name, dtype in (
            (pop_grp, "source_node_id", np.uint64),
            (pop_grp, "target_node_id", np.uint64),
            (grp, "weight", np.float32),
            (grp, "delay", np.float32),
        ):
            datasets.append(
                parent.create_dataset(
                    ds_name, shape=(0,), maxshape=(None,), dtype=dtype, chunks=(chunk,)
                )
            )
        datasets[0].attrs["node_population"] = source_name
        datasets[1].attrs["node_population"] = target_name

        num_edges = 0
        for sources, targets, weights, delays in batches:
            n = len(sources)
            if n == 0:
                continue
            order = np.lexsort((sources, targets))
            for ds, data in zip(datasets, (sources, targets, weights, delays), strict=False):
                ds.resize((num_edges + n,))
                ds[num_edges:] = data[order]
            num_edges += n

        pop_grp.create_dataset("edge_type_id", shape=(num_edges,), dtype=np.int64, fillvalue=-1)

        self.edge_populations[name] = (source_name, target_name)

    def __write_edge_indices(self) -> None:
        """Writes the SONATA source->target and target->source edge indices."""
        try:
            import libsonata  # ruff: ignore[import-outside-top-level]
        except ImportError:
            warnings.warn(
                "libsonata is not installed; SONATA edge indices are not written.", stacklevel=2
            )
            return

        for name, (source, target) in self.edge_populations.items():
            libsonata.EdgePopulation.write_indices(
                str(self.edges_file),
                name,
                self.node_populations[source][1],
                self.node_populations[target][1],
                overwrite=True,
            )

    def __write_node_sets(self) -> None:
        """Writes node sets for each neuronal population, for excitatory and
        inhibitory neurons, and for each node population.
        """
        node_sets = {name: {"population": name} for name in self.node_populations}
        if self.background_name is not None:
            # compound node set of all background populations
            node_sets[self.background_name] = self.__background_population_names()
        node_sets["Excitatory"] = {"population": self.population_name, "synapse_class": "EXC"}
        node_sets["Inhibitory"] = {"population": self.population_name, "synapse_class": "INH"}
        for name in self.population_names:
            node_sets[str(name)] = {"population": self.population_name, "mtype": str(name)}

        with self.node_sets_file.open("w", encoding="utf-8") as f:
            json.dump(node_sets, f, indent=4)

    def __write_circuit_config(self) -> None:
        """Writes the SONATA circuit configuration file."""
        config = {
            "version": 2.4,
            "manifest": {"$BASE_DIR": "."},
            "node_sets_file": "$BASE_DIR/node_sets.json",
            "networks": {
                "nodes": [
                    {
                        "nodes_file": f"$BASE_DIR/{path.name}",
                        "populations": {name: {"type": self.node_populations[name][0]}},
                    }
                    for name, path in self.nodes_files.items()
                ],
                "edges": [
                    {
                        "edges_file": "$BASE_DIR/edges.h5",
                        "populations": {
                            name: {"type": "chemical"} for name in self.edge_populations
                        },
                    }
                ],
            },
            "metadata": {
                "description": "Cortical microcircuit model of Potjans & Diesmann (2014)",
                "N_scaling": float(self.n_scaling),
                "K_scaling": float(self.k_scaling),
                "neuron_model": _NEURON_MODEL,
                "synapse_model": "static_synapse",
                "bg_input_type": _BG_INPUT_TYPE,
                "rng_seed": self.rng_seed,
                "units": {"weight": "pA", "delay": "ms"},
            },
        }
        with self.circuit_config_file.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)

    def __redraw_normal(
        self, mean: float, std: float, size: int, low: float, high: float
    ) -> np.ndarray:
        """Draws normally distributed values; values outside ``[low, high]``
        are redrawn (equivalent to ``nest.math.redraw(nest.random.normal())``).
        """
        values = self.rng.normal(mean, std, size)
        bad = (values < low) | (values > high)
        while np.any(bad):
            values[bad] = self.rng.normal(mean, std, np.count_nonzero(bad))
            bad = (values < low) | (values > high)
        return values

    @staticmethod
    def __layer_of(pop_name: str) -> str:
        """Extracts the layer from a population name, e.g. ``L23E`` -> ``2/3``.

        Returns ``"N/A"`` for names that do not follow the ``L<digits><E|I>`` pattern.
        """
        if (
            len(pop_name) < _MIN_POP_NAME_LENGTH
            or pop_name[0] != "L"
            or not pop_name[1:-1].isdigit()
        ):
            return "N/A"
        layer = pop_name[1:-1]
        return "2/3" if layer == "23" else layer
