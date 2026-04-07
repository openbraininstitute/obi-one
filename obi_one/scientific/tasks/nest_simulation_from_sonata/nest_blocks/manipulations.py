"""NEST manipulation handlers mirroring OBI-ONE manipulation block types.

Each class translates a SONATA ``connection_overrides`` entry or
``conditions.modifications`` entry into NEST operations.
"""

from typing import Any

from obi_one.scientific.tasks.nest_simulation_from_sonata.nest_blocks.base import (
    NestConnectionOverrideHandler,
    NestFeatureNotSupportedError,
)


def _raise_unsupported(name: str, description: str) -> None:
    """Raise NestFeatureNotSupportedError for an unsupported manipulation."""
    msg = f"'{name}': {description}"
    raise NestFeatureNotSupportedError(msg)


class NestDisconnectSynapticManipulation(NestConnectionOverrideHandler):
    """Mirrors ``DisconnectSynapticManipulation``. Partially supported."""

    def apply(self, override_config: dict, *_a: Any, **_kw: Any) -> None:  # noqa: PLR6301
        _raise_unsupported(
            override_config.get("name", "unnamed"),
            "Disconnect (weight=0) synaptic manipulation requires identifying "
            "individual connections post-build. Consider rebuilding the circuit "
            "without these connections instead.",
        )


class NestConnectSynapticManipulation(NestConnectionOverrideHandler):
    """Mirrors ``ConnectSynapticManipulation``. NOT SUPPORTED."""

    def apply(self, override_config: dict, *_a: Any, **_kw: Any) -> None:  # noqa: PLR6301
        _raise_unsupported(
            override_config.get("name", "unnamed"),
            "Connect (weight=1) synaptic manipulation is not directly "
            "supported in NEST post-build.",
        )


class NestSynapticMgManipulation(NestConnectionOverrideHandler):
    """Mirrors ``SynapticMgManipulation``. NOT SUPPORTED."""

    def apply(self, override_config: dict, *_a: Any, **_kw: Any) -> None:  # noqa: PLR6301
        _raise_unsupported(
            override_config.get("name", "unnamed"),
            "Synaptic magnesium manipulation (synapse_configure with 'mg') "
            "is not supported in NEST. Magnesium-dependent synapse models are NEURON-specific.",
        )


class NestScaleAcetylcholineUSESynapticManipulation(NestConnectionOverrideHandler):
    """Mirrors ``ScaleAcetylcholineUSESynapticManipulation``. NOT SUPPORTED."""

    def apply(self, override_config: dict, *_a: Any, **_kw: Any) -> None:  # noqa: PLR6301
        _raise_unsupported(
            override_config.get("name", "unnamed"),
            "Acetylcholine USE scaling manipulation is not supported in NEST. "
            "USE-dependent synaptic models are NEURON-specific.",
        )


class NestSetSpontaneousMiniRateSynapticManipulation(NestConnectionOverrideHandler):
    """Mirrors ``SetSpontaneousMinisRateSynapticManipulation``. NOT SUPPORTED."""

    def apply(self, override_config: dict, *_a: Any, **_kw: Any) -> None:  # noqa: PLR6301
        _raise_unsupported(
            override_config.get("name", "unnamed"),
            "Spontaneous minis rate manipulation (spont_minis) is not supported "
            "in NEST. Spontaneous miniature release is NEURON-specific.",
        )


class NestBySectionListNeuronalManipulation(NestConnectionOverrideHandler):
    """Mirrors ``BySectionListMechanismVariableNeuronalManipulation``. NOT SUPPORTED."""

    def apply(self, override_config: dict, *_a: Any, **_kw: Any) -> None:  # noqa: PLR6301
        _raise_unsupported(
            override_config.get("name", "unnamed"),
            "Section-list-based neuronal manipulation is not supported in NEST. "
            "It requires morphologically-detailed neuron models.",
        )


class NestByNeuronMechanismVariableNeuronalManipulation(NestConnectionOverrideHandler):
    """Mirrors ``ByNeuronMechanismVariableNeuronalManipulation``. NOT SUPPORTED."""

    def apply(self, override_config: dict, *_a: Any, **_kw: Any) -> None:  # noqa: PLR6301
        _raise_unsupported(
            override_config.get("name", "unnamed"),
            "Neuron mechanism variable manipulation is not supported in NEST. "
            "Mechanism variables are NEURON-specific.",
        )


def get_connection_override_handler(
    override_config: dict,
) -> NestConnectionOverrideHandler:
    """Return the appropriate handler for a SONATA connection override entry."""
    if "synapse_configure" in override_config:
        configure = override_config["synapse_configure"]
        if "mg" in configure.lower():
            return NestSynapticMgManipulation()
        if "use" in configure.lower():
            return NestScaleAcetylcholineUSESynapticManipulation()

    if "spont_minis" in override_config:
        return NestSetSpontaneousMiniRateSynapticManipulation()

    weight = override_config.get("weight")
    if weight is not None:
        if weight == 0.0:
            return NestDisconnectSynapticManipulation()
        return NestConnectSynapticManipulation()

    msg = (
        f"Unknown connection override type for "
        f"'{override_config.get('name', 'unnamed')}'. "
        f"No NEST handler is registered for this combination."
    )
    raise NestFeatureNotSupportedError(msg)


def get_modification_handler(
    modification_config: dict,
) -> NestConnectionOverrideHandler:
    """Return the appropriate handler for a SONATA conditions.modifications entry."""
    mod_type = modification_config.get("type", "")
    if mod_type in {"section_list", "configure_all_sections"}:
        return NestBySectionListNeuronalManipulation()
    return NestByNeuronMechanismVariableNeuronalManipulation()
