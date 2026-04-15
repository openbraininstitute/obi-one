"""Brian2 recording handlers mirroring OBI-ONE recording block types."""

from typing import Any

import numpy as np

from obi_one.scientific.tasks.brian2_simulation_from_sonata.brian2_blocks.base import (
    Brian2FeatureNotSupportedError,
    Brian2ReportHandler,
    resolve_node_set_to_indices,
)


class Brian2SomaVoltageRecording(Brian2ReportHandler):
    """Mirrors ``SomaVoltageRecording`` and ``TimeWindowSomaVoltageRecording``.

    SONATA report with ``type`` ``compartment`` and ``variable_name`` ``v``.
    Translates to a Brian2 ``StateMonitor`` on the target subgroup.
    """

    def apply(  # noqa: PLR6301
        self,
        report_name: str,
        report_config: dict,
        neuron_group: Any,
        node_population: str,
        node_sets: dict[str, Any],
        brian2_objects: list,
        b2: Any,
    ) -> Any:
        n_nodes = len(neuron_group)
        idx = resolve_node_set_to_indices(
            report_config.get("cells", "All"), node_population, node_sets, n_nodes
        )
        if len(idx) == 0:
            return None

        dt_ms = float(report_config.get("dt", 0.1))
        sm = b2.StateMonitor(
            neuron_group,
            "v",
            record=np.asarray(idx, dtype=int),
            dt=dt_ms * b2.ms,
            name=f"monitor_{report_name}",
        )
        brian2_objects.append(sm)
        return sm


class Brian2SpikeRecording(Brian2ReportHandler):
    """Always-on spike recording via ``SpikeMonitor``."""

    def apply(  # noqa: PLR6301
        self,
        report_name: str,  # noqa: ARG002
        report_config: dict,  # noqa: ARG002
        neuron_group: Any,
        node_population: str,  # noqa: ARG002
        node_sets: dict[str, Any],  # noqa: ARG002
        brian2_objects: list,
        b2: Any,
    ) -> Any:
        # Use Brian2's default SpikeMonitor name so the object name matches the
        # reference run_trial flow (which also uses the default).
        sm = b2.SpikeMonitor(neuron_group)
        brian2_objects.append(sm)
        return sm


class Brian2IonChannelVariableRecording(Brian2ReportHandler):
    """Mirrors ``IonChannelVariableRecording``. NOT SUPPORTED."""

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
            f"(variable '{variable_name}') is not supported in Brian2 point models."
        )
        raise Brian2FeatureNotSupportedError(msg)


def get_report_handler(report_config: dict) -> Brian2ReportHandler:
    """Return the appropriate handler for a SONATA report entry."""
    report_type = report_config.get("type", "")
    variable_name = report_config.get("variable_name", "")

    if report_type == "compartment" and variable_name == "v":
        return Brian2SomaVoltageRecording()

    if report_type == "compartment":
        return Brian2IonChannelVariableRecording()

    msg = f"Unknown SONATA report type '{report_type}' with variable_name '{variable_name}'."
    raise Brian2FeatureNotSupportedError(msg)
