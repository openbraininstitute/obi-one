from obi_one.core.block import Block


class IntracellularLocationSet(Block):
    """Base class of intracellular locations."""

    neuron_ids: tuple[int, ...] | list[tuple[int, ...]]


class SectionIntracellularLocationSet(IntracellularLocationSet):
    section: str | list[str]
