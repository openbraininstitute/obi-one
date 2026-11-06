import morphio
import pandas as pd
import pytest
from morphio import PointLevel, SectionType
from morphio.mut import Morphology as MutMorphology
from pydantic import TypeAdapter, ValidationError

from obi_one.core.schema import SchemaKey
from obi_one.scientific.blocks.morphology_locations.clustered import (
    ClusteredMorphologyLocations,
    ClusteredPathDistanceMorphologyLocations,
)
from obi_one.scientific.blocks.morphology_locations.explicit import (
    ExplicitMorphologyLocations,
    MorphologyLocationPoint,
)
from obi_one.scientific.blocks.morphology_locations.path_distance import (
    PathDistanceMorphologyLocations,
)
from obi_one.scientific.blocks.morphology_locations.random import RandomMorphologyLocations
from obi_one.scientific.library.entity_property_types import (
    CircuitUsability,
    MappedPropertiesGroup,
)
from obi_one.scientific.library.morphology_locations import (
    _SEC_ID,
    _SEC_LOC,
    _SEG_ID,
    _SEG_OFF,
    OptimizedMorphologyPathDistanceCalculator,
    add_normalized_section_offset,
)
from obi_one.scientific.unions_and_references.morphology_locations import (
    CircuitMorphologyLocationUnion,
    MorphologyLocationUnion,
)


def test_random_morphology_locations_requires_section_types():
    with pytest.raises(ValidationError):
        RandomMorphologyLocations(
            random_seed=0,
            number_of_locations=2,
        )


def test_random_morphology_locations_accepts_tuple_section_types():
    locations = RandomMorphologyLocations(
        random_seed=0,
        number_of_locations=2,
        section_types=(3, 4),
    )

    assert locations.section_types == (3, 4)


def test_random_morphology_locations_accepts_list_of_tuple_section_types_for_scan():
    locations = RandomMorphologyLocations(
        random_seed=0,
        number_of_locations=2,
        section_types=[(3,), (4,), (3, 4)],
    )

    assert locations.section_types == [(3,), (4,), (3, 4)]


def test_generated_morphology_locations_report_configured_output_count():
    locations = RandomMorphologyLocations(number_of_locations=3, section_types=(3, 4))

    assert locations.output_location_count() == 3


def test_generated_morphology_locations_report_no_count_for_parameter_sweeps():
    locations = RandomMorphologyLocations(number_of_locations=[2, 3], section_types=(3, 4))

    assert locations.output_location_count() is None


def test_explicit_morphology_locations_report_selected_point_count():
    locations = ExplicitMorphologyLocations(
        locations=(
            MorphologyLocationPoint(section_id=1, offset=0.25),
            MorphologyLocationPoint(section_id=2, offset=0.75),
        )
    )

    assert locations.output_location_count() == 2


def test_explicit_morphology_locations_report_no_count_without_selection():
    locations = ExplicitMorphologyLocations()

    assert locations.output_location_count() is None


@pytest.mark.parametrize("parameter", ["number_of_locations", "random_seed", "section_types"])
def test_explicit_morphology_locations_do_not_expose_sampling_parameters(parameter):
    """Hand-picked points are not sampled, so the sampling knobs must not exist at all."""
    schema_properties = ExplicitMorphologyLocations.model_json_schema()["properties"]

    assert parameter not in ExplicitMorphologyLocations.model_fields
    assert parameter not in schema_properties


@pytest.mark.parametrize("parameter", ["number_of_locations", "random_seed", "section_types"])
def test_generated_morphology_locations_expose_sampling_parameters(parameter):
    assert parameter in RandomMorphologyLocations.model_fields


@pytest.mark.parametrize(
    "block_type",
    [
        RandomMorphologyLocations,
        ClusteredMorphologyLocations,
        ClusteredPathDistanceMorphologyLocations,
        PathDistanceMorphologyLocations,
    ],
)
def test_every_generated_block_owns_the_group_count(block_type):
    """n_groups moved onto the shared base, so every generated block carries it (default 1)."""
    assert "n_groups" in block_type.model_fields
    assert block_type.model_fields["n_groups"].default == 1


def test_explicit_morphology_locations_do_not_expose_a_group_count():
    """A hand-picked block is always a single group (one presynaptic neuron)."""
    assert "n_groups" not in ExplicitMorphologyLocations.model_fields
    assert "n_groups" not in ExplicitMorphologyLocations.model_json_schema()["properties"]


def test_group_count_must_be_positive():
    with pytest.raises(ValidationError, match="greater than 0"):
        RandomMorphologyLocations(number_of_locations=4, n_groups=0, section_types=(3, 4))


