"""Import PyNEST without leaving its dlopen flags set.

``nest`` sets ``RTLD_GLOBAL`` on import and never restores it. Every extension module imported
afterwards, such as PyTables, h5py or NEURON, then exposes its symbols and clashes with the
libraries bundled in the NEST wheel, which aborts the process.
"""

import sys

flags = sys.getdlopenflags()
try:
    import nest  # ruff: ignore[unused-import]
finally:
    sys.setdlopenflags(flags)
