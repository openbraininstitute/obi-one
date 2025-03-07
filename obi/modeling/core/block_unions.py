from typing import Union, Type
from obi.modeling.core.block import Block

from obi.modeling.circuit.circuit import Circuit
from obi.modeling.circuit.neuron_sets import NeuronSet
from obi.modeling.circuit.synapse_sets import SynapseSet

from obi.modeling.simulation.timestamps import Timestamps
from obi.modeling.simulation.stimulus import Stimulus
from obi.modeling.simulation.recording import Recording

def block_union(block_parent_class) -> Type[Union[Block]]:
    subclasses = block_parent_class.__subclasses__()
    return Union[tuple(subclasses)]


NeuronSetUnion = block_union(NeuronSet)
SynapseSetUnion = block_union(SynapseSet)

TimestampsUnion = block_union(Timestamps)
StimulusUnion = block_union(Stimulus)
RecordingUnion = block_union(Recording)


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