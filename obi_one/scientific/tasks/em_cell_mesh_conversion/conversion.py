"""OBJ to Draco GLB conversion, with the checks Ultraliser does not make itself.

Ultraliser runs in a child process: it can end the process with exit code 0 on an error,
and when it runs out of memory the kernel kills the child, not this process. Its OBJ reader
skips malformed lines and does not range-check face indices, so this process scans the OBJ
itself while the child converts it, then checks the GLB the child wrote.
"""

import json
import logging
import signal
import struct
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
from dataclasses import dataclass
from pathlib import Path

from obi_one.core.exception import OBIONEError

L = logging.getLogger(__name__)

ULTRALISER_EXPORT_MODULE = "obi_one.scientific.tasks.em_cell_mesh_conversion.ultraliser_export"
GLB_MAGIC = b"glTF"
GLB_VERSION = 2
GLB_JSON_CHUNK = b"JSON"
GLB_HEADER = struct.Struct("<4sIII4s")
DRACO_EXTENSION = "KHR_draco_mesh_compression"
MIN_FACE_VERTICES = 3
# The line starts Ultraliser's OBJ reader accepts; it skips every other line.
VERTEX_PREFIXES = (b"v ", b"v\t")
FACE_PREFIXES = (b"f ", b"f\t")


class MeshConversionError(OBIONEError):
    """The OBJ could not be converted to a valid Draco GLB."""


@dataclass(frozen=True)
class ObjSummary:
    vertices: int
    faces: int
    min_index: int
    max_index: int


def scan_obj(obj_path: Path) -> ObjSummary:
    """Counts vertices and faces and finds the face index range in one streaming pass."""
    vertices = 0
    faces = 0
    min_index = sys.maxsize
    max_index = 0
    with obj_path.open("rb") as obj_file:
        for line_number, line in enumerate(obj_file, start=1):
            if line.startswith(VERTEX_PREFIXES):
                vertices += 1
            elif line.startswith(FACE_PREFIXES):
                faces += 1
                try:
                    indices = [int(token.split(b"/", 1)[0]) for token in line.split()[1:]]
                except ValueError as error:
                    msg = f"Line {line_number} of the OBJ is not a valid face."
                    raise MeshConversionError(msg) from error
                if len(indices) < MIN_FACE_VERTICES:
                    msg = f"Line {line_number} of the OBJ is a face with fewer than 3 vertices."
                    raise MeshConversionError(msg)
                min_index = min(min_index, *indices)
                max_index = max(max_index, *indices)
    return ObjSummary(vertices=vertices, faces=faces, min_index=min_index, max_index=max_index)


def check_obj(summary: ObjSummary) -> None:
    if summary.faces == 0:
        msg = "The OBJ has no faces."
        raise MeshConversionError(msg)
    if summary.min_index < 1:
        msg = "The OBJ has a face with a zero or relative (negative) vertex index."
        raise MeshConversionError(msg)
    if summary.max_index > summary.vertices:
        msg = (
            f"A face of the OBJ refers to vertex {summary.max_index},"
            f" but the OBJ has {summary.vertices} vertices."
        )
        raise MeshConversionError(msg)


def check_glb(glb_path: Path) -> None:
    """Checks that the file is a complete binary glTF 2.0 that uses Draco compression."""
    with glb_path.open("rb") as glb_file:
        header = glb_file.read(GLB_HEADER.size)
        if len(header) < GLB_HEADER.size:
            msg = "Ultraliser wrote a GLB that is too short."
            raise MeshConversionError(msg)
        magic, version, length, json_length, chunk_type = GLB_HEADER.unpack(header)
        if magic != GLB_MAGIC or version != GLB_VERSION or chunk_type != GLB_JSON_CHUNK:
            msg = "Ultraliser wrote a file that is not a binary glTF 2.0."
            raise MeshConversionError(msg)
        if length != glb_path.stat().st_size:
            msg = "Ultraliser wrote an incomplete GLB."
            raise MeshConversionError(msg)
        try:
            gltf = json.loads(glb_file.read(json_length))
        except ValueError as error:
            msg = "Ultraliser wrote a GLB whose JSON chunk cannot be read."
            raise MeshConversionError(msg) from error
    if DRACO_EXTENSION not in gltf.get("extensionsUsed", []):
        msg = "Ultraliser wrote a GLB without Draco compression."
        raise MeshConversionError(msg)


def _ultraliser_command(obj_path: Path, output_dir: Path, counts_path: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        ULTRALISER_EXPORT_MODULE,
        str(obj_path),
        str(output_dir),
        str(counts_path),
    ]


def _exit_reason(returncode: int) -> str:
    if returncode >= 0:
        return f"exit code {returncode}"
    signal_number = -returncode
    if signal_number == signal.SIGKILL:
        return "SIGKILL, most likely out of memory"
    return f"signal {signal_number}"


def _check_counts(counts_path: Path) -> None:
    if not counts_path.is_file():
        msg = "Ultraliser could not read the OBJ."
        raise MeshConversionError(msg)
    counts = json.loads(counts_path.read_text(encoding="utf-8"))
    L.info(f"Ultraliser read {counts['vertices']} vertices and {counts['triangles']} triangles")
    if counts["vertices"] == 0 or counts["triangles"] == 0:
        msg = "Ultraliser read no triangles from the OBJ."
        raise MeshConversionError(msg)


def convert_obj_to_glb(obj_path: Path, work_dir: Path) -> Path:
    """Converts the OBJ to a Draco GLB in ``work_dir`` and returns the GLB's path."""
    output_dir = work_dir / "glb"
    output_dir.mkdir(parents=True, exist_ok=True)
    counts_path = work_dir / "ultraliser_counts.json"

    process = subprocess.Popen(_ultraliser_command(obj_path, output_dir, counts_path))  # ruff: ignore[subprocess-without-shell-equals-true]
    try:
        summary = scan_obj(obj_path)
        L.info(f"OBJ scan: {summary}")
        check_obj(summary)
    except BaseException:
        process.kill()
        process.wait()
        raise

    returncode = process.wait()
    if returncode != 0:
        msg = f"Ultraliser stopped with {_exit_reason(returncode)}."
        raise MeshConversionError(msg)

    _check_counts(counts_path)
    glb_paths = sorted(output_dir.glob("*.glb"))
    if len(glb_paths) != 1:
        msg = f"Ultraliser wrote {len(glb_paths)} GLB files instead of one."
        raise MeshConversionError(msg)
    check_glb(glb_paths[0])
    return glb_paths[0]
