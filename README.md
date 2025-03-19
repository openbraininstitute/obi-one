# Install instructions (draft/notes)

cd \<repo folder\>

uv venv

source .venv/bin/activate

uv sync

uv pip install '.[jupyter,subcircuit_extraction,connectivity_extraction,fastapi_app,database]'

uv pip install -e .

python -m ipykernel install --user --name=.venv --display-name "Python (.venv)"


# Todo

Rewrite several comments in scan.py

Complete bbp-workflow like simulation campaign config

Test building Block dependency tree

Test/integrate Block dictionary parameters for filtering


## Feedback/Noticed by Christoph

When a path of type string is specified as a parameter (i.e. circuit paths), generating the output paths produces many subpaths (for each "/")

Check serialization / deserialization of lists (parsing to json coverts tuples to lists) ... OK

Should wrong list lengths be checked for on Coupled Coordinate generation?

Lists of length 1 don't get cast to single values on scan generation

GridScan with no multi params. Default subdirectory name or don't call it grid scan?

