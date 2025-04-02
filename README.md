# Install instructions

```
cd obi-one
uv venv
source .venv/bin/activate
uv sync
uv pip install -e .
python -m ipykernel install --user --name=.venv --display-name "Python (.venv)"
```