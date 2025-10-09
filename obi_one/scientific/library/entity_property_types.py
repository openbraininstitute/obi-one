from enum import StrEnum


class CircuitPropertyType(StrEnum):
    NODE_SET = "Circuit.NodeSet"
    POPULATION = "Circuit.Population"
    BIOPHYSICAL_POPULATION = "Circuit.BiophysicalPopulation"
    VIRTUAL_POPULATION = "Circuit.VirtualPopulation"
