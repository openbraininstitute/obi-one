"""Block holding the list of protocols with per-protocol feature selections."""

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.tasks.emodel_optimization._01_efeature_extraction.protocols_and_features import (
    APWaveform,
    IDrest,
    IDthresh,
    IV,
    Protocol,
    ProtocolUnion,
    SAHP,
    available_features_by_protocol_name,
)


def _default_protocols() -> tuple[Protocol, ...]:
    """L5PC-style defaults — set ``extract=True`` on the same features the old
    ``ExtractionTargets`` mirror used. Amplitudes are no longer a user
    parameter (they're read from the NWB at task execution time), so this only
    pre-selects features.
    """
    idrest = IDrest()
    for fname in (
        "spikecount",
        "mean_frequency",
        "time_to_first_spike",
        "time_to_last_spike",
        "inv_time_to_first_spike",
        "inv_first_isi",
        "inv_second_isi",
        "inv_third_isi",
        "inv_last_isi",
        "ahp_depth",
        "ahp_time_from_peak",
        "min_ahp_values",
        "depol_block_bool",
        "voltage_base",
    ):
        getattr(idrest, fname).extract = True

    iv = IV()
    iv.voltage_base.extract = True
    iv.ohmic_input_resistance_vb_ssse.extract = True

    apwaveform = APWaveform()
    for fname in ("ap_amplitude", "ap1_amp", "ap_duration_half_width", "ahp_depth"):
        getattr(apwaveform, fname).extract = True

    sahp = SAHP()
    for fname in ("mean_frequency", "voltage_base", "depol_block_bool"):
        getattr(sahp, fname).extract = True

    return (IDthresh(), idrest, iv, apwaveform, sahp)


class ProtocolAndFeatureSelection(Block):
    """Per-protocol picker for timing, amplitudes, and chosen efeatures.

    Each entry in ``protocols`` is a concrete :class:`Protocol` instance
    carrying its own timing (``ton``/``toff``/``tmid``/``tmid2``), amplitudes,
    and one typed field per valid :class:`EFeature`. Whether each feature is
    actually extracted is controlled by its own ``extract`` flag. The
    catalogue of features available per protocol lives in
    ``protocols_and_features`` and is advertised to the frontend via the
    ``available_efeatures_by_protocol`` key on the field's ``json_schema_extra``.

    ``protocols`` is a tuple — not a list — so the obi-one scan framework
    leaves it alone instead of expanding it as a parameter-scan dimension.
    """

    protocols: tuple[ProtocolUnion, ...] = Field(
        default_factory=_default_protocols,
        title="Protocols",
        description=(
            "Protocols to extract features from. Defaults mirror the L5PC"
            " example; the frontend can repopulate this from the catalogue and"
            " the protocols returned by"
            " ``/declared/electrical-cell-recording-protocols``."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.SELECT_EFEATURES_BY_PROTOCOL,
            "available_efeatures_by_protocol": available_features_by_protocol_name(),
        },
    )
