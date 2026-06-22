"""Circuit customization endpoint."""

import json
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
from entitysdk.types import AssetLabel, DerivationType
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


class NodeValidationError(ValueError):
    """Raised when a node file fails validation."""


class NodeSetsValidationError(ValueError):
    """Raised when a nodeset file fails validation."""


def _save_uploads(files: list[UploadFile], target_dir: Path) -> list[Path]:
    """Save uploaded files to a directory and return their paths."""
    paths = []
    for f in files:
        dest = target_dir / f.filename  # ty:ignore[unsupported-operator]
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


def _validate_nodes(paths: list[Path]) -> None:
    """Layer 1 validation for node files."""
    for path in paths:
        try:
            with h5py.File(path, "r") as f:
                if "nodes" not in f:
                    msg = f"'{path.name}': missing 'nodes' group"
                    raise NodeValidationError(msg)
                for pop_name in f["nodes"]:
                    pop = f["nodes"][pop_name]
                    if "node_type_id" not in pop and "0" not in pop:
                        msg = f"'{path.name}' population '{pop_name}': missing 'node_type_id'"
                        raise NodeValidationError(msg)
        except OSError as e:
            msg = f"'{path.name}': not a valid HDF5 file: {e}"
            raise NodeValidationError(msg) from e


def _validate_nodeset_expression(path: Path, key: str, expr: object) -> None:
    """Validate a single SONATA nodeset expression (recursive for compound expressions)."""
    if isinstance(expr, dict):
        _validate_nodeset_dict(path, key, expr)
    elif isinstance(expr, list):
        _validate_nodeset_list(path, key, expr)
    else:
        msg = f"'{path.name}' nodeset '{key}': expression must be a dict or list"
        raise NodeSetsValidationError(msg)


def _validate_nodeset_dict(path: Path, key: str, expr: dict) -> None:
    """Validate a dict-based nodeset expression."""
    VALID_OPERATORS = {"$regex", "$gt", "$lt", "$gte", "$lte"}  # noqa: N806

    for k, v in expr.items():
        if k == "population":
            if not isinstance(v, str | list):
                msg = f"'{path.name}' nodeset '{key}': 'population' value must be a string or list"
                raise NodeSetsValidationError(msg)
        elif k == "node_id":
            if not isinstance(v, list | int):
                msg = (
                    f"'{path.name}' nodeset '{key}': 'node_id' value must be an int or list of ints"
                )
                raise NodeSetsValidationError(msg)
        elif k in VALID_OPERATORS:
            pass  # operator values are unconstrained at this layer
        elif not isinstance(v, str | int | float | list):
            msg = (
                f"'{path.name}' nodeset '{key}': "
                f"attribute filter value for '{k}' must be a scalar or list"
            )
            raise NodeSetsValidationError(msg)


def _validate_nodeset_list(path: Path, key: str, expr: list) -> None:
    """Validate a list-based compound nodeset expression."""
    for item in expr:
        if not isinstance(item, str | dict):
            msg = (
                f"'{path.name}' nodeset '{key}': compound expression items must be strings or dicts"
            )
            raise NodeSetsValidationError(msg)
        if isinstance(item, dict):
            _validate_nodeset_expression(path, key, item)


def _validate_node_sets(path: Path) -> None:
    """Layer 1 validation for a SONATA nodeset JSON file."""
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        msg = f"'{path.name}': invalid JSON: {e}"
        raise NodeSetsValidationError(msg) from e

    if not isinstance(content, dict):
        msg = f"'{path.name}': must be a JSON object at top level"
        raise NodeSetsValidationError(msg)

    for key, expr in content.items():
        if not isinstance(key, str):
            msg = f"'{path.name}': all top-level keys must be strings"
            raise NodeSetsValidationError(msg)
        _validate_nodeset_expression(path, key, expr)


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


def _validate_nodes_hoc_consistency(node_paths: list[Path], hoc_paths: list[Path]) -> None:
    """Check consistency between uploaded nodes and HOC files.

    Validates:
    1. All model_templates in the nodes reference existing HOC files (uploaded or will be in parent)
    2. All uploaded HOC files are referenced by at least one node's model_template
    """
    import h5py as h5  # noqa: PLC0415

    # Collect all model_template values from uploaded nodes files
    templates_in_nodes: set[str] = set()
    for node_path in node_paths:
        try:
            with h5.File(node_path, "r") as f:
                for pop_name in f.get("nodes", {}):
                    group = f["nodes"][pop_name].get("0", f["nodes"][pop_name])
                    if "model_template" in group:
                        ds = group["model_template"]
                        templates_in_nodes.update(
                            v.decode() if isinstance(v, bytes) else v for v in ds[:]
                        )
        except Exception:  # noqa: BLE001, S112
            continue

    if not templates_in_nodes:
        return

    # Extract HOC template names from uploaded files
    uploaded_hoc_stems = {p.stem for p in hoc_paths}

    # Check: every uploaded HOC must be used in at least one node
    node_template_stems = set()
    for t in templates_in_nodes:
        if ":" in t:
            node_template_stems.add(t.split(":", 1)[1])

    unused_hoc = uploaded_hoc_stems - node_template_stems
    if unused_hoc:
        msg = (
            f"Uploaded HOC file(s) {unused_hoc} are not referenced "
            f"by any model_template in the uploaded nodes files"
        )
        raise ValueError(msg)


