"""NEST stimulus handlers mirroring OBI-ONE stimulus block types.

Each class translates a SONATA ``inputs`` entry (identified by its ``module``
and ``input_type``) into NEST generator devices.  Unsupported stimulus types
raise ``NestFeatureNotSupportedError`` with a descriptive message.
"""

from pathlib import Path
from typing import Any

import h5py
import numpy as np

from obi_one.scientific.tasks.nest_simulation_from_sonata.nest_blocks.base import (
    NestFeatureNotSupportedError,
    NestInputHandler,
    resolve_node_set_to_nest_nodes,
)


class NestConstantCurrentClamp(NestInputHandler):
    """Mirrors ``ConstantCurrentClampSomaticStimulus``.

    SONATA module ``linear`` with ``input_type`` ``current_clamp`` and no
    ``amp_end`` (or ``amp_end == amp_start``).
    Translates to a NEST ``dc_generator``.
    """

    def apply(  # noqa: PLR6301
        self,
        input_name: str,  # noqa: ARG002
        input_config: dict,
        node_collections: dict[str, Any],
        node_sets: dict[str, Any],
        nest: Any,
    ) -> Any:
        targets = resolve_node_set_to_nest_nodes(
            input_config["node_set"], node_collections, node_sets
        )
        amplitude_pa = input_config.get("amp_start", 0.0) * 1000.0
        delay = input_config.get("delay", 0.0)
        duration = input_config.get("duration", 1000.0)

        gen = nest.Create(
            "dc_generator",
            params={"amplitude": amplitude_pa, "start": delay, "stop": delay + duration},
        )
        nest.Connect(gen, targets)
        return gen


class NestLinearCurrentClamp(NestInputHandler):
    """Mirrors ``LinearCurrentClampSomaticStimulus``.

    SONATA module ``linear`` with ``amp_end != amp_start``.
    Approximated with a NEST ``step_current_generator`` using linear steps.
    """

    def apply(  # noqa: PLR6301
        self,
        input_name: str,  # noqa: ARG002
        input_config: dict,
        node_collections: dict[str, Any],
        node_sets: dict[str, Any],
        nest: Any,
    ) -> Any:
        targets = resolve_node_set_to_nest_nodes(
            input_config["node_set"], node_collections, node_sets
        )
        amp_start_pa = input_config.get("amp_start", 0.0) * 1000.0
        amp_end_pa = input_config.get("amp_end", amp_start_pa / 1000.0) * 1000.0
        delay = input_config.get("delay", 0.0)
        duration = input_config.get("duration", 1000.0)

        n_steps = max(2, int(duration / 1.0))
        times = np.linspace(delay, delay + duration, n_steps, endpoint=False).tolist()
        amplitudes = np.linspace(amp_start_pa, amp_end_pa, n_steps).tolist()

        gen = nest.Create(
            "step_current_generator",
            params={"amplitude_times": times, "amplitude_values": amplitudes},
        )
        nest.Connect(gen, targets)
        return gen


class NestNormallyDistributedCurrentClamp(NestInputHandler):
    """Mirrors ``NormallyDistributedCurrentClampSomaticStimulus``.

    SONATA module ``noise`` with ``input_type`` ``current_clamp`` and an
    absolute ``mean`` field (not ``mean_percent``).
    Translates to a NEST ``noise_generator``.
    """

    def apply(  # noqa: PLR6301
        self,
        input_name: str,  # noqa: ARG002
        input_config: dict,
        node_collections: dict[str, Any],
        node_sets: dict[str, Any],
        nest: Any,
    ) -> Any:
        targets = resolve_node_set_to_nest_nodes(
            input_config["node_set"], node_collections, node_sets
        )
        mean_pa = input_config.get("mean", 0.0) * 1000.0
        std_pa = np.sqrt(input_config.get("variance", 0.0)) * 1000.0
        delay = input_config.get("delay", 0.0)
        duration = input_config.get("duration", 1000.0)

        gen = nest.Create(
            "noise_generator",
            params={"mean": mean_pa, "std": std_pa, "start": delay, "stop": delay + duration},
        )
        nest.Connect(gen, targets)
        return gen


