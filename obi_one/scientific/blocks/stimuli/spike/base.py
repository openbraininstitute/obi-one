from abc import abstractmethod
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
from pydantic import Field, NonNegativeFloat, PrivateAttr

from obi_one.core.exception import OBIONEError
from obi_one.scientific.blocks.stimuli.stimulus import (
    StimulusWithTimestamps,
    _TIMESTAMPS_OFFSET_FIELD,
)
from obi_one.scientific.blocks.timestamps.single import SingleTimestamp
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    resolve_neuron_set_ref_to_node_set,
)
from obi_one.scientific.unions.unions_timestamps import (
    TimestampsReference,
    resolve_timestamps_ref_to_timestamps_block,
)


class SpikeStimulus(StimulusWithTimestamps):
    _module: str = "synapse_replay"
    _input_type: str = "spikes"
    _spike_file: Path | None = None
    _simulation_length: float | None = None
    source_neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Source)",
        description="Source neuron set to simulate",
        json_schema_extra={
            "ui_element": "reference",
            "reference_type": NeuronSetReference.__name__,
            "supports_virtual": True,
        },
    )

    targeted_neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Target)",
        description="Target neuron set to simulate",
        json_schema_extra={
            "ui_element": "reference",
            "reference_type": NeuronSetReference.__name__,
            "supports_virtual": True,
        },
    )

    timestamp_offset: float | list[float] = _TIMESTAMPS_OFFSET_FIELD

    def config(
        self,
        circuit: Circuit,
        population: str | None = None,
        default_node_set: str = "All",
        default_timestamps: TimestampsReference = None,
    ) -> dict:
        self._default_node_set = default_node_set

        if (self.targeted_neuron_set is not None) and (
            self.targeted_neuron_set.block.population_type(circuit, population) != "biophysical"
        ):
            msg = (
                f"Target Neuron Set '{self.targeted_neuron_set.block.block_name}' for "
                f"{self.__class__.__name__}: '{self.block_name}' should be biophysical!"
            )
            raise OBIONEError(msg)

        if default_timestamps is None:
            default_timestamps = SingleTimestamp(start_time=0.0)
        self._default_timestamps = default_timestamps


        # HERE
        source_node_set = resolve_neuron_set_ref_to_node_set(
            self.targeted_neuron_set, self._default_node_set
        )

        target_node_set = resolve_neuron_set_ref_to_node_set(
            self.targeted_neuron_set, self._default_node_set
        )


        return self._generate_config()

    def _generate_config(self) -> dict:
        if self._spike_file is None:
            msg = "Spike file must be set before generating SONATA config"
            raise ValueError(msg)
        if self._simulation_length is None:
            msg = "Simulation length must be set before generating SONATA config"
            " component for SpikeStimulus."
            raise ValueError(msg)

        sonata_config = {}
        sonata_config[self.block_name] = {
            "delay": 0.0,  # If present, the simulation filters out those times before the delay
            "duration": self._simulation_length,
            "node_set": resolve_neuron_set_ref_to_node_set(
                self.targeted_neuron_set, self._default_node_set
            ),
            "module": self._module,
            "input_type": self._input_type,
            "spike_file": str(self._spike_file),  # os.path.relpath #
        }

        return sonata_config

    def generate_spikes(
        self,
        circuit: Circuit,
        spike_file_path: Path,
        simulation_length: NonNegativeFloat,
        source_node_population: str | None = None,
    ) -> None:
        msg = "Subclasses should implement this method."
        raise NotImplementedError(msg)

    @staticmethod
    def write_spike_file(
        gid_spike_map: dict, spike_file: Path, source_node_population: str | None = None
    ) -> None:
        """Writes SONATA output spike trains to file.

        Spike file format specs: https://github.com/AllenInstitute/sonata/blob/master/docs/SONATA_DEVELOPER_GUIDE.md#spike-file
        """
        # IMPORTANT: Convert SONATA node IDs (0-based) to NEURON cell IDs (1-based)!!
        # (See https://sonata-extension.readthedocs.io/en/latest/blueconfig-projection-example.html#dat-spike-files)
        gid_spike_map = {k + 1: v for k, v in gid_spike_map.items()}

        out_path = Path(spike_file).parent
        if not out_path.exists():
            out_path.mkdir(parents=True)

        time_list = []
        gid_list = []
        for gid, spike_times in gid_spike_map.items():
            if spike_times is not None:
                for t in spike_times:
                    time_list.append(t)
                    gid_list.append(gid)
        spike_df = pd.DataFrame(np.array([time_list, gid_list]).T, columns=["t", "gid"])
        spike_df = spike_df.astype({"t": float, "gid": int})
        """
        # plt.figure()
        # plt.scatter(spike_df["t"], spike_df["gid"], s=1)
        # plt.savefig("/Users/james/Documents/obi/code/obi-one/obi_one/scientific/spike_raster.png")
        # plt.close()
        """
        spike_df_sorted = spike_df.sort_values(by=["t", "gid"])  # Sort by time
        with h5py.File(spike_file, "w") as f:
            pop = f.create_group(f"/spikes/{source_node_population}")
            ts = pop.create_dataset(
                "timestamps", data=spike_df_sorted["t"].values, dtype=np.float64
            )
            pop.create_dataset("node_ids", data=spike_df_sorted["gid"].values, dtype=np.uint64)
            ts.attrs["units"] = "ms"
