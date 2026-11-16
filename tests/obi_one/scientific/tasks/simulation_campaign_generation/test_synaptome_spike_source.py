"""An unset spike source in a synaptome simulation replays from its virtual populations."""

import h5py

from obi_one.core.info import Info
from obi_one.core.run_tasks import run_tasks_for_generated_scan
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.scientific.blocks.stimuli.spike.poisson import PoissonSpikeStimulus
from obi_one.scientific.blocks.timestamps.regular import RegularTimestamps
from obi_one.scientific.library.memodel_circuit import MEModelWithSynapsesCircuit
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model_with_synapses import (  # ruff: ignore[line-too-long]
    MEModelWithSynapsesCircuitSimulationScanConfig,
)
from obi_one.scientific.unions_and_references.reference_tags import ReferenceTag

from tests.utils import SINGLE_NEURON_CIRCUIT_DIR

# One neuron whose only synapses come from the virtual populations POm and VPM.
SYNAPTOME_PATH = (
    SINGLE_NEURON_CIRCUIT_DIR / "SingleNeuronCircuit__top_nodes_dim6__IDX1" / "circuit_config.json"
)


def test_synaptome_form_defaults_the_spike_source_to_all_virtual_neurons():
    defaults = MEModelWithSynapsesCircuitSimulationScanConfig.model_json_schema()[
        "reference_tag_defaults"
    ]

    assert defaults[ReferenceTag.SPIKE_STIMULUS_SOURCE]["name"] == "Default: All Virtual Neurons"


def test_unset_source_replays_spikes_from_every_virtual_population(tmp_path):
    circuit = MEModelWithSynapsesCircuit(name="synaptome", path=str(SYNAPTOME_PATH))
    config = MEModelWithSynapsesCircuitSimulationScanConfig.empty_config()
    config.set(Info(campaign_name="Synaptome", campaign_description="x"), name="info")
    timestamps = RegularTimestamps(start_time=0.0, number_of_repetitions=1, interval=500.0)
    config.add(timestamps, name="Timestamps")
    config.add(
        PoissonSpikeStimulus(
            duration=200.0, timestamps=timestamps.ref, frequency=20.0, random_seed=0
        ),
        name="Poisson",
    )
    config.set(
        MEModelWithSynapsesCircuitSimulationScanConfig.Initialize(
            circuit=circuit, simulation_length=500.0
        ),
        name="initialize",
    )
    scan = GridScanGenerationTask(
        form=config.validated_config(),
        output_root=tmp_path,
        coordinate_directory_option="ZERO_INDEX",
    )
    scan.execute()
    run_tasks_for_generated_scan(scan)

    with h5py.File(tmp_path / "0" / "Poisson_spikes.h5", "r") as f:
        assert sorted(f["spikes"]) == ["POm", "VPM"]
        assert all(len(f[f"spikes/{pop}/node_ids"]) > 0 for pop in ("POm", "VPM"))
