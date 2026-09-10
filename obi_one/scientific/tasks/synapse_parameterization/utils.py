import h5py
import numpy as np
import pandas as pd
from bluepysnap.edges import EdgePopulation
from pandas import DataFrame

from obi_one.scientific.blocks.synaptic_models.base import SynapticModelBase
from obi_one.scientific.blocks.synaptic_models.family_defaults import default_synaptic_model_for
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.unions_and_references.synaptic_model_assigner import (
    SynapticModelAssignerUnion,
)


def compatible_with(cls_a: SynapticModelBase, cls_b: SynapticModelBase) -> None:
    """Tests whether this subclass of SynapticModelBase is compatible
    with another. A required but not sufficient condition is that
    they provide the same list of synapse parameters.
    More generally, compatibility means that the .default of one
    class is functionally identical to the one of the other.
    """
    if cls_a.synapse_model_family() != cls_b.synapse_model_family():
        msg = "Synapse models incompatible! They belong to different synapse model families."
        raise ValueError(msg)
    # Below should not be needed. Just to be safe...
    param_names = cls_a.parameter_names()
    other_names = cls_b.parameter_names()
    for k in param_names:
        if k not in other_names:
            msg = "Synapse models incompatible! Parameter name mismatch."
            raise ValueError(msg)
    for k in other_names:
        if k not in param_names:
            msg = "Synapse models incompatible! Parameter name mismatch."
            raise ValueError(msg)


def check_consistent_synapse_models(lst_model_assigners: list[SynapticModelAssignerUnion]) -> None:
    # Due to the way lst_model_assigners is created, this is guaranteed to have len >= 1
    reference = lst_model_assigners[0]
    reference_model = reference.synaptic_model.block  # ty:ignore[unresolved-attribute]
    for check in lst_model_assigners[1:]:
        check_model = check.synaptic_model.block  # ty:ignore[unresolved-attribute]
        compatible_with(reference_model, check_model)


def get_default_for(
    lst_model_assigners: list[SynapticModelAssignerUnion], edge_population_name: str, circ: Circuit
) -> DataFrame:
    """Build the parameter table an edge population starts from.

    One row per edge. Parameters the edge file already carries are read from it;
    the rest are sampled from the family's registered default model. The caller
    then lets each assigner overwrite the rows it covers, so every synapse no
    assigner claims keeps what the default model produced here.
    """
    if not lst_model_assigners:
        msg = (
            f"No synaptic model assigners were given for edge population "
            f"{edge_population_name!r}, so there is no synapse model family to parameterize it."
        )
        raise ValueError(msg)

    configured_model = lst_model_assigners[0].synaptic_model.block  # ty:ignore[unresolved-attribute]
    # The family's default rather than `type(configured_model)()`: the assigners are ordered
    # by the configuration, not by biology, so taking the first one's class made an inhibitory
    # assigner in first position stamp its syn_type_id on every unclaimed synapse.
    default_model = default_synaptic_model_for(configured_model)
    # The assigners are checked against each other, never against the default. A default
    # registered for a mismatched parameter list would quietly fill the wrong columns.
    compatible_with(default_model, configured_model)

    parameter_names = default_model.parameter_names()
    ep = circ.sonata_circuit.edges[edge_population_name]
    already_parameterized = [prop_ for prop_ in ep.property_names if prop_ in parameter_names]
    to_be_filled = [prop_ for prop_ in parameter_names if prop_ not in already_parameterized]
    df = ep.get(ep.ids(), properties=already_parameterized)  # Confirmed to work for empty list
    indices = ep.get(ep.ids(), properties=["@source_node", "@target_node"])
    # Seeded from the same assigner the family came from. The synapses filled here are the ones
    # no assigner claims, so none of them owns this draw; taking the seed from the group that
    # was checked consistent keeps it reproducible and moves with a sweep over that seed.
    to_fill = default_model.sample(
        indices, rng=np.random.default_rng(lst_model_assigners[0].random_seed)
    )
    return pd.concat([df, to_fill[to_be_filled]], axis=1)


def write_back_to_edge_file(df: DataFrame, ep: EdgePopulation) -> None:
    n_edges = len(df)
    with h5py.File(ep.h5_filepath, "a") as h5:
        grp = h5["edges"][ep.name]["0"]  # TODO: Support multiple edge_group_ids
        for col in df.columns:
            if col in grp:
                if grp[col].shape[0] != n_edges:
                    msg = f"Column {col!r} has {grp[col].shape[0]} rows, expected {n_edges}"
                    raise ValueError(msg)
                grp[col][:] = df[col].to_numpy()
            else:
                grp.create_dataset(col, data=df[col].to_numpy())
