"""Runtime morphology capability checks for Task 2.

Loads the staged source morphology once and reports which physical source
sections it provides, alongside the modifier's myelinated capability. This lets
the params compiler reject a configured region (e.g. ``apical`` for an axon-only
or aspiny interneuron reconstruction) with an actionable error instead of
silently compiling a mechanism row that NEURON cannot place.
"""

from pathlib import Path
from typing import Any

import morphio
from pydantic import BaseModel, ConfigDict, NonNegativeInt

from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.section_lists import (
    PHYSICAL_SECTION_LIST_NAMES,
    AxonModifier,
    PhysicalSectionListName,
)

try:
    from obi_one.scientific.library.morphology_loader import load_morphology_nrn_order
except ImportError:  # pragma: no cover - exercised only if morphology_loader moves
    load_morphology_nrn_order = None  # ty:ignore[invalid-assignment]


class MorphologyCapabilities(BaseModel):
    """Capabilities discovered from the imported source morphology and modifier."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    has_myelinated: bool | None = None
    axonal_section_count: NonNegativeInt | None = None
    available_physical_sections: tuple[PhysicalSectionListName, ...] = ()
    """Physical section lists (excluding ``myelinated``) with at least one source section.

    Empty by default, which means "not inspected" — callers that construct this model directly
    (e.g. in tests) opt out of the per-region availability check in the compiler. Only
    :func:`preflight_morphology` populates this from a real morphology.
    """


# morphio.SectionType values that map onto our physical section-list vocabulary.
# morphio has no "myelinated" SectionType; myelination is tracked separately via
# ``has_myelinated`` because it is synthesized only by a compatible axon modifier.
# A staged SWC/ASC asset cannot establish a populated runtime myelinated section list.
_SECTION_TYPE_TO_PHYSICAL_NAME: dict[Any, PhysicalSectionListName] = {
    morphio.SectionType.soma: "somatic",
    morphio.SectionType.apical_dendrite: "apical",
    morphio.SectionType.basal_dendrite: "basal",
    morphio.SectionType.axon: "axonal",
}

_MINIMUM_SOURCE_AXONAL_SECTIONS: dict[AxonModifier, int] = {
    AxonModifier.REPLACE_AXON_WITH_TAPER: 3,
    AxonModifier.REPLACE_AXON_LEGACY: 2,
}


def _count_axonal_sections(morphology: Any) -> int:
    """Count source sections classified as axon by MorphIO."""
    return sum(section.type == morphio.SectionType.axon for section in morphology.sections)


def _available_physical_sections(morphology: Any) -> tuple[PhysicalSectionListName, ...]:
    """Return the physical section lists with at least one source section."""
    present: set[PhysicalSectionListName] = set()
    for section in morphology.sections:
        physical_name = _SECTION_TYPE_TO_PHYSICAL_NAME.get(section.type)
        if physical_name is not None:
            present.add(physical_name)

    soma = getattr(morphology, "soma", None)
    soma_points = getattr(soma, "points", None)
    if soma_points is not None and len(soma_points) > 0:
        present.add("somatic")

    return tuple(name for name in PHYSICAL_SECTION_LIST_NAMES if name in present)


def preflight_morphology(
    path: Path,
    axon_modifier: AxonModifier | str,
) -> MorphologyCapabilities:
    """Load the staged morphology and return its section-list capabilities.

    Counts source axon sections and enforces the modifier's known minimum
    (tapered replacement needs at least 3, legacy replacement needs at least 2).
    Also reports which physical section lists (``somatic``, ``basal``, ``apical``,
    ``axonal``) are actually present in the source reconstruction, so the compiler
    can reject a configured region the morphology does not provide.

    A staged SWC/ASC asset cannot establish a populated runtime myelinated section
    list. In no-replacement mode, ``has_myelinated`` therefore remains unknown and
    myelinated parameter rows are rejected.
    """
    if load_morphology_nrn_order is None:  # pragma: no cover - defensive
        msg = "Morphology preflight requires obi_one.scientific.library.morphology_loader."
        raise RuntimeError(msg)
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
        has_myelinated = None

    return MorphologyCapabilities(
        has_myelinated=has_myelinated,
        axonal_section_count=axonal_section_count,
        available_physical_sections=_available_physical_sections(morphology),
    )


__all__ = ["MorphologyCapabilities", "preflight_morphology"]
