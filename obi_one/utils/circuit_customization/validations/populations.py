"""Validation functions for population customization inputs."""

from pathlib import Path

from bluepysnap import Circuit
from bluepysnap.exceptions import BluepySnapError


def _validate_file(path: str | Path, expected_suffix: str, label: str) -> Path:
    """Validate that a file exists and has the expected extension."""
    path = Path(path)
    if not path.is_file() or path.suffix.lower() != expected_suffix:
        msg = f"{label} '{path}' does not exist or has wrong format (must be {expected_suffix})!"
        raise ValueError(msg)
    return path


def _validate_file_dict(
    paths: dict[str, str | Path], expected_suffix: str, label: str
) -> dict[str, Path]:
    """Validate a dict of file paths and return them as Path objects."""
    result = {k: Path(v) for k, v in paths.items()}
    wrong = [
        path
        for path in result.values()
        if not path.is_file() or path.suffix.lower() != expected_suffix
    ]
    if wrong:
        msg = (
            f"{label} path(s) don't exist or have wrong format (must be {expected_suffix}): {wrong}"
        )
        raise ValueError(msg)
    return result


def check_input_files(
    new_circuit_config_path: str | Path | None = None,
    new_node_sets_path: str | Path | None = None,
    new_node_population_paths: dict[str, str | Path] | None = None,
    new_edge_population_paths: dict[str, str | Path] | None = None,
) -> tuple[Path | None, Path | None, dict[str, Path] | None, dict[str, Path] | None]:
    """Validate all population customization input files.

    Checks that at least one customization is provided and that all specified
    files exist with the correct format.

    Args:
        new_circuit_config_path: Path to a replacement circuit_config.json file.
        new_node_sets_path: Path to a replacement node_sets.json file.
        new_node_population_paths: Mapping of population name to replacement nodes .h5 file.
        new_edge_population_paths: Mapping of population name to replacement edges .h5 file.

    Returns:
        Tuple of validated paths (circuit_config, node_sets, node_populations, edge_populations).

    Raises:
        ValueError: If no customization files are provided or any file is invalid.
    """
    if (
        not new_circuit_config_path
        and not new_node_sets_path
        and not new_node_population_paths
        and not new_edge_population_paths
    ):
        msg = "No customization files provided!"
        raise ValueError(msg)

    validated_config = None
    if new_circuit_config_path:
        validated_config = _validate_file(new_circuit_config_path, ".json", "New config file")
        if validated_config.name != "circuit_config.json":
            msg = "Circuit config file 'circuit_config.json' required!"
            raise ValueError(msg)

    validated_node_sets = None
    if new_node_sets_path:
        validated_node_sets = _validate_file(new_node_sets_path, ".json", "New node sets file")

    validated_node_pops = None
    if new_node_population_paths:
        validated_node_pops = _validate_file_dict(
            new_node_population_paths, ".h5", "New node population file"
        )

    validated_edge_pops = None
    if new_edge_population_paths:
        validated_edge_pops = _validate_file_dict(
            new_edge_population_paths, ".h5", "New edge population file"
        )

    return validated_config, validated_node_sets, validated_node_pops, validated_edge_pops


def check_customized_circuit(new_circuit_path: Path) -> None:
    """Validate that the customized circuit can be loaded successfully.

    Attempts to load the circuit and access node/edge populations and node sets.
    This will raise if files are missing or corrupted.

    Args:
        new_circuit_path: Path to the new circuit folder (containing circuit_config.json).

    Raises:
        ValueError: If the circuit cannot be loaded or population/node set files are invalid.
    """
    try:
        circuit = Circuit(new_circuit_path / "circuit_config.json")
        circuit.nodes.size  # noqa: B018
        circuit.edges.size  # noqa: B018
        circuit.node_sets  # noqa: B018
    except Exception as e:
        msg = f"Failed to load customized circuit: {e}"
        raise ValueError(msg) from e


