import os

import pandas  # NOQA: ICN001
import voxcell
from entitysdk import Client
from voxcell import CellCollection

from obi_one.scientific.from_id.em_dataset_from_id import EMDataSetFromID


def get_specified_tables(
    em_dataset: EMDataSetFromID, db_client: Client, cave_version: int, specs: dict
) -> tuple[dict, list]:
    lst_tbls = []
    for _x in specs.values():
        if _x["table"] not in lst_tbls:
            lst_tbls.append(_x["table"])

    dict_tpls = []
    lst_notices = []
    for tbl_name in lst_tbls:
        data, notice = em_dataset.neuron_info_df(tbl_name, cave_version, db_client=db_client)
        lst_notices.append(notice)
        dict_tpls.append((tbl_name, data))
    return dict(dict_tpls), lst_notices


def resolve_position_to_xyz(resolutions: list):  # NOQA: ANN201
    def func(lst_xyz: list) -> pandas.Series:
        if hasattr(lst_xyz, "__iter__"):
            return pandas.Series(
                {_col: lst_xyz[_i] * resolutions[_col] for _i, _col in enumerate(["x", "y", "z"])}
            )
        return pandas.Series({_col: -1 for _i, _col in enumerate(["x", "y", "z"])})

    return func


def assemble_collection_from_specs(
    em_dataset: EMDataSetFromID,
    db_client: Client,
    cave_version: int,
    specs: dict,
    pt_root_mapping: pandas.DataFrame,
) -> voxcell.CellCollection:
    tables, lst_notices = get_specified_tables(em_dataset, db_client, cave_version, specs)

    out_cols = []
    for col_out, entry in specs.items():
        col = tables[entry["table"]].reindex(pt_root_mapping.index)[entry["column"]]
        if not col_out.startswith("__"):
            col = col.fillna(entry["default"])
            col.name = col_out
        else:
            col = col.apply(resolve_position_to_xyz(entry["resolution"]))
        out_cols.append(col)
    out_df = pandas.concat(out_cols, axis=1)
    out_df = out_df.reset_index().rename(columns={"pre_pt_root_id": "pt_root_id"})
    out_df.index = pandas.Index(range(1, len(out_df) + 1))
    return voxcell.CellCollection.from_dataframe(out_df), lst_notices


def write_nodes(
    fn_out: os.PathLike,
    population_name: str,
    cell_collection: CellCollection,
    write_mode: str = "w",
) -> None:
    cell_collection.population_name = population_name
    cell_collection.save_sonata(fn_out, mode=write_mode)
