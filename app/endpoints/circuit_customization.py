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
from obi_one.scientific.validations.emodels import BUILTIN_NEURON_MECHANISMS
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
    from obi_one.scientific.validations.emodels import check_structure  # noqa: PLC0415

    for path in paths:
        if path.suffix.lower() != ".hoc":
            msg = f"'{path.name}': expected .hoc extension"
            raise HocValidationError(msg)
        try:
            check_structure(path)
        except ValueError as e:
            raise HocValidationError(str(e)) from e


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


def _validate_hoc_mechanisms(
    hoc_paths: list[Path], mod_paths: list[Path], parent_mechanism_names: set[str] | None = None
) -> None:
    """Check that mechanisms used in HOC files are available (built-in or from provided MODs)."""
    from obi_one.scientific.validations.emodels import check_mechanisms  # noqa: PLC0415

    available = BUILTIN_NEURON_MECHANISMS | _extract_mod_mechanism_names(mod_paths)
    if parent_mechanism_names:
        available |= parent_mechanism_names

    for hoc_path in hoc_paths:
        try:
            check_mechanisms(hoc_path, available)
        except ValueError as e:
            raise HocValidationError(str(e)) from e


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
                        if ds.dtype.kind in ("U", "S", "O"):
                            # String dataset — read directly
                            templates_in_nodes.update(
                                v.decode() if isinstance(v, bytes) else v for v in ds[:]
                            )
                        else:
                            # Enumerated (uint) — resolve via @library
                            lib_path = f"nodes/{pop_name}/0/@library/model_template"
                            if lib_path in f:
                                lib = f[lib_path]
                                templates_in_nodes.update(
                                    v.decode() if isinstance(v, bytes) else v for v in lib[:]
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
    hoc_paths: list[Path],
    mod_paths: list[Path],
    node_paths: list[Path],
    parent_mechanism_names: set[str] | None = None,
) -> list[str]:
    """Run cross-file validations and return collected error messages."""
    errors: list[str] = []
    if hoc_paths:
        try:
            _validate_hoc_mechanisms(hoc_paths, mod_paths, parent_mechanism_names)
        except HocValidationError as e:
            errors.append(f"hoc/mod cross-check: {e}")
    if node_paths and hoc_paths and not errors:
        try:
            _validate_nodes_hoc_consistency(node_paths, hoc_paths)
        except ValueError as e:
            errors.append(f"nodes/hoc cross-check: {e}")
    if mod_paths and parent_mechanism_names is not None:
        synapse_errors = _validate_new_mod_not_synapse(mod_paths, parent_mechanism_names)
        errors.extend(synapse_errors)
    return errors


def _validate_new_mod_not_synapse(
    mod_paths: list[Path], parent_mechanism_names: set[str]
) -> list[str]:
    """Reject new MOD files that are synapse mechanisms (contain NET_RECEIVE).

    Modification of existing MODs (same name as parent) is always allowed.
    New MODs are only allowed if they are ion channels (no NET_RECEIVE).
    """
    errors: list[str] = []
    for path in mod_paths:
        # Check if this MOD name already exists in the parent
        stem = path.stem
        if stem in parent_mechanism_names:
            continue  # modification of existing MOD — allowed
        # New MOD — check for NET_RECEIVE
        content = path.read_text(encoding="utf-8", errors="replace")
        if "NET_RECEIVE" in content:
            errors.append(
                f"mechanisms: '{path.name}' is a new synapse mechanism (contains NET_RECEIVE). "
                f"New synapse mechanisms are not supported — only ion channel MODs can be added."
            )
    return errors


