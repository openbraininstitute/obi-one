"""Circuit customization: new emodels."""

from pathlib import Path
import bluepysnap
import glob
import h5py

import shutil

from obi_one.utils.circuit import get_morphology_path, get_source_morph_dirs
from obi_one.utils.circuit_customization.validations.new_emodels import read_node_file  # move these to more general utils
from obi_one.utils.mechanisms import clean_compiled_mechanisms, compile_mechanisms


# 1. validate stuff. 2. create circuit. 3. upload circuit.


def hoc_morph_names(node_pop, id_) -> tuple[str, str]:
    """Returns the hoc file name and morph name for a given circuit template id."""
    model_template = node_pop.get_attribute("model_template", id_)
    hoc_stem = model_template.split(":", 1)[1]  # model_template format is "hoc:hoc_path"
    hoc_fname = f"{hoc_stem}.hoc"
    morph_stem = node_pop.get_attribute("morphology", id_)
    return hoc_fname, morph_stem


def map_ids_to_updated_memodel(old_nodes_file_path: str|Path, new_nodes_file_path: str|Path, new_emodels_file_paths: str|Path) -> dict[str, str]:
    """Creates two maps of ids to memodels that have been modified. One for old circuit one for new circuit.
    
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
        if old_hoc_morph_names != new_hoc_morph_names or (new_hoc_morph_names[0] in new_emodels_file_names):
            new_id_mapping[id_] = new_hoc_morph_names
            old_id_mapping[id_] = old_hoc_morph_names
            if new_hoc_morph_names not in new_to_old_memodel_mapping:
                new_to_old_memodel_mapping[new_hoc_morph_names] = old_hoc_morph_names

    return old_id_mapping, new_id_mapping, new_to_old_memodel_mapping


def get_all_emodel_file_paths(new_nodes_file_path: str|Path, circuit_emodels_dir: str|Path) -> set[Path]:
    """Returns the set of all emodel file paths that are needed for the new circuit based on the new nodes file."""
    node_pop = read_node_file(new_nodes_file_path)
    selection = node_pop.select_all()
    model_templates = set(node_pop.get_attribute("model_template", selection))
    model_template_names = {temp.split(":", 1)[1] for temp in model_templates}
    emodel_file_paths = {Path(circuit_emodels_dir) / f"{name}.hoc" for name in model_template_names}
    return emodel_file_paths


def get_biophysical_population(circuit_path: str|Path) -> bluepysnap.nodes.NodePopulation:
    """Open circuit and returns the biophysical population."""
    circuit_config_path = Path(circuit_path) / "circuit_config.json"
    circuit = bluepysnap.Circuit(circuit_config_path)
    biophysical_pops = [
        pop for pop in circuit.nodes.values()
        if pop.type == "biophysical"
    ]
    assert len(biophysical_pops) == 1, f"Expect one and only one biophysical population, found {len(biophysical_pops)}"
    return biophysical_pops[0]


def create_modified_circuit(parent_circuit_path: str|Path, new_nodes_file_path: str|Path, new_emodels_file_paths: list[str|Path], new_circuit_path: str|Path|None = None) -> Path:
    """Create a new circuit with new nodes file and new emodel hoc files.

    Returns the path of the circuit.
    
    Args:
        parent_circuit_path: path to the parent circuit folder
        new_nodes_file_path: path to the new nodes file
        new_emodels_file_paths: list of paths to the new emodel hoc files
        new_circuit_path: path to the new circuit folder to be created.
            If None, a new folder will be created with name {parent_circuit_path}-updated.
    """
    from bluecellulab.tools import calculate_SS_voltage, compute_memodel_properties_v2
    from bluecellulab.circuit.circuit_access import EmodelProperties

    bcl_template_format = "v6"  # maybe make this a global?
    # - copy old circuit into new circuit directory
    if new_circuit_path is None:
        new_circuit_path = f"{parent_circuit_path}-updated"  # TODO: might want to change that in case users modify multiple times their circuits
    assert not Path(new_circuit_path).exists(), f"New circuit path {new_circuit_path} already exists. Please provide a different path for the new circuit or delete the existing one."
    shutil.copytree(parent_circuit_path, new_circuit_path)

    # - open new circuit
    pop = get_biophysical_population(new_circuit_path)
    circuit_emodels_dir = pop.models._properties.biophysical_neuron_models_dir  # I am using private property here. Is there another way to get this?
    available_morph_dirs = get_source_morph_dirs(pop)
    mechanisms_dir = Path(new_circuit_path) / "mod"  # I think this is hardcoded for all circuits

    # - get emodel and morph dirs for old circuit
    parent_pop = get_biophysical_population(parent_circuit_path)
    parent_circuit_emodels_dir = parent_pop.models._properties.biophysical_neuron_models_dir  # I am using private property here. Is there another way to get this?
    available_parent_morph_dirs = get_source_morph_dirs(parent_pop)

    # - create a map of circuit id to new emodel name
    old_memodel_mapping, new_memodel_mapping, new_to_old_memodel_mapping = map_ids_to_updated_memodel(parent_pop.h5_filepath, new_nodes_file_path, new_emodels_file_paths)

    # - create set of unique new memodels
    new_memodels_set = set(new_memodel_mapping.values())

    # - get all emodel file paths for new circuit
    all_emodel_file_paths = get_all_emodel_file_paths(new_nodes_file_path, circuit_emodels_dir)

    # - copy new nodes file and new emodels files
    for new_emodel_path in new_emodels_file_paths:
        shutil.copy(new_emodel_path, circuit_emodels_dir)
    shutil.copy(new_nodes_file_path, Path(pop.h5_filepath))

    # - remove unused (old) emodel files if any
    all_emodels_in_parent_circuit = set(glob.glob(str(Path(circuit_emodels_dir) / "*.hoc")))
    for emodel_fpath in all_emodels_in_parent_circuit:
        if Path(emodel_fpath) not in all_emodel_file_paths:
            Path(emodel_fpath).unlink()

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
            assert morph_fpath is not None, f"Could not find morphology {morph_stem}"

            holding_voltages[old_memodel] =  calculate_SS_voltage(
                hoc_fpath, morph_fpath, bcl_template_format, emodel_properties_filler, old_holding_currents[ihold_column_name][id_],
            )


    # - compute dynamics params
    memodels_dynamics_params = {}  # (hoc_fname, morph_fname): {"holding_curent": float, "resting_potential": float, "input_resistance": float, "threshold_current": float}
    for memodel in new_memodels_set:
        hoc_fname, morph_stem = memodel
        hoc_fpath = Path(circuit_emodels_dir) / hoc_fname
        morph_fpath = get_morphology_path(morph_stem, available_morph_dirs)
        assert morph_fpath is not None, f"Could not find morphology {morph_stem}"
        holding_voltage = holding_voltages[new_to_old_memodel_mapping[memodel]]

        memodels_dynamics_params[memodel] = compute_memodel_properties_v2(
            hoc_fpath,
            morph_fpath,
            bcl_template_format,
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
    with h5py.File(pop.h5_filepath, 'r+') as new_node:
        for id_, memodel in new_memodel_mapping.items():
            # -- update dynamics params
            dyn_params = memodels_dynamics_params[memodel]
            new_node[dynamics_params_base_path]["holding_current"][id_] = dyn_params["holding_current"]
            new_node[dynamics_params_base_path]["resting_potential"][id_] = dyn_params["resting_potential"]
            new_node[dynamics_params_base_path]["input_resistance"][id_] = dyn_params["input_resistance"]
            new_node[dynamics_params_base_path]["threshold_current"][id_] = dyn_params["threshold_current"]

            # -- update mecombo
            hoc_stem = memodel[0].split(".hoc")[0]
            morph_stem = memodel[1]

            mtype = mtype_layer_df["mtype"].get(id_)
            layer = mtype_layer_df["layer"].get(id_)
            mecombo = f"{hoc_stem}_{mtype}_{layer}_{morph_stem}"
            new_node[nodes_base_path]["me_combo"][id_] = mecombo.encode("utf-8", "ignore")

    # - return path of updated circuit
    return Path(new_circuit_path)
