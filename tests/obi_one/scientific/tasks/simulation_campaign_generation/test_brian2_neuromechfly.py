"""The Brian2 NeuroMechFly campaign writes the experiment into the SONATA simulation config.

Which neurons the body drives and reads is the circuit's body interface, so the config names none.
"""

import json
from pathlib import Path

import pytest

from obi_one.core.exception import ConfigValidationError
from obi_one.core.info import Info
from obi_one.core.run_tasks import run_tasks_for_generated_scan
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.scientific.blocks.neuromechfly.closed_loop import (
    BodyForce,
    LegOverride,
    OdourArena,
    OdourSource,
    Wall,
)
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.simulation.neuromechfly.config import ClosedLoopConfig
from obi_one.scientific.tasks.generate_simulations.config.brian2.brian2_neuromechfly import (
    Brian2NeuroMechFlySimulationScanConfig,
)

from tests.obi_one.scientific.library.simulation.embodied_circuit import write_embodied_circuit

EPISODE = 2000.0


def _generate(
    tmp_path: Path,
    *,
    sources=((25.0, 0.0), (30.0, 5.0)),
    body_interface: bool = True,
    perturb: bool = False,
) -> list[dict]:
    circuit_config = write_embodied_circuit(tmp_path / "circuit", body_interface=body_interface)
    sim_conf = Brian2NeuroMechFlySimulationScanConfig.empty_config()
    sim_conf.set(Info(campaign_name="T", campaign_description="T"), name="info")
    sim_conf.set(OdourArena(start_heading=[0.0, 30.0]), name="arena")
    odours = ("yeasty_volatile", "carbon_dioxide_volatile")
    for index, (x, y) in enumerate(sources):
        sim_conf.add(OdourSource(x=x, y=y, odour=odours[index % 2]), name=f"Source {index}")
    sim_conf.add(Wall(), name="Wall")
    if perturb:
        sim_conf.add(
            BodyForce(segment="head", force_y=-3.0, force_z=1.0, start=500.0, duration=100.0),
            name="Push",
        )
        sim_conf.add(
            LegOverride(leg="right_hind", mode="swing", joint="femur", amplitude=15.0),
            name="Swing",
        )
    sim_conf.set(
        Brian2NeuroMechFlySimulationScanConfig.Initialize(
            circuit=Circuit(name="embodied", path=str(circuit_config)),
            simulation_length=EPISODE,
        ),
        name="initialize",
    )
    scan = GridScanGenerationTask(
        form=sim_conf.validated_config(),
        output_root=tmp_path / "scan",
        coordinate_directory_option="ZERO_INDEX",
    )
    scan.execute()
    run_tasks_for_generated_scan(scan)
    return [
        json.loads(path.read_text())
        for path in sorted((tmp_path / "scan").glob("*/simulation_config.json"))
    ]


class TestBrian2NeuroMechFlyCampaign:
    def test_the_closed_loop_section(self, tmp_path):
        configs = _generate(tmp_path)

        assert len(configs) == 2  # one per start heading
        config = configs[1]
        assert config["target_simulator"] == "Brian2"
        assert config["run"]["dt"] == pytest.approx(0.1)
        # the network and the body run together from the start
        assert config["run"]["tstop"] == pytest.approx(EPISODE)
        loop = ClosedLoopConfig.model_validate(config["neuromechfly"])
        assert loop.arena.odour_sources == ((25.0, 0.0), (30.0, 5.0))
        assert loop.arena.odour_classes == ("yeasty_volatile", "carbon_dioxide_volatile")
        assert loop.arena.walls == ((15.0, -4.0, 15.0, 6.0),)
        assert loop.arena.start_heading == pytest.approx(30.0)
        assert loop.coupling_step == pytest.approx(1.0)

    def test_pushes_and_leg_overrides(self, tmp_path):
        loop = ClosedLoopConfig.model_validate(_generate(tmp_path, perturb=True)[0]["neuromechfly"])

        (push,) = loop.forces
        assert (push.segment, push.frame) == ("head", "body")
        assert push.force == (0.0, -3.0, 1.0)
        assert (push.start, push.duration, push.frequency) == (500.0, 100.0, 0.0)
        (swing,) = loop.leg_overrides
        assert (swing.leg, swing.mode, swing.joint) == ("right_hind", "swing", "femur")
        assert (swing.amplitude, swing.frequency) == (15.0, 5.0)
        plain = _generate(tmp_path / "plain")[0]["neuromechfly"]
        assert ClosedLoopConfig.model_validate(plain).forces == ()

    def test_an_arena_needs_a_source(self, tmp_path):
        with pytest.raises(ConfigValidationError, match="at least one Odour Source"):
            _generate(tmp_path, sources=())

    def test_the_circuit_needs_a_body_interface(self, tmp_path):
        with pytest.raises(ConfigValidationError, match="not connected to a body"):
            _generate(tmp_path, body_interface=False)

    def test_episodes_are_capped(self, tmp_path):
        circuit_config = write_embodied_circuit(tmp_path)
        with pytest.raises(ValueError, match="30000"):
            Brian2NeuroMechFlySimulationScanConfig.Initialize(
                circuit=Circuit(name="embodied", path=str(circuit_config)),
                simulation_length=30001.0,
            )
