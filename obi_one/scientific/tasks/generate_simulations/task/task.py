import logging
from pathlib import Path
from typing import ClassVar, get_args, get_type_hints

import entitysdk
from pydantic import PrivateAttr

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.task import Task
from obi_one.scientific.blocks.neuron_sets.base import NeuronSetPopulationType
from obi_one.scientific.blocks.neuron_sets.combined import CombinedBaseNeuronSet
from obi_one.scientific.blocks.stimuli.brian2_poisson import Brian2DirectPoissonStimulus
from obi_one.scientific.blocks.stimuli.spike.base import SpikeStimulus
from obi_one.scientific.blocks.timestamps.single import SingleTimestamp
from obi_one.scientific.from_id.circuit_from_id import (
    CircuitFromID,
    MEModelWithSynapsesCircuitFromID,
)
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.ion_channel_model_circuit import CircuitFromIonChannelModels
from obi_one.scientific.library.memodel_circuit import MEModelCircuit
from obi_one.scientific.library.sonata_circuit_helpers import (
    write_circuit_node_set_file,
)
from obi_one.scientific.tasks.generate_simulations.config.brian2.brian2_circuit import (
    Brian2CircuitSimulationSingleConfig,
)
from obi_one.scientific.unions_and_references.combined_neuron_sets import (
    ALL_NEURON_SETS_REFERENCE_UNION,
    resolve_neuron_set_ref_to_node_set,
)
from obi_one.scientific.unions_and_references.neuron_sets import (
    BaseNeuronSetReference,
    NeuronSetReference,
)
from obi_one.scientific.unions_and_references.simulations import (
    SIMULATION_GENERATION_SINGLE_CONFIGS,
)
from obi_one.utils.sonata import write_simulation_config

L = logging.getLogger(__name__)

DEFAULT_TIMESTAMPS = SingleTimestamp(start_time=0.0)


