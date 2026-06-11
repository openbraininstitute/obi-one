import h5py
import pandas as pd
from bluepysnap.edges import EdgePopulation
from pandas import DataFrame

from obi_one.scientific.blocks.synaptic_models.base import SynapticModelBase
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.unions.unions_synaptic_model_assigner import (
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
    synaptic_model_block = lst_model_assigners[0].synaptic_model.block  # ty:ignore[unresolved-attribute]
    default_model = type(synaptic_model_block)()
    ep = circ.sonata_circuit.edges[edge_population_name]
    already_parameterized = [
        prop_ for prop_ in ep.property_names if prop_ in synaptic_model_block.parameter_names()
    ]
    to_be_filled = [
        prop_
        for prop_ in synaptic_model_block.parameter_names()
        if prop_ not in already_parameterized
    ]
    df = ep.get(ep.ids(), properties=already_parameterized)  # Confirmed to work for empty list
    indices = ep.get(ep.ids(), properties=["@source_node", "@target_node"])
    to_fill = default_model.sample(indices)
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