def _get_morph_paths(circuit: Circuit) -> set[str]:
    """Get all unique morphology directory paths referenced by the circuit."""
    morph_paths = set()
    for npop in circuit.nodes.population_names:
        morph = circuit.nodes[npop].morph
        for ext in ["swc", "asc", "h5"]:
            try:
                morph_path = morph._get_morphology_base(ext)  # noqa: SLF001
            except BluepySnapError:
                continue
            if morph_path:
                morph_paths.add(morph_path)
    return morph_paths


def _get_morph_names(circuit: Circuit) -> set[str]:
    """Get all unique morphology names referenced by the circuit's node populations."""
    morph_names = set()
    for npop in circuit.nodes.population_names:
        nodes = circuit.nodes[npop]
        if "morphology" in nodes.property_names:
            morph_names.update(nodes.get(properties="morphology").to_list())
    return morph_names


def check_morphologies(new_circuit: Circuit, parent_circuit: Circuit) -> None:
    """Check that all morphology paths and names in the new circuit exist in the parent.

    Ensures the customized circuit does not reference morphology directories or
    morphology names that were not present in the parent circuit.

    Args:
        new_circuit: The loaded new circuit (after customization).
        parent_circuit: The loaded parent circuit (before customization).

    Raises:
        ValueError: If new morphology paths or names are not a subset of the parent's.
    """
    new_morph_paths = _get_morph_paths(new_circuit)
    old_morph_paths = _get_morph_paths(parent_circuit)
    extra_paths = new_morph_paths - old_morph_paths
    if extra_paths:
        msg = f"Morphology path(s) not found in parent circuit: {extra_paths}"
        raise ValueError(msg)

    new_morph_names = _get_morph_names(new_circuit)
    old_morph_names = _get_morph_names(parent_circuit)
    extra_names = new_morph_names - old_morph_names
    if extra_names:
        msg = f"{len(extra_names)} morphology name(s) not found in parent circuit!"
        raise ValueError(msg)


def _get_hoc_paths(circuit: Circuit) -> set[str]:
    """Get all unique electrical model .hoc directory paths referenced by the circuit."""
    hoc_paths = set()
    for npop in circuit.nodes.population_names:
        nodes = circuit.nodes[npop]
        if nodes.type == "virtual":
            continue
        hoc_path = nodes.config.get("biophysical_neuron_models_dir", "")
        if hoc_path:
            hoc_paths.add(hoc_path)
    return hoc_paths


def _get_hoc_names(circuit: Circuit) -> set[str]:
    """Get all unique electrical model .hoc names referenced by the circuit's node populations."""
    hoc_names = set()
    for npop in circuit.nodes.population_names:
        nodes = circuit.nodes[npop]
        if "model_template" in nodes.property_names:
            hoc_names.update(nodes.get(properties="model_template").to_list())
    return hoc_names


def check_electrical_models(new_circuit: Circuit, parent_circuit: Circuit) -> None:
    """Check that all electrical model paths and names in the new circuit exist in the parent.

    Ensures the customized circuit does not reference .hoc directories or
    model templates that were not present in the parent circuit.

    Args:
        new_circuit: The loaded new circuit (after customization).
        parent_circuit: The loaded parent circuit (before customization).

    Raises:
        ValueError: If new .hoc paths or model names are not a subset of the parent's.
    """
    new_hoc_paths = _get_hoc_paths(new_circuit)
    old_hoc_paths = _get_hoc_paths(parent_circuit)
    extra_paths = new_hoc_paths - old_hoc_paths
    if extra_paths:
        msg = f"Electrical model .hoc path(s) not found in parent circuit: {extra_paths}"
        raise ValueError(msg)

    new_hoc_names = _get_hoc_names(new_circuit)
    old_hoc_names = _get_hoc_names(parent_circuit)
    extra_names = new_hoc_names - old_hoc_names
    if extra_names:
        msg = f"{len(extra_names)} electrical model .hoc name(s) not found in parent circuit!"
        raise ValueError(msg)
