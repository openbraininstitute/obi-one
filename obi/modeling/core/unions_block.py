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



"""
May want to have specific functions for each
Block parent class type in future as below
so can do checks for specific function implementations, 
or also include parent class
"""
# def timestamps_union() -> Type[Union[Timestamps]]:
#     subclasses = Timestamps.__subclasses__()
#     return Union[tuple(subclasses)]

# TimestampsUnion = timestamps_union(class)