def _run_cross_validations(
    hoc_paths: list[Path], mod_paths: list[Path], node_paths: list[Path]
) -> list[str]:
    """Run cross-file validations and return collected error messages."""
    errors: list[str] = []
    if hoc_paths:
        try:
            _validate_hoc_mechanisms(hoc_paths, mod_paths)
        except HocValidationError as e:
            errors.append(f"hoc/mod cross-check: {e}")
    if node_paths and hoc_paths and not errors:
        try:
            _validate_nodes_hoc_consistency(node_paths, hoc_paths)
        except ValueError as e:
            errors.append(f"nodes/hoc cross-check: {e}")
    return errors


def _run_validations(
    tmp: Path,
    edges_files: list[UploadFile] | None,
    emodel_files: list[UploadFile] | None,
    mechanism_files: list[UploadFile] | None,
    node_files: list[UploadFile] | None,
    node_sets_file: UploadFile | None,
) -> tuple[list[Path], list[Path], list[Path], list[Path], Path | None, list[str]]:
    """Save uploads and run Layer 1 validations. Returns paths and collected errors."""
    edge_paths: list[Path] = []
    hoc_paths: list[Path] = []
    mod_paths: list[Path] = []
    node_paths: list[Path] = []
    node_sets_path: Path | None = None
    errors: list[str] = []

    edge_paths, hoc_paths, mod_paths, node_paths, errors = _validate_file_groups(
        tmp, edges_files, emodel_files, mechanism_files, node_files
    )

    if node_sets_file:
        node_sets_path = tmp / node_sets_file.filename  # ty:ignore[unsupported-operator]
        node_sets_path.write_bytes(node_sets_file.file.read())
        try:
            _validate_node_sets(node_sets_path)
        except NodeSetsValidationError as e:
            errors.append(f"node_sets: {e}")

    return edge_paths, hoc_paths, mod_paths, node_paths, node_sets_path, errors


def _validate_file_groups(
    tmp: Path,
    edges_files: list[UploadFile] | None,
    emodel_files: list[UploadFile] | None,
    mechanism_files: list[UploadFile] | None,
    node_files: list[UploadFile] | None,
) -> tuple[list[Path], list[Path], list[Path], list[Path], list[str]]:
    """Validate individual file groups (edges, hoc, mod, nodes)."""
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
        try:
            _validate_nodes(node_paths)
        except ValueError as e:
            errors.append(f"nodes: {e}")

    return edge_paths, hoc_paths, mod_paths, node_paths, errors