class NestMultiPulseCurrentClamp(NestInputHandler):
    """Mirrors ``MultiPulseCurrentClampSomaticStimulus``.

    SONATA module ``pulse`` with ``input_type`` ``current_clamp``.
    Translates to a NEST ``step_current_generator`` with on/off steps.
    """

    def apply(  # noqa: PLR6301
        self,
        input_name: str,  # noqa: ARG002
        input_config: dict,
        node_collections: dict[str, Any],
        node_sets: dict[str, Any],
        nest: Any,
    ) -> Any:
        targets = resolve_node_set_to_nest_nodes(
            input_config["node_set"], node_collections, node_sets
        )
        amp_pa = input_config.get("amp_start", 0.0) * 1000.0
        delay = input_config.get("delay", 0.0)
        duration = input_config.get("duration", 1000.0)
        width_ms = input_config.get("width", 5.0)
        freq_hz = input_config.get("frequency", 1.0)
        period_ms = 1000.0 / freq_hz if freq_hz > 0 else duration

        times: list[float] = []
        amplitudes: list[float] = []
        t = delay
        end = delay + duration
        while t < end:
            times.append(t)
            amplitudes.append(amp_pa)
            pulse_end = min(t + width_ms, end)
            times.append(pulse_end)
            amplitudes.append(0.0)
            t += period_ms

        if not times:
            times = [delay]
            amplitudes = [0.0]

        gen = nest.Create(
            "step_current_generator",
            params={"amplitude_times": times, "amplitude_values": amplitudes},
        )
        nest.Connect(gen, targets)
        return gen


class NestSinusoidalCurrentClamp(NestInputHandler):
    """Mirrors ``SinusoidalCurrentClampSomaticStimulus``.

    SONATA module ``sinusoidal`` with ``input_type`` ``current_clamp``.
    Translates to a NEST ``ac_generator``.
    """

    def apply(  # noqa: PLR6301
        self,
        input_name: str,  # noqa: ARG002
        input_config: dict,
        node_collections: dict[str, Any],
        node_sets: dict[str, Any],
        nest: Any,
    ) -> Any:
        targets = resolve_node_set_to_nest_nodes(
            input_config["node_set"], node_collections, node_sets
        )
        amp_pa = input_config.get("amp_start", 0.0) * 1000.0
        freq_hz = input_config.get("frequency", 1.0)
        delay = input_config.get("delay", 0.0)
        duration = input_config.get("duration", 1000.0)

        gen = nest.Create(
            "ac_generator",
            params={
                "amplitude": amp_pa,
                "frequency": freq_hz,
                "start": delay,
                "stop": delay + duration,
            },
        )
        nest.Connect(gen, targets)
        return gen


class NestOrnsteinUhlenbeckCurrentClamp(NestInputHandler):
    """Mirrors ``OrnsteinUhlenbeckCurrentSomaticStimulus``.

    SONATA module ``ornstein_uhlenbeck`` with ``input_type`` ``current_clamp``.
    Approximated with a NEST ``noise_generator``.
    """

    def apply(  # noqa: PLR6301
        self,
        input_name: str,  # noqa: ARG002
        input_config: dict,
        node_collections: dict[str, Any],
        node_sets: dict[str, Any],
        nest: Any,
    ) -> Any:
        targets = resolve_node_set_to_nest_nodes(
            input_config["node_set"], node_collections, node_sets
        )
        mean_pa = input_config.get("mean", 0.0) * 1000.0
        sigma_pa = input_config.get("sigma", 0.0) * 1000.0
        delay = input_config.get("delay", 0.0)
        duration = input_config.get("duration", 1000.0)

        gen = nest.Create(
            "noise_generator",
            params={"mean": mean_pa, "std": sigma_pa, "start": delay, "stop": delay + duration},
        )
        nest.Connect(gen, targets)
        return gen


class NestSynapseReplay(NestInputHandler):
    """Mirrors ``PoissonSpikeStimulus``, ``FullySynchronousSpikeStimulus``,
    and ``SinusoidalPoissonSpikeStimulus``.

    SONATA module ``synapse_replay`` with ``input_type`` ``spikes``.
    Loads pre-generated spike times from the SONATA spike HDF5 file and
    creates NEST ``spike_generator`` devices for each source neuron.
    """

    def apply(  # noqa: PLR6301
        self,
        input_name: str,
        input_config: dict,
        node_collections: dict[str, Any],
        node_sets: dict[str, Any],
        nest: Any,
    ) -> Any:
        spike_file = input_config.get("spike_file")
        if spike_file is None:
            msg = (
                f"Synapse replay input '{input_name}' requires a 'spike_file' field "
                f"in the SONATA config."
            )
            raise NestFeatureNotSupportedError(msg)

        spike_path = Path(spike_file)
        if not spike_path.is_absolute():
            msg = (
                f"Spike file path '{spike_file}' for input '{input_name}' "
                f"must be resolved to an absolute path before applying."
            )
            raise NestFeatureNotSupportedError(msg)

        targets = resolve_node_set_to_nest_nodes(
            input_config["node_set"], node_collections, node_sets
        )

        generators = []
        with h5py.File(spike_path, "r") as f:
            spikes_grp = f["spikes"]
            for pop_name in spikes_grp:
                grp = spikes_grp[pop_name]
                if "node_ids" in grp:
                    node_ids = grp["node_ids"][:]
                elif "gids" in grp:
                    node_ids = grp["gids"][:]
                else:
                    continue

                timestamps = grp["timestamps"][:]
                unique_ids = np.unique(node_ids)

                for nid in unique_ids:
                    spike_times = sorted(timestamps[node_ids == nid].tolist())
                    if spike_times:
                        gen = nest.Create(
                            "spike_generator",
                            params={
                                "spike_times": spike_times,
                                "allow_offgrid_times": True,
                            },
                        )
                        nest.Connect(gen, targets)
                        generators.append(gen)

        return generators


