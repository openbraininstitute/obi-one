"""Circuit customization: new emodels."""

import shutil
from pathlib import Path
import tempfile

import bluepysnap
import bluepysnap.nodes
import h5py
import libsonata
import uuid

from entitysdk import Client
from entitysdk.models import Circuit
from entitysdk.staging.circuit import stage_circuit

from obi_one.utils.circuit import (
    BCL_TEMPLATE_FORMAT,
    get_morphology_path,
    get_source_morph_dirs,
    read_node_file,
)
from obi_one.utils.circuit_customization.download import download_node_sets
from obi_one.utils.circuit_customization.upload import upload_customized_circuit
from obi_one.utils.circuit_customization.validations.new_emodels import (
    check_bluecellulab_initializable,
    check_hoc_files_exist,
    check_hoc_mechanisms_compatible_with_circuit,
    check_new_hoc_in_nodes_file,
    check_new_node_columns,
)
from obi_one.utils.circuit_registration.links import CustomizationType
from obi_one.utils.mechanisms import clean_compiled_mechanisms, compile_mechanisms

type Memodel_tuple = tuple[str, str]


def hoc_morph_names(node_pop: libsonata.NodePopulation, id_: int) -> tuple[str, str]:
    """Returns the hoc file name and morph name for a given circuit template id."""
    model_template = node_pop.get_attribute("model_template", id_)
    hoc_stem = model_template.split(":", 1)[1]  # model_template format is "hoc:hoc_path"
    hoc_fname = f"{hoc_stem}.hoc"
    morph_stem = node_pop.get_attribute("morphology", id_)
    return hoc_fname, morph_stem


def map_ids_to_updated_memodel(
    old_nodes_file_path: str | Path,
    new_nodes_file_path: str | Path,
    new_emodels_file_paths: list[str | Path],
) -> tuple[dict[int, Memodel_tuple], dict[int, Memodel_tuple], dict[Memodel_tuple, Memodel_tuple]]:
    """Creates maps of ids to memodels modified between old and new circuits.

    Also creates a mapping from new memodel to old memodel.
    """
    new_id_mapping = {}
    old_id_mapping = {}
    new_to_old_memodel_mapping = {}  # new_memodel: old_memodel
    old_node_pop = read_node_file(old_nodes_file_path)
    new_node_pop = read_node_file(new_nodes_file_path)

    new_emodels_file_names = {Path(fpath).name for fpath in new_emodels_file_paths}

    all_ids = old_node_pop.select_all().flatten()  # selection is the same for the two circuits
    for id_ in all_ids:
        old_hoc_morph_names = hoc_morph_names(old_node_pop, id_)
        new_hoc_morph_names = hoc_morph_names(new_node_pop, id_)
        # two types of modification possible: hoc file name has been changed in nodes,
        # OR hoc file name is the same, BUT a new hoc file with same name has been provided.
        if old_hoc_morph_names != new_hoc_morph_names or (
            new_hoc_morph_names[0] in new_emodels_file_names
        ):
            new_id_mapping[id_] = new_hoc_morph_names
            old_id_mapping[id_] = old_hoc_morph_names
            if new_hoc_morph_names not in new_to_old_memodel_mapping:
                new_to_old_memodel_mapping[new_hoc_morph_names] = old_hoc_morph_names

    return old_id_mapping, new_id_mapping, new_to_old_memodel_mapping


