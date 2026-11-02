"""The closed loop on an 8-neuron circuit with a body interface and the flygym body.

flygym is not an obi-one dependency (the closed-loop launch job installs it), so this test only
runs where it is installed.
"""

import json

import h5py
import numpy as np
import pytest

pytest.importorskip("flygym")

from obi_one.scientific.library.simulation.neuromechfly import (
    simulate_neuromechfly as test_module,
)

from tests.obi_one.scientific.library.simulation.embodied_circuit import (
    POPULATION,
    write_embodied_circuit,
)

DURATION_MS = 200.0
# Where the left front tibia sits in a replay frame's joints: the left front leg's chain holds the
# coxa's three joints and the femur's two before it.
LF_TIBIA = 5


def write_simulation(tmp_path, *, circuit=None, tstop=DURATION_MS, **section_updates):
    circuit_config = circuit or write_embodied_circuit(tmp_path / "circuit")
    section = {"arena": {"odour_sources": [[3.0, 2.0]]}} | section_updates
    config = {
        "run": {"tstop": tstop, "dt": 0.1, "random_seed": 1},
        "target_simulator": "Brian2",
        "network": str(circuit_config),
        "conditions": {"v_init": -52.0},
        "output": {"output_dir": str(tmp_path / "output"), "spikes_file": "spikes.h5"},
        "neuromechfly": section,
    }
    path = tmp_path / "simulation_config.json"
    path.write_text(json.dumps(config))
    return path


def spike_counts(tmp_path) -> np.ndarray:
    with h5py.File(tmp_path / "output/spikes.h5") as h5:
        ids = h5[f"spikes/{POPULATION}/node_ids"][:]
    return np.bincount(ids.astype(np.int64), minlength=8)


class TestClosedLoop:
    def test_episode(self, tmp_path):
        summary = test_module.run_closed_loop(write_simulation(tmp_path))

        assert summary["episode_s"] == pytest.approx(DURATION_MS / 1000)
        assert not summary["physics_fault"]
        assert summary["sources_total"] == 1
        counts = spike_counts(tmp_path)
        # 3.6 mm from the source, the yeasty receptors fire far above their 2 Hz at rest, the left
        # one firing the tibia flexor's motor neuron (which resets between inputs, so misses some);
        # nothing drives the extensor's.
        assert counts[0] > 10
        assert counts[1] > 10
        assert counts[4] > 5
        assert counts[5] == 0
        with h5py.File(tmp_path / "output/spikes.h5") as h5:
            trajectory = h5["neuromechfly"]
            # a row as the body starts and one every 10 ms
            assert len(trajectory["x"]) == DURATION_MS / 10 + 1
            assert json.loads(trajectory.attrs["summary"]) == summary
        replay = json.loads((tmp_path / "output/neuromechfly_replay.json").read_text())
        assert replay["start_ms"] == 0
        assert len(replay["frames"]["thorax"]) == DURATION_MS / 10 + 1
        assert (tmp_path / "output/neuromechfly_trajectory.csv").exists()

    def test_the_odour_reaches_the_legs_only_through_the_circuit(self, tmp_path):
        """A yeasty source drives the left receptor, its motor neuron and the tibia flexor; a
        fruity one, which no receptor of this circuit is tuned to, leaves the tibia at rest.
        """
        tibia = {}
        for odour in ("yeasty_volatile", "fruity_volatile"):
            run = tmp_path / odour
            run.mkdir()
            arena = {"odour_sources": [[3.0, 2.0]], "odour_classes": [odour]}
            test_module.run_closed_loop(write_simulation(run, arena=arena))
            replay = json.loads((run / "output/neuromechfly_replay.json").read_text())
            tibia[odour] = np.mean([joints[LF_TIBIA] for joints in replay["frames"]["joints"][-5:]])
            if odour == "fruity_volatile":
                assert spike_counts(run)[4] <= 2
        assert tibia["yeasty_volatile"] > tibia["fruity_volatile"] + 0.3

    def test_pushes_and_leg_overrides_mark_the_rows_they_act_in(self, tmp_path):
        simulation = write_simulation(
            tmp_path,
            forces=[{"segment": "thorax", "force": [0, 3, 0], "start": 30, "duration": 20}],
            leg_overrides=[{"leg": "left_middle", "mode": "lift", "start": 120, "duration": 25}],
        )
        summary = test_module.run_closed_loop(simulation)

        assert not summary["physics_fault"]
        with h5py.File(tmp_path / "output/spikes.h5") as h5:
            perturbed = h5["neuromechfly/perturbed"][:].tolist()
        # rows every 10 ms, each saying whether anything acted since the one before
        acted = [index for index, flag in enumerate(perturbed) if flag]
        assert acted == [4, 5, 13, 14, 15]

    def test_a_circuit_without_a_body_interface_is_refused(self, tmp_path):
        circuit = write_embodied_circuit(tmp_path / "circuit", body_interface=False)
        with pytest.raises(ValueError, match="no body interface"):
            test_module.run_closed_loop(write_simulation(tmp_path, circuit=circuit))

    def test_an_interface_of_hand_made_rules_is_refused(self, tmp_path):
        circuit = write_embodied_circuit(
            tmp_path / "circuit", interface={"body": "NeuroMechFly", "steering": {}}
        )
        with pytest.raises(ValueError, match="version 1"):
            test_module.run_closed_loop(write_simulation(tmp_path, circuit=circuit))

    def test_a_config_without_the_section_is_refused(self, tmp_path):
        path = tmp_path / "simulation_config.json"
        path.write_text(json.dumps({"run": {"tstop": 1, "dt": 0.1}}))
        with pytest.raises(ValueError, match="no 'neuromechfly' section"):
            test_module.read_closed_loop_config(path)
