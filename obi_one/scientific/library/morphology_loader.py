from pathlib import Path

import morphio


def load_morphology_nrn_order(path: Path) -> morphio.Morphology:
    """Load morphology with NEURON-compatible section ordering.

    This is REQUIRED for compatibility with Neurodamus / SONATA section_id semantics.
    """
    collection = morphio.Collection(str(path.parent), extensions=[path.suffix])
    return collection.load(path.stem, morphio.Option.nrn_order)
