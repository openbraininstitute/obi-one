"""ScanConfig and SingleConfig for the 01_efeature_extraction stage."""

from enum import StrEnum
from typing import ClassVar

from entitysdk import Client
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.library.entity_property_types import MappedPropertiesGroup
from obi_one.scientific.library.info_scan_config.config import (
    BlockGroup as InfoBlockGroup,
    InfoScanConfig,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks.initialize import (
    ExtractionInitialize,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks.protocol_and_feature_selection import (  # ruff: ignore[line-too-long]
    ProtocolAndFeatureSelection,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks.settings import (
    Settings,
)

# Base of the eFEL feature documentation; the frontend appends
# ``#<efel_doc_anchor>`` to deep-link a specific feature.
EFEL_DOC_BASE_URL = "https://efel.readthedocs.io/en/latest/eFeatures.html"

# Root of the eFEL docs' figure directory. Each feature class names its own
# figure file via SchemaKey.EFEL_FEATURE_IMAGE; the frontend joins the two.
EFEL_FIGURES_BASE_URL = (
    "https://raw.githubusercontent.com/openbraininstitute/eFEL/master/docs/source/_static/figures"
)


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
