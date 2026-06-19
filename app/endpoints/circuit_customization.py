"""Circuit customization endpoint."""

import logging
import tempfile
from pathlib import Path
from typing import Annotated
from uuid import UUID

import entitysdk.client
import entitysdk.exception
import h5py
import httpx
import numpy as np
from entitysdk import models
from entitysdk.types import AssetLabel, ContentType, DerivationType
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import settings
from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.dependencies.launch_system import LaunchSystemClientDep
from obi_one.utils.circuit_customization.staging import stage_customized_circuit

L = logging.getLogger(__name__)

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


class CircuitCustomizationResponse(BaseModel):
    """Response for circuit customization."""

    circuit_id: UUID
    status: str
    message: str


class EdgeValidationError(ValueError):
    """Raised when an edge file fails validation."""


class HocValidationError(ValueError):
    """Raised when a HOC file fails validation."""


class ModValidationError(ValueError):
    """Raised when a MOD file fails validation."""


def _save_uploads(files: list[UploadFile], target_dir: Path) -> list[Path]:
    """Save uploaded files to a directory and return their paths."""
    paths = []
    for f in files:
        dest = target_dir / f.filename
        dest.write_bytes(f.file.read())
        paths.append(dest)
    return paths


def _validate_edge_population(path: Path, pop_name: str, pop: h5py.Group) -> None:
    """Validate a single edge population group."""
    for required in ("source_node_id", "target_node_id", "edge_type_id"):
        if required not in pop:
            msg = f"'{path.name}' population '{pop_name}': missing '{required}'"
            raise EdgeValidationError(msg)
    for key in pop:
        ds = pop[key]
        if hasattr(ds, "dtype") and ds.dtype.kind == "f":
            data = ds[:]
            if np.any(~np.isfinite(data)):
                msg = f"'{path.name}' population '{pop_name}': column '{key}' contains NaN or Inf"
                raise EdgeValidationError(msg)


def _validate_edges(paths: list[Path]) -> None:
    """Layer 1 validation for edge files."""
    for path in paths:
        try:
            with h5py.File(path, "r") as f:
                if "edges" not in f:
                    msg = f"'{path.name}': missing 'edges' group"
                    raise EdgeValidationError(msg)
                for pop_name in f["edges"]:
                    pop = f["edges"][pop_name]
                    _validate_edge_population(path, pop_name, pop)
        except OSError as e:
            msg = f"'{path.name}': not a valid HDF5 file: {e}"
            raise EdgeValidationError(msg) from e


def _validate_hoc(paths: list[Path]) -> None:
    """Layer 1 validation for HOC files: check template structure (begintemplate/endtemplate)."""
    for path in paths:
        if path.suffix.lower() != ".hoc":
            msg = f"'{path.name}': expected .hoc extension"
            raise HocValidationError(msg)

        content = path.read_text(encoding="utf-8", errors="replace")

        # Find begintemplate declaration
        template_name = None
        for line in content.splitlines():
            parts = line.strip().split()
            if len(parts) == 2 and parts[0] == "begintemplate":  # noqa: PLR2004
                template_name = parts[1]
                break

        if template_name is None:
            msg = f"'{path.name}': could not find 'begintemplate' — not a valid HOC template"
            raise HocValidationError(msg)
        if f"endtemplate {template_name}" not in content:
            msg = (
                f"'{path.name}': found 'begintemplate {template_name}'"
                " but missing matching 'endtemplate'"
            )
            raise HocValidationError(msg)


def _validate_mod(paths: list[Path]) -> None:
    """Sync validation for MOD files: check structure only. Compilation runs in ECS task."""
    for path in paths:
        if path.suffix.lower() != ".mod":
            msg = f"'{path.name}': expected .mod extension"
            raise ModValidationError(msg)
        content = path.read_text(encoding="utf-8", errors="replace")
        if "NEURON" not in content:
            msg = f"'{path.name}': missing NEURON block"
            raise ModValidationError(msg)


