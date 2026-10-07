"""Circuit staging helpers for entitysdk.

Kept separate from ``db_sdk`` so launch CLIs that only need activity/asset helpers
do not import ``Circuit`` / bluepysnap.
"""

import logging
from pathlib import Path

from entitysdk import Client, models

from obi_one_lazy.core.exception import OBIONEError
from obi_one_lazy.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one_lazy.scientific.library.circuit import Circuit

L = logging.getLogger(__name__)


def resolve_circuit(
    circuit: Circuit | CircuitFromID,
    *,
    db_client: Client,
    entity_cache: bool,
    cache_root: Path,
    temp_dir: Path,
) -> tuple[Circuit, models.Circuit | None]:
    """Resolve a circuit object into a staged local circuit.

    Handles both local Circuit instances and CircuitFromID references that
    need to be staged from entitycore.

    Args:
        circuit: A Circuit instance (local) or CircuitFromID (remote).
        db_client: The entitycore SDK client.
        entity_cache: If True, stage into a persistent cache directory under
            cache_root; otherwise stage into temp_dir.
        cache_root: Root path for the entity cache (e.g., scan_output_root).
        temp_dir: Temporary directory path to use when entity_cache is False.

    Returns:
        Tuple of (resolved Circuit, circuit entity or None).
    """
    if isinstance(circuit, Circuit):
        L.info("Circuit is a local Circuit instance.")
        return circuit, None

    if isinstance(circuit, CircuitFromID):
        L.info("Circuit is a CircuitFromID instance.")
        circuit_id = circuit.id_str

        if entity_cache:
            L.info("Use entity cache")
            dest_dir = cache_root / "entity_cache" / "sonata_circuit" / circuit_id
        else:
            dest_dir = temp_dir / "sonata_circuit"

        staged_circuit = circuit.stage_circuit(
            db_client=db_client, dest_dir=dest_dir, entity_cache=entity_cache
        )
        circuit_entity = circuit.entity(db_client=db_client)
        return staged_circuit, circuit_entity  # ty:ignore[invalid-return-type]

    msg = f"Unsupported circuit type: {type(circuit)}"
    raise OBIONEError(msg)
