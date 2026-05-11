import obi_one as obi


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