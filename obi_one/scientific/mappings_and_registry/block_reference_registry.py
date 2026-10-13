"""Declarative block reference types for ScanConfig.add() lookup.

Each reference class is declared as a ``(module path, class name)`` reference, so importing
this module imports no union or block implementation. Classes are imported on first
``block_ref_registry.get_by_name`` lookup.
"""

from obi_one.utils.lazy_import import ClassRef

_BLOCK_REFERENCES = "obi_one.scientific.unions_and_references"

BLOCK_REFERENCE_SPECS: dict[str, ClassRef] = {
    "CombinedBiophysicalNeuronSetReference": (
        f"{_BLOCK_REFERENCES}.combined_neuron_sets",
        "CombinedBiophysicalNeuronSetReference",
    ),
    "CombinedNonVirtualNeuronSetReference": (
        f"{_BLOCK_REFERENCES}.combined_neuron_sets",
        "CombinedNonVirtualNeuronSetReference",
    ),
    "CombinedPointNeuronSetReference": (
        f"{_BLOCK_REFERENCES}.combined_neuron_sets",
        "CombinedPointNeuronSetReference",
    ),
    "CombinedVirtualNeuronSetReference": (
        f"{_BLOCK_REFERENCES}.combined_neuron_sets",
        "CombinedVirtualNeuronSetReference",
    ),
    "BiophysicalNeuronSetReference": (
        f"{_BLOCK_REFERENCES}.neuron_sets",
        "BiophysicalNeuronSetReference",
    ),
    "VirtualNeuronSetReference": (
        f"{_BLOCK_REFERENCES}.neuron_sets",
        "VirtualNeuronSetReference",
    ),
    "PointNeuronSetReference": (
        f"{_BLOCK_REFERENCES}.neuron_sets",
        "PointNeuronSetReference",
    ),
    "StimulusReference": (f"{_BLOCK_REFERENCES}.stimuli", "StimulusReference"),
    "SynapticManipulationsReference": (
        f"{_BLOCK_REFERENCES}.manipulations",
        "SynapticManipulationsReference",
    ),
    "NeuronalManipulationReference": (
        f"{_BLOCK_REFERENCES}.neuronal_manipulations",
        "NeuronalManipulationReference",
    ),
    "RecordingReference": (f"{_BLOCK_REFERENCES}.recordings", "RecordingReference"),
    "TimestampsReference": (f"{_BLOCK_REFERENCES}.timestamps", "TimestampsReference"),
    "MorphologyLocationsReference": (
        f"{_BLOCK_REFERENCES}.morphology_locations",
        "MorphologyLocationsReference",
    ),
    "AllDistributionsReference": (
        f"{_BLOCK_REFERENCES}.distributions",
        "AllDistributionsReference",
    ),
    "SynapticModelReference": (
        f"{_BLOCK_REFERENCES}.synaptic_models",
        "SynapticModelReference",
    ),
    "SynapticModelAssignerReference": (
        f"{_BLOCK_REFERENCES}.synaptic_model_assigner",
        "SynapticModelAssignerReference",
    ),
    "ExtracellularLocationsReference": (
        f"{_BLOCK_REFERENCES}.extracellular_locations",
        "ExtracellularLocationsReference",
    ),
}