def _get_parent_mechanism_names(
    db_client: entitysdk.client.Client, parent: models.Circuit
) -> set[str]:
    """Get the set of MOD file stems from the parent circuit's mechanisms_dir."""
    import libsonata  # noqa: PLC0415

    try:
        # Stage parent config to get mechanism dir path (EFS-backed, fast)
        from entitysdk.staging.circuit import stage_circuit  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as ptmp:
            config_path = stage_circuit(db_client, model=parent, output_dir=Path(ptmp))
            config = libsonata.CircuitConfig.from_file(str(config_path))
            cfg = json.loads(config.expanded_json)
            mech_dir = cfg.get("components", {}).get("mechanisms_dir", "")
            if mech_dir and Path(mech_dir).is_dir():
                return {p.stem for p in Path(mech_dir).glob("*.mod")}
            # Fallback: scan staged directory for MOD files
            mods = list(Path(ptmp).rglob("*.mod"))
            if mods:
                return {p.stem for p in mods}
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as e:
        L.warning("Could not resolve parent mechanism names: %s", e)
    return set()


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
    asset_gen_callback = {
        "action_type": "http_request_with_token",
        "event_type": "job_on_success",
        "config": {
            "url": (
                f"{settings.API_URL}/api/obi-one/declared/circuit"
                f"/{circuit_id}/generate-assets?force=true"
            ),
            "method": "POST",
        },
    }
    job_data = {
        "code": {
            "type": "python_repository",
            "location": settings.OBI_ONE_REPO,
            "ref": "commit:e33cd3dc88e25f252581c2e8b4d030b86f574499",  # TODO: use tag after merge
            "path": f"{launch_path}/main.py",
            "dependencies": f"{launch_path}/dependencies/default.txt",
            "staged_directories": ["obi_one/"],
        },
        "resources": {
            "type": "machine",
            "image_type": "obi_one",
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
        "callbacks": [asset_gen_callback],
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

    # Compute metadata from the merged circuit
    merged_config = staged_dir / "circuit_config.json"
    if not merged_config.exists():
        raise HTTPException(status_code=500, detail="Staged circuit is missing circuit_config.json")

    try:
        from obi_one.scientific.library.circuit import Circuit as OBICircuit  # noqa: PLC0415
        from obi_one.utils.circuit import (  # noqa: PLC0415
            get_circuit_properties,
            get_circuit_size,
        )

        c = OBICircuit(name=name, path=str(merged_config))
        scale, number_neurons, number_synapses, number_connections = get_circuit_size(c)
        has_morphologies, has_point_neurons, has_electrical_cell_models, has_spines = (
            get_circuit_properties(c)
        )
    except (OSError, ValueError, RuntimeError) as e:
        raise HTTPException(
            status_code=422, detail=f"Failed to compute circuit metadata: {e}"
        ) from e

    circuit_model = models.Circuit(
        name=name,
        description=description,
        subject=parent.subject,
        brain_region=parent.brain_region,
        license=parent.license,
        number_neurons=number_neurons,
        number_synapses=number_synapses,
        number_connections=number_connections,
        has_morphologies=has_morphologies,
        has_point_neurons=has_point_neurons,
        has_electrical_cell_models=has_electrical_cell_models,
        has_spines=has_spines,
        scale=scale,
        build_category=parent.build_category,
        target_simulator=parent.target_simulator,
        root_circuit_id=parent.id,
        lifecycle_status="draft",
    )

    try:
        registered = db_client.register_entity(circuit_model)
    except entitysdk.exception.EntitySDKError as e:
        raise HTTPException(status_code=500, detail=f"Failed to register circuit: {e}") from e

    merged_files = {p.relative_to(staged_dir): p for p in staged_dir.rglob("*") if p.is_file()}
    db_client.upload_directory(
        entity_id=registered.id,  # ty:ignore[invalid-argument-type]
        entity_type=models.Circuit,
        name="sonata_circuit",
        paths=merged_files,  # ty:ignore[invalid-argument-type]
        label=AssetLabel.sonata_circuit,
    )

    # Generate and register stats + visualization assets
    from obi_one.utils.circuit_registration.generate import (  # noqa: PLC0415
        generate_connectivity_matrix_asset,
        generate_connectivity_plot_assets,
        generate_overview_image_asset,
        generate_sim_designer_image_asset,
    )

    edge_pop = (
        c.default_edge_population_name if c.sonata_circuit.edges.population_names else None
    )
    if edge_pop is not None:
        matrix_dir = staged_dir / "__CONN_MATRIX__"
        plot_dir = staged_dir / "__BASIC_PLOTS__"
        viz_dir = staged_dir / "__CIRCUIT_VIZ__"

        _, matrix_config_path, edge_pop = generate_connectivity_matrix_asset(
            circuit_path=merged_config,
            output_dir=matrix_dir,
            edge_population=edge_pop,
        )

        generate_connectivity_plot_assets(
            matrix_config=matrix_config_path,
            edge_population=edge_pop,
            output_dir=plot_dir,
            client=db_client,
            circuit_entity=registered,
        )

        generate_overview_image_asset(
            plot_dir=plot_dir,
            output_dir=viz_dir,
            client=db_client,
            circuit_entity=registered,
        )

        generate_sim_designer_image_asset(
            plot_dir=plot_dir,
            output_dir=viz_dir,
            client=db_client,
            circuit_entity=registered,
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
    description: Annotated[str, Form()] = "",
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
            parent_mech_names = (
                _get_parent_mechanism_names(db_client, parent)
                if (mod_paths or hoc_paths)
                else None
            )
            errors.extend(
                _run_cross_validations(hoc_paths, mod_paths, node_paths, parent_mech_names)
            )

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

    # 5. Trigger async validation task via launch-system
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
