"""Complex MEModel validation tests that require custom logic.

These tests subclass ValidationTest directly because they don't fit the
composable ParametricValidation pattern (they need multi-recording stimuli,
custom analysis pipelines, or multiple measurements from the same trace).
"""

from pathlib import Path
from typing import Any

import efel
import numpy as np
from bluecellulab.analysis.analysis import BPAP, compute_plot_fi_curve, compute_plot_iv_curve
from bluecellulab.analysis.inject_sequence import run_multirecordings_stimulus, run_stimulus
from bluecellulab.cell.core import Cell
from bluecellulab.simulation.neuron_globals import NeuronGlobals
from bluecellulab.stimulus.factory import IDRestTimings, StimulusFactory
from bluecellulab.validation.base import TestResult, ValidationTest
from bluecellulab.validation.plotting import plot_trace, plot_traces

from obi_one.scientific.validations.memodel.config import SimulatorConfig
from obi_one.scientific.validations.memodel.names import ValidationName

_DEFAULT_BPAP_SPIKE_THRESHOLD_MV = -20.0
_MIN_BPAP_TRACE_SAMPLES = 2
_MAX_INPUT_RESISTANCE_MOHM = 1_000
_MIN_CURVE_POINTS = 2


def _count_bpap_spikes(
    time: np.ndarray,
    voltage: np.ndarray,
    *,
    start: float,
    end: float,
    threshold: float,
) -> int | None:
    """Count soma spikes in a complete BPAP analysis interval with eFEL."""
    trace = {
        "T": time,
        "V": voltage,
        "stim_start": [start],
        "stim_end": [end],
    }
    previous_threshold = float(efel.get_settings().Threshold)
    try:
        efel.set_setting("Threshold", threshold)
        feature_results = efel.get_feature_values([trace], ["spike_count"])
    finally:
        # eFEL settings are process-global; do not change the following tests.
        efel.set_setting("Threshold", previous_threshold)

    if not feature_results:
        return None
    spike_counts = feature_results[0].get("spike_count")
    if spike_counts is None or len(spike_counts) == 0:
        return None
    spike_count = float(spike_counts[0])
    if not np.isfinite(spike_count) or not spike_count.is_integer() or spike_count < 0:
        return None
    return int(spike_count)


class HyperpolarizationTest(ValidationTest):
    """Hyperpolarization: steady-state voltage during -40% step should be below RMP."""

    @property
    def name(self) -> str:
        return ValidationName.HYPERPOLARIZATION

    def run(self, template_params: Any, rheobase: float, out_dir: Path) -> TestResult:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        stim_factory = StimulusFactory(dt=1.0)
        step_stimulus = stim_factory.iv(threshold_current=rheobase, threshold_percentage=-40)
        recording = run_stimulus(
            template_params,
            step_stimulus,
            "soma[0]",
            0.5,
            add_hypamp=True,
        )

        fig_path = plot_trace(
            recording,
            out_dir,
            fname="hyperpolarization_validation.pdf",
            title="Hyperpolarization Validation - Step at -40% of Rheobase",
        )

        trace = {
            "T": recording.time,
            "V": recording.voltage,
            "stim_start": [IDRestTimings.PRE_DELAY.value],
            "stim_end": [IDRestTimings.PRE_DELAY.value + IDRestTimings.DURATION.value],
        }
        features = efel.get_feature_values(
            [trace], ["voltage_base", "steady_state_voltage_stimend"]
        )
        rmp = features[0]["voltage_base"]
        ss_voltage = features[0]["steady_state_voltage_stimend"]

        if rmp is None or len(rmp) == 0 or ss_voltage is None or len(ss_voltage) == 0:
            return TestResult(
                name=self.name,
                passed=False,
                details="Could not determine RMP or steady state voltage.",
                figures=[fig_path],
            )

        rmp_val = rmp[0]
        ss_val = ss_voltage[0]
        passed = bool(ss_val < rmp_val)

        if passed:
            details = f"Hyperpolarized voltage ({ss_val:.2f} mV) is below RMP ({rmp_val:.2f} mV)."
        else:
            details = (
                f"Hyperpolarized voltage ({ss_val:.2f} mV) is not lower than "
                f"RMP ({rmp_val:.2f} mV)."
            )

        return TestResult(name=self.name, passed=passed, details=details, figures=[fig_path])


