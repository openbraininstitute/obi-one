from enum import StrEnum


class EntityType(StrEnum):
    CIRCUIT = "circuit"


class CircuitPropertyType(StrEnum):
    NODE_SET = "NodeSet"
    POPULATION = "Population"
    BIOPHYSICAL_POPULATION = "BiophysicalPopulation"
    VIRTUAL_POPULATION = "VirtualPopulation"


class CircuitSimulationVisibilityOption(StrEnum):
    SHOW_ELECTRIC_FIELD_STIMULI = "ShowElectricFieldStimuli"
    INPUT_RESISTANCE_BASED_STIMULI = "InputResistanceBasedStimuli"
