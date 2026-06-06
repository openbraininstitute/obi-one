import pandas as pd
import h5py

from pandas import DataFrame
from bluepysnap.edges import EdgePopulation

from obi_one.scientific.unions.unions_synaptic_model_assigner import (
    SynapticModelAssignerUnion,
)
from obi_one.scientific.library.circuit import Circuit

def check_consistent_synapse_models(lst_model_assigners: list[SynapticModelAssignerUnion]):
        # Due to the way lst_model_assigners is created, this is guaranteed to have len >= 1
        reference = lst_model_assigners[0]
        reference_model = reference.synaptic_model.block
        for check in lst_model_assigners[1:]:
            check_model = check.synaptic_model.block
            reference_model.compatible_with(check_model)


def get_default_for(lst_model_assigners: list[SynapticModelAssignerUnion],
                     edge_population_name: str, circ: Circuit) -> DataFrame:
    reference = lst_model_assigners[0].synaptic_model.block
    default_model = reference.default()
    ep = circ.sonata_circuit.edges[edge_population_name]
    already_parameterized = [prop_ for prop_ in ep.property_names
                                if prop_ in reference.parameter_names()]
    to_be_filled = [prop_ for prop_ in reference.parameter_names()
                    if prop_ not in already_parameterized]
    df = ep.get(ep.ids(), properties=already_parameterized)  # Confirmed to work for empty list
    indices = ep.get(ep.ids(), properties=["@source_node", "@target_node"])
    to_fill = default_model.sample(indices)
    return pd.concat([
        df, to_fill[to_be_filled]
    ], axis=1)

def write_back_to_edge_file(df: DataFrame, ep: EdgePopulation):
    with h5py.File(ep.h5_filepath, "a") as h5:  # TODO: Support write in chunks
        grp = h5["edges"][ep.name]["0"]  # TODO: Support multiple edge_group_ids
        for col in df.columns:
            if col in grp.keys():
                assert grp[col].shape[0] == len(df)
                grp[col][:] = df[col].to_numpy()
            else:
                grp.create_dataset(col, data=df[col].to_numpy())
