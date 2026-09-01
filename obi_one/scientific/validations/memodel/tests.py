"""Complex MEModel validation tests that require custom logic.

These tests subclass ValidationTest directly because they don't fit the
composable ParametricValidation pattern (they need multi-recording stimuli,
custom analysis pipelines, or multiple measurements from the same trace).
"""

from pathlib import Path

import efel
import numpy as np

from bluecellulab.analysis.analysis import BPAP, compute_plot_fi_curve, compute_plot_iv_curve
from bluecellulab.analysis.inject_sequence import run_multirecordings_stimulus, run_stimulus
from bluecellulab.cell.core import Cell
from bluecellulab.stimulus.factory import IDRestTimings, StimulusFactory
from bluecellulab.validation.base import TestResult, ValidationTest
from bluecellulab.validation.plotting import plot_trace, plot_traces


class HyperpolarizationTest(ValidationTest):
    """Hyperpolarization: steady-state voltage during -40% step should be below RMP."""

    @property
    def name(self) -> str:
        return "Simulatable Neuron Hyperpolarization Validation"

    def run(self, template_params, rheobase: float, out_dir) -> TestResult:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        stim_factory = StimulusFactory(dt=1.0)
        step_stimulus = stim_factory.iv(threshold_current=rheobase, threshold_percentage=-40)
        recording = run_stimulus(
            template_params, step_stimulus, "soma[0]", 0.5, add_hypamp=True,
        )

        fig_path = plot_trace(
            recording, out_dir,
            fname="hyperpolarization_validation.pdf",
            title="Hyperpolarization Validation - Step at -40% of Rheobase",
        )

        trace = {
            "T": recording.time,
            "V": recording.voltage,
            "stim_start": [IDRestTimings.PRE_DELAY.value],
            "stim_end": [IDRestTimings.PRE_DELAY.value + IDRestTimings.DURATION.value],
        }
        features = efel.get_feature_values([trace], ["voltage_base", "steady_state_voltage_stimend"])
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
            details = (
                f"Hyperpolarized voltage ({ss_val:.2f} mV) is lower than "
                f"RMP ({rmp_val:.2f} mV)."
            )
        else:
            details = (
                f"Hyperpolarized voltage ({ss_val:.2f} mV) is not lower than "
                f"RMP ({rmp_val:.2f} mV)."
            )

        return TestResult(name=self.name, passed=passed, details=details, figures=[fig_path])


class RinTest(ValidationTest):
    """Input resistance should be within a biologically realistic range (< 1000 MOhm)."""

    def __init__(self, rin: float) -> None:
        self.rin = rin

    @property
    def name(self) -> str:
        return "Simulatable Neuron Input Resistance Validation"

    def run(self, template_params, rheobase: float, out_dir) -> TestResult:
        passed = bool(self.rin < 1000)

        if passed:
            details = f"Input resistance (Rin) = {self.rin:.2f} MOhm is less than 1000 MOhm."
        else:
            details = (
                f"Input resistance (Rin) = {self.rin:.2f} MOhm exceeds 1000 MOhm, "
                f"which is not biologically realistic."
            )

        return TestResult(name=self.name, passed=passed, details=details, figures=[])


class AISSpikingTest(ValidationTest):
    """AIS spiking: axon should spike before soma at 200% rheobase."""

    @property
    def name(self) -> str:
        return "Simulatable Neuron AIS Spiking Validation"

    def run(self, template_params, rheobase: float, out_dir) -> TestResult:
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
            threshold_current=rheobase, threshold_percentage=200,
        )
        recordings = run_multirecordings_stimulus(
            template_params, step_stimulus, "soma[0]", 0.5,
            add_hypamp=True,
            recording_locations=[("axon[0]", 0.5), ("soma[0]", 0.5)],
        )
        axon_recording, soma_recording = recordings

        fig1 = plot_traces(
            recordings, out_dir,
            fname="ais_spiking_validation.pdf",
            title="AIS Spiking Validation - Step at 200% of Rheobase",
            labels=["axon[0]", "soma[0]"],
        )
        fig2 = plot_traces(
            recordings, out_dir,
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
            axon_spike_time is None or soma_spike_time is None
            or len(axon_spike_time) == 0 or len(soma_spike_time) == 0
        ):
            return TestResult(
                name=self.name,
                passed=False,
                details="Could not determine spike times for axon or soma.",
                figures=[fig1, fig2],
            )

        passed = bool(axon_spike_time[0] <= soma_spike_time[0])
        if passed:
            details = "Axon spikes before soma."
        else:
            details = "Axon does not spike before soma."

        return TestResult(name=self.name, passed=passed, details=details, figures=[fig1, fig2])


