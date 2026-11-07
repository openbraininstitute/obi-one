"""ScanConfig and SingleConfig for the 01_efeature_extraction stage."""

import math
from enum import StrEnum
from typing import ClassVar, Self

from entitysdk import Client
from pydantic import Field, model_validator

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.library.entity_property_types import MappedPropertiesGroup
from obi_one.scientific.library.info_scan_config.config import (
    BlockGroup as InfoBlockGroup,
    InfoScanConfig,
)
from obi_one.scientific.library.recording_summary import gives_rheobase
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks.initialize import (
    ExtractionInitialize,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks.protocol_and_feature_selection import (  # ruff: ignore[line-too-long]
    ProtocolAndFeatureSelection,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks.settings import (
    Settings,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.protocols import (  # ruff: ignore[line-too-long]
    protocol_class_by_type,
)

# Base of the eFEL feature documentation; the frontend appends
# ``#<efel_doc_anchor>`` to deep-link a specific feature.
EFEL_DOC_BASE_URL = "https://efel.readthedocs.io/en/latest/eFeatures.html"

# Root of the eFEL docs' figure directory. Each feature class names its own
# figure file via SchemaKey.EFEL_FEATURE_IMAGE; the frontend joins the two.
EFEL_FIGURES_BASE_URL = (
    "https://raw.githubusercontent.com/openbraininstitute/eFEL/master/docs/source/_static/figures"
)


def _check_step_protocol(type_name: str, setting: str, *, rheobase: bool = False) -> None:
    """``type_name`` must name a step ``Protocol`` (giving a rheobase when ``rheobase``)."""
    cls = protocol_class_by_type(type_name)
    if cls is None:
        msg = f"`{setting}`: unknown protocol type {type_name!r}."
        raise ValueError(msg)
    if cls.ecode_class != "Step" or (rheobase and not gives_rheobase(cls)):
        msg = (
            f"`{setting}` must be a step protocol"
            f"{' recorded with a current step' if rheobase else ''}, got {type_name}"
            f" ({cls.ecode_class} eCode)."
        )
        raise ValueError(msg)


class BlockGroup(StrEnum):
    """Block groups for the extraction stage."""

    INPUTS = "Inputs"
    PROTOCOLS_FEATURES = "Protocols & features"
    SETTINGS = "Settings"


class EModelEFeatureExtractionScanConfig(InfoScanConfig):
    """ScanConfig for the experimental e-feature extraction step.

    Runs BluePyEModel's ``extract_save_features_protocols`` on the experimental
    ephys traces and writes the resulting fitness-calculator configuration to
    ``./extracted_features.json``, ready to be picked up by the optimisation
    stage. No model assets are needed at this point.
    """

    name: ClassVar[str] = "EModel EFeature Extraction"
    description: ClassVar[str] = (
        "Extract experimental e-features from ephys traces via BluePyEModel."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            InfoBlockGroup.SETUP_BLOCK_GROUP,
            BlockGroup.INPUTS,
            BlockGroup.PROTOCOLS_FEATURES,
            BlockGroup.SETTINGS,
        ],
        SchemaKey.EFEL_DOC_BASE_URL: EFEL_DOC_BASE_URL,
        SchemaKey.EFEL_FIGURES_BASE_URL: EFEL_FIGURES_BASE_URL,
        SchemaKey.PROPERTY_ENDPOINTS: {
            MappedPropertiesGroup.ELECTRICAL_CELL_RECORDINGS: (
                "/declared/mapped-electrical-cell-recording-properties"
            ),
        },
    }

    @model_validator(mode="after")
    def _check_relative_mode(self) -> Self:
        """Relative amplitudes need step protocols for the rheobase, RMP and R_in.

        bluepyefe computes each recording's rheobase from the ``rheobase_protocols``
        sweeps; BluePyEModel's threshold-based optimisation needs the RMP and input
        resistance targets, measured on two different sets of sweeps of selected
        protocols. Only amplitude-matched eCodes take relative amplitudes. These
        settings are ignored in absolute mode.
        """
        settings = self.settings
        if settings.amplitude_mode != "relative":
            return self
        selection = self.efeatures_by_protocol.selection
        for type_name in settings.rheobase_protocols:
            _check_step_protocol(type_name, "rheobase_protocols", rheobase=True)
        for setting in ("rmp_protocol", "rin_protocol"):
            type_name = getattr(settings, setting)
            _check_step_protocol(type_name, setting)
            if selection.protocol_of_type(type_name) is None:
                msg = f"`{setting}` {type_name} is not one of the selected protocols."
                raise ValueError(msg)
        if settings.rmp_protocol == settings.rin_protocol and math.isclose(
            settings.rmp_amplitude, settings.rin_amplitude
        ):
            msg = (
                f"`rmp_amplitude` and `rin_amplitude` are both {settings.rmp_amplitude}% of"
                f" {settings.rmp_protocol}; the input resistance needs a hyperpolarising"
                " amplitude distinct from the RMP one."
            )
            raise ValueError(msg)
        not_targeted = [
            p.protocol_name
            for p in selection.protocols
            if p.extraction_amplitudes and not p.amplitude_targeted
        ]
        if not_targeted:
            msg = (
                "Relative amplitudes cannot be used on protocols that are not"
                " amplitude-targeted (their eCode does not match on an amplitude):"
                f" {', '.join(not_targeted)}."
            )
            raise ValueError(msg)
        return self

    def input_entities(self, db_client: Client) -> list:
        return [r.entity(db_client=db_client) for r in self.initialize.electrical_cell_recording]

    initialize: ExtractionInitialize = Field(
        title="Inputs",
        description="Input recordings for feature extraction.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.INPUTS,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    efeatures_by_protocol: ProtocolAndFeatureSelection = Field(
        default_factory=ProtocolAndFeatureSelection,
        title="Protocols & features",
        description=(
            "Per-protocol timing, amplitudes and e-feature selection. The"
            " frontend renders a ``select_efeatures_by_protocol`` picker,"
            " restricted to the protocols returned by"
            " ``/declared/mapped-electrical-cell-recording-properties`` for the chosen"
            " recordings."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.PROTOCOLS_FEATURES,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    settings: Settings = Field(
        default_factory=Settings,
        title="Settings",
        description="Global extraction-flow parameters and amplitude mode.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETTINGS,
            SchemaKey.GROUP_ORDER: 0,
        },
    )


class EModelEFeatureExtractionSingleConfig(EModelEFeatureExtractionScanConfig, SingleConfigMixin):
    """Single-coordinate variant of :class:`EModelEFeatureExtractionScanConfig`."""
