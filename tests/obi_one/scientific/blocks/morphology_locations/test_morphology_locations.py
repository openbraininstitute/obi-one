from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

import obi_one as obi
from obi_one.core.schema import SchemaKey
from obi_one.scientific.library.entity_property_types import (
    CircuitUsability,
    MappedPropertiesGroup,
)
from obi_one.scientific.library.morphology_locations import (
    _SEC_ID,
    _SEC_LOC,
    _SEG_ID,
    _SEG_OFF,
    add_normalized_section_offset,
)


def test_random_morphology_locations_defaults_to_dendrite_section_types():
    locations = obi.RandomMorphologyLocations(
        random_seed=0,
        number_of_locations=2,
    )

    assert locations.section_types == (3, 4)


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


def test_random_morphology_locations_rejects_axon_section_type():
    with pytest.raises(ValidationError):
        obi.RandomMorphologyLocations(
            random_seed=0,
            number_of_locations=2,
            section_types=(2,),
        )


def test_morphology_locations_have_circuit_usability_metadata():
    usability = obi.RandomMorphologyLocations.model_json_schema()[
        SchemaKey.BLOCK_USABILITY_DICTIONARY
    ]

    assert usability[SchemaKey.PROPERTY_GROUP] == MappedPropertiesGroup.CIRCUIT
    assert usability[SchemaKey.PROPERTY] == CircuitUsability.SHOW_MORPHOLOGY_LOCATIONS


@pytest.mark.parametrize(
    ("block_type", "kwargs"),
    [
        (obi.RandomMorphologyLocations, {"random_seed": -1}),
        (obi.RandomMorphologyLocations, {"number_of_locations": 0}),
        (obi.RandomMorphologyLocations, {"number_of_locations": 20_001}),
        (obi.ClusteredMorphologyLocations, {"n_clusters": 0}),
        (obi.ClusteredMorphologyLocations, {"cluster_max_distance": -1.0}),
        (obi.PathDistanceMorphologyLocations, {"path_dist_mean": -1.0}),
        (obi.PathDistanceMorphologyLocations, {"path_dist_tolerance": 0.0}),
        (obi.ClusteredPathDistanceMorphologyLocations, {"path_dist_sd": 0.0}),
    ],
)
def test_morphology_locations_reject_invalid_numeric_parameters(block_type, kwargs):
    with pytest.raises(ValidationError):
        block_type(**kwargs)


@pytest.mark.parametrize(
    "block_type",
    [
        obi.ClusteredMorphologyLocations,
        obi.ClusteredPathDistanceMorphologyLocations,
    ],
)
def test_clustered_morphology_locations_require_at_least_one_location_per_cluster(block_type):
    with pytest.raises(ValidationError, match="Number of locations"):
        block_type(number_of_locations=2, n_clusters=3)


def test_normalized_section_offset_includes_segment_offset():
    section = SimpleNamespace(
        points=np.array(
            [
                [0.0, 0.0, 0.0],
                [10.0, 0.0, 0.0],
                [20.0, 0.0, 0.0],
            ]
        )
    )
    morphology = SimpleNamespace(sections=[section])
    path_distance_calculator = SimpleNamespace(offset=np.array([[0.0, 10.0]]))
    dataframe = pd.DataFrame(
        {
            _SEC_ID: [1],
            _SEG_ID: [1],
            _SEG_OFF: [5.0],
        }
    )

    add_normalized_section_offset(dataframe, morphology, path_distance_calculator)

    assert dataframe[_SEC_LOC].to_list() == [0.75]
