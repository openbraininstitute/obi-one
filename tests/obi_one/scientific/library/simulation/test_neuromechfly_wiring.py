"""The senses and muscles of the body interface, on the 8-neuron test circuit.

The wiring reads the body's state, so these tests need flygym, which is not an obi-one dependency
(the closed-loop launch job installs it): they only run where it is installed.
"""

import bluepysnap
import numpy as np
import pytest

pytest.importorskip("flygym")

from obi_one.scientific.library.simulation.neuromechfly.body import BodyState
from obi_one.scientific.library.simulation.neuromechfly.interface import (
    JOINTS,
    BodyInterface,
    read_body_interface,
)
from obi_one.scientific.library.simulation.neuromechfly.wiring import Muscles, Senses

from tests.obi_one.scientific.library.simulation.embodied_circuit import (
    POPULATION,
    write_embodied_circuit,
)

LEFT_ANTENNA = 2


def wired(tmp_path, interface: dict | None = None):
    config = write_embodied_circuit(tmp_path / "circuit", interface=interface)
    circuit = bluepysnap.Circuit(config)
    return circuit.nodes[POPULATION], read_body_interface(circuit, config)


def state(**changes) -> BodyState:
    still = np.zeros((6, 7))
    defaults = {
        "angles": still,
        "velocities": still,
        "accelerations": still,
        "rest": still,
        "load": np.zeros(6),
        "load_change": np.zeros(6),
        "odour_classes": ("yeasty_volatile",),
        "odour": np.zeros((1, 4)),
    }
    return BodyState(**(defaults | changes))


def rates_by_neuron(senses: Senses, body: BodyState) -> dict[int, float]:
    return dict(zip(senses.ids.tolist(), senses.rates(body).tolist(), strict=True))


class TestSenses:
    def test_each_receptor_reads_its_own_class_at_its_own_organ(self, tmp_path):
        population, interface = wired(tmp_path)
        senses = Senses(population, interface)
        response = interface.sensing.odour
        odour = np.zeros((1, 4))
        odour[0, LEFT_ANTENNA] = response.half_intensity

        rates = rates_by_neuron(senses, state(odour=odour))

        assert rates[0] == pytest.approx((response.spontaneous + response.maximum) / 2)
        assert rates[1] == pytest.approx(response.spontaneous)

    def test_an_odour_of_another_class_leaves_the_receptors_at_rest(self, tmp_path):
        population, interface = wired(tmp_path)
        senses = Senses(population, interface)

        rates = rates_by_neuron(
            senses, state(odour_classes=("fruity_volatile",), odour=np.ones((1, 4)))
        )

        assert rates[0] == pytest.approx(interface.sensing.odour.spontaneous)

    def test_a_claw_neuron_fires_most_at_its_preferred_angle(self, tmp_path):
        population, interface = wired(tmp_path)
        senses = Senses(population, interface)
        angles = np.zeros((6, 7))
        response = interface.sensing.claw

        angles[0, JOINTS.index("Tibia")] = 1.64
        assert rates_by_neuron(senses, state(angles=angles))[2] == pytest.approx(response.maximum)
        angles[0, JOINTS.index("Tibia")] = 1.64 + 1.0
        assert rates_by_neuron(senses, state(angles=angles))[2] < response.spontaneous + 1

    def test_bristles_fire_as_contact_changes_not_while_it_holds(self, tmp_path):
        population, interface = wired(tmp_path)
        senses = Senses(population, interface)
        response = interface.sensing.touch
        load, change = np.zeros(6), np.zeros(6)

        load[0] = 5.0
        assert rates_by_neuron(senses, state(load=load))[3] == pytest.approx(response.spontaneous)
        change[0] = -response.saturation_change
        rates = rates_by_neuron(senses, state(load=load, load_change=change))
        assert rates[3] == pytest.approx(response.maximum)

    def test_with_nothing_to_sense_the_neurons_fire_at_rest(self, tmp_path):
        population, interface = wired(tmp_path)
        senses = Senses(population, interface)
        far_from_preference = np.full((6, 7), -2.0)

        rates = senses.rates(state(angles=far_from_preference))

        np.testing.assert_allclose(rates, senses.spontaneous, atol=1e-6)


class TestMuscles:
    def test_each_motor_neuron_feeds_its_own_muscle(self, tmp_path):
        population, interface = wired(tmp_path)
        muscles = Muscles(population, interface)

        assert muscles.names == [
            "LF/long_tendon_muscle",
            "LF/tibia_extensor_muscle",
            "LF/tibia_flexor_muscle",
        ]
        np.testing.assert_array_equal(muscles.neuron_ids, [6, 5, 4])
        # one motor neuron each: a spike adds 1 / (100 Hz x 20 ms) of activation
        np.testing.assert_allclose(muscles.increments, 0.5)

    def test_activations_become_torques_on_their_joints_and_the_grip(self, tmp_path):
        population, interface = wired(tmp_path)
        muscles = Muscles(population, interface)

        torques, grip = muscles.drive(np.array([1.0, 0.25, 1.0]))

        tibia = JOINTS.index("Tibia")
        assert torques[tibia] == pytest.approx(20.0 - 0.25 * 20.0)
        assert np.count_nonzero(torques) == 1
        np.testing.assert_array_equal(grip, [1.0, 0, 0, 0, 0, 0])

    def test_an_activation_past_full_pulls_no_harder(self, tmp_path):
        population, interface = wired(tmp_path)
        muscles = Muscles(population, interface)

        torques, _ = muscles.drive(np.array([0.0, 0.0, 5.0]))

        assert torques[JOINTS.index("Tibia")] == pytest.approx(20.0)

    def test_a_muscle_the_table_lacks_is_refused(self, tmp_path):
        population, interface = wired(
            tmp_path, interface=BodyInterface(muscles={"LF": {}}).model_dump(mode="json")
        )
        with pytest.raises(ValueError, match="does not name"):
            Muscles(population, interface)
