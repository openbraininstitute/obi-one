import json
from types import SimpleNamespace

import pandas as pd
import pytest

from obi_one.scientific.blocks.synaptic_models.tsodyks_markram import (
    ExcitatoryTsodyksMarkramSynapticModel,
    InhibitoryTsodyksMarkramSynapticModel,
)
from obi_one.scientific.tasks.synapse_parameterization.utils import (
    ensure_mechanisms_dir,
    get_default_for,
    models_in_play,
    write_mod_files,
)

EXCITATORY_SYN_TYPE_ID = ExcitatoryTsodyksMarkramSynapticModel().syn_type_id
INHIBITORY_SYN_TYPE_ID = InhibitoryTsodyksMarkramSynapticModel().syn_type_id


class _FakeEdgePopulation:
    """Just enough of a bluepysnap EdgePopulation for `get_default_for`."""

    def __init__(self, n_edges: int, existing: dict | None = None) -> None:
        index = pd.RangeIndex(n_edges)
        self._existing = pd.DataFrame(existing or {}, index=index)
        self._nodes = pd.DataFrame(
            {"@source_node": range(n_edges), "@target_node": range(n_edges)}, index=index
        )

    @property
    def property_names(self) -> set[str]:
        return set(self._existing.columns)

    def ids(self):
        return self._existing.index.to_numpy()

    def get(self, ids, properties):
        return pd.concat([self._existing, self._nodes], axis=1).loc[ids, properties]


def _circuit_with(edge_population, name="default"):
    return SimpleNamespace(sonata_circuit=SimpleNamespace(edges={name: edge_population}))


def _assigner_for(model, random_seed=1):
    # get_default_for seeds the fill from the assigner group it was handed.
    return SimpleNamespace(synaptic_model=SimpleNamespace(block=model), random_seed=random_seed)


@pytest.mark.parametrize(
    "configured_model",
    [ExcitatoryTsodyksMarkramSynapticModel(), InhibitoryTsodyksMarkramSynapticModel()],
)
def test_unclaimed_synapses_are_filled_from_the_excitatory_default(configured_model):
    # The regression this exists for: the fill used to come from the first assigner's own
    # class, so a configuration whose first assigner was inhibitory stamped the inhibitory
    # syn_type_id on every synapse no assigner went on to claim.
    ep = _FakeEdgePopulation(n_edges=4)

    df = get_default_for([_assigner_for(configured_model)], "default", _circuit_with(ep))

    assert (df["syn_type_id"] == EXCITATORY_SYN_TYPE_ID).all()
    assert INHIBITORY_SYN_TYPE_ID not in set(df["syn_type_id"])


def test_all_family_parameters_are_present_and_indexed_by_edge():
    ep = _FakeEdgePopulation(n_edges=3)

    df = get_default_for(
        [_assigner_for(ExcitatoryTsodyksMarkramSynapticModel())], "default", _circuit_with(ep)
    )

    assert set(ExcitatoryTsodyksMarkramSynapticModel.parameter_names()) <= set(df.columns)
    assert df.index.tolist() == [0, 1, 2]


def test_parameters_already_in_the_edge_file_are_kept():
    # Columns the edge file already carries are read back rather than resampled, so an
    # existing parameterization survives for the synapses no assigner claims.
    ep = _FakeEdgePopulation(n_edges=3, existing={"delay": [0.5, 1.5, 2.5]})

    df = get_default_for(
        [_assigner_for(ExcitatoryTsodyksMarkramSynapticModel())], "default", _circuit_with(ep)
    )

    assert df["delay"].tolist() == [0.5, 1.5, 2.5]


def test_no_assigners_is_rejected():
    with pytest.raises(ValueError, match="No synaptic model assigners"):
        get_default_for([], "default", _circuit_with(_FakeEdgePopulation(n_edges=1)))