def get_hoc_morph_paths(
        old_nodes_file_path: str | Path,
        new_node_file_path: str | Path,
        new_hoc_files_paths: list[str | Path],
        parent_circuit_emodels_dir: str | Path,
        available_parent_morph_dirs: dict[str, str],
    ) -> list[dict[str: str]]:
    """Returns a list of dict containing the hoc and morphology path for each memodel."""
    hoc_morph_paths = []
    _, new_hoc_morph_names_mapping, _ = map_ids_to_updated_memodel(
        old_nodes_file_path=old_nodes_file_path,
        new_nodes_file_path=new_node_file_path,
        new_emodels_file_paths=new_hoc_files_paths,
    )

    for memodel in new_hoc_morph_names_mapping.values():
        hoc_fname, morph_stem = memodel
        selected_hoc_path = None
        for new_hoc_file_path in new_hoc_files_paths:
            new_hoc_file = str(Path(new_hoc_file_path).name)
            if hoc_fname == new_hoc_file:
                selected_hoc_path = new_hoc_file_path
        if selected_hoc_path is None:
            selected_hoc_path = Path(parent_circuit_emodels_dir) / hoc_fname
        morph_fpath = get_morphology_path(morph_stem, available_parent_morph_dirs)
        hoc_morph_paths.append({"hoc_path": selected_hoc_path, "morphology_path": morph_fpath})
    
    return hoc_morph_paths


def get_all_emodel_file_paths(
    new_nodes_file_path: str | Path, circuit_emodels_dir: str | Path
) -> set[Path]:
    """Returns emodel file paths required by the new circuit nodes file."""
    node_pop = read_node_file(new_nodes_file_path)
    selection = node_pop.select_all()
    model_templates = set(node_pop.get_attribute("model_template", selection))
    model_template_names = {temp.split(":", 1)[1] for temp in model_templates}
    return {Path(circuit_emodels_dir) / f"{name}.hoc" for name in model_template_names}


def get_biophysical_population(circuit_path: str | Path) -> bluepysnap.nodes.NodePopulation:
    """Open circuit and returns the biophysical population."""
    circuit_config_path = Path(circuit_path) / "circuit_config.json"
    circuit = bluepysnap.Circuit(circuit_config_path)
    biophysical_pops = [pop for pop in circuit.nodes.values() if pop.type == "biophysical"]
    if len(biophysical_pops) != 1:
        msg = f"Expected one and only one biophysical population, found {len(biophysical_pops)}"
        raise ValueError(msg)
    return biophysical_pops[0]


