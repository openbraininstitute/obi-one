from enum import StrEnum


class EntityType(StrEnum):
    CIRCUIT = "circuit"
    IONCHANNELMODEL = "ion_channel_model"


class CircuitPropertyType(StrEnum):
    NODE_SET = "NodeSet"
    POPULATION = "Population"
    BIOPHYSICAL_POPULATION = "BiophysicalPopulation"
    VIRTUAL_POPULATION = "VirtualPopulation"


class IonChannelPropertyType(StrEnum):
    RECORDABLE_VARIABLES = "RecordableVariables"