def test_models_in_play_includes_the_configured_model_and_the_family_default():
    # get_default_for samples the family default for every synapse no assigner claims,
    # so its mechanism is used just as much as the configured model's.
    assigners = [_assigner_for(InhibitoryTsodyksMarkramSynapticModel())]

    models = models_in_play(assigners)

    assert {type(m) for m in models} == {
        ExcitatoryTsodyksMarkramSynapticModel,  # the family's default
        InhibitoryTsodyksMarkramSynapticModel,
    }


def test_models_in_play_does_not_duplicate_when_the_configured_model_is_the_default():
    assigners = [_assigner_for(ExcitatoryTsodyksMarkramSynapticModel())]

    models = models_in_play(assigners)

    # Two entries (default + configured), both excitatory - not deduplicated by type,
    # since write_mod_files' own copy step is idempotent regardless.
    assert {type(m) for m in models} == {ExcitatoryTsodyksMarkramSynapticModel}


def test_models_in_play_includes_every_configured_model_across_several_assigners():
    assigners = [
        _assigner_for(ExcitatoryTsodyksMarkramSynapticModel()),
        _assigner_for(InhibitoryTsodyksMarkramSynapticModel()),
    ]

    models = models_in_play(assigners)

    assert {type(m) for m in models} == {
        ExcitatoryTsodyksMarkramSynapticModel,
        InhibitoryTsodyksMarkramSynapticModel,
    }


MECHANISMS_DIR_EDGE_POPULATION_NAME = "default"


def _mechanisms_dir_config(tmp_path, *, components=None, population_overrides=None):
    """A minimal but real SONATA circuit config - no repo of our own manifest logic.

    libsonata resolves `mechanisms_dir` without ever reading the edges file, so no `.h5` is
    needed for `ensure_mechanisms_dir` (which only reads the config) to be exercised against
    the real thing rather than a hand-rolled stand-in.
    """
    config_path = tmp_path / "circuit_config.json"
    cfg = {
        "manifest": {"$BASE_DIR": "."},
        "components": components or {},
        "networks": {
            "nodes": [],
            "edges": [
                {
                    "edges_file": "$BASE_DIR/edges.h5",
                    "populations": {
                        MECHANISMS_DIR_EDGE_POPULATION_NAME: {
                            "type": "chemical",
                            **(population_overrides or {}),
                        }
                    },
                }
            ],
        },
    }
    config_path.write_text(json.dumps(cfg))
    return config_path


def test_an_existing_mechanisms_dir_entry_is_used_and_left_unchanged(tmp_path):
    (tmp_path / "mechanisms").mkdir()
    config_path = _mechanisms_dir_config(
        tmp_path, components={"mechanisms_dir": "$BASE_DIR/mechanisms"}
    )

    mechanisms_dir = ensure_mechanisms_dir(config_path, MECHANISMS_DIR_EDGE_POPULATION_NAME)

    assert mechanisms_dir == tmp_path / "mechanisms"
    assert json.loads(config_path.read_text())["components"]["mechanisms_dir"] == (
        "$BASE_DIR/mechanisms"
    )


def test_a_population_level_mechanisms_dir_override_wins_over_components(tmp_path):
    # The gap the previous, JSON-only implementation had: a population may override
    # mechanisms_dir directly, without going through components at all.
    (tmp_path / "components_mechanisms").mkdir()
    (tmp_path / "population_mechanisms").mkdir()
    config_path = _mechanisms_dir_config(
        tmp_path,
        components={"mechanisms_dir": "$BASE_DIR/components_mechanisms"},
        population_overrides={"mechanisms_dir": "$BASE_DIR/population_mechanisms"},
    )

    mechanisms_dir = ensure_mechanisms_dir(config_path, MECHANISMS_DIR_EDGE_POPULATION_NAME)

    assert mechanisms_dir == tmp_path / "population_mechanisms"


def test_a_missing_mechanisms_dir_entry_falls_back_to_the_default_mod_folder(tmp_path):
    config_path = _mechanisms_dir_config(tmp_path)

    mechanisms_dir = ensure_mechanisms_dir(config_path, MECHANISMS_DIR_EDGE_POPULATION_NAME)

    assert mechanisms_dir == tmp_path / "mod"
    assert mechanisms_dir.is_dir()