class BPAPTest(ValidationTest):
    """Back-propagating action potential: amplitude should decay along dendrites."""

    def __init__(
        self,
        *,
        amplitude_factor: float = 10.0,
        sim_duration: float = 1500.0,
        stim_duration: float = 5.0,
    ) -> None:
        """Initialize the BPAP test.

        Args:
            amplitude_factor: Multiplier of rheobase for stimulus amplitude.
            sim_duration: Total simulation duration in ms.
            stim_duration: Duration of the current pulse in ms.
                The default is 5 ms. For thalamic cells that burst, try 1-2 ms
                to trigger a single AP.
        """
        self.amplitude_factor = amplitude_factor
        self.sim_duration = sim_duration
        self.stim_duration = stim_duration

    @property
    def name(self) -> str:
        return "Simulatable Neuron Back-propagating Action Potential Validation"

    def run(self, template_params, rheobase: float, out_dir) -> TestResult:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        amplitude = self.amplitude_factor * rheobase
        bpap = BPAP(Cell.from_template_parameters(template_params), stim_duration=self.stim_duration)
        bpap.run(duration=self.sim_duration, amplitude=amplitude)
        soma_amp, dend_amps, dend_dist, apic_amps, apic_dist = bpap.get_amplitudes_and_distances()

        # If no AP was detected in soma, validation fails
        if not soma_amp:
            return TestResult(
                name=self.name,
                passed=False,
                details=(
                    f"No action potential detected in soma "
                    f"(amplitude_factor={self.amplitude_factor}, "
                    f"stim_duration={self.stim_duration} ms). "
                    f"Try increasing amplitude_factor or stim_duration."
                ),
                figures=[],
            )

        validated, notes = bpap.validate(
            soma_amp, dend_amps, dend_dist, apic_amps, apic_dist,
            validate_with_fit=False,
        )

        fig1 = bpap.plot_amp_vs_dist(
            soma_amp, dend_amps, dend_dist, apic_amps, apic_dist,
            show_figure=False, save_figure=True,
            output_dir=out_dir,
            output_fname="back-propagating_action_potential.pdf",
            do_fit=False,
        )
        fig2 = bpap.plot_recordings(
            show_figure=False, save_figure=True,
            output_dir=out_dir,
            output_fname="back-propagating_action_potential_recordings.pdf",
        )

        figures = [f for f in [fig1, fig2] if f is not None]

        return TestResult(name=self.name, passed=validated, details=notes, figures=figures)


class IVCurveTest(ValidationTest):
    """IV curve should have a positive slope."""

    def __init__(
        self,
        *,
        n_processes: int | None = None,
        celsius: float = 34.0,
        v_init: float = -80.0,
    ) -> None:
        self.n_processes = n_processes
        self.celsius = celsius
        self.v_init = v_init

    @property
    def name(self) -> str:
        return "Simulatable Neuron IV Curve Validation"

    def run(self, template_params, rheobase: float, out_dir) -> TestResult:
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
            celsius=self.celsius,
            v_init=self.v_init,
        )

        fig_path = out_dir / "iv_curve.pdf"

        if len(amps) < 2 or len(steady_states) < 2:
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
        celsius: float = 34.0,
        v_init: float = -80.0,
    ) -> None:
        self.n_processes = n_processes
        self.celsius = celsius
        self.v_init = v_init

    @property
    def name(self) -> str:
        return "Simulatable Neuron FI Curve Validation"

    def run(self, template_params, rheobase: float, out_dir) -> TestResult:
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
            celsius=self.celsius,
            v_init=self.v_init,
        )

        fig_path = out_dir / "fi_curve.pdf"

        if len(amps) < 2 or len(spike_counts) < 2:
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
