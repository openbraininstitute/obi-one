from enum import StrEnum


class EntityType(StrEnum):
    CIRCUIT = "circuit"


class MappedPropertiesGroup(StrEnum):
    CIRCUIT = "Circuit"


class CircuitMappedProperties(StrEnum):
    NODE_SET = "NodeSet"
    POPULATION = "Population"
    BIOPHYSICAL_POPULATION = "BiophysicalPopulation"
    VIRTUAL_POPULATION = "VirtualPopulation"


class UsabilityGroup(StrEnum):
    CIRCUIT = "Circuit"


class CircuitUsability(StrEnum):
    SHOW_ELECTRIC_FIELD_STIMULI = "ShowElectricFieldStimuli"
    SHOW_INPUT_RESISTANCE_BASED_STIMULI = "InputResistanceBasedStimuli"
