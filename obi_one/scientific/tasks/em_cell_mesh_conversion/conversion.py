"""OBJ to Draco GLB conversion with pylmesh, with the checks pylmesh does not make itself.

pylmesh does not range-check face indices: an index past the last vertex crashes the process
in ``save_mesh`` instead of raising. It also keeps only the first three indices of a polygon.
So the OBJ is scanned first, reading lines the way pylmesh does, and pylmesh's counts must
match the scan's before the GLB is written.
"""

import json
import logging
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

import pylmesh

from obi_one.core.exception import OBIONEError

L = logging.getLogger(__name__)

# pylmesh picks its reader by a lowercase ".obj" suffix, so the OBJ is saved under this name.
OBJ_FILE_NAME = "mesh.obj"
GLB_FILE_NAME = "mesh.glb"
GLB_MAGIC = b"glTF"
GLB_VERSION = 2
GLB_JSON_CHUNK = b"JSON"
GLB_HEADER = struct.Struct("<4sIII4s")
DRACO_EXTENSION = "KHR_draco_mesh_compression"
TRIANGLE_VERTICES = 3
VERTEX_STATEMENT = b"v"
FACE_STATEMENT = b"f"


class MeshConversionError(OBIONEError):
    """The OBJ could not be converted to a valid Draco GLB."""


@dataclass(frozen=True)
class ObjSummary:
    vertices: int
    faces: int
    min_index: int
    max_index: int


def _face_indices(tokens: bytes, line_number: int) -> list[int]:
    try:
        indices = [int(token.split(b"/", 1)[0]) for token in tokens.split()]
    except ValueError as error:
        msg = f"Line {line_number} of the OBJ is not a valid face."
        raise MeshConversionError(msg) from error
    if len(indices) != TRIANGLE_VERTICES:
        msg = (
            f"Line {line_number} of the OBJ is a face with {len(indices)} vertices;"
            " only triangles are supported."
        )
        raise MeshConversionError(msg)
    return indices


def scan_obj(obj_path: Path) -> ObjSummary:
    """Counts vertices and faces and finds the face index range in one streaming pass.

    A line's statement is its first whitespace-separated token, as in pylmesh's reader.
    """
    vertices = 0
    faces = 0
    min_index = sys.maxsize
    max_index = 0
    with obj_path.open("rb") as obj_file:
        for line_number, line in enumerate(obj_file, start=1):
            parts = line.split(maxsplit=1)
            if not parts:
                continue
            if parts[0] == VERTEX_STATEMENT:
                vertices += 1
            elif parts[0] == FACE_STATEMENT:
                faces += 1
                indices = _face_indices(parts[1] if len(parts) > 1 else b"", line_number)
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
            msg = "The conversion wrote a GLB that is too short."
            raise MeshConversionError(msg)
        magic, version, length, json_length, chunk_type = GLB_HEADER.unpack(header)
        if magic != GLB_MAGIC or version != GLB_VERSION or chunk_type != GLB_JSON_CHUNK:
            msg = "The conversion wrote a file that is not a binary glTF 2.0."
            raise MeshConversionError(msg)
        if length != glb_path.stat().st_size:
            msg = "The conversion wrote an incomplete GLB."
            raise MeshConversionError(msg)
        try:
            gltf = json.loads(glb_file.read(json_length))
        except ValueError as error:
            msg = "The conversion wrote a GLB whose JSON chunk cannot be read."
            raise MeshConversionError(msg) from error
    if DRACO_EXTENSION not in gltf.get("extensionsUsed", []):
        msg = "The conversion wrote a GLB without Draco compression."
        raise MeshConversionError(msg)


def _load_mesh(obj_path: Path, summary: ObjSummary) -> pylmesh.Mesh:
    try:
        mesh = pylmesh.load_mesh(str(obj_path))
    except (RuntimeError, ValueError) as error:
        msg = f"pylmesh could not read the OBJ: {error}"
        raise MeshConversionError(msg) from error
    vertices, faces = mesh.vertex_count(), mesh.face_count()
    L.info(f"pylmesh read {vertices} vertices and {faces} faces")
    if (vertices, faces) != (summary.vertices, summary.faces):
        msg = (
            f"pylmesh read {vertices} vertices and {faces} faces,"
            f" but the scan found {summary.vertices} and {summary.faces}."
        )
        raise MeshConversionError(msg)
    return mesh


def convert_obj_to_glb(obj_path: Path, work_dir: Path) -> Path:
    """Converts the OBJ to a Draco GLB in ``work_dir`` and returns the GLB's path.

    ``obj_path`` must end in a lowercase ``.obj``; see ``OBJ_FILE_NAME``.
    """
    summary = scan_obj(obj_path)
    L.info(f"OBJ scan: {summary}")
    check_obj(summary)

    mesh = _load_mesh(obj_path, summary)
    glb_path = work_dir / GLB_FILE_NAME
    try:
        pylmesh.save_mesh(str(glb_path), mesh)
    except (RuntimeError, ValueError) as error:
        msg = f"pylmesh could not write the GLB: {error}"
        raise MeshConversionError(msg) from error
    check_glb(glb_path)
    return glb_path
