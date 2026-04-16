from enum import StrEnum


class EntityType(StrEnum):
    CIRCUIT = "circuit"
    IONCHANNELMODEL = "ion_channel_model"


class MappedPropertiesGroup(StrEnum):
    CIRCUIT = "Circuit"
    ION_CHANNEL_MODEL = "IonChannelModel"


class CircuitMappedProperties(StrEnum):
    NODE_SET = "NodeSet"
    POPULATION = "Population"
    BIOPHYSICAL_POPULATION = "BiophysicalPopulation"
    VIRTUAL_POPULATION = "VirtualPopulation"
    MECHANISM_VARIABLES_BY_ION_CHANNEL = "MechanismVariablesByIonChannel"


class CircuitUsability(StrEnum):
    SHOW_ELECTRIC_FIELD_STIMULI = "ShowElectricFieldStimuli"
    SHOW_INPUT_RESISTANCE_BASED_STIMULI = "InputResistanceBasedStimuli"


class IonChannelPropertyType(StrEnum):
    RECORDABLE_VARIABLES = "RecordableVariables"