class RinTest(ValidationTest):
    """Input resistance should be within a biologically realistic range (< 1000 MOhm)."""

    def __init__(self, rin: float) -> None:
        """Initialize the test with the measured input resistance in MOhm."""
        self.rin = rin

    @property
    def name(self) -> str:
        return ValidationName.INPUT_RESISTANCE

    def run(self, _template_params: Any, _rheobase: float, _out_dir: Path) -> TestResult:
        passed = bool(self.rin < _MAX_INPUT_RESISTANCE_MOHM)

        if passed:
            details = (
                f"Input resistance (Rin) = {self.rin:.2f} MOhm is less than "
                f"{_MAX_INPUT_RESISTANCE_MOHM} MOhm."
            )
        else:
            details = (
                f"Input resistance (Rin) = {self.rin:.2f} MOhm exceeds "
                f"{_MAX_INPUT_RESISTANCE_MOHM} MOhm, which is not biologically realistic."
            )

        return TestResult(name=self.name, passed=passed, details=details, figures=[])


class AISSpikingTest(ValidationTest):
    """AIS spiking: axon should spike before soma at 200% rheobase."""

    @property
    def name(self) -> str:
        return ValidationName.AIS_SPIKING

    def run(self, template_params: Any, rheobase: float, out_dir: Path) -> TestResult:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        # Check that the cell has an axon
        cell = Cell.from_template_parameters(template_params)
        if len(cell.axonal) == 0 or "axon[0]" not in cell.sections:
            return TestResult(
                name=self.name,
                passed=True,
                details="Skipped: Cell does not have an axon section.",
                figures=[],
            )

        stim_factory = StimulusFactory(dt=1.0)
        step_stimulus = stim_factory.idrest(
            threshold_current=rheobase,
            threshold_percentage=200,
        )
        recordings = run_multirecordings_stimulus(
            template_params,
            step_stimulus,
            "soma[0]",
            0.5,
            add_hypamp=True,
            recording_locations=[("axon[0]", 0.5), ("soma[0]", 0.5)],
        )
        axon_recording, soma_recording = recordings

        fig1 = plot_traces(
            recordings,
            out_dir,
            fname="ais_spiking_validation.pdf",
            title="AIS Spiking Validation - Step at 200% of Rheobase",
            labels=["axon[0]", "soma[0]"],
        )
        fig2 = plot_traces(
            recordings,
            out_dir,
            fname="ais_spiking_validation_zoomed.pdf",
            title="AIS Spiking Validation - Step at 200% of Rheobase (zoomed)",
            labels=["axon[0]", "soma[0]"],
            xlim=(IDRestTimings.PRE_DELAY.value, IDRestTimings.PRE_DELAY.value + 100),
        )

        traces = [
            {
                "T": axon_recording.time,
                "V": axon_recording.voltage,
                "stim_start": [IDRestTimings.PRE_DELAY.value],
                "stim_end": [IDRestTimings.PRE_DELAY.value + IDRestTimings.DURATION.value],
            },
            {
                "T": soma_recording.time,
                "V": soma_recording.voltage,
                "stim_start": [IDRestTimings.PRE_DELAY.value],
                "stim_end": [IDRestTimings.PRE_DELAY.value + IDRestTimings.DURATION.value],
            },
        ]
        efel.set_setting("Threshold", -40.0)
        features = efel.get_feature_values(traces, ["peak_time"])
        axon_spike_time = features[0]["peak_time"]
        soma_spike_time = features[1]["peak_time"]

        if (
            axon_spike_time is None
            or soma_spike_time is None
            or len(axon_spike_time) == 0
            or len(soma_spike_time) == 0
        ):
            return TestResult(
                name=self.name,
                passed=False,
                details="Could not determine spike times for axon or soma.",
                figures=[fig1, fig2],
            )

        passed = bool(axon_spike_time[0] <= soma_spike_time[0])
        details = "Axon spikes before soma." if passed else "Axon does not spike before soma."

        return TestResult(name=self.name, passed=passed, details=details, figures=[fig1, fig2])


