from enum import IntEnum, StrEnum, auto

ALL_POPULATIONS = "_ALL_"
TYPES_OF_CHEMICAL_SYNS = ["chemical", "Exp2Syn_synapse", "point_process"]
TYPES_OF_ELECTRICAL_SYNS = ["electrical"]
TYPES_OF_BIOPHYS_NODES = ["biophysical"]
TYPES_OF_VIRTUAL_NODES = ["virtual"]
TYPES_OF_POINT_NODES = ["point_process", "point_neuron", "brian2_point", "inait_point_neuron_lif"]


class NodePopulationType(StrEnum):
    biophysical = auto()
    virtual = auto()
    point = auto()


class EdgePopulationType(StrEnum):
    chemical = auto()
    electrical = auto()


class SpatialCoordinate(StrEnum):
    x = auto()
    y = auto()
    z = auto()


class DegreeTypes(StrEnum):
    indegree = auto()
    outdegree = auto()
    totaldegree = auto()
    degreedifference = auto()


class CircuitStatsLevelOfDetail(IntEnum):
    none = 0
    basic = 1
    advanced = 2
    full = 3


MAX_UNIQUE_VALUES = {
    CircuitStatsLevelOfDetail.basic: 25,
    CircuitStatsLevelOfDetail.advanced: 50,
    CircuitStatsLevelOfDetail.full: 100,
}
