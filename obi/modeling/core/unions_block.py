from obi.modeling.core.unions import subclass_union
from obi.modeling.circuit.neuron_sets import *
from obi.modeling.circuit.synapse_sets import *
from obi.modeling.simulation.timestamps import *
from obi.modeling.simulation.stimulus import *
from obi.modeling.simulation.recording import *

NeuronSetUnion = subclass_union(NeuronSet)
SynapseSetUnion = subclass_union(SynapseSet)
TimestampsUnion = subclass_union(Timestamps)
StimulusUnion = subclass_union(Stimulus)
RecordingUnion = subclass_union(Recording)