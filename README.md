# Install instructions (draft/notes)

uv venv

source .venv/bin/activate

uv sync

uv pip install '.[jupyter,subcircuit_extraction]'

uv pip install -e .


# Todo

Rewrite several comments in scan.py

Complete bbp-workflow like simulation campaign config

Test building Block dependency tree

Test/integrate Block dictionary parameters for filtering


## Feedback/Noticed by Christoph

When a path of type string is specified as a parameter (i.e. circuit paths), generating the output paths produces many subpaths (for each "/")

Check serialization / deserialization of lists (parsing to json coverts tuples to lists)

Should wrong list lengths be checked for on Coupled Coordinate generation?

Coordinate output root not generated automatically

Lists of length 1 don't get cast to single values on scan generation

