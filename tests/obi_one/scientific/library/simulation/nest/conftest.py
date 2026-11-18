"""Import PyNEST without its dlopen flags before any test module imports it."""

from obi_one.scientific.library.simulation.nest.nest_import import nest  # ruff: ignore[unused-import]
