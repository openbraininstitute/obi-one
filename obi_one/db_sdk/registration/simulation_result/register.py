"""Compatibility re-export; implementation moved to obi_one_lazy."""

from obi_one_lazy.db_sdk.registration.simulation_result.register import (
    EXTENSION_TO_CONTENT_TYPE,
    register_simulation_results,
)

__all__ = ["EXTENSION_TO_CONTENT_TYPE", "register_simulation_results"]
