"""Circuit customization endpoint."""

import json
import logging
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated
from uuid import UUID

import entitysdk.client
import entitysdk.exception
import h5py
import libsonata
from bluepysnap import Circuit as SnapCircuit
from entitysdk import models
from entitysdk.staging.circuit import stage_circuit
from entitysdk.types import DerivationType, EntityLifecycleStatus
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.dependencies.auth import user_verified
from app.dependencies.compute_cell import ComputeCellDep
from app.dependencies.entitysdk import get_client
from app.dependencies.launch_system import LaunchSystemClientDep
from app.endpoints.circuit_helpers import trigger_validation_task
from obi_one.db_sdk.registration.circuit import register_circuit
from obi_one.scientific.validations.emodels import (
    BUILTIN_NEURON_MECHANISMS,
    check_mechanisms,
    check_structure,
)
from obi_one.utils.circuit_customization.staging import stage_customized_circuit

L = logging.getLogger(__name__)

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


class CircuitCustomizationResponse(BaseModel):
    """Response for circuit customization."""

    circuit_id: UUID
    status: str
    message: str
    job_id: UUID | None = None


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


@dataclass(frozen=True)
class ParentCircuitContext:
    """What the cross-file validations need to know about the parent circuit.

    Collected in a single staging pass, since staging the parent is the expensive
    part. Every field is empty when the parent could not be resolved, in which
    case the checks that depend on it are skipped rather than failed.
    """

    mechanism_names: set[str]
    hoc_stems: set[str]
    model_template_stems: set[str]


def _safe_upload_name(filename: str | None) -> str:
    """Return the basename of an upload filename, discarding any path components."""
    if not filename:
        msg = "Uploaded file must have a filename"
        raise ValueError(msg)
    return Path(filename).name


def _save_upload(upload: UploadFile, target_dir: Path) -> Path:
    """Save a single uploaded file into target_dir using only its basename."""
    dest = target_dir / _safe_upload_name(upload.filename)
    dest.write_bytes(upload.file.read())
    return dest


def _save_uploads(files: list[UploadFile], target_dir: Path) -> list[Path]:
    """Save uploaded files to a directory and return their paths."""
    return [_save_upload(f, target_dir) for f in files]


def _validate_edge_population(path: Path, pop_name: str, pop: h5py.Group) -> None:
    """Validate the structure of a single edge population group."""
    for required in ("source_node_id", "target_node_id", "edge_type_id"):
        if required not in pop:
            msg = f"'{path.name}' population '{pop_name}': missing '{required}'"
            raise EdgeValidationError(msg)


def _validate_edges(paths: list[Path]) -> None:
    """Layer 1 validation for edge files."""
    for path in paths:
        try:  # ruff: ignore[too-many-statements-in-try-clause]
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
            if len(parts) >= 2 and parts[0] == "SUFFIX":  # ruff: ignore[magic-value-comparison]
                names.add(parts[1])
    return names


def _validate_nodes(paths: list[Path]) -> None:
    """Layer 1 validation for node files."""
    for path in paths:
        try:  # ruff: ignore[too-many-statements-in-try-clause]
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
    VALID_OPERATORS = {"$regex", "$gt", "$lt", "$gte", "$lte"}  # ruff: ignore[non-lowercase-variable-in-function]

    for k, v in expr.items():
        if k == "population":
            if not isinstance(v, str | list):
                msg = f"'{path.name}' nodeset '{key}': 'population' value must be a string or list"
                raise NodeSetsValidationError(msg)
        elif k == "node_id":
            if not isinstance(v, list) or not all(isinstance(i, int) for i in v):
                msg = f"'{path.name}' nodeset '{key}': 'node_id' value must be a list of ints"
                raise NodeSetsValidationError(msg)
        elif k in VALID_OPERATORS:
            pass  # operator values are unconstrained at this layer
        elif not isinstance(v, str | int | float | bool | list):
            msg = (
                f"'{path.name}' nodeset '{key}': "
                f"attribute filter value for '{k}' must be a scalar or list"
            )
            raise NodeSetsValidationError(msg)


def _validate_nodeset_list(path: Path, key: str, expr: list) -> None:
    """Validate a list-based compound nodeset expression (names of other node sets)."""
    for item in expr:
        if not isinstance(item, str):
            msg = (
                f"'{path.name}' nodeset '{key}': "
                "compound expression items must be strings (node set names)"
            )
            raise NodeSetsValidationError(msg)


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
    available = BUILTIN_NEURON_MECHANISMS | _extract_mod_mechanism_names(mod_paths)
    if parent_mechanism_names:
        available |= parent_mechanism_names

    for hoc_path in hoc_paths:
        try:
            check_mechanisms(hoc_path, available)  # ty:ignore[invalid-argument-type]
        except ValueError as e:
            raise HocValidationError(str(e)) from e


def _template_stems(templates: Iterable[str]) -> set[str]:
    """Reduce SONATA model_template values ('hoc:MyCell') to their file stems."""
    return {t.split(":", 1)[1] for t in templates if ":" in t}