def _raise_unsupported(input_name: str, description: str, reason: str) -> Any:
    """Raise NestFeatureNotSupportedError for an unsupported stimulus type."""
    msg = f"Input '{input_name}': {description} is not supported in NEST. {reason}"
    raise NestFeatureNotSupportedError(msg)


class NestRelativeConstantCurrentClamp(NestInputHandler):
    """Mirrors ``RelativeConstantCurrentClampSomaticStimulus``. NOT SUPPORTED."""

    def apply(self, input_name: str, input_config: dict, *_a: Any, **_kw: Any) -> Any:  # noqa: ARG002, PLR6301
        return _raise_unsupported(
            input_name,
            "Relative constant current clamp (SONATA module 'relative_linear')",
            "Requires per-cell threshold current data from biophysical NEURON models.",
        )


class NestRelativeLinearCurrentClamp(NestInputHandler):
    """Mirrors ``RelativeLinearCurrentClampSomaticStimulus``. NOT SUPPORTED."""

    def apply(self, input_name: str, input_config: dict, *_a: Any, **_kw: Any) -> Any:  # noqa: ARG002, PLR6301
        return _raise_unsupported(
            input_name,
            "Relative linear current clamp (SONATA module 'relative_linear' with percent_end)",
            "Requires per-cell threshold current data from biophysical NEURON models.",
        )


class NestRelativeNormallyDistributedCurrentClamp(NestInputHandler):
    """Mirrors ``RelativeNormallyDistributedCurrentClampSomaticStimulus``. NOT SUPPORTED."""

    def apply(self, input_name: str, input_config: dict, *_a: Any, **_kw: Any) -> Any:  # noqa: ARG002, PLR6301
        return _raise_unsupported(
            input_name,
            "Relative normally distributed current clamp (SONATA module 'noise' with mean_percent)",
            "Requires per-cell threshold current data from biophysical NEURON models.",
        )


class NestSubthresholdCurrentClamp(NestInputHandler):
    """Mirrors ``SubthresholdCurrentClampSomaticStimulus``. NOT SUPPORTED."""

    def apply(self, input_name: str, input_config: dict, *_a: Any, **_kw: Any) -> Any:  # noqa: ARG002, PLR6301
        return _raise_unsupported(
            input_name,
            "Subthreshold current clamp (SONATA module 'subthreshold')",
            "Requires per-cell threshold current data from biophysical NEURON models.",
        )


class NestHyperpolarizingCurrentClamp(NestInputHandler):
    """Mirrors ``HyperpolarizingCurrentClampSomaticStimulus``. NOT SUPPORTED."""

    def apply(self, input_name: str, input_config: dict, *_a: Any, **_kw: Any) -> Any:  # noqa: ARG002, PLR6301
        return _raise_unsupported(
            input_name,
            "Hyperpolarizing current clamp (SONATA module 'hyperpolarizing')",
            "Requires per-cell holding current data from biophysical NEURON models.",
        )


class NestOrnsteinUhlenbeckConductanceClamp(NestInputHandler):
    """Mirrors ``OrnsteinUhlenbeckConductanceSomaticStimulus``. NOT SUPPORTED."""

    def apply(self, input_name: str, input_config: dict, *_a: Any, **_kw: Any) -> Any:  # noqa: ARG002, PLR6301
        return _raise_unsupported(
            input_name,
            "Ornstein-Uhlenbeck conductance clamp "
            "(module 'ornstein_uhlenbeck', type 'conductance')",
            "Conductance-based injection with reversal potential is not available in NEST.",
        )


class NestRelativeOrnsteinUhlenbeckCurrentClamp(NestInputHandler):
    """Mirrors ``RelativeOrnsteinUhlenbeckCurrentSomaticStimulus``. NOT SUPPORTED."""

    def apply(self, input_name: str, input_config: dict, *_a: Any, **_kw: Any) -> Any:  # noqa: ARG002, PLR6301
        return _raise_unsupported(
            input_name,
            "Relative Ornstein-Uhlenbeck current clamp (module 'relative_ornstein_uhlenbeck')",
            "Requires per-cell threshold current data from biophysical NEURON models.",
        )


