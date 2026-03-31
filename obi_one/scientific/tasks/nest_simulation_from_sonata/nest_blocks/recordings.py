"""NEST recording handlers mirroring OBI-ONE recording block types.

Each class translates a SONATA ``reports`` entry into NEST recording devices.
"""

from typing import Any

from obi_one.scientific.tasks.nest_simulation_from_sonata.nest_blocks.base import (
    NestFeatureNotSupportedError,
    NestReportHandler,
    resolve_node_set_to_nest_nodes,
)


class NestSomaVoltageRecording(NestReportHandler):
    """Mirrors ``SomaVoltageRecording`` and ``TimeWindowSomaVoltageRecording``.

    SONATA report with ``type`` ``compartment`` and ``variable_name`` ``v``.
    Translates to a NEST ``voltmeter``.
    """

    def apply(  # noqa: PLR6301
        self,
        report_name: str,
        report_config: dict,
        node_collections: dict[str, Any],
        node_sets: dict[str, Any],
        nest: Any,
    ) -> Any:
        targets = resolve_node_set_to_nest_nodes(
            report_config.get("cells", "All"), node_collections, node_sets
        )

        dt = report_config.get("dt", 0.1)
        start_time = report_config.get("start_time", 0.0)
        end_time = report_config.get("end_time")

        params: dict[str, Any] = {
            "interval": dt,
            "start": start_time,
            "record_to": "memory",
            "label": report_name,
        }
        if end_time is not None:
            params["stop"] = end_time

        vm = nest.Create("voltmeter", params=params)
        nest.Connect(vm, targets)
        return vm


class NestSpikeRecording(NestReportHandler):
    """Always-on spike recording.

    This handler is not driven by a SONATA report entry; it is always
    added to capture spikes from the full network.
    Translates to a NEST ``spike_recorder``.
    """

    def apply(  # noqa: PLR6301
        self,
        report_name: str,
        report_config: dict,  # noqa: ARG002
        node_collections: dict[str, Any],
        node_sets: dict[str, Any],  # noqa: ARG002
        nest: Any,
    ) -> Any:
        sr = nest.Create(
            "spike_recorder",
            params={"record_to": "memory", "label": report_name},
        )
        for nc in node_collections.values():
            nest.Connect(nc, sr)
        return sr


class NestIonChannelVariableRecording(NestReportHandler):
    """Mirrors ``IonChannelVariableRecording``. NOT SUPPORTED.

    NEST point neuron models do not expose individual ion channel
    mechanism variables for recording.
    """

    def apply(  # noqa: PLR6301
        self,
        report_name: str,
        report_config: dict,
        *_args: Any,
        **_kw: Any,
    ) -> Any:
        variable_name = report_config.get("variable_name", "unknown")
        msg = (
            f"Report '{report_name}': Ion channel variable recording "
            f"(variable '{variable_name}') is not supported in NEST. "
            f"NEST point neuron models do not expose individual ion "
            f"channel mechanism variables for recording."
        )
        raise NestFeatureNotSupportedError(msg)


def get_report_handler(report_config: dict) -> NestReportHandler:
    """Return the appropriate handler for a SONATA report entry."""
    report_type = report_config.get("type", "")
    variable_name = report_config.get("variable_name", "")

    if report_type == "compartment" and variable_name == "v":
        return NestSomaVoltageRecording()

    if report_type == "compartment":
        return NestIonChannelVariableRecording()

    msg = (
        f"Unknown SONATA report type '{report_type}' with "
        f"variable_name '{variable_name}'. "
        f"No NEST handler is registered for this combination."
    )
    raise NestFeatureNotSupportedError(msg)
