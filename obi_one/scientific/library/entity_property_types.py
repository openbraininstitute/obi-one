from enum import StrEnum


class CircuitPropertyType(StrEnum):
    NODE_SET = "CircuitNodeSet"
    POPULATION = "CircuitPopulation"
    BIOPHYSICAL_POPULATION = "CircuitBiophysicalPopulation"
    VIRTUAL_POPULATION = "CircuitVirtualPopulation"
