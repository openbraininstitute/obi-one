"""Declarative block reference types for ScanConfig.add() lookup.

Each reference class is declared as a ``(module path, class name)`` reference, so importing
this module imports no union or block implementation. Classes are imported on first
``block_ref_registry.get_by_name`` lookup.
"""

from obi_one.utils.lazy_import import ClassRef, import_class

_BLOCK_REFERENCES = "obi_one.scientific.unions_and_references"

_BLOCK_REFERENCE_SPECS: dict[str, ClassRef] = {
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
    "SimplificationAlgorithmReference": (
        f"{_BLOCK_REFERENCES}.simplification_algorithms",
        "SimplificationAlgorithmReference",
    ),
    "ExtracellularLocationsReference": (
        f"{_BLOCK_REFERENCES}.extracellular_locations",
        "ExtracellularLocationsReference",
    ),
}


class BlockReferenceRegistry:
    """Maps BlockReference subclass names to their classes.

    Used by ScanConfig.add() to resolve a reference type by name when adding a block.
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._by_name: dict[str, type] = {}

    def get_by_name(self, name: str) -> type | None:
        """Return the BlockReference subclass with the given name, or None."""
        if name in self._by_name:
            return self._by_name[name]
        class_ref = _BLOCK_REFERENCE_SPECS.get(name)
        if class_ref is None:
            return None
        cls = import_class(class_ref)
        self._by_name[name] = cls
        return cls


block_ref_registry = BlockReferenceRegistry()
