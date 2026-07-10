"""Tests for the mesh LOD generation library."""

import asyncio
import concurrent.futures
import pathlib
import sys
import types
from concurrent.futures.process import BrokenProcessPool
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from obi_one.scientific.library import mesh_lod_generation as mod

TARGET_MODULE = "obi_one.scientific.library.mesh_lod_generation"


class _ImmediateExecutor:
    def __init__(self, *args, **kwargs):
        pass

    def submit(self, fn, *args, **kwargs):
        future = concurrent.futures.Future()
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            future.set_exception(exc)
        else:
            future.set_result(result)
        return future

    def shutdown(self, *, wait=True):
        pass


class _BrokenPoolExecutor:
    def __init__(self, *args, **kwargs):
        pass

    def submit(self, _fn, *_args, **_kwargs):
        future = concurrent.futures.Future()
        future.set_exception(BrokenProcessPool("subprocess died"))
        return future

    def shutdown(self, *, wait=True):
        pass


class _HangingExecutor:
    def __init__(self, *args, **kwargs):
        pass

    def submit(self, _fn, *_args, **_kwargs):
        return concurrent.futures.Future()

    def shutdown(self, *, wait=True):
        pass


def test_generate_lods_worker_invokes_ultraliser(tmp_path, monkeypatch):
    calls = {}

    class _FakeMesh:
        def __init__(self, file_name, verbose):
            calls["mesh_file_name"] = file_name
            calls["verbose"] = verbose

    class _FakeGenerator:
        def __init__(self, mesh):
            calls["generator_mesh"] = mesh

        def generate_web_lods(self, output_dir):
            calls["output_dir"] = output_dir

    fake_ultraliser = types.SimpleNamespace(Mesh=_FakeMesh, LODGenerator=_FakeGenerator)
    monkeypatch.setitem(sys.modules, "ultraliser", fake_ultraliser)

    mesh_path = str(tmp_path / "mesh.obj")
    output_dir = str(tmp_path / "output")

    mod._generate_lods_worker(mesh_path, output_dir)

    assert calls["mesh_file_name"] == mesh_path
    assert calls["output_dir"] == output_dir


