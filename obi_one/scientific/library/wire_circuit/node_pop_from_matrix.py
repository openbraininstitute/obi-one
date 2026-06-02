import pandas
import os

from conntility import ConnectivityMatrix
from entitysdk import models, types, Client
from voxcell.cell_collection import CellCollection


COL_ME_MODEL_ID_ = "me_model_id"

def from_calibration(calibration: models.MEModelCalibrationResult) -> pandas.Series:
    return pandas.Series({
        "@dynamics:holding_current": calibration.holding_current,
        "@dynamics:input_resistance": calibration.rin,
        "@dynamics:threshold_current": calibration.threshold_current,
        "@dynamics:resting_potential": -80.0  # TODO!
    })

def from_etype(etype: models.ETypeClass) -> pandas.Series:
    return pandas.Series({
        "etype": etype.pref_label
    })

def from_brain_region(region: models.BrainRegion) -> pandas.Series:
    return pandas.Series({
        "region": region.acronym
    })

def from_emodel(emodel: models.EModel) -> pandas.Series:
    asset_dict = {
        asset.label: asset
        for asset in emodel.assets
    }
    hoc_paths = os.path.splitext(asset_dict[types.AssetLabel.neuron_hoc].path)
    hoc_str = ":".join([hoc_paths[1].replace(".", ""), hoc_paths[0]])
    return pandas.Series({
        "me_combo": emodel.name,
        "model_template": hoc_str
    })

def from_mtype(mtype: models.MTypeClass) -> pandas.Series:
    return pandas.Series({
        "mtype": mtype.pref_label
    })

def from_morphology(morph: models.CellMorphology) -> pandas.Series:
    return pandas.Series({
        "morphology": morph.name
    })

def constants() -> pandas.Series:
    return pandas.Series({
        "x": 0.0,
        "y": 0.0,
        "z": 0.0,
        'orientation_w': 0.0,
        'orientation_x': 0.0,
        'orientation_y': 0.0,
        'orientation_z': 0.0
    })

def node_population_dataframe(
        M: ConnectivityMatrix,
        client: Client
    ) -> pandas.DataFrame:
    if COL_ME_MODEL_ID_ not in M.vertex_properties:
        raise ValueError("Input ConnectivityMatrix does not specify MEModel ids!")
    memodel_ids = M.vertices[COL_ME_MODEL_ID_].to_numpy()
    memodels = {
        id_str: client.get_entity(entity_id=id_str, entity_type=models.MEModel)
        for id_str in memodel_ids
    }
    additional_node_props = pandas.concat([
        pandas.concat(
            [from_calibration(memodels[k].calibration_result) for k in memodel_ids],
            axis=1
        ).transpose(),
        pandas.concat(
            [from_brain_region(memodels[k].brain_region) for k in memodel_ids],
            axis=1
        ).transpose(),
        pandas.concat(
            [from_etype(memodels[k].etypes[0]) for k in memodel_ids],
            axis=1
        ).transpose(),
        pandas.concat(
            [from_emodel(memodels[k].emodel) for k in memodel_ids],
            axis=1
        ).transpose(),
        pandas.concat(
            [from_mtype(memodels[k].mtypes[0]) for k in memodel_ids],
            axis=1
        ).transpose(),
        pandas.concat(
            [from_morphology(memodels[k].morphology) for k in memodel_ids],
            axis=1
        ).transpose(),
        pandas.concat(
            [constants() for _ in memodel_ids],
            axis=1
        ).transpose()
    ], axis=1)
    return additional_node_props

def create_cell_collection(
        M: ConnectivityMatrix,
        client: Client,
        population_name: str
    ) -> CellCollection:
    additional_props_df = node_population_dataframe(M, client)

    for col_name in additional_props_df.columns:
        M.add_vertex_property(col_name, additional_props_df[col_name].to_numpy(),
                            overwrite=True)

    coll = CellCollection.from_dataframe(M._vertex_properties, index_offset=0)
    coll.population_name = population_name
    return coll
