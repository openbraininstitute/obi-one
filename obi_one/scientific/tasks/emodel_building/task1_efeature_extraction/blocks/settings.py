"""Global extraction-flow settings for the e-feature extraction stage.

Advanced extraction knobs that BluePyEModel's
``extract_save_features_protocols`` forwards to ``bluepyefe.extract``.

Also holds the amplitude mode and, for relative (% of rheobase) amplitudes, the
protocols the rheobase, resting membrane potential (RMP) and input resistance come
from. Per-protocol settings (amplitudes, timing) live on :class:`Protocol`.
Per-feature eFEL detection knobs live on :class:`EFeature`.
"""

from typing import Literal

from pydantic import Field, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.library.entity_property_types import (
    ElectricalCellRecordingMappedProperties,
    MappedPropertiesGroup,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.constants import (
    SPIKE_DETECTION_THRESHOLD_DESCRIPTION,
    SPIKE_DETECTION_THRESHOLD_TITLE,
    TRACE_RESAMPLING_TIMESTEP_DESCRIPTION,
    TRACE_RESAMPLING_TIMESTEP_TITLE,
)

# Percentage points of rheobase within which a sweep matches a relative target.
DEFAULT_RELATIVE_AMPLITUDE_TOLERANCE = 10.0


class Settings(Block):
    """Advanced extraction settings (statistical knobs and output toggles).

    Also holds the global eFEL detection knobs (``spike_detection_threshold``,
    ``trace_resampling_timestep``) — the base of the settings cascade. Protocols
    and features may override them (feature > protocol > global); left unset
    there, the global value applies.
    """

    # -- Global eFEL detection knobs (base of the cascade) --------------------
    spike_detection_threshold: float | None = Field(
        default=-20.0,
        title=SPIKE_DETECTION_THRESHOLD_TITLE,
        description=SPIKE_DETECTION_THRESHOLD_DESCRIPTION,
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL,
            SchemaKey.UNITS: Units.MILLIVOLTS,
        },
    )
    trace_resampling_timestep: PositiveFloat | None = Field(
        default=0.025,
        title=TRACE_RESAMPLING_TIMESTEP_TITLE,
        description=TRACE_RESAMPLING_TIMESTEP_DESCRIPTION,
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    default_std_value: PositiveFloat | list[PositiveFloat] = Field(
        default=0.01,
        title="Default std value",
        description="Replaces zero standard deviations during feature extraction.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    threshold_nvalue_save: int | list[int] = Field(
        default=1,
        title="Min values to save feature",
        description=(
            "bluepyefe ``threshold_nvalue_save``: minimum number of recordings a feature"
            " must be measured on to be kept in the output."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    bound_max_std: bool = Field(
        default=False,
        title="Bound max std",
        description=(
            "If set, cap each feature's standard deviation at its mean value after extraction."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    interpolate_rmp: bool = Field(
        default=False,
        title="Interpolate RMP",
        description=(
            "If set, estimate the resting membrane potential as ``V_hold - R_in * I_hold``"
            " when no zero-holding recording is available."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    threshold_efeature_std: float | list[float] = Field(
        default=0.0,
        title="Threshold efeature std",
        description=(
            "Floor each feature's standard deviation at"
            " ``abs(threshold_efeature_std * mean)``. Set to 0 to disable."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    minimum_protocol_delay: float | list[float] = Field(
        default=0.0,
        title="Minimum protocol delay",
        description="Protocols with a shorter initial delay are padded to this value (ms).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    # -- Amplitude mode and the relative (% of rheobase) protocols -----------
    amplitude_mode: Literal["absolute", "relative"] = Field(
        default="absolute",
        title="Amplitude mode",
        description=(
            "``absolute``: protocols' ``extraction_amplitudes`` are in nA, and the"
            " e-model is optimised and validated at those currents. ``relative``: they"
            " are in % of each recording's rheobase (from ``rheobase_protocols``), and"
            " the e-model is optimised and validated at the same % of its own"
            " threshold current, which needs the RMP and input resistance targets set"
            " below."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    rheobase_protocols: tuple[str, ...] = Field(
        default=("IDThreshProtocol",),
        min_length=1,
        title="Rheobase protocols",
        description=(
            "Relative mode: step protocols (``Protocol`` type names) whose sweeps give"
            " each recording's rheobase, the smallest amplitude firing a spike. With"
            " several, the smallest of their rheobases is used. Offered by the"
            " ``RheobaseProtocols`` property of"
            " ``/declared/mapped-electrical-cell-recording-properties``."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.ENTITY_PROPERTY_MULTI_SELECT,
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.ELECTRICAL_CELL_RECORDINGS,
            SchemaKey.PROPERTY: ElectricalCellRecordingMappedProperties.RHEOBASE_PROTOCOLS,
        },
    )
    rmp_protocol: str = Field(
        default="IVProtocol",
        min_length=1,
        title="RMP protocol",
        description=(
            "Relative mode: step protocol (``Protocol`` type name, one of the selected"
            " protocols) whose ``voltage_base`` at ``rmp_amplitude`` is the resting"
            " membrane potential the e-model is fitted to."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.ENTITY_PROPERTY_DROPDOWN,
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.ELECTRICAL_CELL_RECORDINGS,
            SchemaKey.PROPERTY: ElectricalCellRecordingMappedProperties.PROTOCOLS,
        },
    )
    rmp_amplitude: float = Field(
        default=0.0,
        title="RMP amplitude",
        description="Relative mode: amplitude (% of rheobase) of the RMP sweeps.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_INPUT,
            SchemaKey.UNITS: Units.PERCENT,
        },
    )
    rin_protocol: str = Field(
        default="IVProtocol",
        min_length=1,
        title="Input resistance protocol",
        description=(
            "Relative mode: step protocol (``Protocol`` type name, one of the selected"
            " protocols) whose ``voltage_base`` and ``ohmic_input_resistance_vb_ssse``"
            " at ``rin_amplitude`` are the holding voltage and input resistance the"
            " e-model is fitted to."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.ENTITY_PROPERTY_DROPDOWN,
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.ELECTRICAL_CELL_RECORDINGS,
            SchemaKey.PROPERTY: ElectricalCellRecordingMappedProperties.PROTOCOLS,
        },
    )
    rin_amplitude: float = Field(
        default=-20.0,
        title="Input resistance amplitude",
        description=(
            "Relative mode: amplitude (% of rheobase) of the hyperpolarising input"
            " resistance sweeps; must differ from ``rmp_amplitude`` when both use the"
            " same protocol."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_INPUT,
            SchemaKey.UNITS: Units.PERCENT,
        },
    )
    # bluepyefe's "interpolation" strategy is left out: it needs subthreshold sweeps
    # with a spike count of 0, but bluepyefe leaves their spike count unset.
    rheobase_strategy: Literal["absolute", "flush", "majority"] = Field(
        default="absolute",
        title="Rheobase strategy",
        description=(
            "Relative mode: how bluepyefe computes each recording's rheobase from the"
            " ``rheobase_protocols`` sweeps: ``absolute``"
            " (lowest amplitude with a spike), ``flush`` (lowest spiking amplitude"
            " whose next sweep also spikes) or ``majority`` (bluepyefe's binned"
            " estimate: the centre of the first 10 pA amplitude bin where most sweeps"
            " spike)."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    relative_amplitude_tolerance: PositiveFloat = Field(
        default=DEFAULT_RELATIVE_AMPLITUDE_TOLERANCE,
        title="Relative amplitude tolerance",
        description=(
            "When amplitudes are relative, a sweep is used for a target if its"
            " amplitude is within this many percentage points of rheobase of it."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_INPUT,
            SchemaKey.UNITS: Units.PERCENT,
        },
    )

    def global_efel_settings(self) -> dict:
        """Return the global eFEL settings dict — the base of the cascade.

        ``strict_stiminterval`` is fixed to True (only count spikes strictly within
        the stimulus interval) rather than exposed as a setting. A threshold or
        resampling timestep left unset (None) is omitted so eFEL falls back to its
        own default.
        """
        efel_settings: dict[str, float | bool] = {"strict_stiminterval": True}
        if self.spike_detection_threshold is not None:
            efel_settings["Threshold"] = self.spike_detection_threshold
        if self.trace_resampling_timestep is not None:
            efel_settings["interp_step"] = self.trace_resampling_timestep
        return efel_settings
