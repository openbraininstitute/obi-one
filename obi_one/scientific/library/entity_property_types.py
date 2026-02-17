from enum import StrEnum


class EntityType(StrEnum):
    CIRCUIT = "circuit"


class CircuitPropertyType(StrEnum):
    NODE_SET = "NodeSet"
    POPULATION = "Population"
    BIOPHYSICAL_POPULATION = "BiophysicalPopulation"
    VIRTUAL_POPULATION = "VirtualPopulation"
    MECHANISM_VARIABLES = "MechanismVariables"
    ION_CHANNEL_RANGE_VARIABLES = "IonChannelRangeVariables"
    ION_CHANNEL_GLOBAL_VARIABLES = "IonChannelGlobalVariables"
