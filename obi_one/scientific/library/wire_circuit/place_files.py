import os
from pathlib import Path
from entitysdk import models, types, Client

def place_morphologies_for(
        mdl: models.MEModel,
        client: Client,
        path_ascii: Path,
        path_h5: Path
    ) -> tuple[Path | None, Path | None]:
    morph = mdl.morphology
    if morph is None:
        return (None, None)

    asset_dict = {
        asset.content_type: asset for asset in morph.assets if asset.label == types.AssetLabel.morphology
    }
    if morph.id is not None and morph.name is not None:
        if types.ContentType.application_asc in asset_dict.keys():
            client.download_file(
                entity_id=morph.id,
                entity_type=models.CellMorphology,
                asset_id=asset_dict[types.ContentType.application_asc].id,
                output_path=path_ascii / (morph.name + ".asc")
            )
        if types.ContentType.application_x_hdf5 in asset_dict.keys():
            client.download_file(
                entity_id=morph.id,
                entity_type=models.CellMorphology,
                asset_id=asset_dict[types.ContentType.application_x_hdf5].id,
                output_path=path_h5 / (morph.name + ".h5")
            )
        return (path_ascii / (morph.name + ".asc"), path_h5 / (morph.name + ".h5"))
    return (None, None)

def place_hoc_files_for(
        mdl: models.MEModel,
        client: Client,
        path_hoc: Path
    ):
    emodel = mdl.emodel
    if emodel is None:
        return

    asset_dict = {
        asset.label: asset for asset in emodel.assets
    }
    if emodel.id is not None and types.AssetLabel.neuron_hoc in asset_dict.keys():
        hoc_asset = asset_dict[types.AssetLabel.neuron_hoc]
        client.download_file(
            entity_id=emodel.id,
            entity_type=models.EModel,
            asset_id=hoc_asset.id,
            output_path=path_hoc / hoc_asset.path
        )

def place_all_morphologies(
        memodels: dict[str, models.MEModel],
        client: Client,
        circuit_root: Path
    ) -> tuple[
        dict[str, dict[str, str] | str],
        dict[str, tuple[Path | None, Path | None]]
    ]:
    morph_file_dict = {}
    path_ascii = circuit_root / "morphologies" / "ascii"
    path_h5 = circuit_root / "morphologies" / "h5"
    os.makedirs(str(path_ascii), exist_ok=True)
    os.makedirs(str(path_h5), exist_ok=True)
    for memodel_name, memodel in memodels.items():
        morph_file_dict[memodel_name] = place_morphologies_for(memodel, client, path_ascii, path_h5)
    return ({
            "alternate_morphologies": {
                "h5v1": "$BASE_DIR/morphologies/h5",
                "neurolucida-asc": "$BASE_DIR/morphologies/ascii"
            },
            "morphologies_dir": "$BASE_DIR/morphologies"
        },
        morph_file_dict)

def place_all_hoc_files(
        memodels: dict[str, models.MEModel],
        client: Client,
        circuit_root: Path
    ) -> dict[str, dict[str, str] | str]:
    path_hoc = circuit_root / "hoc"
    os.makedirs(str(path_hoc), exist_ok=True)
    for memodel in memodels.values():
        place_hoc_files_for(
            memodel, client, path_hoc
        )
    return {
        "biophysical_neuron_models_dir": "$BASE_DIR/hoc"
    }
