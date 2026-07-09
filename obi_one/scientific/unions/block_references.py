from obi_one.core.registry import block_ref_registry
from obi_one.scientific.unions.unions_combined_neuron_sets import (
    CombinedBiophysicalNeuronSetReference,
    CombinedNonVirtualNeuronSetReference,
    CombinedPointNeuronSetReference,
    CombinedVirtualNeuronSetReference,
)
from obi_one.scientific.unions.unions_distributions import (
    AllDistributionsReference,
)
from obi_one.scientific.unions.unions_extracellular_locations import (
    ExtracellularLocationsReference,
)
from obi_one.scientific.unions.unions_manipulations import SynapticManipulationsReference
from obi_one.scientific.unions.unions_neuron_sets import (
    BiophysicalNeuronSetReference,
    PointNeuronSetReference,
    VirtualNeuronSetReference,
)
from obi_one.scientific.unions.unions_recordings import RecordingReference
from obi_one.scientific.unions.unions_stimuli import StimulusReference
from obi_one.scientific.unions.unions_synaptic_model_assigner import (
    SynapticModelAssignerReference,
)
from obi_one.scientific.unions.unions_synaptic_models import SynapticModelReference
from obi_one.scientific.unions.unions_timestamps import TimestampsReference

AllBlockReferenceTypes = [
    CombinedBiophysicalNeuronSetReference,
    CombinedNonVirtualNeuronSetReference,
    CombinedPointNeuronSetReference,
    CombinedVirtualNeuronSetReference,
    BiophysicalNeuronSetReference,
    VirtualNeuronSetReference,
    PointNeuronSetReference,
    StimulusReference,
    SynapticManipulationsReference,
    RecordingReference,
    TimestampsReference,
    AllDistributionsReference,
    SynapticModelReference,
    SynapticModelAssignerReference,
    ExtracellularLocationsReference,
]


def _populate_block_ref_registry() -> None:
    """Populate the core BlockReferenceRegistry with all block reference types.

    Called once at module load time.
    """
    for cls in AllBlockReferenceTypes:
        block_ref_registry.register(cls)


# Runs exactly once at module load (Python caches modules in sys.modules).
_populate_block_ref_registry()