class NestRelativeOrnsteinUhlenbeckConductanceClamp(NestInputHandler):
    """Mirrors ``RelativeOrnsteinUhlenbeckConductanceSomaticStimulus``. NOT SUPPORTED."""

    def apply(self, input_name: str, input_config: dict, *_a: Any, **_kw: Any) -> Any:  # noqa: ARG002, PLR6301
        return _raise_unsupported(
            input_name,
            "Relative Ornstein-Uhlenbeck conductance clamp "
            "(module 'relative_ornstein_uhlenbeck', type 'conductance')",
            "Requires per-cell input conductance data from biophysical NEURON models.",
        )


class NestSEClamp(NestInputHandler):
    """Mirrors ``SEClampSomaticStimulus``. NOT SUPPORTED."""

    def apply(self, input_name: str, input_config: dict, *_a: Any, **_kw: Any) -> Any:  # noqa: ARG002, PLR6301
        return _raise_unsupported(
            input_name,
            "Single electrode voltage clamp (SONATA module 'seclamp')",
            "Voltage clamp is a NEURON-specific feature.",
        )


class NestSpatiallyUniformElectricField(NestInputHandler):
    """Mirrors ``SpatiallyUniformElectricFieldStimulus``. NOT SUPPORTED."""

    def apply(self, input_name: str, input_config: dict, *_a: Any, **_kw: Any) -> Any:  # noqa: ARG002, PLR6301
        return _raise_unsupported(
            input_name,
            "Spatially uniform electric field stimulus (module 'spatially_uniform_e_field')",
            "Extracellular stimulation requires morphologically-detailed neuron models.",
        )


class NestTemporallyCosineSpatiallyUniformElectricField(NestInputHandler):
    """Mirrors ``TemporallyCosineSpatiallyUniformElectricFieldStimulus``. NOT SUPPORTED."""

    def apply(self, input_name: str, input_config: dict, *_a: Any, **_kw: Any) -> Any:  # noqa: ARG002, PLR6301
        return _raise_unsupported(
            input_name,
            "Temporally cosine spatially uniform electric field stimulus",
            "Extracellular stimulation requires morphologically-detailed neuron models.",
        )


def get_input_handler(input_config: dict) -> NestInputHandler:  # noqa: PLR0911, PLR0912, C901
    """Return the appropriate handler for a SONATA input entry.

    Dispatch is based on the ``module`` and ``input_type`` fields,
    plus the presence of certain fields that disambiguate subtypes.
    """
    module = input_config.get("module", "")
    input_type = input_config.get("input_type", "")

    if module == "linear" and input_type == "current_clamp":
        if "amp_end" in input_config and input_config["amp_end"] != input_config.get("amp_start"):
            return NestLinearCurrentClamp()
        return NestConstantCurrentClamp()

    if module == "relative_linear" and input_type == "current_clamp":
        if "percent_end" in input_config:
            return NestRelativeLinearCurrentClamp()
        return NestRelativeConstantCurrentClamp()

    if module == "noise" and input_type == "current_clamp":
        if "mean_percent" in input_config:
            return NestRelativeNormallyDistributedCurrentClamp()
        return NestNormallyDistributedCurrentClamp()

    if module == "pulse" and input_type == "current_clamp":
        return NestMultiPulseCurrentClamp()

    if module == "sinusoidal" and input_type == "current_clamp":
        return NestSinusoidalCurrentClamp()

    if module == "subthreshold" and input_type == "current_clamp":
        return NestSubthresholdCurrentClamp()

    if module == "hyperpolarizing" and input_type == "current_clamp":
        return NestHyperpolarizingCurrentClamp()

    if module == "ornstein_uhlenbeck":
        if input_type == "conductance":
            return NestOrnsteinUhlenbeckConductanceClamp()
        return NestOrnsteinUhlenbeckCurrentClamp()

    if module == "relative_ornstein_uhlenbeck":
        if input_type == "conductance":
            return NestRelativeOrnsteinUhlenbeckConductanceClamp()
        return NestRelativeOrnsteinUhlenbeckCurrentClamp()

    if module == "seclamp":
        return NestSEClamp()

    if module == "synapse_replay" and input_type == "spikes":
        return NestSynapseReplay()

    if module == "spatially_uniform_e_field":
        return NestSpatiallyUniformElectricField()

    msg = (
        f"Unknown SONATA input module '{module}' with input_type '{input_type}'. "
        f"No NEST handler is registered for this combination."
    )
    raise NestFeatureNotSupportedError(msg)