BUILTIN_NEURON_MECHANISMS = {"pas", "hh", "extracellular", "capacitance"}


def _extract_mod_mechanism_names(mod_paths: list[Path]) -> set[str]:
    """Extract SUFFIX names from MOD files (the mechanism names they define)."""
    names = set()
    for path in mod_paths:
        content = path.read_text(encoding="utf-8", errors="replace")
        for line in content.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and parts[0] == "SUFFIX":  # noqa: PLR2004
                names.add(parts[1])
    return names


def _extract_hoc_mechanisms(hoc_path: Path) -> set[str]:
    """Extract mechanism names used via 'insert' statements in a HOC file."""
    content = hoc_path.read_text(encoding="utf-8", errors="replace")
    mechanisms = set()
    for line in content.splitlines():
        parts = line.strip().split()
        if len(parts) == 2 and parts[0] == "insert":  # noqa: PLR2004
            mechanisms.add(parts[1])
    return mechanisms


def _validate_hoc_mechanisms(hoc_paths: list[Path], mod_paths: list[Path]) -> None:
    """Check that mechanisms used in HOC files are available (built-in or from provided MODs)."""
    available = BUILTIN_NEURON_MECHANISMS | _extract_mod_mechanism_names(mod_paths)

    for hoc_path in hoc_paths:
        used = _extract_hoc_mechanisms(hoc_path)
        missing = used - available
        if missing:
            msg = (
                f"'{hoc_path.name}': uses mechanisms {missing} "
                f"that are not built-in or provided in MOD files"
            )
            raise HocValidationError(msg)


def _run_validations(
    tmp: Path,
    edges_files: list[UploadFile] | None,
    emodel_files: list[UploadFile] | None,
    mechanism_files: list[UploadFile] | None,
    node_files: list[UploadFile] | None,
) -> tuple[list[Path], list[Path], list[Path], list[Path], list[str]]:
    """Save uploads and run Layer 1 validations, returning paths and errors."""
    edge_paths: list[Path] = []
    hoc_paths: list[Path] = []
    mod_paths: list[Path] = []
    node_paths: list[Path] = []
    errors: list[str] = []

    if edges_files:
        edge_paths = _save_uploads(edges_files, tmp)
        try:
            _validate_edges(edge_paths)
        except ValueError as e:
            errors.append(f"edges: {e}")

    if emodel_files:
        hoc_paths = _save_uploads(emodel_files, tmp)
        try:
            _validate_hoc(hoc_paths)
        except ValueError as e:
            errors.append(f"emodels: {e}")

    if mechanism_files:
        mod_paths = _save_uploads(mechanism_files, tmp)
        try:
            _validate_mod(mod_paths)
        except ValueError as e:
            errors.append(f"mechanisms: {e}")

    if node_files:
        node_paths = _save_uploads(node_files, tmp)

    # Cross-validation: HOC mechanisms must exist in provided MOD files
    if hoc_paths and mod_paths and not errors:
        try:
            _validate_hoc_mechanisms(hoc_paths, mod_paths)
        except HocValidationError as e:
            errors.append(f"hoc/mod cross-check: {e}")

    return edge_paths, hoc_paths, mod_paths, node_paths, errors


