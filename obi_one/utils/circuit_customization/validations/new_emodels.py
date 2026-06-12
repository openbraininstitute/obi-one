"""Circuit customization-related validations."""

import uuid
from multiprocessing import Process, Queue
from pathlib import Path
import shutil
import subprocess

from entitysdk import Client
import libsonata

from obi_one.scientific.validations.emodels import bluecellulab_initializable
from obi_one.scientific.validations.emodels import check_mechanisms
from obi_one.utils.circuit import get_mechanisms_suffixes
from obi_one.utils.circuit_customization.download import download_mechanisms
from obi_one.utils.mechanisms import clean_compiled_mechanisms, compile_mechanisms


def check_hoc_mechanisms_compatible_with_circuit(db_client: Client, hoc_path: str|Path, circuit_id: str|uuid.UUID) -> None:
    """Checks that the mechanisms declared in the hoc file are compatible with the mechanisms used in the circuit.
    
    This is done by downloading the mechanisms from the circuit, extracting their suffixes, and checking that the suffixes of the mechanisms declared in the hoc file are in the set of suffixes from the circuit.
    Raises an error if any of the declared mechanisms in the hoc file is not compatible with the circuit.
    """
    expected_suffixes = get_mechanisms_suffixes(circuit_id=circuit_id, db_client=db_client)
    check_mechanisms(hoc_path=hoc_path, expected_suffixes=expected_suffixes)


def compile_mechs_and_load_hoc(circuit_id: str|uuid.UUID, hoc_path: str|Path, morphology_path: str|Path, mech_dir: str|Path, proj_context, environment, access_token, result_queue: Queue) -> None:
    """Download and compile mechanisms and check if emodel can be initialized in bluecellulab.
    
    To be called in a subprocesss to avoid errors if we try to instiantiate different models.
    """
    try:
        # the hoc file has to only use the mechanisms from the circuit for this test to pass
        db_client = Client(
            project_context=proj_context,
            environment=environment,
            token_manager=access_token,
        )
        _ = download_mechanisms(circuit_id=circuit_id, db_client=db_client, dest_dir=mech_dir)
        compile_mechanisms(mechanisms_dir=mech_dir)

        bluecellulab_initializable(hoc_path=hoc_path, morphology_path=morphology_path, template_format="v6", holding_current=0.0, threshold_current=0.0)
        result_queue.put(True)
    except Exception as e:
        result_queue.put(False)


def check_bluecellulab_initializable(paths: list[dict], circuit_id: str|uuid.UUID, proj_context, environment: str, access_token) -> None:
    """Checks that the hoc file can be initialized in bluecellulab.
    
    Args:
        paths: list of dict containing "hoc_path" and "morphology_path"
    """
    # run in just one process for simplicity. Can be parallelized later if needed.
    for path in paths:
        # remove previously compiled mechanisms for each hoc
        clean_compiled_mechanisms()
        mech_dir = Path("mechanisms")
        if mech_dir.exists():
            shutil.rmtree(mech_dir)

        result_queue = Queue()
        p = Process(
            target=compile_mechs_and_load_hoc,
            args=(circuit_id, path["hoc_path"], path["morphology_path"], mech_dir, proj_context, environment, access_token, result_queue,))
        p.start()
        p.join()

        # Get the result from the Queue
        if not result_queue.empty():
            result = result_queue.get()
            if result is False:
                raise RuntimeError(f"Emodel instantiation check in bluecellulab failed for hoc {path['hoc_path']}")
        else:
            raise RuntimeError("No result returned from subprocess when running bluecellulab instantiation check")


# see if should be moved to more general circuit utils
def read_node_file(fpath):
    """Reads a node file and returns the node population."""
    nodes = libsonata.NodeStorage(fpath)
    pop_name = next(iter(nodes.population_names))  # expects size 1
    node_pop = nodes.open_population(pop_name)
    return node_pop


