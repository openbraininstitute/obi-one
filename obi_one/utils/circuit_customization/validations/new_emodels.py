"""Circuit customization-related validations."""

import uuid
from multiprocessing import Process
from pathlib import Path
import shutil
import subprocess

from entitysdk import Client

from obi_one.scientific.validation.emodels import bluecellulab_initializable
from obi_one.scientific.validation.emodels import check_mechanisms
from obi_one.utils.circuit import get_mechanisms_suffixes
from obi_one.utils.circuit_customization.download import download_mechanisms


def check_hoc_mechanisms_compatible_with_circuit(db_client: Client, hoc_path: str|Path, circuit_id: str|uuid.UUID) -> None:
    """Checks that the mechanisms declared in the hoc file are compatible with the mechanisms used in the circuit.
    
    This is done by downloading the mechanisms from the circuit, extracting their suffixes, and checking that the suffixes of the mechanisms declared in the hoc file are in the set of suffixes from the circuit.
    Raises an error if any of the declared mechanisms in the hoc file is not compatible with the circuit.
    """
    expected_suffixes = get_mechanisms_suffixes(circuit_id=circuit_id, db_client=db_client)
    check_mechanisms(hoc_path=hoc_path, expected_suffixes=expected_suffixes)


def compile_mechanisms(mechanisms_dir: str|Path) -> None:
    """Compile mechanisms in the given directory.

    Args:
        mechanisms_dir (str or Pathlib.Path): path to the directory with mechanisms
    """
    subprocess.run(
        [
            "nrnivmodl",
            "-incflags",
            "-DDISABLE_REPORTINGLIB",
            str(mechanisms_dir),
        ],
        check=True,
    )


def compile_mechs_and_load_hoc(circuit_id: str|uuid.UUID, hoc_path: str|Path, morphology_path: str|Path, db_client: Client, mech_dir: str|Path, result_queue: Queue) -> None:
    """Download and compile mechanisms and check if emodel can be initialized in bluecellulab.
    
    To be called in a subprocesss to avoid errors if we try to instiantiate different models.
    """
    try:
        # the hoc file has to only use the mechanisms from the circuit for this test to pass
        _ = download_mechanisms(circuit_id=circuit_id, db_client=db_client, dest_dir=mech_dir)
        compile_mechanisms(mechanisms_dir=mech_dir)

        bluecellulab_initializable(hoc_path=hoc_path, morphology_path=morphology_path, template_format="v6", holding_current=0.0, threshold_current=0.0)
        result_queue.put(True)
    except Exception as e:
        result_queue.put(False)


def check_bluecellulab_initializable(paths: list[dict], circuit_id: str|uuid.UUID, db_client: Client) -> None:
    """Checks that the hoc file can be initialized in bluecellulab.
    
    Args:
        paths: list of dict containing "hoc_path" and "morphology_path"
    """
    # run in just one process for simplicity. Can be parallelized later if needed.
    for path in paths:
        # remove previously compiled mechanisms for each hoc
        mech_dir = Path("mechanisms")
        compiled_mech_possible_dirs = [
            Path("x86_64"),
            Path("arm64"),
        ]
        for compiled_dir in compiled_mech_possible_dirs:
            if compiled_dir.exists():
                shutil.rmtree(compiled_dir)
        if mech_dir.exists():
            shutil.rmtree(mech_dir)

        result_queue = Queue()
        p = Process(
            target=compile_mechs_and_load_hoc,
            args=(circuit_id, path["hoc_path"], path["morphology_path"], db_client, mech_dir, result_queue,))
        p.start()
        p.join()

        # Get the result from the Queue
        if not result_queue.empty():
            result = result_queue.get()
            if result is False:
                raise RuntimeError(f"Emodel instantiation check in bluecellulab failed for hoc {path['hoc_path']}")
        else:
            raise RuntimeError("No result returned from subprocess when running bluecellulab instantiation check")