@pytest.mark.parametrize(
    ("retired_type", "expected_class"),
    [
        ("RandomGroupedMorphologyLocations", RandomMorphologyLocations),
        ("ClusteredGroupedMorphologyLocations", ClusteredMorphologyLocations),
    ],
)
def test_retired_grouped_type_deserialises_onto_its_base_block(retired_type, expected_class):
    """Configs saved with a retired grouped type still load, remapped and keeping n_groups."""
    payload = {
        "type": retired_type,
        "number_of_locations": 4,
        "n_groups": 3,
        "section_types": [3, 4],
        "random_seed": 0,
    }
    if expected_class is ClusteredMorphologyLocations:
        payload["n_clusters"] = 2

    block = TypeAdapter(MorphologyLocationUnion).validate_python(payload)

    assert isinstance(block, expected_class)
    assert block.type == expected_class.__name__
    assert block.n_groups == 3


def test_retired_grouped_type_is_remapped_through_the_circuit_union():
    block = TypeAdapter(CircuitMorphologyLocationUnion).validate_python(
        {
            "type": "RandomGroupedMorphologyLocations",
            "number_of_locations": 4,
            "n_groups": 2,
            "section_types": [3, 4],
            "random_seed": 0,
        }
    )

    assert isinstance(block, RandomMorphologyLocations)
    assert block.n_groups == 2


def test_explicit_morphology_locations_do_not_expose_a_neuron_set():
    """The selected points already belong to the single neuron being simulated."""
    assert "neuron_set" not in ExplicitMorphologyLocations.model_fields


def test_generated_morphology_locations_expose_a_neuron_set():
    assert "neuron_set" in RandomMorphologyLocations.model_fields


def test_random_morphology_locations_rejects_invalid_section_type():
    with pytest.raises(ValidationError):
        RandomMorphologyLocations(
            random_seed=0,
            number_of_locations=2,
            section_types=(1,),
        )


def test_random_morphology_locations_rejects_axon_section_type():
    with pytest.raises(ValidationError):
        RandomMorphologyLocations(
            random_seed=0,
            number_of_locations=2,
            section_types=(2,),
        )


def test_morphology_locations_have_circuit_usability_metadata():
    usability = RandomMorphologyLocations.model_json_schema()[SchemaKey.BLOCK_USABILITY_DICTIONARY]

    assert usability[SchemaKey.PROPERTY_GROUP] == MappedPropertiesGroup.CIRCUIT
    assert usability[SchemaKey.PROPERTY] == CircuitUsability.SHOW_MORPHOLOGY_LOCATIONS


@pytest.mark.parametrize(
    ("block_type", "kwargs"),
    [
        (RandomMorphologyLocations, {"random_seed": -1}),
        (RandomMorphologyLocations, {"number_of_locations": 0}),
        (RandomMorphologyLocations, {"number_of_locations": 20_001}),
        (ClusteredMorphologyLocations, {"n_clusters": 0}),
        (ClusteredMorphologyLocations, {"cluster_max_distance": -1.0}),
        (PathDistanceMorphologyLocations, {"path_dist_mean": -1.0}),
        (PathDistanceMorphologyLocations, {"path_dist_tolerance": 0.0}),
        (ClusteredPathDistanceMorphologyLocations, {"path_dist_sd": 0.0}),
    ],
)
def test_morphology_locations_reject_invalid_numeric_parameters(block_type, kwargs):
    with pytest.raises(ValidationError):
        block_type(**kwargs)


@pytest.mark.parametrize(
    "block_type",
    [
        ClusteredMorphologyLocations,
        ClusteredPathDistanceMorphologyLocations,
    ],
)
def test_clustered_morphology_locations_require_at_least_one_location_per_cluster(block_type):
    with pytest.raises(ValidationError, match="Number of locations"):
        block_type(number_of_locations=2, n_clusters=3, section_types=(3, 4))


def test_normalized_section_offset_includes_segment_offset():
    # One root section of length 20 (two segments of 10). A point in segment 1 (which starts
    # 10 along the section) at offset 5 sits 15 along a 20-long section -> normalized 0.75.
    mut = MutMorphology()
    mut.append_root_section(
        PointLevel([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [20.0, 0.0, 0.0]], [1.0, 1.0, 1.0]),
        SectionType.axon,
    )
    morphology = morphio.Morphology(mut)
    path_distance_calculator = OptimizedMorphologyPathDistanceCalculator(morphology)
    dataframe = pd.DataFrame(
        {
            _SEC_ID: [1],
            _SEG_ID: [1],
            _SEG_OFF: [5.0],
        }
    )

    add_normalized_section_offset(dataframe, morphology, path_distance_calculator)

    assert dataframe[_SEC_LOC].to_list() == [0.75]
