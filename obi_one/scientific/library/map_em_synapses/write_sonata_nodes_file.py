import pandas
import voxcell


# def access_cave_client_table(client, table_name):
#     tbl = client.materialize.query_table(table_name)
#     counts = tbl["pt_root_id"].value_counts()
#     tbl = tbl.set_index('pt_root_id').loc[counts.index[counts == 1]]
#     return tbl

def get_specified_tables(em_dataset, db_client, specs):
    lst_tbls = []
    for _x in specs.values():
        if _x["table"] not in lst_tbls:
            lst_tbls.append(_x["table"])
    return dict([(tbl_name, em_dataset.neuron_info_df(tbl_name, db_client=db_client))
                 for tbl_name in lst_tbls])

def resolve_position_to_xyz(resolutions):
    def func(lst_xyz):
        if hasattr(lst_xyz, "__iter__"):
            return pandas.Series(dict([
                (_col, lst_xyz[_i] * resolutions[_col])
                for _i, _col in enumerate(["x", "y", "z"])
            ]))
        return pandas.Series(dict([
                (_col, -1)
                for _i, _col in enumerate(["x", "y", "z"])
            ]))
    return func


def assemble_collection_from_specs(em_dataset, db_client, specs, pt_root_mapping):
    tables = get_specified_tables(em_dataset, db_client, specs)

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
    return voxcell.CellCollection.from_dataframe(out_df)


def write_nodes(fn_out, population_name, cell_collection, write_mode="w"):
    cell_collection.population_name=population_name
    cell_collection.save_sonata(fn_out, mode=write_mode)


