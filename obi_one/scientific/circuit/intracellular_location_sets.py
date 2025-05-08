from obi_one.core.block import Block


class IntracellularLocationSet(Block):
    """ """

    neuron_ids: tuple[int, ...] | list[tuple[int, ...]]


class SectionIntracellularLocationSet(IntracellularLocationSet):
    """ """

    section: str | list[str]
