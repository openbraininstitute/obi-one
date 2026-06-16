"""Circuit customization-related validations."""

import shutil
import uuid
from multiprocessing import Process, Queue
from pathlib import Path

from entitysdk import Client

from obi_one.scientific.validations.emodels import bluecellulab_initializable, check_mechanisms
from obi_one.utils.circuit import BCL_TEMPLATE_FORMAT, get_mechanisms_suffixes, read_node_file
from obi_one.utils.circuit_customization.download import download_mechanisms
from obi_one.utils.mechanisms import clean_compiled_mechanisms, compile_mechanisms


def check_hoc_mechanisms_compatible_with_circuit(
    db_client: Client, hoc_paths: list[str | Path], circuit_id: str | uuid.UUID
) -> None:
    """Checks hoc mechanisms are compatible with the circuit mechanisms.

    This downloads circuit mechanisms, extracts their suffixes, and checks that hoc
    mechanism suffixes are included in that set.
    """
    expected_suffixes = get_mechanisms_suffixes(circuit_id=circuit_id, db_client=db_client)
    for hoc_path in hoc_paths:
        check_mechanisms(hoc_path=hoc_path, expected_suffixes=expected_suffixes)


def check_bluecellulab_initializable_subprocess(
    circuit_id: str | uuid.UUID,
    hoc_path: str | Path,
    morphology_path: str | Path,
    result_queue: Queue,
) -> None:
    """Download and compile mechanisms and check if emodel can be initialized in bluecellulab.

    To be called in a subprocesss to avoid errors if we try to instiantiate different models.
    """
    try:
        bluecellulab_initializable(
            hoc_path=hoc_path,
            morphology_path=morphology_path,
            template_format=BCL_TEMPLATE_FORMAT,
            holding_current=0.0,
            threshold_current=0.0,
        )
        result_queue.put(True)  # noqa: FBT003
    except Exception:  # noqa: BLE001
        result_queue.put(False)  # noqa: FBT003


def check_bluecellulab_initializable(
    db_client: Client,
    paths: list[dict],
    circuit_id: str | uuid.UUID,
) -> None:
    """Checks that the hoc file can be initialized in bluecellulab.

    Args:
        paths: list of dict containing "hoc_path" and "morphology_path"
        circuit_id: circuit identifier used to download mechanisms
        proj_context: entitysdk project context
        environment: entitysdk environment name
        access_token: entitysdk access token manager
    """
    # run in just one process for simplicity. Can be parallelized later if needed.
    for path in paths:
        # remove previously compiled mechanisms for each hoc
        clean_compiled_mechanisms()
        mech_dir = Path("mechanisms")
        if mech_dir.exists():
            shutil.rmtree(mech_dir)

        _ = download_mechanisms(
            circuit_id=str(circuit_id), db_client=db_client, dest_dir=Path(mech_dir)
        )
        compile_mechanisms(mechanisms_dir=mech_dir)

        result_queue = Queue()
        p = Process(
            target=check_bluecellulab_initializable_subprocess,
            args=(
                circuit_id,
                path["hoc_path"],
                path["morphology_path"],
                result_queue,
            ),
        )
        p.start()
        p.join()

        # Get the result from the Queue
        if not result_queue.empty():
            result = result_queue.get()
            if result is False:
                msg = (
                    f"Emodel instantiation check in bluecellulab failed for hoc {path['hoc_path']}"
                )
                raise RuntimeError(msg)
        else:
            msg = "No result returned from subprocess when running bluecellulab instantiation check"
            raise RuntimeError(msg)


