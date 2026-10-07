"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import]

from obi_one_lazy.scientific.from_id.circuit_from_id import (
    Circuit,
    CircuitFromID,
    ClassVar,
    Client,
    EntityFromID,
    MEModelWithSynapsesCircuit,
    MEModelWithSynapsesCircuitFromID,
    models,
    OBIONEError,
    Path,
    PrivateAttr,
    SONATA_CIRCUIT_ASSET_SELECTION,
    stage_circuit,
    stage_circuit_nodes,
)
