import json
import struct
from pathlib import Path
from unittest.mock import Mock

import pylmesh
import pytest

from obi_one.scientific.tasks.em_cell_mesh_conversion import conversion as test_module
from obi_one.scientific.tasks.em_cell_mesh_conversion.conversion import (
    MeshConversionError,
    ObjSummary,
)

CUBE_CORNER_OBJ = """\
# a comment
v 0 0 0
v 1 0 0
v 0 1 0
v 0 0 1
vn 0 0 1
f 1 2 3
f 1/1/1 3/1/1 4/1/1
"""


def make_glb(gltf: dict, *, length_delta: int = 0, magic: bytes = b"glTF") -> bytes:
    json_chunk = json.dumps(gltf).encode()
    json_chunk += b" " * (-len(json_chunk) % 4)
    total = 12 + 8 + len(json_chunk)
    return (
        struct.pack("<4sII", magic, 2, total + length_delta)
        + struct.pack("<I4s", len(json_chunk), b"JSON")
        + json_chunk
    )


DRACO_GLTF = {"asset": {"version": "2.0"}, "extensionsUsed": ["KHR_draco_mesh_compression"]}


def write(path: Path, content: str | bytes) -> Path:
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


class TestScanObj:
    def test_counts_vertices_and_faces(self, tmp_path):
        summary = test_module.scan_obj(write(tmp_path / "mesh.obj", CUBE_CORNER_OBJ))

        assert summary == ObjSummary(vertices=4, faces=2, min_index=1, max_index=4)
        test_module.check_obj(summary)

    @pytest.mark.parametrize(
        ("face", "match"),
        [
            ("f 1 x 3\n", "not a valid face"),
            ("f 1 2\n", "a face with 2 vertices; only triangles"),
            ("f 1 2 3 1\n", "a face with 4 vertices; only triangles"),
            ("f \n", "a face with 0 vertices"),
        ],
    )
    def test_rejects_malformed_faces(self, tmp_path, face, match):
        obj = "v 0 0 0\nv 1 0 0\nv 0 1 0\n" + face

        with pytest.raises(MeshConversionError, match=f"Line 4 .*{match}"):
            test_module.scan_obj(write(tmp_path / "mesh.obj", obj))

    @pytest.mark.parametrize("vertex", ["v abc\n", "v 1 2\n", "v nan 0 0\n", "v 0 inf 0\n", "v\n"])
    def test_rejects_vertices_without_three_finite_coordinates(self, tmp_path, vertex):
        obj = "v 0 0 0\nv 1 0 0\n" + vertex + "f 1 2 3\n"

        with pytest.raises(MeshConversionError, match=r"Line 3 .*three finite coordinates"):
            test_module.scan_obj(write(tmp_path / "mesh.obj", obj))

    def test_reads_statements_like_pylmesh(self, tmp_path):
        obj = "v\t0 0 0\nv\t1 0 0\nv\t0 1 0\n  v 9 9 9\nvt 0 0\nvn 0 0 1\n\n\tf\t1 2 4\nf 4 3 2"

        summary = test_module.scan_obj(write(tmp_path / "mesh.obj", obj))

        assert summary == ObjSummary(vertices=4, faces=2, min_index=1, max_index=4)


class TestCheckObj:
    @pytest.mark.parametrize(
        ("faces", "match"),
        [
            ("", "no faces"),
            ("f 0 1 2\n", "zero or relative"),
            ("f -1 -2 -3\n", "zero or relative"),
            ("f 1 2 9\n", "refers to vertex 9, but the OBJ has 4 vertices"),
        ],
    )
    def test_rejects_bad_indices(self, tmp_path, faces, match):
        obj = "v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\n" + faces

        summary = test_module.scan_obj(write(tmp_path / "mesh.obj", obj))

        with pytest.raises(MeshConversionError, match=match):
            test_module.check_obj(summary)


class TestCheckGlb:
    def test_accepts_a_draco_glb(self, tmp_path):
        test_module.check_glb(write(tmp_path / "mesh.glb", make_glb(DRACO_GLTF)))

    @pytest.mark.parametrize(
        ("content", "match"),
        [
            (b"glTF", "too short"),
            (make_glb(DRACO_GLTF, magic=b"PK\x03\x04"), "not a binary glTF"),
            (make_glb(DRACO_GLTF, length_delta=100), "incomplete"),
            (make_glb({"asset": {"version": "2.0"}}), "without Draco"),
        ],
    )
    def test_rejects_invalid_files(self, tmp_path, content, match):
        with pytest.raises(MeshConversionError, match=match):
            test_module.check_glb(write(tmp_path / "mesh.glb", content))


class TestConvertObjToGlb:
    def test_writes_a_draco_glb_with_every_triangle(self, tmp_path):
        obj_path = write(tmp_path / "mesh.obj", CUBE_CORNER_OBJ)

        glb_path = test_module.convert_obj_to_glb(obj_path, tmp_path)

        assert glb_path == tmp_path / "mesh.glb"
        test_module.check_glb(glb_path)
        assert pylmesh.load_mesh(str(glb_path)).face_count() == 2

    def test_refuses_a_bad_index_before_pylmesh_reads_it(self, monkeypatch, tmp_path):
        load = Mock()
        monkeypatch.setattr(test_module.pylmesh, "load_mesh", load)
        obj_path = write(tmp_path / "mesh.obj", "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 99999999\n")

        with pytest.raises(MeshConversionError, match="refers to vertex 99999999"):
            test_module.convert_obj_to_glb(obj_path, tmp_path)
        load.assert_not_called()

    def test_refuses_counts_that_differ_from_the_scan(self, monkeypatch, tmp_path):
        save = Mock()
        monkeypatch.setattr(
            test_module.pylmesh,
            "load_mesh",
            Mock(
                return_value=Mock(
                    vertex_count=Mock(return_value=4), face_count=Mock(return_value=1)
                )
            ),
        )
        monkeypatch.setattr(test_module.pylmesh, "save_mesh", save)
        obj_path = write(tmp_path / "mesh.obj", CUBE_CORNER_OBJ)

        with pytest.raises(MeshConversionError, match="read 4 vertices and 1 faces, but the scan"):
            test_module.convert_obj_to_glb(obj_path, tmp_path)
        save.assert_not_called()

    @pytest.mark.parametrize(
        ("step", "match"),
        [("load_mesh", "could not read the OBJ"), ("save_mesh", "could not write the GLB")],
    )
    def test_reports_pylmesh_errors(self, monkeypatch, tmp_path, step, match):
        monkeypatch.setattr(test_module.pylmesh, step, Mock(side_effect=RuntimeError("boom")))
        obj_path = write(tmp_path / "mesh.obj", CUBE_CORNER_OBJ)

        with pytest.raises(MeshConversionError, match=f"{match}: boom"):
            test_module.convert_obj_to_glb(obj_path, tmp_path)