class GenerateSimulationTask(Task):
    config: SIMULATION_GENERATION_SINGLE_CONFIGS

    CONFIG_FILE_NAME: ClassVar[str] = "simulation_config.json"
    NODE_SETS_FILE_NAME: ClassVar[str] = "node_sets.json"

    _sonata_config: dict = PrivateAttr(default={})
    _circuit: Circuit | MEModelCircuit | None = PrivateAttr(default=None)
    _entity_cache: bool = PrivateAttr(default=False)

    def _resolve_circuit(self, db_client: entitysdk.client.Client) -> None:
        """Set circuit variable based on the type of initialize.circuit."""
        if hasattr(self.config.initialize, "circuit"):
            circuit = self.config.initialize.circuit
        elif hasattr(self.config, "circuit"):
            circuit = self.config.circuit
        else:
            msg = "No circuit specified in config!"
            raise OBIONEError(msg)

        if isinstance(circuit, Circuit):
            L.info("initialize.circuit is a Circuit instance.")
            self._circuit = circuit
            self._sonata_config["network"] = str(Path(circuit.path).resolve())

        elif isinstance(
            circuit,
            (
                CircuitFromID,
                MEModelFromID,
                MEModelWithSynapsesCircuitFromID,
                CircuitFromIonChannelModels,
            ),
        ):
            self._circuit_id = circuit.id_str

            circuit_dest_dir = self.config.coordinate_output_root / "sonata_circuit"
            if self._entity_cache and db_client:
                L.info("Use entity cache")
                circuit_dest_dir = (
                    self.config.scan_output_root
                    / "entity_cache"
                    / "sonata_circuit"
                    / self._circuit_id
                )

            self._circuit = circuit.stage_circuit(
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
            if isinstance(stimulus, SpikeStimulus):
                self._sonata_config["inputs"].update(
                    stimulus.config(
                        circuit=self._circuit,  # ty:ignore[invalid-argument-type]
                        sonata_simulation_config_directory=self.config.coordinate_output_root,
                        simulation_length=self.config.initialize.simulation_length,  # ty:ignore[invalid-argument-type]
                        default_timestamps=DEFAULT_TIMESTAMPS,  # ty:ignore[invalid-argument-type]
                        default_source_neuron_set_reference=self._default_neuron_set_ref(),
                        default_target_neuron_set_reference=self._default_neuron_set_ref(),
                    )
                )
            elif isinstance(stimulus, Brian2DirectPoissonStimulus):
                self._sonata_config["inputs"].update(
                    stimulus.config(
                        circuit=self._circuit,  # ty:ignore[invalid-argument-type]
                        default_node_set=self.config.default_node_set_name,
                        default_timestamps=DEFAULT_TIMESTAMPS,  # ty:ignore[invalid-argument-type]
                    )
                )
            else:
                self._sonata_config["inputs"].update(
                    stimulus.config(
                        default_node_set=self.config.default_node_set_name,
                        default_timestamps=DEFAULT_TIMESTAMPS,  # ty:ignore[invalid-argument-type]
                    )
                )

    def _add_sonata_simulation_config_reports(
        self, db_client: entitysdk.client.Client | None
    ) -> None:
        self._sonata_config["reports"] = {}
        for recording in getattr(self.config, "recordings", {}).values():
            self._sonata_config["reports"].update(
                recording.config(
                    self.config.initialize.simulation_length,
                    self.config.default_node_set_name,
                    db_client,
                )
            )

    def _add_sonata_simulation_config_manipulations(self) -> None:
        if hasattr(self.config, "synaptic_manipulations"):
            # Generate list of synaptic manipulation configs (executed in the order in the list)
            # TODO: Ensure that the order in the self.synaptic_manipulations dict is preserved!
            manipulation_list = [
                item
                for manipulation in getattr(self.config, "synaptic_manipulations", {}).values()
                for item in manipulation.config(self.config.default_node_set_name)
            ]
            if len(manipulation_list) > 0:
                self._sonata_config["connection_overrides"] = manipulation_list

        if hasattr(self.config, "neuronal_manipulations"):
            # Separate RANGE (section_list) and GLOBAL (mechanisms) modifications
            range_modifications = []
            mechanisms: dict = {}
            for modification in getattr(self.config, "neuronal_manipulations", {}).values():
                result = modification.config(
                    self.config.default_node_set_name,
                )
                if isinstance(result, list):
                    # RANGE variables -> conditions.modifications list
                    range_modifications.extend(result)
                else:
                    # GLOBAL variables -> conditions.mechanisms dict
                    for channel, props in result.items():
                        mechanisms.setdefault(channel, {}).update(props)
            if range_modifications:
                self._sonata_config["conditions"]["modifications"] = range_modifications
            if mechanisms:
                self._sonata_config["conditions"]["mechanisms"] = mechanisms

    def _ensure_block_has_neuron_set_reference_if_neuron_sets_dictionary_exists(
        self, block: Block
    ) -> None:
        """If the block's NeuronSetReference is None, set it to the default NeuronSetReference.

        This is only done if the config has a neuron_sets attribute.
        """

        def is_optional_neuronsetreference(attr_value: type) -> bool:
            none_type = type(None)
            args = get_args(attr_value)
            none_args = [arg for arg in args if arg is none_type]
            reference_args = [arg for arg in args if arg is not none_type]
            return (
                len(none_args) == 1
                and len(reference_args) >= 1
                and all(
                    isinstance(arg, type)
                    and issubclass(arg, (BaseNeuronSetReference, NeuronSetReference))
                    for arg in reference_args
                )
            )

        if hasattr(self.config, "neuron_sets"):
            type_hints = get_type_hints(block.__class__)

            for attr_name, attr_type in type_hints.items():
                if is_optional_neuronsetreference(attr_type):
                    attr_value = getattr(block, attr_name, None)
                    if attr_value is None:
                        # A Brian2 Poisson stimulus with no target drives the `sugar` node set,
                        # not the simulation-wide default (every point neuron); see
                        # Brian2SimulationScanConfig.
                        if isinstance(block, Brian2DirectPoissonStimulus):
                            setattr(block, attr_name, self._default_stimulus_neuron_set_ref())
                        else:
                            setattr(block, attr_name, self._default_neuron_set_ref())

    def _ensure_all_blocks_have_neuron_set_reference_if_neuron_sets_dictionary_exists(self) -> None:
        """Ensure all blocks have a NeuronSetReference if the neuron_sets dictionary exists."""
        if hasattr(self.config, "neuron_sets"):
            for recording in getattr(self.config, "recordings", {}).values():
                self._ensure_block_has_neuron_set_reference_if_neuron_sets_dictionary_exists(
                    recording
                )
            for stimulus in getattr(self.config, "stimuli", {}).values():
                self._ensure_block_has_neuron_set_reference_if_neuron_sets_dictionary_exists(
                    stimulus
                )
            for neuron_set in list(getattr(self.config, "neuron_sets", {}).values()):
                if isinstance(neuron_set, CombinedBaseNeuronSet):
                    self._ensure_combined_neuron_set_has_references(neuron_set)

    def _ensure_combined_neuron_set_has_references(self, neuron_set: CombinedBaseNeuronSet) -> None:
        """Ensure a combined neuron set's base and combined_with references are filled."""
        default_ref = self._default_neuron_set_ref_for_population_type(
            neuron_set.get_neuron_set_population_type()
        )

        if neuron_set.base_neuron_set is None:
            neuron_set.base_neuron_set = default_ref

        updated_entries = []
        for ref, op in neuron_set.combined_with:
            if ref is None:
                updated_entries.append((default_ref, op))
            else:
                updated_entries.append((ref, op))
        neuron_set.combined_with = tuple(updated_entries)

    def _default_neuron_set_ref_for_population_type(
        self, population_type: NeuronSetPopulationType
    ) -> ALL_NEURON_SETS_REFERENCE_UNION:
        """Returns the appropriate default neuron set reference for the given population type."""
        if population_type == NeuronSetPopulationType.VIRTUAL:
            return self._default_virtual_neuron_set_ref()
        if population_type == NeuronSetPopulationType.POINT:
            return self._default_point_neuron_set_ref()
        return self._default_neuron_set_ref()

    def _default_virtual_neuron_set_ref(self) -> ALL_NEURON_SETS_REFERENCE_UNION:
        """Returns the reference for the default virtual neuron set."""
        ref = self.config.default_virtual_neuron_set_reference  # ty:ignore[unresolved-attribute]
        if (
            ref.block_name in self.config.neuron_sets  # ty:ignore[unresolved-attribute]
            and not isinstance(
                self.config.neuron_sets[ref.block_name],  # ty:ignore[unresolved-attribute]
                self.config.default_virtual_neuron_set_type,  # ty:ignore[unresolved-attribute]
            )
        ):
            msg = (
                f"Default virtual neuron set name '{ref.block_name}' already exists in "
                f"neuron_sets but is not an "
                f"{self.config.default_virtual_neuron_set_type.__name__} set!"  # ty:ignore[unresolved-attribute]
            )
            raise OBIONEError(msg)
        if ref.block_name not in self.config.neuron_sets:  # ty:ignore[unresolved-attribute]
            self.config.neuron_sets[ref.block_name] = ref.block  # ty:ignore[unresolved-attribute,invalid-assignment]
        return ref

    def _default_point_neuron_set_ref(self) -> ALL_NEURON_SETS_REFERENCE_UNION:
        """Returns the reference for the default point neuron set."""
        ref = self.config.default_point_neuron_set_reference  # ty:ignore[unresolved-attribute]
        if (
            ref.block_name in self.config.neuron_sets  # ty:ignore[unresolved-attribute]
            and not isinstance(
                self.config.neuron_sets[ref.block_name],  # ty:ignore[unresolved-attribute]
                self.config.default_point_neuron_set_type,  # ty:ignore[unresolved-attribute]
            )
        ):
            msg = (
                f"Default point neuron set name '{ref.block_name}' already exists in "
                f"neuron_sets but is not an "
                f"{self.config.default_point_neuron_set_type.__name__} set!"  # ty:ignore[unresolved-attribute]
            )
            raise OBIONEError(msg)
        if ref.block_name not in self.config.neuron_sets:  # ty:ignore[unresolved-attribute]
            self.config.neuron_sets[ref.block_name] = ref.block  # ty:ignore[unresolved-attribute,invalid-assignment]
        return ref

    def _default_neuron_set_ref(self) -> ALL_NEURON_SETS_REFERENCE_UNION:
        """Returns the reference for the default neuron set."""
        default_neuron_set_ref = self.config.default_neuron_set_reference

        if (
            default_neuron_set_ref.block_name in self.config.neuron_sets  # ty:ignore[unresolved-attribute]
            and not isinstance(
                self.config.neuron_sets[default_neuron_set_ref.block_name],  # ty:ignore[unresolved-attribute]
                self.config.default_neuron_set_type,
            )
        ):
            msg = (
                f"Default neuron set name '{default_neuron_set_ref.block_name}' already exists "
                f"in neuron_sets but is not an "
                f"{self.config.default_neuron_set_type.__name__} set!"
            )
            raise OBIONEError(msg)

        if default_neuron_set_ref.block_name not in self.config.neuron_sets:  # ty:ignore[unresolved-attribute]
            self.config.neuron_sets[default_neuron_set_ref.block_name] = (  # ty:ignore[unresolved-attribute,invalid-assignment]
                default_neuron_set_ref.block
            )

        return default_neuron_set_ref

    def _default_stimulus_neuron_set_ref(self) -> ALL_NEURON_SETS_REFERENCE_UNION:
        """Returns the reference for the default stimulus neuron set (Brian2: the `sugar` set).

        The circuit is already resolved: ``execute`` calls ``_resolve_circuit`` before it fills
        in the missing neuron set references.
        """
        ref = self.config.default_stimulus_neuron_set_reference(self._circuit)  # ty:ignore[unresolved-attribute,invalid-argument-type]
        if ref.block_name not in self.config.neuron_sets:  # ty:ignore[unresolved-attribute]
            self.config.neuron_sets[ref.block_name] = ref.block  # ty:ignore[unresolved-attribute,invalid-assignment]
        return ref

    """
    NEW NEURON SETS REFACTOR: SOME OF THIS CAN PROBABLY BE REMOVED NOW THE
    NEURON SETS HAVE TYPES (BIOPHYSICAL, POINT, ETC.)
    """

    def _ensure_simulation_target_node_set(self) -> None:
        """Ensure a neuron set exists matching `initialize.node_set`.

        Infer default if needed. Assert non-virtual (biophysical or point).
        """
        if hasattr(self.config, "neuron_sets"):
            if hasattr(self.config.initialize, "node_set"):
                if self.config.initialize.node_set is None:
                    L.info("initialize.node_set is None — setting default node set.")
                    self.config.initialize.node_set = self._default_neuron_set_ref()  # ty:ignore[invalid-assignment]

                # Assert that simulation neuron set is non-virtual (skip for Brian2)
                if (
                    not isinstance(self.config, Brian2CircuitSimulationSingleConfig)
                    and isinstance(self.config.initialize.node_set, BaseNeuronSetReference)
                    and self._circuit is not None
                    and (
                        self.config.initialize.node_set.block.get_neuron_set_population_type()
                        not in {
                            NeuronSetPopulationType.BIOPHYSICAL,
                            NeuronSetPopulationType.POINT,
                            NeuronSetPopulationType.NONVIRTUAL,
                        }
                    )
                ):
                    # Get list of non-virtual populations to help user
                    non_virtual_populations = Circuit.get_node_population_names(
                        self._circuit.sonata_circuit,
                        incl_virtual=False,
                        incl_point=True,
                    )
                    non_virtual_list = (
                        ", ".join(f"'{pop}'" for pop in non_virtual_populations)
                        if non_virtual_populations
                        else "none found"
                    )

                    msg = (
                        f"Simulation Neuron Set (Initialize -> Neuron Set): "
                        f"'{self.config.initialize.node_set.block_name}' is virtual. "
                        "Please use a non-virtual (biophysical or point) Neuron Set type. "
                        f"Available non-virtual populations: {non_virtual_list}. "
                        f"You may be able to reference one through an "
                        f"MultiPopulationPredefinedNeuronSet block type. "
                        "In future we will support population selection for any neuron set."
                    )
                    raise OBIONEError(msg)

                self._sonata_config["node_set"] = resolve_neuron_set_ref_to_node_set(
                    self.config.initialize.node_set,  # ty:ignore[invalid-argument-type]
                    self.config.default_node_set_name,
                )
            elif not hasattr(self.config.initialize, "node_set"):
                _ = self._default_neuron_set_ref()
                self._sonata_config["node_set"] = self.config.default_node_set_name

        else:
            self._sonata_config["node_set"] = self.config.default_node_set_name

    def _resolve_neuron_sets_and_write_simulation_node_sets_file(self) -> None:
        """Resolve neuron sets and add them to the SONATA circuit object.

        In the case where there is no neuron_sets dictionary in the config, the config's
        default_neuron_set_type is created and added to the SONATA circuit object.
        The neuron_sets dict key is always used as the name of the new node set, even for a
        predefined neuron set, in which case a new node set is created which references the
        existing one. This makes behaviour consistent whether random subsampling is used or not.
        It also means, however, that existing node_set names cannot be used as keys in neuron_sets.
        """
        sonata_circuit = self._circuit.sonata_circuit  # ty:ignore[unresolved-attribute]

        if hasattr(self.config, "neuron_sets"):
            # circuit.sonata_circuit should be created once. Currently this would break other code.

            L.info("self.config.neuron_sets: %s", self.config.neuron_sets)

            for neuron_set_key, neuron_set_ in self.config.neuron_sets.items():  # ty:ignore[unresolved-attribute]
                # 1. Check that the neuron sets block name matches the dict key
                if neuron_set_key != neuron_set_.block_name:
                    msg = "Neuron set name mismatch! \
                        Using sim_conf.add(neuron_set, name=neuron_set_name) should ensure this."
                    raise OBIONEError(msg)

                # 2.Add node set to SONATA circuit object - raises error if already existing
                neuron_set_.add_node_set_definition_to_sonata_circuit(
                    self._circuit, sonata_circuit, force_resolve_ids=True
                )

        else:
            neuron_set = self.config.default_neuron_set_type()
            neuron_set.set_block_name(self.config.default_node_set_name)
            neuron_set.add_node_set_definition_to_sonata_circuit(
                self._circuit,  # ty:ignore[invalid-argument-type]
                sonata_circuit,
                force_resolve_ids=True,
            )

        # 3. Write node sets from SONATA circuit object to .json file
        write_circuit_node_set_file(
            sonata_circuit,
            self.config.coordinate_output_root,  # ty:ignore[invalid-argument-type]
            file_name=self.NODE_SETS_FILE_NAME,
            overwrite_if_exists=False,
        )
        self._sonata_config["node_sets_file"] = self.NODE_SETS_FILE_NAME

    def _update_simulation_number_neurons(self, db_client: entitysdk.client.Client | None) -> None:
        if db_client:
            if hasattr(self.config, "neuron_sets") and hasattr(self.config.initialize, "node_set"):
                neuron_set = self.config.initialize.node_set
                if neuron_set is None:
                    msg = "initialize.node_set is None — cannot update number_neurons. \
                    Even if originally set to None, its value should be set already by \
                        _ensure_simulation_target_node_set()"
                    raise OBIONEError(msg)
                neuron_set_ids = neuron_set.block.get_neuron_ids(self._circuit)  # ty:ignore[unresolved-attribute]
                number_neurons = sum(len(v) for v in neuron_set_ids.values())
            else:
                # Essentially the memodel case when no neuron_sets
                number_neurons = 1

            db_client.update_entity(
                entity_id=self.config.single_entity.id,
                entity_type=entitysdk.models.Simulation,  # ty:ignore[possibly-missing-submodule]
                attrs_or_entity={"number_neurons": number_neurons},
            )

    def _write_simulation_config_to_file(self) -> None:
        write_simulation_config(
            config=self._sonata_config,
            output_path=Path(self.config.coordinate_output_root, self.CONFIG_FILE_NAME),
        )

    def _save_generated_simulation_assets_to_entity(
        self, db_client: entitysdk.client.Client | None
    ) -> None:
        if db_client:
            L.info("-- Upload custom_node_sets")
            _ = db_client.upload_file(
                entity_id=self.config.single_entity.id,
                entity_type=entitysdk.models.Simulation,  # ty:ignore[possibly-missing-submodule]
                file_path=Path(self.config.coordinate_output_root, "node_sets.json"),
                file_content_type="application/json",  # ty:ignore[invalid-argument-type]
                asset_label="custom_node_sets",  # ty:ignore[invalid-argument-type]
            )

            L.info("-- Upload spike replay files")
            for input_ in self._sonata_config["inputs"]:
                if "spike_file" in list(self._sonata_config["inputs"][input_]):
                    spike_file = self._sonata_config["inputs"][input_]["spike_file"]
                    if spike_file is not None:
                        _ = db_client.upload_file(
                            entity_id=self.config.single_entity.id,
                            entity_type=entitysdk.models.Simulation,  # ty:ignore[possibly-missing-submodule]
                            file_path=Path(self.config.coordinate_output_root, spike_file),
                            file_content_type="application/x-hdf5",  # ty:ignore[invalid-argument-type]
                            asset_label="replay_spikes",  # ty:ignore[invalid-argument-type]
                        )

            L.info("-- Upload sonata_simulation_config")
            _ = db_client.upload_file(
                entity_id=self.config.single_entity.id,
                entity_type=entitysdk.models.Simulation,  # ty:ignore[possibly-missing-submodule]
                file_path=Path(self.config.coordinate_output_root, "simulation_config.json"),
                file_content_type="application/json",  # ty:ignore[invalid-argument-type]
                asset_label="sonata_simulation_config",  # ty:ignore[invalid-argument-type]
            )

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,
        execution_activity_id: str | None = None,  # noqa: ARG002
    ) -> None:
        """Generates SONATA simulation files."""
        self._entity_cache = entity_cache
        self._sonata_config = self.config.base_sonata_config()
        self._resolve_circuit(db_client)
        self._ensure_simulation_target_node_set()
        self._ensure_all_blocks_have_neuron_set_reference_if_neuron_sets_dictionary_exists()
        self._add_sonata_simulation_config_inputs()
        self._add_sonata_simulation_config_reports(db_client)
        self._add_sonata_simulation_config_manipulations()
        self._resolve_neuron_sets_and_write_simulation_node_sets_file()
        self._update_simulation_number_neurons(db_client)
        self._write_simulation_config_to_file()
        self._save_generated_simulation_assets_to_entity(db_client)
