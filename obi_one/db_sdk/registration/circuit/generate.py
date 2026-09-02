"""Generation and registration of additional circuit assets."""

import logging
import shutil
from pathlib import Path

from entitysdk import Client, models

from obi_one.db_sdk.registration.circuit.assets import (
    OVERVIEW_IMAGE_NAME,
    SIM_DESIGNER_IMAGE_NAME,
    add_compressed_circuit_asset,
    add_connectivity_matrix_asset,
    add_image_assets,
)

L = logging.getLogger(__name__)


def generate_compressed_circuit_asset(
    circuit_path: Path,
    output_dir: Path | None = None,
    client: Client | None = None,
    circuit_entity: models.Circuit | None = None,
) -> None:
    """Generate a compressed circuit archive and optionally register it as an asset.

    If ``circuit_path`` has a .gz extension it is assumed to be an already-compressed
    circuit and is used directly (no recompression).  Otherwise the standard
    compression pipeline is executed.
    """
    if circuit_path.suffix == ".gz":
        L.info("circuit_path is a .gz file; using it directly as compressed circuit.")
        compressed_circuit = circuit_path
    else:
        if output_dir is None:
            msg = "output_dir is required when circuit_path is not a compressed file."
            raise ValueError(msg)

        from obi_one.utils import circuit as circuit_utils  # ruff: ignore[import-outside-top-level]

        compressed_circuit = circuit_utils.run_circuit_folder_compression(
            circuit_path=circuit_path,
            circuit_name=circuit_entity.name if circuit_entity else "circuit",  # ty:ignore[invalid-argument-type]
            output_root=output_dir,
        )

    if client and circuit_entity:
        add_compressed_circuit_asset(
            client=client,
            compressed_file=compressed_circuit,
            registered_circuit=circuit_entity,
        )


def generate_connectivity_matrix_asset(
    circuit_path: Path,
    output_dir: Path,
    edge_population: str | None = None,
    client: Client | None = None,
    circuit_entity: models.Circuit | None = None,
) -> tuple[Path, Path, str]:
    """Generate connectivity matrices and optionally register them as an asset.

    Returns the matrix_dir, matrix_config, and edge_population for downstream use.
    """
    from obi_one.utils import circuit as circuit_utils  # ruff: ignore[import-outside-top-level]

    (
        matrix_dir,
        matrix_config,
        edge_population,
    ) = circuit_utils.run_connectivity_matrix_extraction(
        circuit_path=circuit_path,
        output_root=output_dir,
        edge_population=edge_population,
    )
    if client and circuit_entity:
        add_connectivity_matrix_asset(
            client=client,
            matrix_dir=matrix_dir,
            registered_circuit=circuit_entity,
        )
    return matrix_dir, matrix_config, edge_population


def generate_connectivity_plot_assets(
    matrix_config: Path,
    edge_population: str,
    output_dir: Path,
    client: Client | None = None,
    circuit_entity: models.Circuit | None = None,
) -> tuple[Path, list]:
    """Generate connectivity plots and optionally register them as assets.

    Returns the plot_dir and plot_files for downstream use (overview figure generation).
    """
    from obi_one.utils import circuit as circuit_utils  # ruff: ignore[import-outside-top-level]

    plot_dir, plot_files = circuit_utils.run_basic_connectivity_plots(
        matrix_config=matrix_config,
        edge_population=edge_population,
        output_root=output_dir,
    )
    if client and circuit_entity:
        add_image_assets(
            client=client,
            plot_dir=plot_dir,
            plot_files=plot_files,
            registered_circuit=circuit_entity,
        )
    return plot_dir, plot_files


