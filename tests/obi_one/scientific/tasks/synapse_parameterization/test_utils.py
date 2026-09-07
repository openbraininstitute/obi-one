from types import SimpleNamespace

import pandas as pd
import pytest

from obi_one.scientific.blocks.synaptic_models.tsodyks_markram import (
    ExcitatoryTsodyksMarkramSynapticModel,
    InhibitoryTsodyksMarkramSynapticModel,
)
from obi_one.scientific.tasks.synapse_parameterization.utils import get_default_for

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


def _assigner_for(model):
    return SimpleNamespace(synaptic_model=SimpleNamespace(block=model))


@pytest.mark.parametrize(
    "configured_model",
    [ExcitatoryTsodyksMarkramSynapticModel(), InhibitoryTsodyksMarkramSynapticModel()],
)
def test_unclaimed_synapses_are_filled_from_the_excitatory_default(configured_model):
    # The regression this exists for: the fill used to come from the first assigner's own
    # class, so a configuration whose first assigner was inhibitory stamped syn_type_id 7
    # on every synapse no assigner went on to claim.
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
