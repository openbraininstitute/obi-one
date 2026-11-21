"""An 8-neuron Shiu-style point-neuron circuit with a NeuroMechFly body interface, for tests.

Neurons 0 and 1 are yeasty-class olfactory receptor neurons on the left and right antennae, 2 a
claw proprioceptor and 3 a bristle of the left front leg (``body_input``), and 4-6 motor neurons of
the left front leg's tibia flexor, tibia extensor and long tendon muscles (``body_output``); 7 is
an interneuron. Each spike of the left receptor fires the tibia flexor's motor neuron.
"""

import json
from pathlib import Path

import h5py
import libsonata
import numpy as np

from obi_one.scientific.library.simulation.neuromechfly.interface import (
    BODY_INPUT,
    BODY_OUTPUT,
    BODY_TUNING,
    INTERFACE_COMPONENT,
    BodyInterface,
    JointAction,
    Muscle,
)

POPULATION = "drosophila"
EDGE_POPULATION = f"{POPULATION}__{POPULATION}__brian2_synapse"
NEURONS = 8
UNKNOWN = "[unknown]"
BODY_INPUTS = [
    "odour/antenna/left/yeasty_volatile",
    "odour/antenna/right/yeasty_volatile",
    "chordotonal/LF/claw",
    "touch/LF",
    *[UNKNOWN] * 4,
]
BODY_OUTPUTS = [
    *[UNKNOWN] * 4,
    "muscle/LF/tibia_flexor_muscle",
    "muscle/LF/tibia_extensor_muscle",
    "muscle/LF/long_tendon_muscle",
    UNKNOWN,
]
# The claw neuron prefers the standing tibia angle (radians).
BODY_TUNINGS = [np.nan, np.nan, 1.64, *[np.nan] * 5]
MUSCLES = {
    "LF": {
        "tibia_flexor_muscle": Muscle(actions=(JointAction(joint="Tibia", weight=1.0),)),
        "tibia_extensor_muscle": Muscle(actions=(JointAction(joint="Tibia", weight=-1.0),)),
        "long_tendon_muscle": Muscle(grip=True),
    }
}
# 200 synapses of 0.275 mV: each receptor spike fires the neuron it reaches.
STRONG_MV = 200 * 0.275
CONNECTIONS = [(0, 4), (1, 7)]
NEURON_TEMPLATE = {
    "params": {
        "model": [
            "dv/dt = (v_0 - v + g + R_membrane * I_inj) / t_mbr : volt (unless refractory)",
            "dg/dt = -g / tau : volt (unless refractory)",
            "rfc : second",
            "I_inj : amp",
        ],
        "method": "linear",
        "threshold": "v > v_th",
        "reset": "v = v_rst; w = 0; g = 0 * mV",
        "refractory": "rfc",
    },
    "namespace": {
        "t_mbr": [20.0, "ms"],
        "tau": [5.0, "ms"],
        "v_0": [-52.0, "mV"],
        "v_th": [-45.0, "mV"],
        "v_rst": [-52.0, "mV"],
        "R_membrane": [10.0, "Mohm"],
    },
    "initial": {"v": [-52.0, "mV"], "g": [0, "mV"], "rfc": [2.2, "ms"]},
}
SYNAPSE_TEMPLATE = {
    "params": {"model": "w : volt", "on_pre": "g += w", "delay": [1.8, "ms"]},
    "dynamics": {"w": "mV"},
}


def write_embodied_circuit(
    path: Path, *, body_interface: bool = True, interface: dict | None = None
) -> Path:
    """Write the circuit into ``path``; return its circuit config.

    Without ``body_interface`` it has neither the node properties nor the interface file;
    ``interface`` replaces the interface file's content.
    """
    (path / "models").mkdir(parents=True)
    (path / "models/drosophila.json").write_text(json.dumps(NEURON_TEMPLATE))
    (path / "models/synapse.json").write_text(json.dumps(SYNAPSE_TEMPLATE))
    with h5py.File(path / "nodes.h5", "w") as h5:
        group = h5.create_group(f"nodes/{POPULATION}")
        group.create_dataset("node_type_id", data=np.full(NEURONS, -1))
        group.create_dataset("0/model_template", data=["json:drosophila"] * NEURONS)
        group.create_dataset("0/model_type", data=["brian2_point"] * NEURONS)
        if body_interface:
            group.create_dataset(f"0/{BODY_INPUT}", data=BODY_INPUTS)
            group.create_dataset(f"0/{BODY_OUTPUT}", data=BODY_OUTPUTS)
            group.create_dataset(f"0/{BODY_TUNING}", data=np.array(BODY_TUNINGS, dtype=float))
    source, target = np.array(CONNECTIONS).T
    with h5py.File(path / "edges.h5", "w") as h5:
        group = h5.create_group(f"edges/{EDGE_POPULATION}")
        group.create_dataset("source_node_id", data=source.astype(np.uint64))
        group["source_node_id"].attrs["node_population"] = POPULATION
        group.create_dataset("target_node_id", data=target.astype(np.uint64))
        group["target_node_id"].attrs["node_population"] = POPULATION
        group.create_dataset("edge_type_id", data=np.full(len(source), -1))
        group.create_dataset("0/w", data=np.full(len(source), STRONG_MV))
        group.create_dataset("0/model_template", data=["json:synapse"] * len(source))
    libsonata.EdgePopulation.write_indices(
        str(path / "edges.h5"), EDGE_POPULATION, NEURONS, NEURONS
    )
    (path / "node_sets.json").write_text(json.dumps({"All": {"population": POPULATION}}))
    components = {"point_neuron_models_dir": "models"}
    if body_interface:
        content = interface or json.loads(BodyInterface(muscles=MUSCLES).model_dump_json())
        (path / "body_interface.json").write_text(json.dumps(content, indent=2))
        components[INTERFACE_COMPONENT] = "body_interface.json"
    config = {
        "components": components,
        "node_sets_file": "node_sets.json",
        "target_simulator": "Brian2",
        "networks": {
            "nodes": [
                {"nodes_file": "nodes.h5", "populations": {POPULATION: {"type": "brian2_point"}}}
            ],
            "edges": [
                {
                    "edges_file": "edges.h5",
                    "populations": {EDGE_POPULATION: {"type": "brian2_synapse"}},
                }
            ],
        },
    }
    (path / "circuit_config.json").write_text(json.dumps(config))
    return path / "circuit_config.json"
