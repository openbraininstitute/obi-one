"""Validation functions for population customization inputs."""

from pathlib import Path

from bluepysnap import Circuit


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
    """Validate that the customized circuit can be loaded and has valid populations.

    Attempts to load the circuit and access node/edge population sizes. This will
    raise if files are missing or corrupted.

    Args:
        new_circuit_path: Path to the new circuit folder (containing circuit_config.json).

    Raises:
        ValueError: If the circuit cannot be loaded or population files are invalid.
    """
    try:
        circuit = Circuit(new_circuit_path / "circuit_config.json")
        circuit.nodes.size
        circuit.edges.size
    except Exception as e:
        msg = f"Failed to load customized circuit: {e}"
        raise ValueError(msg) from e