def _upload_overrides(
    db_client: entitysdk.client.Client,
    registered: models.Circuit,
    tmp: Path,
    edge_paths: list[Path],
    hoc_paths: list[Path],
    mod_paths: list[Path],
    node_files: list[UploadFile] | None,
    circuit_config_file: UploadFile | None,
) -> None:
    """Upload override assets to the registered circuit entity."""
    for path in edge_paths:
        db_client.upload_file(
            entity_id=registered.id,
            entity_type=models.Circuit,
            file_path=path,
            file_content_type=ContentType("application/x-hdf5"),
            asset_label=AssetLabel.sonata_circuit,
        )

    for path in hoc_paths:
        db_client.upload_file(
            entity_id=registered.id,
            entity_type=models.Circuit,
            file_path=path,
            file_content_type=ContentType("text/plain"),
            asset_label=AssetLabel.neuron_hoc,
        )

    for path in mod_paths:
        db_client.upload_file(
            entity_id=registered.id,
            entity_type=models.Circuit,
            file_path=path,
            file_content_type=ContentType("text/plain"),
            asset_label=AssetLabel.neuron_mechanisms,
        )

    if node_files:
        for path in _save_uploads(node_files, tmp):
            db_client.upload_file(
                entity_id=registered.id,
                entity_type=models.Circuit,
                file_path=path,
                file_content_type=ContentType("application/x-hdf5"),
                asset_label=AssetLabel.sonata_circuit,
            )

    if circuit_config_file:
        cfg_path = tmp / circuit_config_file.filename
        cfg_path.write_bytes(circuit_config_file.file.read())
        db_client.upload_file(
            entity_id=registered.id,
            entity_type=models.Circuit,
            file_path=cfg_path,
            file_content_type=ContentType("application/json"),
            asset_label=AssetLabel.sonata_circuit,
        )


def _trigger_validation_task(
    *,
    ls_client: httpx.Client,
    circuit_id: UUID,
    parent_circuit_id: UUID,
    project_id: UUID,
    virtual_lab_id: UUID,
) -> None:
    """Submit a circuit validation job to the launch-system."""
    job_data = {
        "code": {
            "type": "python_repository",
            "location": settings.OBI_ONE_REPO,
            "ref": f"tag:{(settings.APP_VERSION or '0.0.0').split('-')[0]}",
            "path": str(Path(settings.OBI_ONE_LAUNCH_PATH) / "main.py"),
            "dependencies": str(
                Path(settings.OBI_ONE_LAUNCH_PATH) / "dependencies" / "default.txt"
            ),
        },
        "resources": {
            "type": "machine",
            "cores": 1,
            "memory": 8,
            "timelimit": "00:30",
            "compute_cell": "local",
        },
        "inputs": [
            "--task-type circuit_validation",
            f"--config_entity_id {circuit_id}",
            f"--parent_circuit_id {parent_circuit_id}",
            f"--virtual_lab_id {virtual_lab_id}",
            f"--project_id {project_id}",
        ],
        "project_id": str(project_id),
        "callbacks": [],
    }

    response = ls_client.post(url="/job", json=job_data)
    if response.is_success:
        L.info("Validation task submitted for circuit %s", circuit_id)
    else:
        L.warning("Failed to submit validation task for circuit %s: %s", circuit_id, response.text)