def generate_overview_image_asset(
    plot_dir: Path | None,
    output_dir: Path,
    *,
    image_path: Path | None = None,
    client: Client | None = None,
    circuit_entity: models.Circuit | None = None,
) -> None:
    """Generate the circuit overview image and optionally register it as an asset.

    If ``image_path`` is provided, it is used directly and generation is skipped.
    Accepted formats: .png or .webp.
    """
    if image_path is not None:
        L.info(f"Using provided overview image: {image_path}")
        output_dir.mkdir(parents=True, exist_ok=True)
        expected_name = OVERVIEW_IMAGE_NAME + image_path.suffix
        viz_path = output_dir / expected_name
        shutil.copy(image_path, viz_path)
    else:
        from obi_one.utils import circuit as circuit_utils  # ruff: ignore[import-outside-top-level]

        viz_path = circuit_utils.generate_overview_figure(
            plot_dir, output_dir / f"{OVERVIEW_IMAGE_NAME}.png"
        )

    if viz_path is None:
        L.info("No overview image generated; skipping registration.")
        return

    if client and circuit_entity:
        add_image_assets(
            client=client,
            plot_dir=output_dir,
            plot_files=[viz_path.name],
            registered_circuit=circuit_entity,
        )


def generate_sim_designer_image_asset(
    plot_dir: Path | None,
    output_dir: Path,
    *,
    image_path: Path | None = None,
    client: Client | None = None,
    circuit_entity: models.Circuit | None = None,
) -> None:
    """Generate the simulation designer image and optionally register it as an asset.

    If ``image_path`` is provided, it is used directly and generation is skipped.
    Accepted format: .png.
    """
    if image_path is not None:
        L.info(f"Using provided sim designer image: {image_path}")
        output_dir.mkdir(parents=True, exist_ok=True)
        expected_name = SIM_DESIGNER_IMAGE_NAME + image_path.suffix
        viz_path = output_dir / expected_name
        shutil.copy(image_path, viz_path)
    else:
        from obi_one.utils import circuit as circuit_utils  # ruff: ignore[import-outside-top-level]

        viz_path = circuit_utils.generate_overview_figure(
            plot_dir, output_dir / f"{SIM_DESIGNER_IMAGE_NAME}.png"
        )

        # Fall back to template if no figure was generated
        if viz_path is None:
            from importlib.resources import files  # ruff: ignore[import-outside-top-level]

            template = Path(
                str(files("obi_one.scientific.library").joinpath("circuit_template.png"))
            )
            output_dir.mkdir(parents=True, exist_ok=True)
            viz_path = output_dir / f"{SIM_DESIGNER_IMAGE_NAME}.png"
            shutil.copy(template, viz_path)

    if client and circuit_entity:
        add_image_assets(
            client=client,
            plot_dir=output_dir,
            plot_files=[viz_path.name],
            registered_circuit=circuit_entity,
        )


def _entity_has_asset(circuit_entity: models.Circuit | None, asset_label: str) -> bool:
    """Return True if circuit_entity already has an asset with the given label."""
    if circuit_entity is None:
        return False
    existing = {
        getattr(asset.label, "value", asset.label) for asset in (circuit_entity.assets or [])
    }
    return asset_label in existing


