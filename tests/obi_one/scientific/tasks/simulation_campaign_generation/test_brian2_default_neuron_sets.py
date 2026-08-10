"""A Brian2 simulation resolves every untargeted block to one default neuron set.

The simulation itself, recordings, stimuli and manipulations all fall back to
``Default: All Point Neurons``, which the generation task injects into ``neuron_sets``. The Direct
Poisson stimulus used to be an exception that drove the smaller ``sugar`` set instead; this guards
against that split coming back, and against the one default being written more than once.
"""

import json
from pathlib import Path

import obi_one as obi
from obi_one.scientific.blocks.stimuli.brian2_poisson import Brian2DirectPoissonStimulus

# The synthetic FlyWire-style point circuit: one `brian2_point` population `drosophila` (3
# neurons), with a `sugar` node set covering neurons 0 and 1.
CIRCUIT_CONFIG = (
    Path(__file__).parents[2] / "library" / "simulation" / "data" / "circuit_config.json"
)

DEFAULT = "Default: All Point Neurons"


def _generate(tmp_path: Path) -> tuple[dict, dict]:
    """Generate a Brian2 campaign of untargeted blocks; return (sim config, node sets)."""
    sim_conf = obi.Brian2CircuitSimulationScanConfig.empty_config()
    sim_conf.set(obi.Info(campaign_name="T", campaign_description="T"), name="info")

    # Nothing names a neuron set, and neither does initialize.node_set: all fall back.
    sim_conf.add(Brian2DirectPoissonStimulus(), name="DirectPoisson")
    sim_conf.add(obi.ConstantCurrentClampSomaticStimulus(), name="Clamp")
    sim_conf.add(obi.SimulationDtSomaVoltageRecording(), name="Voltage")
    sim_conf.add(obi.DisconnectSynapticManipulation(), name="Disconnect")
    sim_conf.set(
        obi.Brian2CircuitSimulationScanConfig.Initialize(
            circuit=obi.Circuit(name="drosophila", path=str(CIRCUIT_CONFIG)),
            simulation_length=100.0,
        ),
        name="initialize",
    )

    scan = obi.GridScanGenerationTask(
        form=sim_conf.validated_config(),
        output_root=tmp_path / "scan",
        coordinate_directory_option="ZERO_INDEX",
    )
    scan.execute()
    obi.run_tasks_for_generated_scan(scan)

    out = tmp_path / "scan" / "0"
    sim_config = json.loads((out / "simulation_config.json").read_text())
    node_sets = json.loads((out / "node_sets.json").read_text())
    return sim_config, node_sets


def test_every_untargeted_block_resolves_to_the_one_default(tmp_path):
    sim_config, node_sets = _generate(tmp_path)

    # The simulation, both stimuli, the recording and the manipulation all name the same set.
    assert sim_config["node_set"] == DEFAULT
    assert sim_config["inputs"]["DirectPoisson"]["node_set"] == DEFAULT
    assert sim_config["inputs"]["Clamp_0"]["node_set"] == DEFAULT
    assert sim_config["reports"]["Voltage"]["cells"] == DEFAULT
    (override,) = sim_config["connection_overrides"]
    assert override["source"] == override["target"] == DEFAULT

    # And it is the whole point population, injected exactly once.
    assert node_sets[DEFAULT]["node_id"] == [0, 1, 2]
    assert sum(name.startswith("Default:") for name in node_sets) == 1