def _trigger_validation_task(
    *,
    ls_client: httpx.Client,
    circuit_id: UUID,
    project_id: UUID,
    virtual_lab_id: UUID,
) -> None:
    """Submit a circuit validation job to the launch-system."""
    launch_path = "launch_scripts/launch_circuit_validation"
    job_data = {
        "code": {
            "type": "python_repository",
            "location": settings.OBI_ONE_REPO,
            "ref": f"tag:{(settings.APP_VERSION or '0.0.0').split('-')[0]}",
            "path": f"{launch_path}/main.py",
            "dependencies": f"{launch_path}/dependencies/default.txt",
        },
        "resources": {
            "type": "machine",
            "cores": 1,
            "memory": 8,
            "timelimit": "00:30",
            "compute_cell": "local",
        },
        "inputs": [
            f"--circuit_id {circuit_id}",
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


def _register_and_stage(
    *,
    db_client: entitysdk.client.Client,
    parent: models.Circuit,
    name: str,
    description: str,
    tmp: Path,
    edge_paths: list[Path],
    hoc_paths: list[Path],
    mod_paths: list[Path],
    node_paths: list[Path],
    node_sets_path: Path | None,
    cfg_path: Path | None,
    pop_map: dict[str, str],
) -> models.Circuit:
    """Register a new circuit entity, stage overrides, and upload the merged directory."""
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

    staged_dir = tmp / "staged"
    staged_dir.mkdir()

    try:
        stage_customized_circuit(
            db_client,
            parent=parent,
            output_dir=staged_dir,
            edge_overrides=edge_paths or None,
            emodel_overrides=hoc_paths or None,
            emodel_population_map=pop_map or None,
            mechanism_overrides=mod_paths or None,
            node_overrides=node_paths or None,
            node_sets_override=node_sets_path,
            circuit_config_override=cfg_path,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    merged_files = {p.relative_to(staged_dir): p for p in staged_dir.rglob("*") if p.is_file()}
    db_client.upload_directory(
        entity_id=registered.id,  # ty:ignore[invalid-argument-type]
        entity_type=models.Circuit,
        name="sonata_circuit",
        paths=merged_files,  # ty:ignore[invalid-argument-type]
        label=AssetLabel.sonata_circuit,
    )

    return registered


def _parse_population_manifest(manifest_json: str | None) -> dict[str, str]:
    """Parse and validate the optional emodel population manifest JSON."""
    if not manifest_json:
        return {}
    try:
        pop_map = json.loads(manifest_json)
        if not isinstance(pop_map, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in pop_map.items()
        ):
            msg = "must be a JSON object with string keys and values"
            raise ValueError(msg)  # noqa: TRY301
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(
            status_code=422,
            detail=f"emodel_population_manifest: invalid JSON: {e}",
        ) from e
    return pop_map


@router.post(
    "/circuit/customize",
    summary="Create a customized circuit from a parent circuit",
    description=(
        "Upload overrides (edges, emodels, mechanisms, nodes, node_sets, circuit_config) to create"
        " a new customized circuit entity derived from the parent. The circuit is created"
        " with status 'draft' and transitions to 'active' after async validation passes."
        "\n\nWhen uploading nodes or edges alongside a circuit_config override, every uploaded"
        " file must be referenced in the config's networks section."
        "\n\nTo place HOC files into a population-specific model directory, supply"
        " emodel_population_manifest as a JSON object mapping filename → population name."
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
    emodel_population_manifest: Annotated[
        str | None,
        Form(
            description=(
                "JSON object mapping HOC filename → population name for per-population"
                ' placement, e.g. \'{"MyCell.hoc": "my_population"}\''
            )
        ),
    ] = None,
    mechanism_files: Annotated[
        list[UploadFile] | None, File(description="MOD mechanism files")
    ] = None,
    node_files: Annotated[
        list[UploadFile] | None, File(description="Node population H5 files")
    ] = None,
    node_sets_file: Annotated[
        UploadFile | None, File(description="SONATA nodeset JSON file")
    ] = None,
    circuit_config_file: Annotated[
        UploadFile | None, File(description="circuit_config.json override")
    ] = None,
) -> CircuitCustomizationResponse:
    """Create a customized circuit from a parent circuit with overrides."""
    has_overrides = any(
        [
            edges_files,
            emodel_files,
            mechanism_files,
            node_files,
            node_sets_file,
            circuit_config_file,
        ]
    )
    if not has_overrides:
        raise HTTPException(status_code=422, detail="At least one override file must be provided.")

    pop_map = _parse_population_manifest(emodel_population_manifest)

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

        cfg_path: Path | None = None
        if circuit_config_file:
            cfg_path = tmp / circuit_config_file.filename  # ty:ignore[unsupported-operator]
            cfg_path.write_bytes(circuit_config_file.file.read())

        edge_paths, hoc_paths, mod_paths, node_paths, node_sets_path, errors = _run_validations(
            tmp, edges_files, emodel_files, mechanism_files, node_files, node_sets_file
        )

        # Cross-validations
        if not errors:
            errors.extend(_run_cross_validations(hoc_paths, mod_paths, node_paths))

        if errors:
            raise HTTPException(status_code=422, detail={"validation_errors": errors})

        # 3. Register, stage, and upload
        registered = _register_and_stage(
            db_client=db_client,
            parent=parent,
            name=name,
            description=description,
            tmp=tmp,
            edge_paths=edge_paths,
            hoc_paths=hoc_paths,
            mod_paths=mod_paths,
            node_paths=node_paths,
            node_sets_path=node_sets_path,
            cfg_path=cfg_path,
            pop_map=pop_map,
        )

    # 5. Create derivation link
    try:
        db_client.create_derivation(  # ty:ignore[unresolved-attribute]
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
        circuit_id=registered.id,  # ty:ignore[invalid-argument-type]
        project_id=db_client.project_context.project_id,  # ty:ignore[unresolved-attribute]
        virtual_lab_id=db_client.project_context.virtual_lab_id,  # ty:ignore[unresolved-attribute, invalid-argument-type]
    )

    L.info(
        "Customized circuit '%s' created: %s (parent: %s)",
        name,
        registered.id,
        parent_circuit_id,
    )

    return CircuitCustomizationResponse(
        circuit_id=registered.id,  # ty:ignore[invalid-argument-type]
        status="draft",
        message=f"Circuit created from parent {parent_circuit_id}. Validation pending.",
    )
