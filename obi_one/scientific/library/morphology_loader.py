from pathlib import Path

import morphio


def load_morphology_nrn_order(path: Path) -> morphio.Morphology:
    """Load morphology with NEURON-compatible section ordering.

    This is REQUIRED for compatibility with Neurodamus / SONATA section_id semantics.
    """
    return load_morphology_nrn_order_from_collection(path.parent, path.stem, path.suffix)


def load_morphology_nrn_order_from_collection(
    base: Path, name: str, extension: str
) -> morphio.Morphology:
    """Load a named morphology from a directory or an `.h5` container.

    `morphio.Collection` accepts either as `base`, which is what makes containerized circuits
    work: they declare no per-morphology file, only a single container.
    """
    collection = morphio.Collection(str(base), extensions=[extension])
    return collection.load(name, morphio.Option.nrn_order)
