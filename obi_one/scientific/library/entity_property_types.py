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
    MECHANISM_VARIABLES_BY_ION_CHANNEL = "MechanismVariablesByIonChannel"
    ION_CHANNEL_RANGE_VARIABLES = "IonChannelRangeVariables"
    ION_CHANNEL_GLOBAL_VARIABLES = "IonChannelGlobalVariables"


class UsabilityGroup(StrEnum):
    CIRCUIT = "Circuit"


class CircuitUsability(StrEnum):
    SHOW_ELECTRIC_FIELD_STIMULI = "ShowElectricFieldStimuli"
    SHOW_INPUT_RESISTANCE_BASED_STIMULI = "InputResistanceBasedStimuli"
