import json
import logging
from pathlib import Path
from typing import ClassVar, get_args, get_type_hints

import entitysdk
from pydantic import PrivateAttr

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.task import Task
from obi_one.scientific.blocks.neuron_sets.specific import AllNeurons
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.memodel_circuit import MEModelCircuit
from obi_one.scientific.library.sonata_circuit_helpers import (
    write_circuit_node_set_file,
)
from obi_one.scientific.tasks.generate_simulation_configs import (
    SONATA_VERSION,
    TARGET_SIMULATOR,
    CircuitSimulationSingleConfig,
    MEModelSimulationSingleConfig,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    resolve_neuron_set_ref_to_node_set,
)

DEFAULT_NODE_SET_NAME = "Default All Biophysical Neurons"
DEFAULT_NEURON_SET_BLOCK_REFERENCE = NeuronSetReference(
    block_dict_name="neuron_sets", block_name=DEFAULT_NODE_SET_NAME
)
DEFAULT_NEURON_SET_BLOCK_REFERENCE.block = AllNeurons()
DEFAULT_NEURON_SET_BLOCK_REFERENCE.block.set_block_name(DEFAULT_NODE_SET_NAME)


L = logging.getLogger(__name__)


class GenerateSimulationTask(Task):
    config: CircuitSimulationSingleConfig | MEModelSimulationSingleConfig

    CONFIG_FILE_NAME: ClassVar[str] = "simulation_config.json"
    NODE_SETS_FILE_NAME: ClassVar[str] = "node_sets.json"

    _sonata_config: dict = PrivateAttr(default={})
    _circuit: Circuit | MEModelCircuit | None = PrivateAttr(default=None)
    _entity_cache: bool = PrivateAttr(default=False)

    def _initialize_sonata_simulation_config(self) -> dict:
        """Returns the default SONATA conditions dictionary."""
        self._sonata_config = {}
        self._sonata_config["version"] = SONATA_VERSION
        self._sonata_config["target_simulator"] = TARGET_SIMULATOR

        self._sonata_config["run"] = {}
        self._sonata_config["run"]["dt"] = self.config.initialize.timestep
        self._sonata_config["run"]["random_seed"] = self.config.initialize.random_seed
        self._sonata_config["run"]["tstop"] = self.config.initialize.simulation_length

        self._sonata_config["conditions"] = {}
        self._sonata_config["conditions"]["extracellular_calcium"] = (
            self.config.initialize.extracellular_calcium_concentration
        )
        self._sonata_config["conditions"]["v_init"] = self.config.initialize.v_init
        self._sonata_config["conditions"]["spike_location"] = self.config.initialize.spike_location

        self._sonata_config["output"] = {"output_dir": "output", "spikes_file": "spikes.h5"}
        self._sonata_config["conditions"]["mechanisms"] = {
            "ProbAMPANMDA_EMS": {"init_depleted": True, "minis_single_vesicle": True},
            "ProbGABAAB_EMS": {"init_depleted": True, "minis_single_vesicle": True},
        }

    def _resolve_circuit(self, db_client: entitysdk.client.Client) -> None:
        """Set circuit variable based on the type of initialize.circuit."""
        if isinstance(self.config.initialize.circuit, Circuit):
            L.info("initialize.circuit is a Circuit instance.")
            self._circuit = self.config.initialize.circuit
            self._sonata_config["network"] = self.config.initialize.circuit.path

        elif isinstance(self.config.initialize.circuit, (CircuitFromID, MEModelFromID)):
            L.info("initialize.circuit is a MEModelFromID instance.")
            self._circuit_id = self.config.initialize.circuit.id_str

            circuit_dest_dir = self.config.coordinate_output_root / "sonata_circuit"
            if self._entity_cache and db_client:
                L.info("Use entity cache")
                circuit_dest_dir = (
                    self.config.scan_output_root
                    / "entity_cache"
                    / "sonata_circuit"
                    / self._circuit_id
                )

            self._circuit = self.config.initialize.circuit.stage_circuit(
                db_client=db_client, dest_dir=circuit_dest_dir, entity_cache=self._entity_cache
            )

            self._sonata_config["network"] = str(
                Path(self._circuit.path).relative_to(
                    self.config.coordinate_output_root, walk_up=True
                )
            )

        if self._circuit is None:
            msg = "Failed to resolve circuit!"
            raise OBIONEError(msg)

    def _add_sonata_simulation_config_inputs(self) -> None:
        self._sonata_config["inputs"] = {}
        for stimulus in self.config.stimuli.values():
            if hasattr(stimulus, "generate_spikes"):
                stimulus.generate_spikes(
                    self._circuit,
                    self.config.coordinate_output_root,
                    self.config.initialize.simulation_length,
                    source_node_population=self._circuit.default_population_name,
                )
            self._sonata_config["inputs"].update(
                stimulus.config(
                    self._circuit, self._circuit.default_population_name, DEFAULT_NODE_SET_NAME
                )
            )

    def _add_sonata_simulation_config_reports(self) -> None:
        self._sonata_config["reports"] = {}
        for recording in self.config.recordings.values():
            self._sonata_config["reports"].update(
                recording.config(
                    self._circuit,
                    self._circuit.default_population_name,
                    self.config.initialize.simulation_length,
                    DEFAULT_NODE_SET_NAME,
                )
            )

    def _add_sonata_simulation_config_manipulations(self) -> None:
        if hasattr(self.config, "synaptic_manipulations"):
            # Generate list of synaptic manipulation configs (executed in the order in the list)
            # TODO: Ensure that the order in the self.synaptic_manipulations dict is preserved!
            manipulation_list = [
                manipulation.config()
                for manipulation in self.config.synaptic_manipulations.values()
            ]
            if len(manipulation_list) > 0:
                self._sonata_config["connection_overrides"] = manipulation_list

    def _ensure_block_has_neuron_set_reference_if_neuron_sets_dictionary_exists(
        self, block: Block
    ) -> None:
        """If the block's NeuronSetReference is None, set it to the default NeuronSetReference.

        This is only done if the config has a neuron_sets attribute.
        """

        def is_optional_neuronsetreference(attr_value: type) -> bool:
            args = get_args(attr_value)
            return args == (NeuronSetReference, type(None))

        if hasattr(self.config, "neuron_sets"):
            type_hints = get_type_hints(block.__class__)

            for attr_name, attr_type in type_hints.items():
                if is_optional_neuronsetreference(attr_type):
                    attr_value = getattr(block, attr_name, None)
                    if attr_value is None:
                        setattr(block, attr_name, self._default_neuron_set_ref())

    def _ensure_all_blocks_have_neuron_set_reference_if_neuron_sets_dictionary_exists(self) -> None:
        """Ensure all blocks have a NeuronSetReference if the neuron_sets dictionary exists."""
        if hasattr(self.config, "neuron_sets"):
            for recording in self.config.recordings.values():
                self._ensure_block_has_neuron_set_reference_if_neuron_sets_dictionary_exists(
                    recording
                )

            for stimulus in self.config.stimuli.values():
                self._ensure_block_has_neuron_set_reference_if_neuron_sets_dictionary_exists(
                    stimulus
                )

    def _default_neuron_set_ref(self) -> NeuronSetReference:
        """Returns the reference for the default neuron set."""
        if (
            DEFAULT_NEURON_SET_BLOCK_REFERENCE.block_name in self.config.neuron_sets
            and not isinstance(
                self.config.neuron_sets[DEFAULT_NEURON_SET_BLOCK_REFERENCE.block_name], AllNeurons
            )
        ):
            msg = f"Default neuron set name '{DEFAULT_NEURON_SET_BLOCK_REFERENCE.block_name}' \
                already exists in neuron_sets but is not an AllNeurons set!"
            raise OBIONEError(msg)

        if DEFAULT_NEURON_SET_BLOCK_REFERENCE.block_name not in self.config.neuron_sets:
            self.config.neuron_sets[DEFAULT_NEURON_SET_BLOCK_REFERENCE.block_name] = (
                DEFAULT_NEURON_SET_BLOCK_REFERENCE.block
            )

        return DEFAULT_NEURON_SET_BLOCK_REFERENCE

    def _ensure_simulation_target_node_set(self) -> None:
        """Ensure a neuron set exists matching `initialize.node_set`.

        Infer default if needed. Assert biophysical.
        """
        if hasattr(self.config, "neuron_sets"):
            if self.config.initialize.node_set is None:
                L.info("initialize.node_set is None — setting default node set.")
                self.config.initialize.node_set = self._default_neuron_set_ref()

            # Assert that simulation neuron set is biophysical
            if isinstance(self.config.initialize.node_set, NeuronSetReference) and (
                self.config.initialize.node_set.block.population_type(
                    self._circuit, self._circuit.default_population_name
                )
                != "biophysical"
            ):
                msg = f"Simulation Neuron Set (Initialize -> Neuron Set): \
                    '{self.config.initialize.node_set.name}' "
                "is not biophysical!"
                raise OBIONEError(msg)

            self._sonata_config["node_set"] = resolve_neuron_set_ref_to_node_set(
                self.config.initialize.node_set, DEFAULT_NODE_SET_NAME
            )

        else:
            self._sonata_config["node_set"] = DEFAULT_NODE_SET_NAME

    def _resolve_neuron_sets_and_write_simulation_node_sets_file(self) -> None:
        """Resolve neuron sets and add them to the SONATA circuit object.

        In the case where there is no neuron_sets dictionary in the config, the default
        AllNeurons neuron set is created and added to the SONATA circuit object.

        The neuron_sets dict key is always used as the name of the new node set, even for a
        PredefinedNeuronSet, in which case a new node set is created which references the
        existing one. This makes behaviour consistent whether random subsampling is used or not.
        It also means, however, that existing node_set names cannot be used as keys in neuron_sets.

        Resolve node set based on current coordinate circuit's default node population
        TODO: Better handling of (default) node population in case there is more than one
        TODO: Inconsistency possible in case a node set definition would span multiple
        populations. May consider force_resolve_ids=False to enforce resolving into given
        population (but which won't be a human-readable representation any more).
        """
        sonata_circuit = self._circuit.sonata_circuit
        if hasattr(self.config, "neuron_sets"):
            # circuit.sonata_circuit should be created once. Currently this would break other code.

            for _neuron_set_key, _neuron_set in self.config.neuron_sets.items():
                # 1. Check that the neuron sets block name matches the dict key
                if _neuron_set_key != _neuron_set.block_name:
                    msg = "Neuron set name mismatch! \
                        Using sim_conf.add(neuron_set, name=neuron_set_name) should ensure this."
                    raise OBIONEError(msg)

                # 2.Add node set to SONATA circuit object - raises error if already existing
                _neuron_set.add_node_set_definition_to_sonata_circuit(self._circuit, sonata_circuit)

        else:
            neuron_set = AllNeurons()
            neuron_set.set_block_name(DEFAULT_NODE_SET_NAME)
            neuron_set.add_node_set_definition_to_sonata_circuit(self._circuit, sonata_circuit)

        # 3. Write node sets from SONATA circuit object to .json file
        write_circuit_node_set_file(
            sonata_circuit,
            self.config.coordinate_output_root,
            file_name=self.NODE_SETS_FILE_NAME,
            overwrite_if_exists=False,
        )
        self._sonata_config["node_sets_file"] = self.NODE_SETS_FILE_NAME

    def _write_simulation_config_to_file(self) -> None:
        simulation_config_path = Path(self.config.coordinate_output_root) / self.CONFIG_FILE_NAME
        with simulation_config_path.open("w", encoding="utf-8") as f:
            json.dump(self._sonata_config, f, indent=2)

    def _save_generated_simulation_assets_to_entity(
        self, db_client: entitysdk.client.Client | None
    ) -> None:
        if db_client:
            L.info("-- Upload sonata_simulation_config")
            _ = db_client.upload_file(
                entity_id=self.config.single_entity.id,
                entity_type=entitysdk.models.Simulation,
                file_path=Path(self.config.coordinate_output_root, "simulation_config.json"),
                file_content_type="application/json",
                asset_label="sonata_simulation_config",
            )

            if hasattr(self.config, "neuron_sets"):
                L.info("-- Upload custom_node_sets")
                _ = db_client.upload_file(
                    entity_id=self.config.single_entity.id,
                    entity_type=entitysdk.models.Simulation,
                    file_path=Path(self.config.coordinate_output_root, "node_sets.json"),
                    file_content_type="application/json",
                    asset_label="custom_node_sets",
                )

            L.info("-- Upload spike replay files")
            for input_ in self._sonata_config["inputs"]:
                if "spike_file" in list(self._sonata_config["inputs"][input_]):
                    spike_file = self._sonata_config["inputs"][input_]["spike_file"]
                    if spike_file is not None:
                        _ = db_client.upload_file(
                            entity_id=self.config.single_entity.id,
                            entity_type=entitysdk.models.Simulation,
                            file_path=Path(self.config.coordinate_output_root, spike_file),
                            file_content_type="application/x-hdf5",
                            asset_label="replay_spikes",
                        )

    def execute(
        self, *, db_client: entitysdk.client.Client = None, entity_cache: bool = False
    ) -> None:
        """Generates SONATA simulation files."""
        self._entity_cache = entity_cache
        self._initialize_sonata_simulation_config()
        self._resolve_circuit(db_client)
        self._ensure_simulation_target_node_set()
        self._ensure_all_blocks_have_neuron_set_reference_if_neuron_sets_dictionary_exists()
        self._add_sonata_simulation_config_inputs()
        self._add_sonata_simulation_config_reports()
        self._add_sonata_simulation_config_manipulations()
        self._resolve_neuron_sets_and_write_simulation_node_sets_file()
        self._write_simulation_config_to_file()
        self._save_generated_simulation_assets_to_entity(db_client)
