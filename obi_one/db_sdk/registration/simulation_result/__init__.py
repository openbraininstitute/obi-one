"""Simulation result registration utilities for entitycore."""

from obi_one.db_sdk.registration.simulation_result.register import (
    EXTENSION_TO_CONTENT_TYPE,
    register_simulation_results,
)

__all__ = [
    "EXTENSION_TO_CONTENT_TYPE",
    "register_simulation_results",
]