def _read_model_templates(node_path: Path) -> set[str]:
    """Read the model_template values of every population in a SONATA nodes file.

    libsonata resolves the ``@library`` indirection, so enumerated and plain string
    storage are read the same way.
    """
    templates: set[str] = set()
    storage = libsonata.NodeStorage(str(node_path))
    for pop_name in storage.population_names:
        pop = storage.open_population(pop_name)
        if "model_template" in pop.enumeration_names:
            templates.update(pop.enumeration_values("model_template"))
        elif "model_template" in pop.attribute_names and pop.size:
            selection = libsonata.Selection([(0, pop.size)])
            templates.update(pop.get_attribute("model_template", selection))
    return templates


def _collect_uploaded_model_templates(node_paths: list[Path]) -> set[str]:
    """Collect the model_template values declared by the uploaded node files."""
    templates: set[str] = set()
    for node_path in node_paths:
        try:
            templates |= _read_model_templates(node_path)
        except (libsonata.SonataError, OSError, RuntimeError) as e:
            # Structure was already checked by _validate_nodes; a file libsonata
            # cannot read simply contributes no templates.
            L.warning("Could not read model templates from '%s': %s", node_path.name, e)
            continue
    return templates


def _validate_nodes_hoc_consistency(
    node_paths: list[Path],
    hoc_paths: list[Path],
    parent: ParentCircuitContext | None = None,
) -> None:
    """Check consistency between the uploaded nodes and HOC files.

    Validates:
    1. Every model_template in the uploaded nodes resolves to a HOC file, either
       uploaded here or already present in the parent. Skipped when the parent's
       HOC files could not be resolved, so that an unreadable parent cannot turn
       into a spurious rejection — the async validation task checks emodel paths
       against the merged circuit either way.
    2. Every uploaded HOC file is referenced by a model_template, either in the
       uploaded nodes or in one of the parent's node populations. The latter covers
       replacing a HOC used by populations the customization does not touch.
    """
    parent_hoc_stems = parent.hoc_stems if parent else set()
    parent_template_stems = parent.model_template_stems if parent else set()

    templates_in_nodes = _collect_uploaded_model_templates(node_paths)
    if not templates_in_nodes:
        return

    uploaded_hoc_stems = {p.stem for p in hoc_paths}
    node_template_stems = _template_stems(templates_in_nodes)

    if parent_hoc_stems:
        missing_hoc = node_template_stems - uploaded_hoc_stems - parent_hoc_stems
        if missing_hoc:
            msg = (
                f"model_template(s) {sorted(missing_hoc)} in the uploaded nodes files have no"
                " matching HOC file, neither uploaded nor present in the parent circuit"
            )
            raise ValueError(msg)

    unused_hoc = uploaded_hoc_stems - node_template_stems - parent_template_stems
    if unused_hoc:
        msg = (
            f"Uploaded HOC file(s) {sorted(unused_hoc)} are not referenced by any model_template,"
            " neither in the uploaded nodes files nor in the parent circuit"
        )
        raise ValueError(msg)


def _run_cross_validations(
    hoc_paths: list[Path],
    mod_paths: list[Path],
    node_paths: list[Path],
    parent: ParentCircuitContext | None = None,
) -> list[str]:
    """Run cross-file validations and return collected error messages."""
    errors: list[str] = []
    if hoc_paths:
        try:
            _validate_hoc_mechanisms(
                hoc_paths, mod_paths, parent.mechanism_names if parent else None
            )
        except HocValidationError as e:
            errors.append(f"hoc/mod cross-check: {e}")
    if node_paths and hoc_paths and not errors:
        try:
            _validate_nodes_hoc_consistency(node_paths, hoc_paths, parent)
        except ValueError as e:
            errors.append(f"nodes/hoc cross-check: {e}")
    if mod_paths and parent is not None:
        synapse_errors = _validate_new_mod_not_synapse(mod_paths, parent.mechanism_names)
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


def _collect_parent_node_facts(circuit: SnapCircuit) -> tuple[set[str], set[str], set[str]]:
    """Collect mechanism, HOC, and model_template names from each node population."""
    mechanism_names: set[str] = set()
    hoc_stems: set[str] = set()
    template_stems: set[str] = set()

    for pop_name in circuit.nodes.population_names:
        pop = circuit.nodes[pop_name]

        mech_dir_str = pop.config.get("mechanisms_dir")
        if mech_dir_str and Path(mech_dir_str).is_dir():
            mechanism_names |= {p.stem for p in Path(mech_dir_str).glob("*.mod")}

        hoc_dir_str = pop.config.get("biophysical_neuron_models_dir")
        if hoc_dir_str and Path(hoc_dir_str).is_dir():
            hoc_stems |= {p.stem for p in Path(hoc_dir_str).glob("*.hoc")}

        if "model_template" in pop.property_names:
            template_stems |= _template_stems(pop.property_values("model_template"))

    return mechanism_names, hoc_stems, template_stems


