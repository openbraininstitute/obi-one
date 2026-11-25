import json
import struct
import sys
import textwrap
from pathlib import Path

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
f 1/1/1 3/1/1 4/1/1 2/1/1
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


def test_scan_obj_counts_vertices_and_faces(tmp_path):
    summary = test_module.scan_obj(write(tmp_path / "mesh.obj", CUBE_CORNER_OBJ))

    assert summary == ObjSummary(vertices=4, faces=2, min_index=1, max_index=4)
    test_module.check_obj(summary)


@pytest.mark.parametrize(
    ("faces", "match"),
    [
        ("", "no faces"),
        ("f 0 1 2\n", "zero or relative"),
        ("f -1 -2 -3\n", "zero or relative"),
        ("f 1 2 9\n", "refers to vertex 9, but the OBJ has 4 vertices"),
    ],
)
def test_check_obj_rejects_bad_indices(tmp_path, faces, match):
    obj = "v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\n" + faces

    summary = test_module.scan_obj(write(tmp_path / "mesh.obj", obj))

    with pytest.raises(MeshConversionError, match=match):
        test_module.check_obj(summary)


@pytest.mark.parametrize(
    ("face", "match"),
    [("f 1 x 3\n", "not a valid face"), ("f 1 2\n", "fewer than 3 vertices"), ("f \n", "fewer")],
)
def test_scan_obj_rejects_malformed_faces(tmp_path, face, match):
    obj = "v 0 0 0\nv 1 0 0\nv 0 1 0\n" + face

    with pytest.raises(MeshConversionError, match=f"Line 4 .*{match}"):
        test_module.scan_obj(write(tmp_path / "mesh.obj", obj))


def test_check_glb_accepts_a_draco_glb(tmp_path):
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
def test_check_glb_rejects_invalid_files(tmp_path, content, match):
    with pytest.raises(MeshConversionError, match=match):
        test_module.check_glb(write(tmp_path / "mesh.glb", content))


def fake_ultraliser(monkeypatch, tmp_path, body: str) -> None:
    """Replaces the Ultraliser child with a script run as `script obj out_dir counts`."""
    script = write(tmp_path / "fake_ultraliser.py", textwrap.dedent(body))
    monkeypatch.setattr(
        test_module,
        "_ultraliser_command",
        lambda obj, out, counts: [sys.executable, str(script), str(obj), str(out), str(counts)],
    )


WRITE_COUNTS = """\
    import json, sys
    from pathlib import Path
    obj, out, counts = sys.argv[1:]
"""


def test_convert_obj_to_glb_returns_the_checked_glb(monkeypatch, tmp_path):
    glb = make_glb(DRACO_GLTF)
    fake_ultraliser(
        monkeypatch,
        tmp_path,
        WRITE_COUNTS
        + f"""\
    Path(counts).write_text(json.dumps({{"vertices": 4, "triangles": 3}}))
    Path(out, "mesh.glb").write_bytes({glb!r})
""",
    )
    obj_path = write(tmp_path / "mesh.obj", CUBE_CORNER_OBJ)

    glb_path = test_module.convert_obj_to_glb(obj_path, tmp_path / "work")

    assert glb_path == tmp_path / "work" / "glb" / "mesh.glb"
    assert glb_path.read_bytes() == glb


def test_convert_obj_to_glb_fails_when_ultraliser_exits_0_without_output(monkeypatch, tmp_path):
    fake_ultraliser(monkeypatch, tmp_path, "import sys\nsys.exit(0)\n")
    obj_path = write(tmp_path / "mesh.obj", CUBE_CORNER_OBJ)

    with pytest.raises(MeshConversionError, match="could not read the OBJ"):
        test_module.convert_obj_to_glb(obj_path, tmp_path / "work")


def test_convert_obj_to_glb_reports_a_killed_child(monkeypatch, tmp_path):
    fake_ultraliser(
        monkeypatch, tmp_path, "import os, signal\nos.kill(os.getpid(), signal.SIGKILL)\n"
    )
    obj_path = write(tmp_path / "mesh.obj", CUBE_CORNER_OBJ)

    with pytest.raises(MeshConversionError, match="SIGKILL, most likely out of memory"):
        test_module.convert_obj_to_glb(obj_path, tmp_path / "work")


def test_convert_obj_to_glb_fails_on_zero_triangles(monkeypatch, tmp_path):
    fake_ultraliser(
        monkeypatch,
        tmp_path,
        WRITE_COUNTS + '    Path(counts).write_text(json.dumps({"vertices": 4, "triangles": 0}))\n',
    )
    obj_path = write(tmp_path / "mesh.obj", CUBE_CORNER_OBJ)

    with pytest.raises(MeshConversionError, match="no triangles"):
        test_module.convert_obj_to_glb(obj_path, tmp_path / "work")


def test_convert_obj_to_glb_stops_the_child_when_the_obj_is_invalid(monkeypatch, tmp_path):
    marker = tmp_path / "finished"
    fake_ultraliser(
        monkeypatch,
        tmp_path,
        f"import time\nfrom pathlib import Path\ntime.sleep(30)\nPath({str(marker)!r}).touch()\n",
    )
    obj_path = write(tmp_path / "mesh.obj", "v 0 0 0\nf 1 2 3\n")

    with pytest.raises(MeshConversionError, match="refers to vertex 3"):
        test_module.convert_obj_to_glb(obj_path, tmp_path / "work")
    assert not marker.exists()
