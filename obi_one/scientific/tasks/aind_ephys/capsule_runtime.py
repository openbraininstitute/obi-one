"""Isolated runtime environments for the AIND ephys capsules.

Each AIND capsule (cloned under ``/tmp/aind-*``) ships its own pinned
dependencies. Those deps conflict with obi-one's environment -- most notably
``aind-data-schema``, which pins ``pydantic<2.12`` while obi-one runs on a newer
pydantic. Installing them into obi-one's ``.venv`` would silently downgrade
pydantic and break ``import obi_one``.

To avoid that, each capsule is executed in its own uv-managed virtual
environment, completely separate from obi-one's ``.venv``. The capsule env is
cached inside the cloned repo and rebuilt only when its dependency set changes.

The dependency list is supplied by each task rather than parsed from the
capsule's ``environment/Dockerfile``: that Dockerfile targets the Code Ocean
Linux/CUDA image and pins packages that either do not build on macOS
(``wavpack-numcodecs`` needs a system library) or are unnecessary for a local
toy run (``s3fs``, the GPU ``torch`` build, the heavy ``spikeinterface[full]``
extras). Each task therefore declares the macOS-installable subset of its
capsule's Dockerfile that is actually exercised locally.
"""

import json
import logging
import os
import subprocess  # noqa: S404
from pathlib import Path

L = logging.getLogger(__name__)

CAPSULE_VENV_DIRNAME = ".obi-capsule-venv"
_DEPS_MARKER_NAME = ".obi-capsule-deps.json"


def ensure_capsule_python(repo_path: Path, deps: list[str]) -> str:
    """Build (or reuse) an isolated venv for a capsule and return its interpreter.

    The venv lives at ``<repo_path>/.obi-capsule-venv`` and is populated with
    ``deps`` via ``uv``. A marker file records the dependency set so the venv is
    only rebuilt when that set changes.

    Args:
        repo_path: Path to the cloned capsule repository.
        deps: Requirement specs to install into the capsule's isolated venv.

    Returns:
        Absolute path (as a string, for use as ``argv[0]``) to the capsule venv's
        Python interpreter.

    Raises:
        ValueError: If ``deps`` is empty.
    """
    if not deps:
        msg = "deps must be a non-empty list of requirement specs."
        raise ValueError(msg)

    venv_dir = repo_path / CAPSULE_VENV_DIRNAME
    bin_subdir = "Scripts" if os.name == "nt" else "bin"
    python = venv_dir / bin_subdir / ("python.exe" if os.name == "nt" else "python")
    marker = venv_dir / _DEPS_MARKER_NAME
    desired = json.dumps(sorted(deps))

    if python.exists() and marker.is_file() and marker.read_text(encoding="utf-8") == desired:
        return str(python)

    if not python.exists():
        L.info("Creating isolated capsule venv at %s", venv_dir)
        subprocess.run(  # noqa: S603
            ["uv", "venv", "--python", "3.12", str(venv_dir)],  # noqa: S607
            check=True,
        )
    L.info("Installing %d capsule dependencies into %s", len(deps), venv_dir)
    subprocess.run(  # noqa: S603
        ["uv", "pip", "install", "--python", str(python), *deps],  # noqa: S607
        check=True,
    )
    marker.write_text(desired, encoding="utf-8")
    return str(python)