def create_modified_circuit(  # noqa: PLR0914, PLR0915, C901
    parent_circuit_path: str | Path,
    new_nodes_file_path: str | Path,
    new_emodels_file_paths: list[str | Path],
    new_circuit_path: str | Path | None = None,
) -> Path:
    """Create a new circuit with new nodes file and new emodel hoc files.

    Returns the path of the circuit.

    Args:
        parent_circuit_path: path to the parent circuit folder
        new_nodes_file_path: path to the new nodes file
        new_emodels_file_paths: list of paths to the new emodel hoc files
        new_circuit_path: path to the new circuit folder to be created.
            If None, a new folder will be created with name {parent_circuit_path}-updated.
    """
    from bluecellulab.circuit.circuit_access import EmodelProperties  # noqa: PLC0415
    from bluecellulab.tools import (  # noqa: PLC0415
        calculate_SS_voltage,
        compute_memodel_properties_v2,
    )

    # - copy old circuit into new circuit directory
    if new_circuit_path is None:
        # TODO: might want to change that in case users modify multiple times their circuits
        new_circuit_path = f"{parent_circuit_path}-updated"
    if Path(new_circuit_path).exists():
        msg = (
            f"New circuit path {new_circuit_path} already exists. Please provide a different "
            "path for the new circuit or delete the existing one."
        )
        raise ValueError(msg)
    shutil.copytree(parent_circuit_path, new_circuit_path)

    # - open new circuit
    pop = get_biophysical_population(new_circuit_path)
    circuit_emodels_dir = (
        pop.models._properties.biophysical_neuron_models_dir  # noqa: SLF001
    )
    available_morph_dirs = get_source_morph_dirs(pop)
    mechanisms_dir = Path(new_circuit_path) / "mod"  # I think this is hardcoded for all circuits

    # - get emodel and morph dirs for old circuit
    parent_pop = get_biophysical_population(parent_circuit_path)
    parent_circuit_emodels_dir = (
        parent_pop.models._properties.biophysical_neuron_models_dir  # noqa: SLF001
    )
    available_parent_morph_dirs = get_source_morph_dirs(parent_pop)

    # - create a map of circuit id to new emodel name
    old_memodel_mapping, new_memodel_mapping, new_to_old_memodel_mapping = (
        map_ids_to_updated_memodel(
            parent_pop.h5_filepath, new_nodes_file_path, new_emodels_file_paths
        )
    )

    # - create set of unique new memodels
    new_memodels_set = set(new_memodel_mapping.values())

    # - get all emodel file paths for new circuit
    all_emodel_file_paths = get_all_emodel_file_paths(new_nodes_file_path, circuit_emodels_dir)

    # - copy new nodes file and new emodels files
    for new_emodel_path in new_emodels_file_paths:
        shutil.copy(new_emodel_path, circuit_emodels_dir)
    shutil.copy(new_nodes_file_path, Path(pop.h5_filepath))

    # - remove unused (old) emodel files if any
    all_emodels_in_parent_circuit = set(Path(circuit_emodels_dir).glob("*.hoc"))
    for emodel_fpath in all_emodels_in_parent_circuit:
        if emodel_fpath not in all_emodel_file_paths:
            emodel_fpath.unlink()

    # - get holding current from parent circuit
    ihold_column_name = "@dynamics:holding_current"
    old_holding_currents = parent_pop.get(properties=[ihold_column_name])

    # - compile mechs for simulations - the mechanisms are the same for the old and new circuit
    clean_compiled_mechanisms()
    compile_mechanisms(mechanisms_dir=mechanisms_dir)

    # - compute holding voltage of all old emodels
    # fake emodel properties for dynamics params computation.
    # is needed to run v6 cells, but is not actually used in dynamics params computation
    emodel_properties_filler = EmodelProperties(holding_current=0.0, threshold_current=0.0)
    holding_voltages = {}  # old_memodel: v_hold
    for id_, old_memodel in old_memodel_mapping.items():
        if old_memodel not in holding_voltages:
            hoc_fname, morph_stem = old_memodel
            hoc_fpath = Path(parent_circuit_emodels_dir) / hoc_fname
            morph_fpath = get_morphology_path(morph_stem, available_parent_morph_dirs)
            if morph_fpath is None:
                msg = f"Could not find morphology {morph_stem}"
                raise ValueError(msg)

            holding_voltages[old_memodel] = calculate_SS_voltage(
                hoc_fpath,
                morph_fpath,
                BCL_TEMPLATE_FORMAT,
                emodel_properties_filler,
                old_holding_currents[ihold_column_name][id_],
            )

    # - compute dynamics params
    memodels_dynamics_params = {}
    for memodel in new_memodels_set:
        hoc_fname, morph_stem = memodel
        hoc_fpath = Path(circuit_emodels_dir) / hoc_fname
        morph_fpath = get_morphology_path(morph_stem, available_morph_dirs)
        if morph_fpath is None:
            msg = f"Could not find morphology {morph_stem}"
            raise ValueError(msg)
        holding_voltage = holding_voltages[new_to_old_memodel_mapping[memodel]]

        memodels_dynamics_params[memodel] = compute_memodel_properties_v2(
            hoc_fpath,
            morph_fpath,
            BCL_TEMPLATE_FORMAT,
            holding_voltage,
            emodel_properties=emodel_properties_filler,
        )

    # get mtype and layer for mecombo
    mtype_layer_df = pop.get(properties=["layer", "mtype"])

    # - update nodes file
    # base path is defined in SONATA as /nodes/<population_name>/<index>
    nodes_base_path = f"nodes/{pop.name}/0"
    dynamics_params_base_path = f"{nodes_base_path}/dynamics_params"
    # this links to new nodes file since it has been copied to new circuit directory
    with h5py.File(pop.h5_filepath, "r+") as new_node:
        for id_, memodel in new_memodel_mapping.items():
            # -- update dynamics params
            dyn_params = memodels_dynamics_params[memodel]
            new_node[dynamics_params_base_path]["holding_current"][id_] = dyn_params[
                "holding_current"
            ]
            new_node[dynamics_params_base_path]["resting_potential"][id_] = dyn_params[
                "resting_potential"
            ]
            new_node[dynamics_params_base_path]["input_resistance"][id_] = dyn_params[
                "input_resistance"
            ]
            new_node[dynamics_params_base_path]["threshold_current"][id_] = dyn_params[
                "threshold_current"
            ]

            # -- update mecombo
            hoc_stem = memodel[0].split(".hoc")[0]
            morph_stem = memodel[1]

            mtype = mtype_layer_df["mtype"].get(id_)
            layer = mtype_layer_df["layer"].get(id_)
            mecombo = f"{hoc_stem}_{mtype}_{layer}_{morph_stem}"
            new_node[nodes_base_path]["me_combo"][id_] = mecombo.encode("utf-8", "ignore")

    # - return path of updated circuit
    return Path(new_circuit_path)


