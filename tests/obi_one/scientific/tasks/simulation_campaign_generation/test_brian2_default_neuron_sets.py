"""A Brian2 simulation defaults both its simulation and its stimuli to all point neurons.

An untargeted Brian2 Poisson stimulus drives whatever the simulation runs, as in every other
config family. This is the end-to-end check that the one default reaches both roles and that the
node set it names is actually written, rather than a role picking up a name nothing defines.
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

POINT_DEFAULT = "Default: All Point Neurons"


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


def test_untargeted_brian2_stimulus_and_simulation_both_default_to_all_point(tmp_path):
    sim_config, node_sets = _generate(tmp_path)

    # The simulation targets all point neurons, named for what it is.
    assert sim_config["node_set"] == POINT_DEFAULT
    assert node_sets[POINT_DEFAULT]["node_id"] == [0, 1, 2]

    # The untargeted stimulus resolves to that same set rather than one of its own.
    assert sim_config["inputs"]["DirectPoisson"]["node_set"] == POINT_DEFAULT

    # One default node set is injected alongside the circuit's own, not one per role.
    assert [name for name in node_sets if name.startswith("Default: ")] == [POINT_DEFAULT]