def _get_parent_context(
    db_client: entitysdk.client.Client, parent: models.Circuit
) -> ParentCircuitContext:
    """Stage the parent circuit once and read what the cross-checks need via SNAP."""
    try:  # ruff: ignore[too-many-statements-in-try-clause]
        with tempfile.TemporaryDirectory() as ptmp:
            config_path = stage_circuit(db_client, model=parent, output_dir=Path(ptmp))
            circuit = SnapCircuit(str(config_path))
            mechanism_names, hoc_stems, template_stems = _collect_parent_node_facts(circuit)

            if not mechanism_names:
                # Fallback for circuits predating per-population "mechanisms_dir"
                mechanism_names = {p.stem for p in Path(ptmp).rglob("*.mod")}

            return ParentCircuitContext(
                mechanism_names=mechanism_names,
                hoc_stems=hoc_stems,
                model_template_stems=template_stems,
            )
    except (OSError, KeyError, ValueError, TypeError) as e:
        L.warning("Could not resolve parent circuit context: %s", e)
    return ParentCircuitContext(mechanism_names=set(), hoc_stems=set(), model_template_stems=set())


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
        node_sets_path = _save_upload(node_sets_file, tmp)
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


def _stage_and_register(
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
    """Stage the parent circuit with the overrides applied, then register the merged circuit.

    Registration itself is delegated to ``register_circuit``, which computes metadata,
    creates the entity and its derivation from the parent, and registers the SONATA
    folder plus visualization assets. The compressed archive is left to the
    post-validation asset job: the staged folder is a tree of symlinks into the parent's
    storage, so compressing it here would archive links rather than data.
    """
    staged_dir = tmp / "staged"
    staged_dir.mkdir()

    try:
        merged_config = stage_customized_circuit(
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

    if parent.brain_region is None or parent.subject is None:
        raise HTTPException(
            status_code=422,
            detail=f"Parent circuit {parent.id} has no brain region or subject to inherit from.",
        )

    try:
        registered = register_circuit(
            client=db_client,
            circuit_path=merged_config,
            name=name,
            description=description,
            build_category=parent.build_category,
            brain_region=parent.brain_region,
            subject=parent.subject,
            target_simulator=parent.target_simulator,
            license=parent.license,
            parent=parent,
            derivation_type=DerivationType.circuit_customization,
            skip_validation=True,
            lifecycle_status="draft",
            include_compressed=False,
        )
    except (OSError, ValueError, RuntimeError) as e:
        raise HTTPException(
            status_code=422, detail=f"Failed to register customized circuit: {e}"
        ) from e
    except entitysdk.exception.EntitySDKError as e:
        raise HTTPException(status_code=500, detail=f"Failed to register circuit: {e}") from e

    if registered is None:
        raise HTTPException(status_code=500, detail="Circuit registration returned no entity")
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
            raise ValueError(msg)  # ruff: ignore[raise-within-try]
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
        "\n\nA node_sets upload replaces the file the circuit config references when it carries"
        " the same name, and is otherwise added with the config repointed at it. Alongside a"
        " circuit_config override, that config is authoritative and must reference the upload."
        "\n\nTo place HOC files into a population-specific model directory, supply"
        " emodel_population_manifest as a JSON object mapping filename → population name."
    ),
)
def customize_circuit_endpoint(  # ruff: ignore[too-many-arguments, too-many-positional-arguments]
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    ls_client: LaunchSystemClientDep,
    compute_cell: ComputeCellDep,
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

    if parent.lifecycle_status != EntityLifecycleStatus.active:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Parent circuit must have lifecycle_status 'active' "
                f"(got '{parent.lifecycle_status}'). "
                "Only validated circuits can be customized."
            ),
        )

    # 2. Save uploads and run Layer 1 validations
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)

        cfg_path: Path | None = None
        if circuit_config_file:
            cfg_path = _save_upload(circuit_config_file, tmp)

        edge_paths, hoc_paths, mod_paths, node_paths, node_sets_path, errors = _run_validations(
            tmp, edges_files, emodel_files, mechanism_files, node_files, node_sets_file
        )

        # Cross-validations
        if not errors:
            parent_context = (
                _get_parent_context(db_client, parent) if (mod_paths or hoc_paths) else None
            )
            errors.extend(_run_cross_validations(hoc_paths, mod_paths, node_paths, parent_context))

        if errors:
            raise HTTPException(status_code=422, detail={"validation_errors": errors})

        # 3. Stage, override, and register
        registered = _stage_and_register(
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

    # 4. Trigger async validation task via launch-system
    job_id = trigger_validation_task(
        ls_client=ls_client,
        circuit_id=registered.id,
        project_id=db_client.project_context.project_id,  # ty:ignore[unresolved-attribute]
        virtual_lab_id=db_client.project_context.virtual_lab_id,  # ty:ignore[unresolved-attribute, invalid-argument-type]
        compute_cell=compute_cell,
    )

    L.info(
        "Customized circuit '%s' created: %s (parent: %s, job_id=%s)",
        name,
        registered.id,
        parent_circuit_id,
        job_id,
    )

    return CircuitCustomizationResponse(
        circuit_id=registered.id,
        status="draft",
        message=f"Circuit created from parent {parent_circuit_id}. Validation pending.",
        job_id=job_id,
    )
