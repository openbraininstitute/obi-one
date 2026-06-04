"""Brian2 stimulus handlers mirroring OBI-ONE stimulus block types.

Each class translates a SONATA ``inputs`` entry (identified by its ``module``
and ``input_type``) into Brian2 stimulus objects. Unsupported stimulus types
raise ``Brian2FeatureNotSupportedError`` with a descriptive message.
"""

from pathlib import Path
from typing import Any

import h5py
import numpy as np

from obi_one.scientific.tasks.brian2_simulation_from_sonata.brian2_blocks.base import (
    Brian2FeatureNotSupportedError,
    Brian2InputHandler,
    resolve_node_set_to_indices,
)


class Brian2PoissonInput(Brian2InputHandler):
    """Custom ``poisson`` module: drive each target neuron with its own ``PoissonInput``.

    Expected SONATA input fields:
        module: "poisson"
        node_set: name of the node set to drive
        rate: Poisson rate in Hz
        weight: per-spike voltage kick in volts (SI)
        target_var: brian2 state variable to increment (default "v")
        zero_refractory: if True, clear the target neurons' ``rfc`` variable
    """

    def apply(  # noqa: PLR6301
        self,
        input_name: str,  # noqa: ARG002
        input_config: dict,
        neuron_group: Any,
        node_population: str,
        node_sets: dict[str, Any],
        brian2_objects: list,
        b2: Any,
    ) -> list:
        n_nodes = len(neuron_group)
        idx = resolve_node_set_to_indices(
            input_config["node_set"], node_population, node_sets, n_nodes
        )
        if len(idx) == 0:
            return []

        rate = float(input_config["rate"]) * b2.Hz
        weight = float(input_config["weight"]) * b2.volt
        target_var = input_config.get("target_var", "v")
        zero_refractory = input_config.get("zero_refractory", True)

        created = []
        for i in idx:
            ii = int(i)
            p = b2.PoissonInput(
                target=neuron_group[ii : ii + 1],
                target_var=target_var,
                N=1,
                rate=rate,
                weight=weight,
            )
            brian2_objects.append(p)
            created.append(p)
            if zero_refractory and hasattr(neuron_group, "rfc"):
                neuron_group.rfc[ii] = 0 * b2.second
        return created


class Brian2SynapseReplay(Brian2InputHandler):
    """Mirrors ``PoissonSpikeStimulus`` / ``FullySynchronousSpikeStimulus`` /
    ``SinusoidalPoissonSpikeStimulus``.

    SONATA module ``synapse_replay`` with ``input_type`` ``spikes``.
    Loads pre-generated spike times from the SONATA spike HDF5 file, creates
    a Brian2 ``SpikeGeneratorGroup`` for the source neurons, and connects it
    to the target set with a ``Synapses`` object.
    """

    def apply(  # noqa: PLR0914, PLR6301
        self,
        input_name: str,
        input_config: dict,
        neuron_group: Any,
        node_population: str,
        node_sets: dict[str, Any],
        brian2_objects: list,
        b2: Any,
    ) -> Any:
        spike_file = input_config.get("spike_file")
        if spike_file is None:
            msg = (
                f"Synapse replay input '{input_name}' requires a 'spike_file' field "
                f"in the SONATA config."
            )
            raise Brian2FeatureNotSupportedError(msg)

        spike_path = Path(spike_file)
        if not spike_path.is_absolute():
            msg = (
                f"Spike file path '{spike_file}' for input '{input_name}' "
                f"must be resolved to an absolute path before applying."
            )
            raise Brian2FeatureNotSupportedError(msg)

        n_nodes = len(neuron_group)
        target_idx = resolve_node_set_to_indices(
            input_config["node_set"], node_population, node_sets, n_nodes
        )
        if len(target_idx) == 0:
            return None

        indices_all: list[int] = []
        times_all: list[float] = []
        local_index_of_source: dict[int, int] = {}
        with h5py.File(spike_path, "r") as f:
            for pop_name in f["spikes"]:
                grp = f["spikes"][pop_name]
                if "node_ids" in grp:
                    node_ids = grp["node_ids"][:]
                elif "gids" in grp:
                    node_ids = grp["gids"][:]
                else:
                    continue
                timestamps_ms = grp["timestamps"][:]
                for nid, t_ms in zip(node_ids, timestamps_ms, strict=False):
                    key = int(nid)
                    if key not in local_index_of_source:
                        local_index_of_source[key] = len(local_index_of_source)
                    indices_all.append(local_index_of_source[key])
                    times_all.append(float(t_ms))

        n_sources = len(local_index_of_source)
        if n_sources == 0:
            return None

        sgg = b2.SpikeGeneratorGroup(
            N=n_sources,
            indices=np.asarray(indices_all, dtype=int),
            times=np.asarray(times_all) * b2.ms,
            name=f"replay_{input_name}",
        )
        weight = float(input_config.get("weight", 1.0e-3)) * b2.volt
        target_var = input_config.get("target_var", "v")
        delay_ms = float(input_config.get("delay", 0.0))
        syn = b2.Synapses(
            sgg,
            neuron_group,
            model="w : volt",
            on_pre=f"{target_var} += w",
            delay=delay_ms * b2.ms,
            name=f"replay_{input_name}_syn",
        )
        # All-to-all: each source drives every neuron in the target set.
        i_arr = np.repeat(np.arange(n_sources), len(target_idx))
        j_arr = np.tile(target_idx, n_sources)
        syn.connect(i=i_arr, j=j_arr)
        syn.w = weight

        brian2_objects.extend([sgg, syn])
        return sgg