class BPAPTest(ValidationTest):
    """Back-propagating action potential with optional full-trace spike guard."""

    def __init__(
        self,
        *,
        amplitude_factor: float = 10.0,
        sim_duration: float = 1500.0,
        stim_duration: float = 5.0,
        holding_current: float | None = None,
        expected_spike_count: int | None = None,
        trace_diagnostics: bool = False,
        spike_threshold: float = _DEFAULT_BPAP_SPIKE_THRESHOLD_MV,
        simulator_config: SimulatorConfig,
    ) -> None:
        """Initialize the BPAP test.

        Args:
            amplitude_factor: Multiplier of rheobase for stimulus amplitude.
            sim_duration: Total simulation duration in ms.
            stim_duration: Duration of the current pulse in ms.
            holding_current: Optional BPAP-specific holding current in nA. When
                omitted, the calibrated value stored on the cell is used.
            expected_spike_count: Optional number of soma spikes expected over
                the complete simulation. ``None`` preserves attenuation-only
                BPAP behavior for generic profiles.
            trace_diagnostics: Whether to append soma trace metrics around the
                BPAP pulse to the returned result details.
            spike_threshold: eFEL voltage threshold used by the optional full
                trace spike-count guard, in mV.
            simulator_config: Shared simulator conditions applied to this test.
        """
        if holding_current is not None:
            try:
                holding_current = float(holding_current)
            except (TypeError, ValueError) as error:
                message = "holding_current must be a finite number or None."
                raise TypeError(message) from error
            if not np.isfinite(holding_current):
                message = "holding_current must be a finite number or None."
                raise ValueError(message)
        if expected_spike_count is not None:
            if isinstance(expected_spike_count, bool) or not isinstance(expected_spike_count, int):
                message = "expected_spike_count must be an integer or None."
                raise TypeError(message)
            if expected_spike_count < 0:
                message = "expected_spike_count must be non-negative."
                raise ValueError(message)
        if not isinstance(trace_diagnostics, bool):
            message = "trace_diagnostics must be a boolean."
            raise TypeError(message)
        if not np.isfinite(spike_threshold):
            message = "spike_threshold must be finite."
            raise ValueError(message)

        self.simulator_config = simulator_config
        self.amplitude_factor = amplitude_factor
        self.sim_duration = sim_duration
        self.stim_duration = stim_duration
        self.holding_current = holding_current
        self.expected_spike_count = expected_spike_count
        self.trace_diagnostics = trace_diagnostics
        self.spike_threshold = float(spike_threshold)

    @property
    def name(self) -> str:
        return ValidationName.BACK_PROPAGATING_AP

    def run(  # ruff: ignore[complex-structure,too-many-branches,too-many-locals,too-many-statements]
        self, template_params: Any, rheobase: float, out_dir: Path
    ) -> TestResult:
        neuron_globals = NeuronGlobals.get_instance()
        saved_params = neuron_globals.export_params()

        try:
            neuron_globals.temperature = self.simulator_config.celsius
            neuron_globals.v_init = self.simulator_config.v_init
            out_dir = Path(out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)

            amplitude = self.amplitude_factor * rheobase
            cell = Cell.from_template_parameters(template_params)
            if self.holding_current is not None:
                cell.hypamp = self.holding_current
            effective_holding_current = getattr(cell, "hypamp", None)
            bpap = BPAP(
                cell,
                stim_duration=self.stim_duration,
            )
            # Cell construction may call model-specific initialization code that
            # changes the process-global value; enforce this test's value at the
            # actual simulation boundary as well.
            neuron_globals.temperature = self.simulator_config.celsius
            neuron_globals.v_init = self.simulator_config.v_init
            bpap.run(duration=self.sim_duration, amplitude=amplitude)

            time = np.asarray(bpap.cell.get_time(), dtype=float)
            soma_recording, _, _ = bpap.get_recordings()
            spike_count: int | None = None
            if soma_recording is not None:
                soma_voltage = np.asarray(soma_recording, dtype=float)
                if time.ndim != 1 or soma_voltage.ndim != 1 or time.size != soma_voltage.size:
                    return TestResult(
                        name=self.name,
                        passed=False,
                        details="Could not align full-duration soma time and voltage recordings.",
                        figures=[],
                    )
                if (
                    time.size < _MIN_BPAP_TRACE_SAMPLES
                    or not np.all(np.isfinite(time))
                    or not np.all(np.isfinite(soma_voltage))
                ):
                    return TestResult(
                        name=self.name,
                        passed=False,
                        details="Full-duration soma recording is empty or non-finite.",
                        figures=[],
                    )

                simulation_start = float(time[0])
                simulation_end = float(time[-1])
                if self.expected_spike_count is not None:
                    spike_count = _count_bpap_spikes(
                        time,
                        soma_voltage,
                        start=simulation_start,
                        end=simulation_end,
                        threshold=self.spike_threshold,
                    )
            else:
                return TestResult(
                    name=self.name,
                    passed=False,
                    details="Could not obtain a full-duration soma voltage recording.",
                    figures=[],
                )

            if time[-1] < bpap.stim_start + bpap.stim_duration:
                details = (
                    "Simulation ended before the complete BPAP pulse: "
                    f"simulation_end={time[-1]:.3f} ms, "
                    f"pulse_end={bpap.stim_start + bpap.stim_duration:.3f} ms."
                )
                return TestResult(
                    name=self.name,
                    passed=False,
                    details=details,
                    figures=[],
                )

            soma_amp, dend_amps, dend_dist, apic_amps, apic_dist = (
                bpap.get_amplitudes_and_distances()
            )

            bpap_parameters = (
                f"BPAP parameters: amplitude_factor={self.amplitude_factor}, "
                f"amplitude={amplitude:.6f} nA, "
                f"holding_current={effective_holding_current} nA, "
                f"stim_duration={self.stim_duration} ms, "
                f"sim_duration={self.sim_duration} ms, "
                f"celsius={self.simulator_config.celsius} C, "
                f"v_init={self.simulator_config.v_init} mV"
            )
            trace_diagnostic_notes = ""
            if self.trace_diagnostics:
                pulse_start = float(bpap.stim_start)
                pre_pulse_target = pulse_start - 1.0
                pre_pulse_index = int(np.abs(time - pre_pulse_target).argmin())
                pre_pulse_time = float(time[pre_pulse_index])
                pre_pulse_voltage = float(soma_voltage[pre_pulse_index])
                diagnostic_end = pulse_start + 30.0
                diagnostic_mask = (time >= pulse_start) & (time <= diagnostic_end)
                maximum_soma_voltage = (
                    float(np.max(soma_voltage[diagnostic_mask]))
                    if np.any(diagnostic_mask)
                    else None
                )
                maximum_soma_voltage_text = (
                    f"{maximum_soma_voltage:.6f} mV"
                    if maximum_soma_voltage is not None
                    else "unavailable"
                )
                pulse_end = pulse_start + float(bpap.stim_duration)
                pre_pulse_spike_count = _count_bpap_spikes(
                    time,
                    soma_voltage,
                    start=simulation_start,
                    end=pulse_start,
                    threshold=self.spike_threshold,
                )
                pulse_spike_count = _count_bpap_spikes(
                    time,
                    soma_voltage,
                    start=pulse_start,
                    end=pulse_end,
                    threshold=self.spike_threshold,
                )
                post_pulse_spike_count = _count_bpap_spikes(
                    time,
                    soma_voltage,
                    start=pulse_end,
                    end=simulation_end,
                    threshold=self.spike_threshold,
                )
                trace_diagnostic_notes = (
                    "BPAP trace diagnostics: "
                    f"nearest pre-pulse sample=t={pre_pulse_time:.6f} ms, "
                    f"V={pre_pulse_voltage:.6f} mV; "
                    f"maximum soma voltage [{pulse_start:.3f}, {diagnostic_end:.3f}] ms="
                    f"{maximum_soma_voltage_text}; "
                    f"spike counts [pre-pulse {simulation_start:.3f}-{pulse_start:.3f} ms, "
                    f"pulse {pulse_start:.3f}-{pulse_end:.3f} ms, "
                    f"post-pulse {pulse_end:.3f}-{simulation_end:.3f} ms]="
                    f"{pre_pulse_spike_count!r}, {pulse_spike_count!r}, "
                    f"{post_pulse_spike_count!r}; "
                    f"holding replay={effective_holding_current!r} nA; "
                    f"pulse step={amplitude:.6f} nA."
                )

            # If no AP was detected in soma, validation fails without creating
            # the two standard BPAP figures because amplitude data is unavailable.
            if not soma_amp:
                details = (
                    f"No action potential detected in soma ({bpap_parameters}). "
                    f"Try increasing amplitude_factor or stim_duration."
                )
                if self.expected_spike_count is not None:
                    details += f" Full-trace soma spike count={spike_count!r}."
                if trace_diagnostic_notes:
                    details = f"{details}\n{trace_diagnostic_notes}"
                return TestResult(
                    name=self.name,
                    passed=False,
                    details=details,
                    figures=[],
                )

            validated, notes = bpap.validate(
                soma_amp,
                dend_amps,
                dend_dist,
                apic_amps,
                apic_dist,
                validate_with_fit=False,
            )

            spike_guard_passed = True
            spike_notes = ""
            if self.expected_spike_count is not None:
                if spike_count is None:
                    spike_guard_passed = False
                    spike_notes = (
                        "Full-trace soma spike count could not be determined "
                        f"using threshold {self.spike_threshold:.1f} mV; "
                        f"{bpap_parameters}."
                    )
                elif spike_count != self.expected_spike_count:
                    spike_guard_passed = False
                    spike_notes = (
                        f"Full-trace soma spike count={spike_count}; "
                        f"expected {self.expected_spike_count} "
                        f"using threshold {self.spike_threshold:.1f} mV; "
                        f"{bpap_parameters}."
                    )
                else:
                    spike_notes = (
                        f"Full-trace soma spike count={spike_count}; "
                        f"expected {self.expected_spike_count}; "
                        f"{bpap_parameters}."
                    )

            fig1 = bpap.plot_amp_vs_dist(
                soma_amp,
                dend_amps,
                dend_dist,
                apic_amps,
                apic_dist,
                show_figure=False,
                save_figure=True,
                output_dir=out_dir,
                output_fname="back-propagating_action_potential.pdf",
                do_fit=False,
            )
            fig2 = bpap.plot_recordings(
                show_figure=False,
                save_figure=True,
                output_dir=out_dir,
                output_fname="back-propagating_action_potential_recordings.pdf",
            )

            figures = [figure for figure in [fig1, fig2] if figure is not None]
            details = notes
            if spike_notes:
                details = f"{details}\n{spike_notes}" if details else spike_notes
            if trace_diagnostic_notes:
                details = (
                    f"{details}\n{trace_diagnostic_notes}" if details else trace_diagnostic_notes
                )
            return TestResult(
                name=self.name,
                passed=bool(validated and spike_guard_passed),
                details=details,
                figures=figures,
            )
        finally:
            neuron_globals.load_params(saved_params)


