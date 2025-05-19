import pandas
import numpy
import os.path

from voxcell import CellCollection

_C_NRN_LOCS = ["x", "y", "z"]
_PREF_SRC = "source__"

__unit_rot = numpy.array([
    [1, 0, 0],
    [0, 1, 0],
    [0, 0, 1]
]).astype(float)

def source_resolution(client):
    resolutions = numpy.array(
        [client.info.get_datastack_info()["viewer_resolution_{0}".format(_coord)]
        for _coord in ["x", "y", "z"]]
    )
    return resolutions

def neuron_info_df(client, table_name, filters, add_position=True):
    q_cells = client.materialize.query_table(table_name)

    for k, v in filters.items():
        q_cells = q_cells.loc[q_cells[k] == v]

    vc = q_cells["pt_root_id"].value_counts()
    q_cells = q_cells.set_index("pt_root_id").loc[vc[vc == 1].index]

    if add_position:
        resolutions = source_resolution(client)
        nrn_locs = q_cells["pt_position"].apply(lambda _x: pandas.Series(_x * resolutions / 1000.0,
                                                                        index=_C_NRN_LOCS))
        q_cells = pandas.concat([q_cells, nrn_locs], axis=1)

    return q_cells

def neuron_info_to_collection(nrn, name, cols_to_rename, cols_to_keep):
    nrn["orientation"] = [__unit_rot for _ in range(len(nrn))]
    if "orientation" not in cols_to_keep:
        cols_to_keep = list(cols_to_keep) + ["orientation"]

    rename_dict = {}
    for _col in cols_to_rename:
        rename_dict[_col] = _PREF_SRC + _col

    nrn_out = pandas.concat([nrn[list(rename_dict.keys())].rename(columns=rename_dict),
                nrn[cols_to_keep]
    ], axis=1)
    nrn_out["pt_root_id"] = nrn_out.index
    nrn_out["morphology"] = nrn_out["pt_root_id"].astype(str)
    nrn_out.index = pandas.RangeIndex(1, len(nrn_out) + 1)

    coll = CellCollection.from_dataframe(nrn_out)
    coll.population_name = name

    return coll

def collection_to_neuron_info(path_to_file, must_exist=True):
    if os.path.isfile(path_to_file):
        coll = CellCollection.load_sonata(path_to_file)
        return coll.properties, coll.population_name
    elif must_exist:
        raise ValueError("{0} is not a valid file!".format(path_to_file))
    
    empty_df = pandas.DataFrame({
        "x": [],
        "y": [],
        "z": [],
        "pt_root_id": []
    })
    return empty_df, "microns_extrinsic"