def test_collect_lod_files(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.obj").write_bytes(b"x")
    (tmp_path / "sub" / "b.bin").write_bytes(b"y")

    result = mod._collect_lod_files(tmp_path)

    assert set(result.keys()) == {pathlib.Path("a.obj"), pathlib.Path("b.bin")}


def test_generate_lods_not_installed_raises(tmp_path):
    with (
        patch.object(mod, "HAS_MESHING", new=False),
        pytest.raises(RuntimeError, match="ultraliser not installed"),
    ):
        asyncio.run(mod._generate_lods(tmp_path / "mesh.obj", "obj", tmp_path / "output_lods"))


def test_generate_lods_unsupported_format_raises(tmp_path):
    with (
        patch.object(mod, "HAS_MESHING", new=True),
        pytest.raises(RuntimeError, match="Unsupported mesh format"),
    ):
        asyncio.run(mod._generate_lods(tmp_path / "mesh.obj", "stl", tmp_path / "output_lods"))


def test_generate_lods_success(tmp_path):
    output_dir = tmp_path / "output_lods"

    def _fake_worker(_mesh_path, out_dir):
        pathlib.Path(out_dir, "lod0.obj").write_bytes(b"fake-lod-content")

    with (
        patch.object(mod, "HAS_MESHING", new=True),
        patch.object(mod, "_generate_lods_worker", side_effect=_fake_worker),
        patch.object(mod, "ProcessPoolExecutor", _ImmediateExecutor),
    ):
        result = asyncio.run(mod._generate_lods(tmp_path / "mesh.obj", "obj", output_dir))

    assert output_dir.exists()
    assert pathlib.Path("lod0.obj") in result


def test_generate_lods_no_output_files_raises(tmp_path):
    output_dir = tmp_path / "output_lods"

    with (
        patch.object(mod, "HAS_MESHING", new=True),
        patch.object(mod, "_generate_lods_worker", MagicMock()),
        patch.object(mod, "ProcessPoolExecutor", _ImmediateExecutor),
        pytest.raises(RuntimeError, match="produced no LOD output files"),
    ):
        asyncio.run(mod._generate_lods(tmp_path / "mesh.obj", "obj", output_dir))


def test_generate_lods_broken_process_pool_raises(tmp_path):
    output_dir = tmp_path / "output_lods"

    with (
        patch.object(mod, "HAS_MESHING", new=True),
        patch.object(mod, "ProcessPoolExecutor", _BrokenPoolExecutor),
        pytest.raises(RuntimeError, match="ultraliser crashed"),
    ):
        asyncio.run(mod._generate_lods(tmp_path / "mesh.obj", "obj", output_dir))


def test_generate_lods_timeout_raises(tmp_path):
    output_dir = tmp_path / "output_lods"

    with (
        patch.object(mod, "HAS_MESHING", new=True),
        patch.object(mod, "LOD_GENERATION_TIMEOUT_S", 0.05),
        patch.object(mod, "ProcessPoolExecutor", _HangingExecutor),
        pytest.raises(RuntimeError, match="timed out"),
    ):
        asyncio.run(mod._generate_lods(tmp_path / "mesh.obj", "obj", output_dir))


def test_delete_existing_asset_by_path_deletes_match():
    existing_asset = MagicMock()
    existing_asset.id = uuid4()
    existing_asset.path = "lod-mesh-directory"
    entity = MagicMock()
    entity.assets = [existing_asset]

    mock_client = MagicMock()
    mock_client.get_entity.return_value = entity

    entity_id = uuid4()
    mod._delete_existing_asset_by_path(mock_client, entity_id, "lod-mesh-directory")

    delete_kwargs = mock_client.delete_asset.call_args.kwargs
    assert delete_kwargs["entity_id"] == entity_id
    assert delete_kwargs["asset_id"] == existing_asset.id


def test_delete_existing_asset_by_path_no_match():
    entity = MagicMock()
    entity.assets = []

    mock_client = MagicMock()
    mock_client.get_entity.return_value = entity

    mod._delete_existing_asset_by_path(mock_client, uuid4(), "lod-mesh-directory")

    mock_client.delete_asset.assert_not_called()


def test_upload_lod_directory_deletes_then_uploads():
    entity = MagicMock()
    entity.assets = []

    mock_client = MagicMock()
    mock_client.get_entity.return_value = entity

    entity_id = uuid4()
    lod_files = {pathlib.Path("a.obj"): pathlib.Path("/tmp/a.obj")}  # noqa: S108

    result = mod._upload_lod_directory(mock_client, entity_id, lod_files)

    assert result == str(entity_id)
    upload_kwargs = mock_client.upload_directory.call_args.kwargs
    assert upload_kwargs["entity_id"] == entity_id
    assert upload_kwargs["paths"] == lod_files
    assert upload_kwargs["name"] == "lod-mesh-directory"


def test_try_generate_and_upload_lods_disabled():
    with patch.object(mod, "HAS_MESHING", new=False):
        result = asyncio.run(
            mod.try_generate_and_upload_lods(MagicMock(), uuid4(), pathlib.Path("mesh.obj"), "obj")
        )

    assert result is None


def test_try_generate_and_upload_lods_success():
    mock_client = MagicMock()
    entity_id = uuid4()
    lod_files = {pathlib.Path("a.obj"): pathlib.Path("/tmp/a.obj")}  # noqa: S108

    with (
        patch.object(mod, "HAS_MESHING", new=True),
        patch.object(mod, "_generate_lods", new_callable=AsyncMock, return_value=lod_files),
        patch.object(mod, "_upload_lod_directory", return_value=str(entity_id)) as mock_upload,
    ):
        result = asyncio.run(
            mod.try_generate_and_upload_lods(
                mock_client, entity_id, pathlib.Path("mesh.obj"), "obj"
            )
        )

    assert result == str(entity_id)
    mock_upload.assert_called_once_with(mock_client, entity_id, lod_files)


def test_try_generate_and_upload_lods_handles_failure():
    with (
        patch.object(mod, "HAS_MESHING", new=True),
        patch.object(
            mod, "_generate_lods", new_callable=AsyncMock, side_effect=RuntimeError("boom")
        ),
    ):
        result = asyncio.run(
            mod.try_generate_and_upload_lods(MagicMock(), uuid4(), pathlib.Path("mesh.obj"), "obj")
        )

    assert result is None