class IVCurveTest(ValidationTest):
    """IV curve should have a positive slope."""

    def __init__(
        self,
        *,
        n_processes: int | None = None,
        simulator_config: SimulatorConfig,
    ) -> None:
        """Initialize the IV test with shared simulator conditions."""
        self.simulator_config = simulator_config
        self.n_processes = n_processes

    @property
    def name(self) -> str:
        return ValidationName.IV_CURVE

    def run(self, template_params: Any, rheobase: float, out_dir: Path) -> TestResult:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        amps, steady_states = compute_plot_iv_curve(
            Cell.from_template_parameters(template_params),
            rheobase=rheobase,
            threshold_voltage=-40.0,
            nb_bins=5,
            show_figure=False,
            save_figure=True,
            output_dir=out_dir,
            output_fname="iv_curve.pdf",
            n_processes=self.n_processes,
            celsius=self.simulator_config.celsius,
            v_init=self.simulator_config.v_init,
        )

        fig_path = out_dir / "iv_curve.pdf"

        if len(amps) < _MIN_CURVE_POINTS or len(steady_states) < _MIN_CURVE_POINTS:
            return TestResult(
                name=self.name,
                passed=False,
                details="Not enough data points to determine slope.",
                figures=[fig_path],
            )

        slope = np.polyfit(amps, steady_states, 1)[0]
        passed = bool(slope > 0)

        if passed:
            details = f"Slope of IV curve = {slope:.2f} is positive."
        else:
            details = f"Slope of IV curve = {slope:.2f} is not positive."

        return TestResult(name=self.name, passed=passed, details=details, figures=[fig_path])


