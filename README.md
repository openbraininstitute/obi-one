___

# Overview

The current scope of obi-one is to:
- Standardize the creation of multi-dimensional parameter scans across different modeling workflows to maximise code reuse for technical aspects such as endpoint generation, reproducibility , and data persistance.
- Seperate scientific modeling functionality from service and database technicalities, to enable fast addition of functionality by scientists.
- Automatically generate FastAPI endpoints which allow for 1) automatic generation of GUIs, 2) integration with LLM agents.
- Standardize serialization of multi-dimensional parameter scans to support reproducibility.
- Standardize database persistance.

In the future, we hope to: 
- Support scientific workflows composing multiple scientific modeling steps.
- Standardize the production of figures for manuscripts and frontend display.


<br>



# Installation

```
cd obi-one
uv venv
source .venv/bin/activate
uv sync
uv pip install -e .
python -m ipykernel install --user --name=.venv --display-name "Python (.venv)"
```

<br>



# Examples
Example notebooks are available in the examples/ directory

<br>



# Technical Overview / Glossary

Specific modeling use cases are built upon several key classes, which each inherit from [OBIBaseModel](obi/modeling/core/base.py). OBIBaseModel extends Pydantic's BaseModel (which supports type checking, json serialization and standardized generation of endpoints) to additionally support correct deserialization of serialized objects.

obi-one has the following base classes:

- [Form](obi/modeling/core/form.py): defines a single modeling use case 

- [Block](obi/modeling/core/block.py): component of a Form



- [Scan](obi/modeling/core/scan.py): a basic 


<br>




# Launching the FAST API Service
To launch the FAST API service simply call:
```
uvicorn examples.launch_service_example:app --reload
```

Once launched, the generated endpoints can then be viewed at: http://127.0.0.1:8000/docs


<br>




# Generative GUI:
Once the service has been launched, the generated gui can additionally be launched: https://github.com/openbraininstitute/obi-generative-gui

<br>




# Developer guidelines

- We recommend that any new features are developed on a new branch originating from the **dev** branch. 
- The name of the new branch should describe the change being worked on (i.e. **current_stimulus_fix**). 
- When multiple developers are working on such a branch it may be preferable to create additioanl branches with a suffix indicating their initials (i.e. **current_stimulus_fix_bfg**).
- Developers should make pull requests into the dev branch. The pull request can be merged by the developer who created it if the changes are small and unlikely to affect other parts of the codebase. Otherwise, if the changes might affect other parts of the codebase or the developer would like a second opinion, the developer can request for another developer to review the pull request.
- Example notebooks/scripts should ideally store output in a directory named **obi-output** that is at the same level as the obi-one repository i.e. outside the respistory.
- Currently all dependencies are required in pyproject.toml to simplify development. This may lead to a slow initial import of obi. In future we can explore adding optional dependencies, and optional imports of obi functionalities into the obi module depending on what dependencies are installed.
- All issues are tracked on the project board, where tickets can be created and moved appropriately: https://github.com/orgs/openbraininstitute/projects/42/views/1 


 


