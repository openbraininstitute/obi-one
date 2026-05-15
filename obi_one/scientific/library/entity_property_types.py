from enum import StrEnum


class EntityType(StrEnum):
    CIRCUIT = "circuit"
    IONCHANNELMODEL = "ion_channel_model"


class MappedPropertiesGroup(StrEnum):
    CIRCUIT = "Circuit"
    ION_CHANNEL_MODEL = "IonChannelModel"


class CircuitMappedProperties(StrEnum):
    NODE_SET = "NodeSet"
    BIOPHYSICAL_NEURONAL_POPULATION = "BiophysicalNeuronalPopulation"
    VIRTUAL_NEURONAL_POPULATION = "VirtualNeuronalPopulation"
    POINT_NEURONAL_POPULATION = "PointNeuronalPopulation"
    MECHANISM_VARIABLES_BY_ION_CHANNEL = "MechanismVariablesByIonChannel"
    NODE_PROPERTY_UNIQUE_VALUES_BY_POPULATION = "NodePropertyUniqueValuesByPopulation"


class CircuitUsability(StrEnum):
    SHOW_ELECTRIC_FIELD_STIMULI = "ShowElectricFieldStimuli"
    SHOW_INPUT_RESISTANCE_BASED_STIMULI = "InputResistanceBasedStimuli"
    SHOW_BIOPHYSICAL_NEURON_SETS = "ShowBiophysicalNeuronSets"
    SHOW_POINT_NEURON_SETS = "ShowPointNeuronSets"
    SHOW_VIRTUAL_NEURON_SETS = "ShowVirtualNeuronSets"


class IonChannelPropertyType(StrEnum):
    RECORDABLE_VARIABLES = "RecordableVariables"