class FICurveTest(ValidationTest):
    """FI curve should have a positive slope."""

    def __init__(
        self,
        *,
        n_processes: int | None = None,
        simulator_config: SimulatorConfig,
    ) -> None:
        """Initialize the FI test with shared simulator conditions."""
        self.simulator_config = simulator_config
        self.n_processes = n_processes

    @property
    def name(self) -> str:
        return ValidationName.FI_CURVE

    def run(self, template_params: Any, rheobase: float, out_dir: Path) -> TestResult:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        amps, spike_counts = compute_plot_fi_curve(
            Cell.from_template_parameters(template_params),
            rheobase=rheobase,
            max_current=3.0 * rheobase,
            threshold_voltage=-40.0,
            nb_bins=5,
            show_figure=False,
            save_figure=True,
            output_dir=out_dir,
            output_fname="fi_curve.pdf",
            n_processes=self.n_processes,
            celsius=self.simulator_config.celsius,
            v_init=self.simulator_config.v_init,
        )

        fig_path = out_dir / "fi_curve.pdf"

        if len(amps) < _MIN_CURVE_POINTS or len(spike_counts) < _MIN_CURVE_POINTS:
            return TestResult(
                name=self.name,
                passed=False,
                details="Not enough data points to determine slope.",
                figures=[fig_path],
            )

        slope = np.polyfit(amps, spike_counts, 1)[0]
        passed = bool(slope > 0)

        if passed:
            details = f"Slope of FI curve = {slope:.2f} is positive."
        else:
            details = f"Slope of FI curve = {slope:.2f} is not positive."

        return TestResult(name=self.name, passed=passed, details=details, figures=[fig_path])
