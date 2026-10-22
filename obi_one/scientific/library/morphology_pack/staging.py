"""The files of a stored circuit its morphology pack is built from, and no others."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import libsonata
from entitysdk import Client, models

from obi_one.scientific.library.circuit_staging import (
    SONATA_CIRCUIT_ASSET_SELECTION,
    stage_circuit_nodes,
)
from obi_one.scientific.library.morphology_pack.circuit import (
    biophysical_populations,
    morphologies_source,
    morphology_files,
)

FETCHES_AT_ONCE = 8


def stage_morphology_pack_inputs(client: Client, circuit: models.Circuit, directory: Path) -> Path:
    """Fetch into `directory` the circuit's config, node sets and nodes, and its biophysical
    populations' morphologies, each from the local store where the client has one that holds it,
    else by download; the config's path.
    """
    directory = directory.resolve()
    asset = client.select_assets(circuit, selection=SONATA_CIRCUIT_ASSET_SELECTION).one()
    config_path = stage_circuit_nodes(client, entity_id=circuit.id, asset=asset, dest_dir=directory)
    config = libsonata.CircuitConfig.from_file(str(config_path))
    files = set()
    for name in biophysical_populations(config):
        population = config.node_population(name)
        morphologies = population.get_attribute("morphology", population.select_all())
        files.update(morphology_files(*morphologies_source(config, name), morphologies))

    def fetch(path: Path) -> None:
        asset_path = path.relative_to(directory)
        client.fetch_file(
            entity_id=circuit.id,
            entity_type=models.Circuit,
            # the asset, not its id: given an id, the client looks the asset up for every file
            asset_id=asset,
            output_path=directory / asset_path,
            asset_path=asset_path,
        )

    with ThreadPoolExecutor(max_workers=FETCHES_AT_ONCE) as pool:
        list(pool.map(fetch, files))
    return config_path
