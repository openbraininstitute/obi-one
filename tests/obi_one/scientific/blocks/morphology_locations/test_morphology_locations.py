import pytest
from pydantic import ValidationError

import obi_one as obi
from obi_one.core.schema import SchemaKey
from obi_one.scientific.library.entity_property_types import (
    CircuitUsability,
    MappedPropertiesGroup,
)


def test_random_morphology_locations_defaults_to_all_available_section_types():
    locations = obi.RandomMorphologyLocations(
        random_seed=0,
        number_of_locations=2,
    )

    assert locations.section_types is None


def test_random_morphology_locations_accepts_tuple_section_types():
    locations = obi.RandomMorphologyLocations(
        random_seed=0,
        number_of_locations=2,
        section_types=(3, 4),
    )

    assert locations.section_types == (3, 4)


def test_random_morphology_locations_accepts_list_of_tuple_section_types_for_scan():
    locations = obi.RandomMorphologyLocations(
        random_seed=0,
        number_of_locations=2,
        section_types=[(3,), (4,), (3, 4)],
    )

    assert locations.section_types == [(3,), (4,), (3, 4)]


def test_random_morphology_locations_rejects_invalid_section_type():
    with pytest.raises(ValidationError):
        obi.RandomMorphologyLocations(
            random_seed=0,
            number_of_locations=2,
            section_types=(1,),
        )


def test_morphology_locations_have_circuit_usability_metadata():
    usability = obi.RandomMorphologyLocations.model_json_schema()[
        SchemaKey.BLOCK_USABILITY_DICTIONARY
    ]

    assert usability[SchemaKey.PROPERTY_GROUP] == MappedPropertiesGroup.CIRCUIT
    assert usability[SchemaKey.PROPERTY] == CircuitUsability.SHOW_MORPHOLOGY_LOCATIONS
