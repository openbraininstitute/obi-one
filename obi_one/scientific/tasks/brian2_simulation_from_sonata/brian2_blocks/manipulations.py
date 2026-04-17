"""Brian2 manipulation handlers.

Brian2's ``Synapses`` API does support post-build weight changes, so
``DisconnectSynapticManipulation`` could in principle be implemented as a
loop that sets ``syn.w[..] = 0*volt`` over matched edges. For now the
implementation is left as unsupported so that any stray SONATA
``connection_overrides`` / ``conditions.modifications`` entries surface a clear
warning instead of silently having no effect.
"""

from typing import Any

from obi_one.scientific.tasks.brian2_simulation_from_sonata.brian2_blocks.base import (
    Brian2ConnectionOverrideHandler,
    Brian2FeatureNotSupportedError,
)


def _raise_unsupported(name: str, description: str) -> None:
    msg = f"'{name}': {description}"
    raise Brian2FeatureNotSupportedError(msg)


class Brian2DisconnectSynapticManipulation(Brian2ConnectionOverrideHandler):
    """Mirrors ``DisconnectSynapticManipulation``. NOT SUPPORTED yet."""

    def apply(self, override_config: dict, *_a: Any, **_kw: Any) -> None:  # noqa: PLR6301
        _raise_unsupported(
            override_config.get("name", "unnamed"),
            "Disconnecting individual post-build synapses is not implemented "
            "for the Brian2 port yet.",
        )


class Brian2ConnectSynapticManipulation(Brian2ConnectionOverrideHandler):
    """Mirrors ``ConnectSynapticManipulation``. NOT SUPPORTED."""

    def apply(self, override_config: dict, *_a: Any, **_kw: Any) -> None:  # noqa: PLR6301
        _raise_unsupported(
            override_config.get("name", "unnamed"),
            "Adding new synapses post-build is not supported by the Brian2 port.",
        )


class Brian2UnsupportedOverride(Brian2ConnectionOverrideHandler):
    """Generic stub for overrides that aren't supported in Brian2 point models."""

    def __init__(self, description: str) -> None:
        """Store the human-readable reason this override type is unsupported."""
        self._description = description

    def apply(self, override_config: dict, *_a: Any, **_kw: Any) -> None:
        _raise_unsupported(override_config.get("name", "unnamed"), self._description)


def get_connection_override_handler(
    override_config: dict,
) -> Brian2ConnectionOverrideHandler:
    """Dispatch connection-override entries to the appropriate handler."""
    manipulation_type = override_config.get("type") or override_config.get("module", "")

    if manipulation_type == "Disconnect":
        return Brian2DisconnectSynapticManipulation()
    if manipulation_type == "Connect":
        return Brian2ConnectSynapticManipulation()

    return Brian2UnsupportedOverride(
        f"Connection override '{manipulation_type}' is not supported in the Brian2 port.",
    )


def get_modification_handler(modification_config: dict) -> Brian2ConnectionOverrideHandler:
    """Dispatch conditions.modifications entries to the appropriate handler."""
    mod_type = modification_config.get("type", "")
    return Brian2UnsupportedOverride(
        f"Modification '{mod_type}' is not supported in the Brian2 port.",
    )