def run(
    client: Client,
    parent_circuit_id: str | uuid.UUID,
    new_node_file_path: str | Path,
    new_hoc_files_paths: list[str | Path],
    name: str,
    description: str,
    new_circuit_path: str | Path | None = None,
    contact_email: str | None = None,
    dry_run: bool = False,
):
    """Validate modifications, build and upload modified circuit."""
    # check existence of new circuit path
    if Path(new_circuit_path).exists():
        msg = (
            f"Found {new_circuit_path}. Cannot create new circuit. "
            "Please provide a path that is empty."
        )
        raise FileExistsError(msg)

    # download parent circuit
    with tempfile.TemporaryDirectory() as parent_circuit_path:
        circuit_model = client.get_entity(entity_id=parent_circuit_id, entity_type=Circuit)
        stage_circuit(client=client, model=circuit_model, output_dir=Path(parent_circuit_path))
        parent_pop = get_biophysical_population(parent_circuit_path)
        parent_circuit_emodels_dir = (
            parent_pop.models._properties.biophysical_neuron_models_dir  # noqa: SLF001
        )
        available_parent_morph_dirs = get_source_morph_dirs(parent_pop)
        old_nodes_file_path = parent_pop.h5_filepath

        # validate
        check_hoc_mechanisms_compatible_with_circuit(
            db_client=client,
            hoc_paths=new_hoc_files_paths,
            circuit_id=parent_circuit_id,
        )
        check_new_node_columns(
            old_node_file_path=old_nodes_file_path,
            new_node_file_path=new_node_file_path,
        )
        print("debug: after check new node columns")
        check_hoc_files_exist(
            node_file_path=new_node_file_path,
            old_hoc_dir=parent_circuit_emodels_dir,
            new_hoc_file_paths=new_hoc_files_paths,
        )
        check_new_hoc_in_nodes_file(
            new_node_file_path=new_node_file_path,
            new_hoc_paths=new_hoc_files_paths,
        )

        # TODO: try to have consitent namings
        hoc_morph_paths = get_hoc_morph_paths(
            old_nodes_file_path=old_nodes_file_path,
            new_node_file_path=new_node_file_path,
            new_hoc_files_paths=new_hoc_files_paths,
            parent_circuit_emodels_dir=parent_circuit_emodels_dir,
            available_parent_morph_dirs=available_parent_morph_dirs,
        )

        check_bluecellulab_initializable(
            db_client=client,
            paths=hoc_morph_paths,
            circuit_id=parent_circuit_id,
        )

        # build
        # first have to download whole circuit
        new_circuit_path = create_modified_circuit(  # noqa: PLR0914, PLR0915, C901
            parent_circuit_path=parent_circuit_path,
            new_nodes_file_path=new_node_file_path,
            new_emodels_file_paths=new_hoc_files_paths,
            new_circuit_path=new_circuit_path, # path, str or None
        )

    # upload
    return upload_customized_circuit(
        client=client,
        name=name,
        description=description,
        circuit_path=new_circuit_path,
        customized_from=uuid.UUID(parent_circuit_id),
        customization_type=CustomizationType.emodel_addition,
        contact_email=contact_email,
        dry_run=dry_run,
    )