def check_new_node_columns(old_node_file_path: str | Path, new_node_file_path: str | Path) -> None:
    """Checks that only the module template and the etype template columns have been changed.
    
    Raises an error if any other column has been changed, or if the attribute names are different between the two files, or if the IDs have been modified.
    """
    modifications_allowed_attrs = {"model_template", "etype"}

    old_node_pop = read_node_file(old_node_file_path)
    new_node_pop = read_node_file(new_node_file_path)

    old_attribute_names = set(old_node_pop.attribute_names)
    new_attribute_names = set(new_node_pop.attribute_names)
    old_dynamic_attribute_names = set(old_node_pop.dynamics_attribute_names)
    new_dynamic_attribute_names = set(new_node_pop.dynamics_attribute_names)

    assert new_attribute_names == old_attribute_names, f"New node file has different attribute names than old node file. Old attribute names: {old_attribute_names}, New attribute names: {new_attribute_names}"
    assert new_dynamic_attribute_names == old_dynamic_attribute_names, f"New node file has different dynamic attribute names than old node file. Old dynamic attribute names: {old_dynamic_attribute_names}, New dynamic attribute names: {new_dynamic_attribute_names}"

    old_selection = old_node_pop.select_all()
    new_selection = new_node_pop.select_all()
    assert (old_selection.flatten() == new_selection.flatten()).all(), f"IDs have been modified in the new node file. Old IDs: {old_selection.flatten()}, New IDs: {new_selection.flatten()}"

    # does this raise an error when we delete one entry in model_template?
    for attr in old_attribute_names:
        if attr not in modifications_allowed_attrs:
            old_values = old_node_pop.get_attribute(attr, old_selection)
            new_values = new_node_pop.get_attribute(attr, old_selection)
            assert (old_values == new_values).all(), f"Values of attribute {attr} have been modified in the new node file. Old values: {old_values}, New values: {new_values}"

    for dyn_attr in old_dynamic_attribute_names:
        old_values = old_node_pop.get_dynamics_attribute(dyn_attr, old_selection)
        new_values = new_node_pop.get_dynamics_attribute(dyn_attr, old_selection)
        assert (old_values == new_values).all(), f"Values of dynamic attribute {dyn_attr} have been modified in the new node file. Old values: {old_values}, New values: {new_values}"


def check_hoc_files_exist(node_file_path: str | Path, old_hoc_dir: str | Path, new_hoc_dir) -> None:
    """Checks that for each model template in the node file, there is a corresponding hoc file in the hoc directory.
    
    Raises an error if any model template in the node file does not have a corresponding hoc file in the hoc directory.

    Args:
        node_file_path: path to the new node file
        old_hoc_dir: path to the directory containing the hoc files of the parent circuit
        new_hoc_dir: path to the direcotry containing the new hoc files
    """
    node_pop = read_node_file(node_file_path)
    selection = node_pop.select_all()

    model_templates = set(node_pop.get_attribute("model_template", selection))
    for model_template in model_templates:
        assert ":" in model_template, f"Expects model template to be in the format 'extention:name', got {model_template}"
        ftype, fname = model_template.split(":", 1)
        assert ftype == "hoc", f"Expects model template to be of extention 'hoc', got {ftype}"
        old_fpath = Path(old_hoc_dir) / f"{fname}.hoc"
        new_fpath = Path(new_hoc_dir) / f"{fname}.hoc"
        if not old_fpath.exists() and not new_fpath.exists():
            raise FileNotFoundError(f"Hoc file for model template {model_template} not found in {old_hoc_dir} nor in {new_hoc_dir}")


def check_new_hoc_in_nodes_file(new_node_file_path: str | Path, new_hoc_paths: list[str|Path]) -> None:
    """Checks that the new hoc files are declared in the new node file.
    
    Raises an error if the new hoc file is not declared in the new node file.

    Args:
        new_node_file_path: path to the new node file
        new_hoc_paths: list of paths to the new hoc files.
    """
    node_pop = read_node_file(new_node_file_path)

    selection = node_pop.select_all()

    model_templates = set(node_pop.get_attribute("model_template", selection))

    for hoc_path in new_hoc_paths:
        hoc_path = Path(hoc_path)
        assert hoc_path.suffix == ".hoc", f"Expects hoc file to have .hoc extension, got {hoc_path.suffix}"
        hoc_temp_name = f"hoc:{hoc_path.stem}"
        assert hoc_temp_name in model_templates, f"Hoc template {hoc_temp_name} is not declared in the new node file. Templates declared in the new node file: {model_templates}"