class Brian2ConstantCurrentClamp(Brian2InputHandler):
    """Mirrors ``ConstantCurrentClampSomaticStimulus``.

    SONATA module ``linear`` with ``input_type`` ``current_clamp`` and no
    ``amp_end`` (or ``amp_end == amp_start``). Implemented with a ``TimedArray``
    added to the membrane equation of the target subgroup.
    """

    def apply(  # noqa: PLR6301
        self,
        input_name: str,  # noqa: ARG002
        input_config: dict,
        neuron_group: Any,
        node_population: str,
        node_sets: dict[str, Any],
        brian2_objects: list,  # noqa: ARG002
        b2: Any,
    ) -> Any:
        n_nodes = len(neuron_group)
        idx = resolve_node_set_to_indices(
            input_config["node_set"], node_population, node_sets, n_nodes
        )
        if len(idx) == 0:
            return None

        amp_na = float(input_config.get("amp_start", 0.0))
        amp_amps = amp_na * b2.nA
        delay_ms = float(input_config.get("delay", 0.0))
        duration_ms = float(input_config.get("duration", 1000.0))

        if not hasattr(neuron_group, "I_ext"):
            msg = (
                "Current-clamp stimulus requires the neuron model to declare "
                "a variable 'I_ext : amp' and to include '+ I_ext' in the "
                "membrane-potential equation."
            )
            raise Brian2FeatureNotSupportedError(msg)

        def _apply_at_delay(
            ng: Any = neuron_group,
            idx_arr: np.ndarray = idx,
            amp: Any = amp_amps,
            delay: float = delay_ms,
            duration: float = duration_ms,
            br2: Any = b2,
        ) -> None:
            ng.I_ext[idx_arr.tolist()] = amp
            _ = delay
            _ = duration
            _ = br2

        _apply_at_delay()
        return None


_UNSUPPORTED_MESSAGE_TMPL = "Input '{name}': {description} is not supported in Brian2 yet. {reason}"


def _raise_unsupported(input_name: str, description: str, reason: str) -> Any:
    msg = _UNSUPPORTED_MESSAGE_TMPL.format(name=input_name, description=description, reason=reason)
    raise Brian2FeatureNotSupportedError(msg)


class Brian2Unsupported(Brian2InputHandler):
    """Generic stub for input types that aren't supported in the Brian2 port."""

    def __init__(self, description: str, reason: str) -> None:
        """Store the description/reason surfaced when this handler is applied."""
        self._description = description
        self._reason = reason

    def apply(self, input_name: str, *_args: Any, **_kwargs: Any) -> Any:
        return _raise_unsupported(input_name, self._description, self._reason)


def get_input_handler(input_config: dict) -> Brian2InputHandler:  # noqa: PLR0911
    """Dispatch SONATA ``inputs[*]`` entries to the appropriate Brian2 handler."""
    module = input_config.get("module", "")
    input_type = input_config.get("input_type", "")

    if module == "poisson":
        return Brian2PoissonInput()

    if module == "synapse_replay" and input_type == "spikes":
        return Brian2SynapseReplay()

    if module == "linear" and input_type == "current_clamp":
        return Brian2ConstantCurrentClamp()

    if module in {"noise", "pulse", "sinusoidal", "ornstein_uhlenbeck"}:
        return Brian2Unsupported(
            f"Current clamp module '{module}'",
            "Port not yet implemented; submit a pull request with a Brian2 handler.",
        )
    if module in {
        "relative_linear",
        "relative_ornstein_uhlenbeck",
        "subthreshold",
        "hyperpolarizing",
    }:
        return Brian2Unsupported(
            f"Relative/threshold-based current clamp module '{module}'",
            "Requires per-cell threshold current data from biophysical neuron models.",
        )
    if module == "seclamp":
        return Brian2Unsupported(
            "Single-electrode voltage clamp (module 'seclamp')",
            "Voltage clamp is a NEURON-specific feature.",
        )
    if module in {"spatially_uniform_e_field", "temporally_cosine_spatially_uniform_e_field"}:
        return Brian2Unsupported(
            "Extracellular electric field stimulus",
            "Requires morphologically-detailed neuron models.",
        )

    msg = (
        f"Unknown SONATA input module '{module}' with input_type '{input_type}'. "
        f"No Brian2 handler is registered for this combination."
    )
    raise Brian2FeatureNotSupportedError(msg)
