import logging
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar

import entitysdk
from pydantic import PrivateAttr

from obi_one.core.block_reference import BlockReference
from obi_one.core.exception import OBIONEError
from obi_one.core.fill_none_references import fill_none_references_in_config
from obi_one.core.task import Task
from obi_one.scientific.blocks.neuron_sets.base import NeuronSet
from obi_one.scientific.blocks.stimuli.spike.base import SpikeStimulus
from obi_one.scientific.from_id.circuit_from_id import (
    CircuitFromID,
    MEModelWithSynapsesCircuitFromID,
)
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.compartment_sets import MaterializedCompartmentSet
from obi_one.scientific.library.ion_channel_model_circuit import CircuitFromIonChannelModels
from obi_one.scientific.library.memodel_circuit import MEModelCircuit
from obi_one.scientific.library.sonata_circuit_helpers import (
    write_circuit_compartment_set_file,
    write_circuit_node_set_file,
)
from obi_one.scientific.tasks.generate_simulations.materialize_locations import (
    materialize_locations_to_compartment_sets,
)
from obi_one.scientific.unions_and_references.simulations import (
    SIMULATION_GENERATION_SINGLE_CONFIGS,
)
from obi_one.utils.sonata import write_simulation_config

L = logging.getLogger(__name__)


class GenerateSimulationTask(Task):
    config: SIMULATION_GENERATION_SINGLE_CONFIGS

    CONFIG_FILE_NAME: ClassVar[str] = "simulation_config.json"
    NODE_SETS_FILE_NAME: ClassVar[str] = "node_sets.json"
    COMPARTMENT_SETS_FILE_NAME: ClassVar[str] = "compartment_sets.json"

    _sonata_config: dict = PrivateAttr(default={})
    _circuit: Circuit | MEModelCircuit | None = PrivateAttr(default=None)
    _entity_cache: bool = PrivateAttr(default=False)
    _materialized_compartment_sets: dict[str, MaterializedCompartmentSet] = PrivateAttr(
        default_factory=dict
    )

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
                entry = stimulus.config(
                    circuit=self._circuit,  # ty:ignore[invalid-argument-type]
                    sonata_simulation_config_directory=self.config.coordinate_output_root,
                    simulation_length=self.config.initialize.simulation_length,  # ty:ignore[invalid-argument-type]
                )
            else:
                entry = stimulus.config()
            self._sonata_config["inputs"].update(entry)

    def _add_sonata_simulation_config_reports(
        self, db_client: entitysdk.client.Client | None
    ) -> None:
        self._sonata_config["reports"] = {}
        for recording in getattr(self.config, "recordings", {}).values():
            self._sonata_config["reports"].update(
                recording.config(
                    end_time=self.config.initialize.simulation_length,
                    db_client=db_client,
                )
            )

    def _add_sonata_simulation_config_manipulations(self) -> None:
        if hasattr(self.config, "synaptic_manipulations"):
            # Generate list of synaptic manipulation configs (executed in the order in the list)
            # TODO: Ensure that the order in the self.synaptic_manipulations dict is preserved!
            manipulation_list = [
                item
                for manipulation in getattr(self.config, "synaptic_manipulations", {}).values()
                for item in manipulation.config()
            ]
            if len(manipulation_list) > 0:
                self._sonata_config["connection_overrides"] = manipulation_list

        if hasattr(self.config, "neuronal_manipulations"):
            # Separate RANGE (section_list) and GLOBAL (mechanisms) modifications
            range_modifications = []
            mechanisms: dict = {}
            for modification in getattr(self.config, "neuronal_manipulations", {}).values():
                result = modification.config()
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

    def _register_default_neuron_sets(self, references: Iterable[BlockReference]) -> None:
        """Add the defaults that were used to the config's neuron sets, so they reach node_sets.

        Only neuron sets need this; default timestamps never become a node set. A config with no
        neuron_sets dictionary -- an ME model simulation holds a single neuron -- has its node set
        written straight from the config's default type instead, so there is nowhere to add to.
        """
        neuron_sets = getattr(self.config, "neuron_sets", None)
        if neuron_sets is None:
            return

        for reference in references:
            block = reference.block
            if not isinstance(block, NeuronSet):
                continue

            existing = neuron_sets.get(reference.block_name)
            if existing is None:
                neuron_sets[reference.block_name] = block
            elif not isinstance(existing, type(block)):
                msg = (
                    f"Default neuron set name '{reference.block_name}' already exists in "
                    f"neuron_sets but is not an {type(block).__name__} set!"
                )
                raise OBIONEError(msg)

    def _fill_none_references(self) -> None:
        """Give every block reference left unset the default for its role.

        This runs once, before anything reads a reference, so no block has to reason about what
        an unset reference means: by the time a block builds its SONATA entry, every reference it
        holds points somewhere. Only the defaults a block actually needed are registered, so a
        simulation whose blocks all name their own targets gains no spurious node sets.
        """
        used = fill_none_references_in_config(
            self.config,
            self.config.default_block_references(),
        )
        self._register_default_neuron_sets(used)

    def _materialize_location_targets(self) -> None:
        circuit = self._circuit
        if circuit is None:
            msg = "Circuit must be resolved before materializing location targets."
            raise OBIONEError(msg)

        population = circuit.default_population_name

        self._materialized_compartment_sets.update(
            materialize_locations_to_compartment_sets(
                single_config=self.config,
                circuit=circuit,
                node_population=population,
                population=population,
            )
        )

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

    def _write_materialized_compartment_sets_file(self) -> None:
        if self._materialized_compartment_sets:
            compartment_sets_dict: dict = {}
            sonata_circuit = self._circuit.sonata_circuit  # ty:ignore[unresolved-attribute]

            for cs_key, comp_set in self._materialized_compartment_sets.items():
                if cs_key != comp_set.name:
                    msg = "Materialized compartment set name mismatch."
                    raise OBIONEError(msg)

                compartment_sets_dict.update(comp_set.to_sonata_dict())

            write_circuit_compartment_set_file(
                sonata_circuit,
                str(self.config.coordinate_output_root),
                compartment_sets=compartment_sets_dict,
                file_name=self.COMPARTMENT_SETS_FILE_NAME,
                overwrite_if_exists=False,
            )

            self._sonata_config["compartment_sets_file"] = self.COMPARTMENT_SETS_FILE_NAME

    def _update_simulation_number_neurons(self, db_client: entitysdk.client.Client | None) -> None:
        if db_client:
            if hasattr(self.config, "neuron_sets") and hasattr(self.config.initialize, "node_set"):
                neuron_set = self.config.initialize.node_set
                if neuron_set is None:
                    msg = (
                        "initialize.node_set is None — cannot update number_neurons. Even if "
                        "originally set to None, _fill_none_references() should have given it "
                        "the default for its reference tag."
                    )
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
                file_path=Path(self.config.coordinate_output_root, self.NODE_SETS_FILE_NAME),
                file_content_type="application/json",  # ty:ignore[invalid-argument-type]
                asset_label="custom_node_sets",  # ty:ignore[invalid-argument-type]
            )

            compartment_sets_path = Path(
                self.config.coordinate_output_root,
                self.COMPARTMENT_SETS_FILE_NAME,
            )
            if compartment_sets_path.exists():
                L.info("-- Upload compartment_sets.json")
                _ = db_client.upload_file(
                    entity_id=self.config.single_entity.id,
                    entity_type=entitysdk.models.Simulation,  # ty:ignore[possibly-missing-submodule]
                    file_path=compartment_sets_path,
                    file_name=self.COMPARTMENT_SETS_FILE_NAME,
                    file_content_type="application/json",  # ty:ignore[invalid-argument-type]
                    asset_label="compartment_sets",  # ty:ignore[invalid-argument-type]
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
                file_path=Path(self.config.coordinate_output_root, self.CONFIG_FILE_NAME),
                file_content_type="application/json",  # ty:ignore[invalid-argument-type]
                asset_label="sonata_simulation_config",  # ty:ignore[invalid-argument-type]
            )

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,
        execution_activity_id: str | None = None,  # ruff: ignore[unused-method-argument]
    ) -> None:
        """Generates SONATA simulation files."""
        self._entity_cache = entity_cache
        self._sonata_config = self.config.base_sonata_config()
        self._resolve_circuit(db_client)
        self._fill_none_references()
        self.config.check_simulation_target(self._circuit)  # ty:ignore[invalid-argument-type]
        self._sonata_config["node_set"] = self.config.simulation_node_set_name
        self._materialize_location_targets()
        self._add_sonata_simulation_config_inputs()
        self._add_sonata_simulation_config_reports(db_client)
        self._add_sonata_simulation_config_manipulations()
        self._resolve_neuron_sets_and_write_simulation_node_sets_file()
        self._write_materialized_compartment_sets_file()
        self._update_simulation_number_neurons(db_client)
        self._write_simulation_config_to_file()
        self._save_generated_simulation_assets_to_entity(db_client)
