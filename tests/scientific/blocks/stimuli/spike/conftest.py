from pathlib import Path

import obi_one as obi

from tests.utils import CIRCUIT_DIR

STIM_CIRCUIT = obi.Circuit(
    name="N_10__top_nodes_dim6",
    path=str(CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"),
)


def make_validated_stimulus(
    source_ns,
    target_ns,
    stim_class,
    timestamps=None,
    circuit_list=None,
    sim_length=5000.0,
    **stim_kwargs,
):
    """Build a scan config, validate it, and return (validated_stim, circuit, source_pop).

    This wires up all block references so .block resolution works.
    """
    sc = obi.CircuitSimulationScanConfig.empty_config()
    sc.set(obi.Info(campaign_name="Test", campaign_description="Test"), name="info")

    sc.add(source_ns, name="source")
    sc.add(target_ns, name="target")

    ts_ref = None
    if timestamps is not None:
        sc.add(timestamps, name="ts")
        ts_ref = timestamps.ref

    stim = stim_class(
        source_neuron_set=source_ns.ref,
        targeted_neuron_set=target_ns.ref,
        timestamps=ts_ref,
        **stim_kwargs,
    )
    sc.add(stim, name="stim")

    if circuit_list is None:
        circuit_list = [STIM_CIRCUIT]

    init = obi.CircuitSimulationScanConfig.Initialize(
        circuit=circuit_list,
        node_set=target_ns.ref,
        simulation_length=sim_length,
    )
    sc.set(init, name="initialize")

    # Add a dummy recording so validation passes
    rec = obi.TimeWindowSomaVoltageRecording(
        neuron_set=target_ns.ref,
        start_time=0.0,
        end_time=sim_length,
    )
    sc.add(rec, name="rec")

    validated = sc.validated_config()
    return validated


def generate_spikes_for_stim(validated_config, tmp_path: Path):
    """Generate spike files for all stimuli in a validated config.

    Returns (stim, circuit, source_pop) for the first stimulus.
    """
    # initialize.circuit can be a list; use the first one
    circuit = validated_config.initialize.circuit
    if isinstance(circuit, list):
        circuit = circuit[0]
    pop = circuit.default_population_name

    for stim in validated_config.stimuli.values():
        source_neuron_set = validated_config.neuron_sets[stim.source_neuron_set.block_name]
        timestamps = validated_config.timestamps[stim.timestamps.block_name]
        stim.generate_spikes(
            circuit,
            tmp_path,
            timestamps=timestamps,
            source_neuron_set=source_neuron_set,
            source_node_population=pop,
        )

    first_name = next(iter(validated_config.stimuli))
    first_stim = validated_config.stimuli[first_name]
    source_ns = validated_config.neuron_sets[first_stim.source_neuron_set.block_name]
    source_pop = source_ns.get_population(pop)
    return first_stim, circuit, source_pop
