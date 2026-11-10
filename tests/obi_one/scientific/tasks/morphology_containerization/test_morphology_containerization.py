from pathlib import Path

import pytest
from bluepysnap import BluepySnapError

from obi_one.scientific.library.circuit import Circuit


def test_morphology_containerization(containerized_hex0_l5_circuit: Circuit):
    """Assert containerized morph wiring on the shared session fixture circuit."""
    circuit = containerized_hex0_l5_circuit
    nodes = circuit.sonata_circuit.nodes[circuit.default_population_name]
    # Check .h5 morph dir --> Error, since .h5 container file
    with pytest.raises(
        BluepySnapError,
        match=r"'.*' is a morphology container, so a directory does not exist",
    ):
        _ = Path(nodes.morph.get_morphology_dir(extension="h5"))
    # Check .swc morph dir --> Error, since no .swc folder defined
    with pytest.raises(BluepySnapError, match="'morphologies_dir' is not defined in config"):
        _ = Path(nodes.morph.get_morphology_dir(extension="swc"))
    # Check .asc morph dir --> Error, since no .asc folder defined
    with pytest.raises(
        BluepySnapError, match="'neurolucida-asc' is not defined in 'alternate_morphologies'"
    ):
        _ = Path(nodes.morph.get_morphology_dir(extension="asc"))
    # Check .h5 container file
    h5_file = Path(nodes.morph._get_morphology_base("h5"))
    assert h5_file.is_file()
    assert h5_file.parts[-1] == "merged-morphologies.h5"
    # Check morph access
    for nid in nodes.ids():
        _ = nodes.morph.get(nid, transform=True, extension="h5")
