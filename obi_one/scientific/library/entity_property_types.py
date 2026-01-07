from enum import StrEnum


class EntityType(StrEnum):
    CIRCUIT = "circuit"


class CircuitPropertyType(StrEnum):
    NODE_SET = "NodeSet"
    POPULATION = "Population"
    BIOPHYSICAL_POPULATION = "BiophysicalPopulation"
    VIRTUAL_POPULATION = "VirtualPopulation"