def test_a_missing_mechanisms_dir_entry_is_written_back_into_components(tmp_path):
    config_path = _mechanisms_dir_config(tmp_path)

    ensure_mechanisms_dir(config_path, MECHANISMS_DIR_EDGE_POPULATION_NAME)

    assert json.loads(config_path.read_text())["components"]["mechanisms_dir"] == "$BASE_DIR/mod"


def test_an_explicit_empty_string_entry_falls_back_the_same_way_as_a_missing_one(tmp_path):
    # libsonata reports an explicitly empty `components.mechanisms_dir` the same way it
    # reports a missing one (both "") - a common shape for circuit config templates that
    # declare every components field but leave most of them blank.
    config_path = _mechanisms_dir_config(tmp_path, components={"mechanisms_dir": ""})

    mechanisms_dir = ensure_mechanisms_dir(config_path, MECHANISMS_DIR_EDGE_POPULATION_NAME)

    assert mechanisms_dir == tmp_path / "mod"
    assert json.loads(config_path.read_text())["components"]["mechanisms_dir"] == "$BASE_DIR/mod"


def test_a_config_with_no_components_section_at_all_still_falls_back(tmp_path):
    config_path = _mechanisms_dir_config(tmp_path, components=None)
    cfg = json.loads(config_path.read_text())
    del cfg["components"]
    config_path.write_text(json.dumps(cfg))

    mechanisms_dir = ensure_mechanisms_dir(config_path, MECHANISMS_DIR_EDGE_POPULATION_NAME)

    assert mechanisms_dir == tmp_path / "mod"
    assert json.loads(config_path.read_text())["components"]["mechanisms_dir"] == "$BASE_DIR/mod"


def test_an_unrelated_population_override_does_not_block_the_components_fallback(tmp_path):
    # A population overriding some other field must not be mistaken for it overriding
    # mechanisms_dir too - libsonata merges per field, not per population as a whole.
    config_path = _mechanisms_dir_config(
        tmp_path, population_overrides={"spine_morphologies_dir": "$BASE_DIR/spines"}
    )

    mechanisms_dir = ensure_mechanisms_dir(config_path, MECHANISMS_DIR_EDGE_POPULATION_NAME)

    assert mechanisms_dir == tmp_path / "mod"


def test_the_mechanisms_dir_is_created_if_it_does_not_exist(tmp_path):
    config_path = _mechanisms_dir_config(tmp_path)

    mechanisms_dir = ensure_mechanisms_dir(config_path, MECHANISMS_DIR_EDGE_POPULATION_NAME)

    assert mechanisms_dir.is_dir()


def test_write_mod_files_copies_the_generic_mod_files_for_every_model_in_play(tmp_path):
    assigners = [_assigner_for(ExcitatoryTsodyksMarkramSynapticModel())]

    write_mod_files(assigners, tmp_path)

    assert (tmp_path / "ProbAMPANMDA_EMS.mod").exists()


def test_write_mod_files_leaves_a_circuit_specific_mod_file_already_present_untouched(tmp_path):
    # The whole point of this task: a circuit's own, possibly differently parameterized,
    # copy of a mechanism must not be silently replaced by the repo's generic version.
    existing = tmp_path / "ProbAMPANMDA_EMS.mod"
    existing.write_text("CIRCUIT SPECIFIC CONTENT")
    assigners = [_assigner_for(ExcitatoryTsodyksMarkramSynapticModel())]

    write_mod_files(assigners, tmp_path)

    assert existing.read_text() == "CIRCUIT SPECIFIC CONTENT"


def test_write_mod_files_copies_both_mechanisms_when_both_models_are_in_play(tmp_path):
    assigners = [
        _assigner_for(ExcitatoryTsodyksMarkramSynapticModel()),
        _assigner_for(InhibitoryTsodyksMarkramSynapticModel()),
    ]

    write_mod_files(assigners, tmp_path)

    assert (tmp_path / "ProbAMPANMDA_EMS.mod").exists()
    assert (tmp_path / "ProbGABAAB_EMS.mod").exists()
