from obi_one.core.registry import block_ref_registry
from obi_one.scientific.unions.unions_distributions import (
    AllDistributionsReference,
)
from obi_one.scientific.unions.unions_manipulations import SynapticManipulationsReference
from obi_one.scientific.unions.unions_neuron_sets import NeuronSetReference
from obi_one.scientific.unions.unions_recordings import RecordingReference
from obi_one.scientific.unions.unions_stimuli import StimulusReference
from obi_one.scientific.unions.unions_timestamps import TimestampsReference

AllBlockReferenceTypes = [
    NeuronSetReference,
    StimulusReference,
    SynapticManipulationsReference,
    RecordingReference,
    TimestampsReference,
    AllDistributionsReference,
]


def _populate_block_ref_registry() -> None:
    """Populate the core BlockReferenceRegistry with all block reference types.

    Called once at module load time.
    """
    for cls in AllBlockReferenceTypes:
        block_ref_registry.register(cls)


# Runs exactly once at module load (Python caches modules in sys.modules).
_populate_block_ref_registry()
