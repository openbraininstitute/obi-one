from enum import StrEnum


class EntityType(StrEnum):
    CIRCUIT = "circuit"


class CircuitPropertyType(StrEnum):
    NODE_SET = "NodeSet"
    POPULATION = "Circuit.Population"
    BIOPHYSICAL_POPULATION = "Circuit.BiophysicalPopulation"
    VIRTUAL_POPULATION = "Circuit.VirtualPopulation"