@router.post(
    "/circuit/customize",
    summary="Create a customized circuit from a parent circuit",
    description=(
        "Upload overrides (edges, emodels, mechanisms, nodes, circuit_config) to create"
        " a new customized circuit entity derived from the parent. The circuit is created"
        " with status 'draft' and transitions to 'active' after async validation passes."
    ),
)
def customize_circuit_endpoint(
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    ls_client: LaunchSystemClientDep,
    parent_circuit_id: Annotated[UUID, Form(...)],
    name: Annotated[str, Form(...)],
    description: Annotated[str, Form("")],
    edges_files: Annotated[
        list[UploadFile] | None, File(description="Edge population H5 files")
    ] = None,
    emodel_files: Annotated[list[UploadFile] | None, File(description="HOC e-model files")] = None,
    mechanism_files: Annotated[
        list[UploadFile] | None, File(description="MOD mechanism files")
    ] = None,
    node_files: Annotated[
        list[UploadFile] | None, File(description="Node population H5 files")
    ] = None,
    circuit_config_file: Annotated[
        UploadFile | None, File(description="circuit_config.json override")
    ] = None,
) -> CircuitCustomizationResponse:
    """Create a customized circuit from a parent circuit with overrides."""
    # Validate at least one override is provided
    has_overrides = any(
        [edges_files, emodel_files, mechanism_files, node_files, circuit_config_file]
    )
    if not has_overrides:
        raise HTTPException(status_code=422, detail="At least one override file must be provided.")

    # 1. Fetch parent circuit
    try:
        parent = db_client.get_entity(entity_id=parent_circuit_id, entity_type=models.Circuit)
    except entitysdk.exception.EntitySDKError as e:
        raise HTTPException(
            status_code=404, detail=f"Parent circuit {parent_circuit_id} not found: {e}"
        ) from e

    # 2. Save uploads and run Layer 1 validations
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)

        edge_paths, hoc_paths, mod_paths, node_paths, errors = _run_validations(
            tmp, edges_files, emodel_files, mechanism_files, node_files
        )

        if errors:
            raise HTTPException(status_code=422, detail={"validation_errors": errors})

        # 3. Create the customized circuit entity
        circuit_model = models.Circuit(
            name=name,
            description=description,
            subject=parent.subject,
            brain_region=parent.brain_region,
            license=parent.license,
            number_neurons=parent.number_neurons,
            number_synapses=parent.number_synapses,
            number_connections=parent.number_connections,
            has_morphologies=parent.has_morphologies,
            has_point_neurons=parent.has_point_neurons,
            has_electrical_cell_models=parent.has_electrical_cell_models,
            has_spines=parent.has_spines,
            scale=parent.scale,
            build_category=parent.build_category,
            target_simulator=parent.target_simulator,
            root_circuit_id=parent.id,
        )

        try:
            registered = db_client.register_entity(circuit_model)
        except entitysdk.exception.EntitySDKError as e:
            raise HTTPException(status_code=500, detail=f"Failed to register circuit: {e}") from e

        # 4. Stage parent + merge overrides + upload as sonata_circuit directory
        staged_dir = tmp / "staged"
        staged_dir.mkdir()

        cfg_path = None
        if circuit_config_file:
            cfg_path = tmp / circuit_config_file.filename
            cfg_path.write_bytes(circuit_config_file.file.read())

        stage_customized_circuit(
            db_client,
            parent=parent,
            output_dir=staged_dir,
            edge_overrides=edge_paths or None,
            emodel_overrides=hoc_paths or None,
            mechanism_overrides=mod_paths or None,
            node_overrides=node_paths or None,
            circuit_config_override=cfg_path if circuit_config_file else None,
        )

        # Upload the merged directory as the circuit's sonata_circuit asset
        merged_files = {p.relative_to(staged_dir): p for p in staged_dir.rglob("*") if p.is_file()}
        db_client.upload_directory(
            entity_id=registered.id,
            entity_type=models.Circuit,
            name="sonata_circuit",
            paths=merged_files,
            label=AssetLabel.sonata_circuit,
        )

    # 5. Create derivation link
    try:
        db_client.create_derivation(
            entity_id=registered.id,
            entity_type=models.Circuit,
            used=[{"id": parent.id, "type": "circuit"}],
            derivation_type=DerivationType.circuit_customization,
        )
    except entitysdk.exception.EntitySDKError:
        L.warning("Failed to create derivation link for %s", registered.id)

    # 6. Trigger async validation task via launch-system
    _trigger_validation_task(
        ls_client=ls_client,
        circuit_id=registered.id,
        parent_circuit_id=parent_circuit_id,
        project_id=db_client.project_context.project_id,
        virtual_lab_id=db_client.project_context.virtual_lab_id,
    )

    L.info(
        "Customized circuit '%s' created: %s (parent: %s)",
        name,
        registered.id,
        parent_circuit_id,
    )

    return CircuitCustomizationResponse(
        circuit_id=registered.id,
        status="draft",
        message=f"Circuit created from parent {parent_circuit_id}. Validation pending.",
    )
