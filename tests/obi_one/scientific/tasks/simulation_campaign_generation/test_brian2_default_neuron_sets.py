"""A Brian2 simulation defaults the simulation to all point neurons and a stimulus to `sugar`.

An untargeted Brian2 Poisson stimulus drives the `sugar` gustatory receptor neurons, while the
simulation itself runs every point neuron. The two are separate defaults; regressions here
(e.g. the stimulus inheriting the simulation-wide default and tripping its 100-neuron limit, or
the simulation target being mislabelled "Sugar…") are what this guards against.
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

SIM_DEFAULT = "Default: All Point Neurons"
STIMULUS_DEFAULT = "Default: Sugar gustatory receptor neurons"


def _generate(tmp_path: Path) -> tuple[dict, dict]:
    """Generate a Brian2 campaign with one untargeted stimulus; return (sim config, node sets)."""
    sim_conf = obi.Brian2CircuitSimulationScanConfig.empty_config()
    sim_conf.set(obi.Info(campaign_name="T", campaign_description="T"), name="info")

    # No neuron_set and no initialize.node_set: both fall back to their defaults.
    sim_conf.add(Brian2DirectPoissonStimulus(), name="DirectPoisson")
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


def test_untargeted_brian2_stimulus_defaults_to_sugar_and_simulation_to_all_point(tmp_path):
    sim_config, node_sets = _generate(tmp_path)

    # The simulation targets all point neurons, named for what it is -- not "Sugar…".
    assert sim_config["node_set"] == SIM_DEFAULT
    assert node_sets[SIM_DEFAULT]["node_id"] == [0, 1, 2]

    # The untargeted stimulus targets the sugar node set -- a strict subset, not the whole
    # circuit -- so it stays under the block's 100-neuron limit rather than raising.
    assert sim_config["inputs"]["DirectPoisson"]["node_set"] == STIMULUS_DEFAULT
    assert node_sets[STIMULUS_DEFAULT]["node_id"] == [0, 1]

    # The two defaults are genuinely different sets.
    assert node_sets[SIM_DEFAULT]["node_id"] != node_sets[STIMULUS_DEFAULT]["node_id"]