def generate_additional_circuit_assets(  # ruff: ignore[complex-structure, too-many-branches]
    circuit_path: Path,
    circuit_path_compressed: Path | None = None,
    edge_population: str | None = None,
    overview_image_path: Path | None = None,
    sim_designer_image_path: Path | None = None,
    client: Client | None = None,
    circuit_entity: models.Circuit | None = None,
    *,
    force: bool = False,
    include_compressed: bool = True,
    include_visualization: bool = True,
) -> None:
    """Generate and register additional circuit assets.

    Considers connectivity matrices, and — when ``include_compressed`` is True
    (default) — the compressed circuit archive. When ``include_visualization``
    is True (default), also generates connectivity plots and overview figures.
    Each step is independent — failures are logged as warnings without aborting
    the remaining steps.

    If client and circuit_entity are provided, assets are registered to entitycore.
    Otherwise, only generation is performed (useful for local runs).

    Args:
        circuit_path: Path to the circuit_config.json file.
        circuit_path_compressed: Path to an already-compressed circuit file (.gz).
            If provided, compression is skipped and this file is used directly (optional).
        edge_population: Name of the edge population for matrix extraction
            and connectivity plots (optional).
        overview_image_path: Path to a pre-existing overview image file (.png or .webp).
            If provided, generation is skipped and this file is registered directly (optional).
        sim_designer_image_path: Path to a pre-existing simulation designer image file (.png).
            If provided, generation is skipped and this file is registered directly (optional).
        client: The entitycore SDK client (optional).
        circuit_entity: The registered circuit entity to attach assets to (optional).
        force: If True, regenerate and re-upload compressed/matrices even when they
            already exist. If False (default), skip assets that are already present.
        include_compressed: If True (default), also generate the compressed circuit
            archive. Set False when the circuit folder is staged as symlinks (circuit
            customization), where compression would archive dangling links — the
            post-validation asset job creates that asset from a fully staged copy.
        include_visualization: If True (default), also generate plots and overview /
            sim-designer images. Set False for the post-validation async job, which
            only needs compressed + connectivity matrices (viz assets are created
            synchronously at register/customize time).
    """
    output_root = circuit_path.parents[1]
    circuit_name = circuit_path.parent.name

    # Define output directories
    compressed_dir = output_root / (circuit_name + "__COMPRESSED__")
    matrix_dir = output_root / (circuit_name + "__CONN_MATRIX__")
    plot_dir = output_root / (circuit_name + "__BASIC_PLOTS__")
    viz_dir = output_root / (circuit_name + "__CIRCUIT_VIZ__")

    # Clean up existing output directories for idempotent reruns
    dirs_to_clean = [matrix_dir]
    if include_compressed:
        dirs_to_clean.append(compressed_dir)
    if include_visualization:
        dirs_to_clean.extend([plot_dir, viz_dir])
    for d in dirs_to_clean:
        if d.exists():
            shutil.rmtree(d)

    # Run additional asset generation
    if not include_compressed:
        L.info(
            "Compression not requested for circuit %s — skipping compressed_sonata_circuit",
            getattr(circuit_entity, "id", None),
        )
    elif not force and _entity_has_asset(circuit_entity, "compressed_sonata_circuit"):
        L.info(
            "compressed_sonata_circuit already present on circuit %s — skipping compression",
            getattr(circuit_entity, "id", None),
        )
    else:
        try:
            generate_compressed_circuit_asset(
                circuit_path=circuit_path_compressed or circuit_path,
                output_dir=compressed_dir,
                client=client,
                circuit_entity=circuit_entity,
            )
        except Exception as e:  # ruff: ignore[blind-except]
            L.warning(f"Compressed circuit asset generation/registration failed: {e}")

    skip_matrices = not force and _entity_has_asset(circuit_entity, "circuit_connectivity_matrices")
    matrix_config = None
    if skip_matrices:
        L.info(
            "circuit_connectivity_matrices already present on circuit %s — skipping",
            getattr(circuit_entity, "id", None),
        )
    elif edge_population is not None:
        try:
            _, matrix_config, edge_population = generate_connectivity_matrix_asset(
                circuit_path=circuit_path,
                output_dir=matrix_dir,
                edge_population=edge_population,
                client=client,
                circuit_entity=circuit_entity,
            )
        except Exception as e:  # ruff: ignore[blind-except]
            L.warning(f"Connectivity matrix asset generation/registration failed: {e}")
            matrix_config = None

    if not include_visualization:
        return

    if matrix_config is not None and edge_population is not None:
        try:
            generate_connectivity_plot_assets(
                matrix_config=matrix_config,
                edge_population=edge_population,
                output_dir=plot_dir,
                client=client,
                circuit_entity=circuit_entity,
            )
        except Exception as e:  # ruff: ignore[blind-except]
            L.warning(f"Connectivity plot assets generation/registration failed: {e}")

    try:
        generate_overview_image_asset(
            plot_dir=plot_dir,
            output_dir=viz_dir,
            image_path=overview_image_path,
            client=client,
            circuit_entity=circuit_entity,
        )
    except Exception as e:  # ruff: ignore[blind-except]
        L.warning(f"Overview image asset generation/registration failed: {e}")

    try:
        generate_sim_designer_image_asset(
            plot_dir=plot_dir,
            output_dir=viz_dir,
            image_path=sim_designer_image_path,
            client=client,
            circuit_entity=circuit_entity,
        )
    except Exception as e:  # ruff: ignore[blind-except]
        L.warning(f"Sim designer image asset generation/registration failed: {e}")
