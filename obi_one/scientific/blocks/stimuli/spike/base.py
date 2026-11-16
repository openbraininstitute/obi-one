from abc import abstractmethod
from pathlib import Path

import h5py
import numpy as np
from pydantic import Field, NonNegativeFloat

from obi_one.core.exception import ConfigValidationError
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.neuron_sets.base import NeuronSet
from obi_one.scientific.blocks.stimuli.stimulus import (
    _TIMESTAMPS_OFFSET_FIELD,
    StimulusWithTimestamps,
)
from obi_one.scientific.blocks.timestamps.single import SingleTimestamp
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.constants import SONATA
from obi_one.scientific.unions_and_references.combined_neuron_sets import (
    ALL_NEURON_SETS_REFERENCE_TYPES,
    ALL_NEURON_SETS_REFERENCE_UNION,
    NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
    NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION,
    resolve_neuron_set_ref_to_neuron_set,
)
from obi_one.scientific.unions_and_references.reference_tags import ReferenceTag
from obi_one.scientific.unions_and_references.timestamps import (
    TimestampsReference,
)


class SpikeStimulus(StimulusWithTimestamps):
    source_neuron_set: ALL_NEURON_SETS_REFERENCE_UNION | None = Field(  # ty:ignore[no-matching-overload]
        default=None,
        title="Neuron set (source)",
        description="Source neuron set to simulate",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: ALL_NEURON_SETS_REFERENCE_TYPES,
            SchemaKey.REFERENCE_TAG: ReferenceTag.SPIKE_STIMULUS_SOURCE,
            SchemaKey.PARAMETER_ORDER_PRIORITY: 100,
        },
    )

    targeted_neuron_set: NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION | None = Field(  # ty:ignore[no-matching-overload]
        default=None,
        title="Neuron set (target)",
        description="Target neuron set to simulate",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
            SchemaKey.PARAMETER_ORDER_PRIORITY: 99,
        },
    )

    timestamp_offset: float | list[float] = _TIMESTAMPS_OFFSET_FIELD

    def _single_timestamp_stimulus_config(self, stim_dict: dict) -> dict:  # ruff: ignore[no-self-use]
        return stim_dict

    def config(
        self,
        circuit: Circuit,
        sonata_simulation_config_directory: Path,
        simulation_length: NonNegativeFloat,
        default_timestamps: TimestampsReference | None = None,
        default_source_neuron_set_reference: ALL_NEURON_SETS_REFERENCE_UNION | None = None,
        default_target_neuron_set_reference: ALL_NEURON_SETS_REFERENCE_UNION | None = None,
    ) -> dict:
        if default_timestamps is None:
            self._default_timestamps = SingleTimestamp(start_time=0.0)  # ty:ignore[invalid-assignment]
        else:
            self._default_timestamps = default_timestamps

        source_neuron_set = resolve_neuron_set_ref_to_neuron_set(
            self.source_neuron_set, default_source_neuron_set_reference
        )

        target_neuron_set = resolve_neuron_set_ref_to_neuron_set(
            self.targeted_neuron_set, default_target_neuron_set_reference
        )

        if (
            not target_neuron_set.has_biophysical_neurons(circuit)  # ty:ignore[unresolved-attribute]
            and not target_neuron_set.has_point_neurons(circuit)  # ty:ignore[unresolved-attribute]
        ):
            msg = "Target Neuron Set of Spike Stimulus must be biophysical or point."
            raise ConfigValidationError(msg)

        # Connectivity is only stored in the edge files, which may not have been staged.
        if circuit.has_staged_edges:
            self._validate_source_connects_to_target(
                circuit=circuit,
                source_neuron_set=source_neuron_set,  # ty:ignore[invalid-argument-type]
                target_neuron_set=target_neuron_set,  # ty:ignore[invalid-argument-type]
            )
        spike_file_relative_path = self.generate_spikes(
            circuit=circuit,
            spike_file_directory=sonata_simulation_config_directory,
            source_neuron_set=source_neuron_set,  # ty:ignore[invalid-argument-type]
        )

        sonata_config = self._generate_config(
            spike_file_relative_path=spike_file_relative_path,
            sonata_simulation_config_directory=sonata_simulation_config_directory,
            simulation_length=simulation_length,
            target_neuron_set=target_neuron_set,  # ty:ignore[invalid-argument-type]
        )

        return sonata_config

    @staticmethod
    def _validate_source_connects_to_target(
        circuit: Circuit,
        source_neuron_set: NeuronSet,
        target_neuron_set: NeuronSet,
    ) -> None:
        """Check that the source population(s) have edges to the target population(s).

        Spikes are replayed through those edges, so a source without any has nothing to drive.
        """
        source_populations = source_neuron_set.get_populations(circuit)
        target_populations = set(target_neuron_set.get_populations(circuit))
        edges = circuit.sonata_circuit.edges
        connected = {
            edges[name].source.name
            for name in edges.population_names
            if edges[name].target.name in target_populations
        }
        unconnected = [pop for pop in source_populations if pop not in connected]
        if unconnected:
            msg = (
                f"Spike stimulus source population(s) {unconnected} have no edges to the "
                f"target population(s) {sorted(target_populations)}, so the spikes cannot be "
                "replayed. Choose a source neuron set whose population is connected to the "
                f"target (populations with edges to the target: {sorted(connected)})."
            )
            raise ConfigValidationError(msg)

    def generate_spikes(
        self,
        circuit: Circuit,
        spike_file_directory: Path,
        source_neuron_set: NeuronSet,
    ) -> Path:
        populations = source_neuron_set.get_populations(circuit)
        if not populations:
            msg = "Spike stimulus source neuron set has no population."
            raise ConfigValidationError(msg)
        neuron_ids = source_neuron_set.get_neuron_ids(circuit)

        # Generate spikes
        if len(populations) == 1:
            (population,) = populations
            spikes_by_population = {
                population: self.generate_spikes_by_gid(source_gids=neuron_ids[population])
            }
        else:
            spikes_by_population = self._generate_spikes_by_population(
                {population: neuron_ids[population] for population in populations}
            )

        # Write spikes to file
        spike_file = f"{self.block_name}_spikes.h5"
        spike_file_relative_path = Path(spike_file)
        spike_file_absolute_path = spike_file_directory / spike_file
        self.write_spike_file(spikes_by_population, spike_file_absolute_path)

        return spike_file_relative_path

    def _generate_spikes_by_population(
        self, gids_by_population: dict[str, list[int]]
    ) -> dict[str, dict[int, list[float]]]:
        """Spikes in one pass, so populations get independent spikes despite shared node IDs."""
        neurons = [(pop, gid) for pop, gids in gids_by_population.items() for gid in gids]
        spikes_by_index = self.generate_spikes_by_gid(source_gids=list(range(len(neurons))))
        spikes_by_population: dict[str, dict[int, list[float]]] = {
            pop: {} for pop in gids_by_population
        }
        for index, spike_times in spikes_by_index.items():
            pop, gid = neurons[index]
            spikes_by_population[pop][gid] = spike_times
        return spikes_by_population

    def _generate_config(
        self,
        spike_file_relative_path: Path,
        sonata_simulation_config_directory: Path,
        simulation_length: NonNegativeFloat,
        target_neuron_set: NeuronSet,
    ) -> dict:  # ty:ignore[invalid-method-override]
        spike_file_absolute_path = (
            sonata_simulation_config_directory / spike_file_relative_path
        ).resolve()
        if not spike_file_absolute_path.exists():
            msg = f"Spike file not found: {spike_file_absolute_path}"
            raise FileNotFoundError(msg)

        sonata_config = {}
        sonata_config[self.block_name] = {
            SONATA.DELAY: 0.0,  # If present, the simulation filters times before the delay
            SONATA.DURATION: simulation_length,
            SONATA.NODE_SET: target_neuron_set.block_name,
            SONATA.MODULE: SONATA.SPIKE_STIMULUS_MODULE,
            SONATA.INPUT_TYPE: SONATA.SPIKE_STIMULUS_INPUT_TYPE,
            SONATA.SPIKE_FILE: str(spike_file_relative_path),
        }

        return sonata_config

    @abstractmethod
    def generate_spikes_by_gid(self, source_gids: list[int]) -> dict[int, list[float]]:
        pass

    @staticmethod
    def write_spike_file(
        spikes_by_population: dict[str, dict[int, list[float]]],
        spike_file: Path,
    ) -> None:
        """Writes SONATA output spike trains to file.

        Spike file format specs: https://github.com/AllenInstitute/sonata/blob/master/docs/SONATA_DEVELOPER_GUIDE.md#spike-file
        """
        out_path = Path(spike_file).parent
        if not out_path.exists():
            out_path.mkdir(parents=True)

        with h5py.File(spike_file, "w") as f:
            for population, spikes_by_gid in spikes_by_population.items():
                times = []
                gids = []
                for gid, spike_times in spikes_by_gid.items():
                    times.extend(spike_times)
                    gids.extend([gid] * len(spike_times))

                sort_idx = np.argsort(times, kind="stable")
                sorted_times = np.array(times, dtype=np.float64)[sort_idx]
                sorted_gids = np.array(gids, dtype=np.uint64)[sort_idx]

                pop = f.create_group(f"/spikes/{population}")
                ts = pop.create_dataset("timestamps", data=sorted_times)
                pop.create_dataset("node_ids", data=sorted_gids)
                ts.attrs["units"] = "ms"
