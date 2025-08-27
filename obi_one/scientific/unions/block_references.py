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
]
