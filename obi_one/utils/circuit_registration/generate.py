"""Generation and registration of additional circuit assets."""

import logging
import shutil
from pathlib import Path

from entitysdk import Client, models

from obi_one.utils.db_sdk import OVERVIEW_IMAGE_NAME, SIM_DESIGNER_IMAGE_NAME

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
    from obi_one.utils import db_sdk  # noqa: PLC0415

    if circuit_path.suffix == ".gz":
        L.info("circuit_path is a .gz file; using it directly as compressed circuit.")
        compressed_circuit = circuit_path
    else:
        if output_dir is None:
            msg = "output_dir is required when circuit_path is not a compressed file."
            raise ValueError(msg)

        from obi_one.utils import circuit as circuit_utils  # noqa: PLC0415

        compressed_circuit = circuit_utils.run_circuit_folder_compression(
            circuit_path=circuit_path,
            circuit_name=circuit_entity.name if circuit_entity else "circuit",  # ty:ignore[invalid-argument-type]
            output_root=output_dir,
        )

    if client and circuit_entity:
        db_sdk.add_compressed_circuit_asset(
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
    from obi_one.utils import circuit as circuit_utils, db_sdk  # noqa: PLC0415

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
        db_sdk.add_connectivity_matrix_asset(
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
    from obi_one.utils import circuit as circuit_utils, db_sdk  # noqa: PLC0415

    plot_dir, plot_files = circuit_utils.run_basic_connectivity_plots(
        matrix_config=matrix_config,
        edge_population=edge_population,
        output_root=output_dir,
    )
    if client and circuit_entity:
        db_sdk.add_image_assets(
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
    from obi_one.utils import db_sdk  # noqa: PLC0415

    if image_path is not None:
        L.info(f"Using provided overview image: {image_path}")
        expected_name = OVERVIEW_IMAGE_NAME + image_path.suffix
        viz_path = output_dir / expected_name
        shutil.copy(image_path, viz_path)
    else:
        from obi_one.utils import circuit as circuit_utils  # noqa: PLC0415

        viz_path = circuit_utils.generate_overview_figure(
            plot_dir, output_dir / f"{OVERVIEW_IMAGE_NAME}.png"
        )

    if client and circuit_entity:
        db_sdk.add_image_assets(
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
    from obi_one.utils import db_sdk  # noqa: PLC0415

    if image_path is not None:
        L.info(f"Using provided sim designer image: {image_path}")
        expected_name = SIM_DESIGNER_IMAGE_NAME + image_path.suffix
        viz_path = output_dir / expected_name
        shutil.copy(image_path, viz_path)
    else:
        from obi_one.utils import circuit as circuit_utils  # noqa: PLC0415

        viz_path = circuit_utils.generate_overview_figure(
            plot_dir, output_dir / f"{SIM_DESIGNER_IMAGE_NAME}.png"
        )

    if client and circuit_entity:
        db_sdk.add_image_assets(
            client=client,
            plot_dir=output_dir,
            plot_files=[viz_path.name],
            registered_circuit=circuit_entity,
        )


def generate_additional_circuit_assets(
    circuit_path: Path,
    circuit_path_compressed: Path | None = None,
    edge_population: str | None = None,
    overview_image_path: Path | None = None,
    sim_designer_image_path: Path | None = None,
    client: Client | None = None,
    circuit_entity: models.Circuit | None = None,
) -> None:
    """Generate and register additional circuit assets.

    Generates compressed circuit, connectivity matrices, connectivity plots,
    and overview figures. Each step is independent — failures are logged as
    warnings without aborting the remaining steps.

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
    """
    output_root = circuit_path.parents[1]
    circuit_name = circuit_path.parent.name

    # Define output directories
    compressed_dir = output_root / (circuit_name + "__COMPRESSED__")
    matrix_dir = output_root / (circuit_name + "__CONN_MATRIX__")
    plot_dir = output_root / (circuit_name + "__BASIC_PLOTS__")
    viz_dir = output_root / (circuit_name + "__CIRCUIT_VIZ__")

    # Clean up existing output directories for idempotent reruns
    for d in (compressed_dir, matrix_dir, plot_dir, viz_dir):
        if d.exists():
            shutil.rmtree(d)

    try:
        generate_compressed_circuit_asset(
            circuit_path=circuit_path_compressed or circuit_path,
            output_dir=compressed_dir,
            client=client,
            circuit_entity=circuit_entity,
        )
    except Exception as e:  # noqa: BLE001
        L.warning(f"Compressed circuit asset generation/registration failed: {e}")

    if edge_population is not None:
        try:
            _, matrix_config, edge_population = generate_connectivity_matrix_asset(
                circuit_path=circuit_path,
                output_dir=matrix_dir,
                edge_population=edge_population,
                client=client,
                circuit_entity=circuit_entity,
            )
        except Exception as e:  # noqa: BLE001
            L.warning(f"Connectivity matrix asset generation/registration failed: {e}")
            matrix_config = None

        if matrix_config is not None:
            try:
                generate_connectivity_plot_assets(
                    matrix_config=matrix_config,
                    edge_population=edge_population,
                    output_dir=plot_dir,
                    client=client,
                    circuit_entity=circuit_entity,
                )
            except Exception as e:  # noqa: BLE001
                L.warning(f"Connectivity plot assets generation/registration failed: {e}")

    try:
        generate_overview_image_asset(
            plot_dir=plot_dir,
            output_dir=viz_dir,
            image_path=overview_image_path,
            client=client,
            circuit_entity=circuit_entity,
        )
    except Exception as e:  # noqa: BLE001
        L.warning(f"Overview image asset generation/registration failed: {e}")

    try:
        generate_sim_designer_image_asset(
            plot_dir=plot_dir,
            output_dir=viz_dir,
            image_path=sim_designer_image_path,
            client=client,
            circuit_entity=circuit_entity,
        )
    except Exception as e:  # noqa: BLE001
        L.warning(f"Sim designer image asset generation/registration failed: {e}")