def check_new_node_columns(old_node_file_path: str | Path, new_node_file_path: str | Path) -> None:
    """Checks that only model_template and etype columns have been changed.

    Raises an error if any other column has been changed, if attribute names differ between
    files, or if IDs have been modified.
    """
    modifications_allowed_attrs = {"model_template", "etype"}

    old_node_pop = read_node_file(old_node_file_path)
    new_node_pop = read_node_file(new_node_file_path)

    old_attribute_names = set(old_node_pop.attribute_names)
    new_attribute_names = set(new_node_pop.attribute_names)
    old_dynamic_attribute_names = set(
        attr for attr in old_node_pop.dynamics_attribute_names if "deprecated" not in attr
    )
    new_dynamic_attribute_names = set(
        attr for attr in new_node_pop.dynamics_attribute_names if "deprecated" not in attr
    )

    if new_attribute_names != old_attribute_names:
        msg = (
            "New node file has different attribute names than old node file. "
            f"Old attribute names: {old_attribute_names}, "
            f"New attribute names: {new_attribute_names}"
        )
        raise ValueError(msg)

    if new_dynamic_attribute_names != old_dynamic_attribute_names:
        msg = (
            "New node file has different dynamic attribute names than old node file. "
            f"Old dynamic attribute names: {old_dynamic_attribute_names}, "
            f"New dynamic attribute names: {new_dynamic_attribute_names}"
        )
        raise ValueError(msg)

    old_selection = old_node_pop.select_all()
    new_selection = new_node_pop.select_all()
    if not (old_selection.flatten() == new_selection.flatten()).all():
        msg = (
            "IDs have been modified in the new node file. "
            f"Old IDs: {old_selection.flatten()}, New IDs: {new_selection.flatten()}"
        )
        raise ValueError(msg)

    for attr in old_attribute_names:
        if attr not in modifications_allowed_attrs:
            old_values = old_node_pop.get_attribute(attr, old_selection)
            new_values = new_node_pop.get_attribute(attr, old_selection)
            if not (old_values == new_values).all():
                msg = (
                    f"Values of attribute {attr} have been modified in the new node file. "
                    f"Old values: {old_values}, New values: {new_values}"
                )
                raise ValueError(msg)

    # remove this check because dynamic params are not consistent depending where you take the node file from
    # ask Christoph if we should fix the data or if I just remove this check.
    # I feel like the check is not really needed anyway, since dynamic params are re-computed afterwards
    # for dyn_attr in old_dynamic_attribute_names:
    #     old_values = old_node_pop.get_dynamics_attribute(dyn_attr, old_selection)
    #     new_values = new_node_pop.get_dynamics_attribute(dyn_attr, new_selection)
    #     if not (old_values == new_values).all():
    #         msg = (
    #             f"Values of dynamic attribute {dyn_attr} have been modified in the new node file. "
    #             f"Old values: {old_values}, New values: {new_values}"
    #         )
    #         raise ValueError(msg)


# modify this: hsould accpet list of hoc paths, not a dir
def check_hoc_files_exist(
    node_file_path: str | Path, old_hoc_dir: str | Path, new_hoc_file_paths: list[str | Path]
) -> None:
    """Checks that each model template in the node file has a corresponding hoc file.

    Raises an error if any model template in the node file does not have a corresponding hoc file
    in either hoc directory.

    Args:
        node_file_path: path to the new node file
        old_hoc_dir: path to the directory containing the hoc files of the parent circuit
        new_hoc_file_paths: paths to the new hoc files
    """
    node_pop = read_node_file(node_file_path)
    selection = node_pop.select_all()

    model_templates = set(node_pop.get_attribute("model_template", selection))
    new_hoc_file_stems = set(str(Path(hoc_path).stem) for hoc_path in new_hoc_file_paths)
    for model_template in model_templates:
        if ":" not in model_template:
            msg = (
                f"Expects model template to be in the format 'extention:name', got {model_template}"
            )
            raise ValueError(msg)
        ftype, fname = model_template.split(":", 1)
        if ftype != "hoc":
            msg = f"Expects model template to be of extention 'hoc', got {ftype}"
            raise ValueError(msg)
        old_fpath = Path(old_hoc_dir) / f"{fname}.hoc"
        if not old_fpath.exists() and fname not in new_hoc_file_stems:
            msg = (
                f"Hoc file for model template {model_template} not found in circuit directory "
                f"nor in provided new hoc files."
            )
            raise FileNotFoundError(msg)


def check_new_hoc_in_nodes_file(
    new_node_file_path: str | Path, new_hoc_paths: list[str | Path]
) -> None:
    """Checks that the new hoc files are declared in the new node file.

    Raises an error if the new hoc file is not declared in the new node file.

    Args:
        new_node_file_path: path to the new node file
        new_hoc_paths: list of paths to the new hoc files.
    """
    node_pop = read_node_file(new_node_file_path)

    selection = node_pop.select_all()

    model_templates = set(node_pop.get_attribute("model_template", selection))

    for hoc_path_item in new_hoc_paths:
        hoc_path = Path(hoc_path_item)
        if hoc_path.suffix != ".hoc":
            msg = f"Expects hoc file to have .hoc extension, got {hoc_path.suffix}"
            raise ValueError(msg)
        hoc_temp_name = f"hoc:{hoc_path.stem}"
        if hoc_temp_name not in model_templates:
            msg = (
                f"Hoc template {hoc_temp_name} is not declared in the new node file. "
                f"Templates declared in the new node file: {model_templates}"
            )
            raise ValueError(msg)
