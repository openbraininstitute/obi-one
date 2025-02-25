from obi.modeling.core.block import Block

class IntracellularLocationSet(Block):
    """
    """
    neuron_ids: tuple[int, ...] | list[tuple[int, ...]]
    section: str | list[str]

# class IDSectionIntracellularLocationSet(IntracellularLocationSet):
#     neuron_ids: tuple[int, ...] | list[tuple[int, ...]]
#     section: str