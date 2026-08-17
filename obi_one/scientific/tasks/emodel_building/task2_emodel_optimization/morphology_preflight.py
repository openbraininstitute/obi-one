"""Runtime morphology capability checks for Task 2."""

from pathlib import Path
from typing import Any

import morphio
from pydantic import BaseModel, ConfigDict, NonNegativeInt

from obi_one.scientific.library.morphology_loader import load_morphology_nrn_order
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.section_lists import (
    AxonModifier,
)


class MorphologyCapabilities(BaseModel):
    """Capabilities discovered from the imported source morphology and modifier."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    has_myelinated: bool | None = None
    axonal_section_count: NonNegativeInt | None = None


_MINIMUM_SOURCE_AXONAL_SECTIONS: dict[AxonModifier, int] = {
    AxonModifier.REPLACE_AXON_WITH_TAPER: 3,
    AxonModifier.REPLACE_AXON_LEGACY: 2,
}


def _count_axonal_sections(morphology: Any) -> int:
    """Count source sections classified as axon by MorphIO."""
    return sum(section.type == morphio.SectionType.axon for section in morphology.sections)


def preflight_morphology(
    path: Path,
    axon_modifier: AxonModifier | str,
    *,
    source_has_myelinated: bool | None = None,
) -> MorphologyCapabilities:
    """Validate modifier prerequisites and return source morphology capabilities.

    A SWC asset does not carry a reliable myelinated-section-list capability. For
    no-replacement mode, callers may provide a trusted entity-level capability; otherwise
    ``has_myelinated`` remains unknown and myelinated parameter rows are rejected.
    """
    if not path.is_file():
        msg = f"Morphology preflight asset does not exist: {path}."
        raise ValueError(msg)

    modifier = AxonModifier(axon_modifier)
    morphology = load_morphology_nrn_order(path)
    axonal_section_count = _count_axonal_sections(morphology)
    minimum = _MINIMUM_SOURCE_AXONAL_SECTIONS.get(modifier)
    if minimum is not None and axonal_section_count < minimum:
        msg = (
            f"Morphology '{path.name}' has {axonal_section_count} source axon sections, "
            f"but axon modifier '{modifier.value}' requires at least {minimum}."
        )
        raise ValueError(msg)

    if modifier in {
        AxonModifier.REPLACE_AXON_WITH_TAPER,
        AxonModifier.REPLACE_AXON_OLFACTORY_BULB,
    }:
        has_myelinated = True
    elif modifier in {
        AxonModifier.REPLACE_AXON_LEGACY,
        AxonModifier.BLUEPYOPT_REPLACE_AXON,
    }:
        has_myelinated = False
    else:
        has_myelinated = source_has_myelinated

    return MorphologyCapabilities(
        has_myelinated=has_myelinated,
        axonal_section_count=axonal_section_count,
    )


__all__ = ["MorphologyCapabilities", "preflight_morphology"]
