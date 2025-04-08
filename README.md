# Overview

obi-one is a standardized library of functions + workflows for biophysically-detailed brain modeling. The current scope is to:
- Standardize the creation of multi-dimensional parameter scans across different modeling workflows to maximise code reuse for technical aspects such as endpoint generation, reproducibility, and data persistance.
- Seperate scientific modeling functionality from service and database technicalities, to enable fast addition of functionality by scientists.
- Automatically generate FastAPI endpoints which allow for 1) automatic generation of GUIs, 2) integration with LLM agents.
- Standardize serialization of multi-dimensional parameter scans to support reproducibility.
- Standardize database persistance.
- Support scientific workflows composing multiple scientific modeling steps.
- Standardize the production of figures for manuscripts and frontend display.

<br>

# Installation


Install [**uv**](https://docs.astral.sh/uv/getting-started/installation/#standalone-installer), [**open-mpi**](https://www.open-mpi.org/), [**boost**](https://www.boost.org/), [**cmake**](https://cmake.org/), for example:
```
brew install uv open-mpi boost cmake
```

```
cd obi-one
CMAKE_POLICY_VERSION_MINIMUM=3.5 uv sync
. .venv/bin/activate
python -m ipykernel install --user --name=.venv --display-name "obi-one"
```

<br>


# Examples
Example notebooks are available in the examples/ directory

<br>


# Technical Overview / Glossary

[Writing in progress]

Specific modeling use cases are built upon several key classes, which each inherit from [OBIBaseModel](obi/modeling/core/base.py). OBIBaseModel extends Pydantic's BaseModel (which supports type checking, json serialization and standardized generation of endpoints) to additionally add the type of objects when they are serialized to json. This allows objects referenced in a parent object to be correctly deserialized.

obi-one has the following base classes, which inherit from OBIBaseModel and from which specific functionalities/components inherit:

- [**Form**](obi/modeling/core/form.py): defines a single modeling use case such as a [SimulationsForm](obi/modeling/simulation/simulations.py) for designing a simulation campaign or [CircuitExtractions](obi/modeling/circuit_extraction/circuit_extraction.py) for specifying a set of circuit extractions. A Form is composed of one or multiple Blocks (see next), which define the parameterization of a use case. Currently Forms can have both single Blocks and dictionaries of Blocks. (Todo: explain need for both). Each Form, for example, has its own Initialize Block for specifying the base parameters of the use case.

- [**Block**](obi/modeling/core/block.py): defines a component of a Form. Blocks are the components which support the specification of parameters which should be scanned over in the multi-dimensional parameter scan. (Todo: explain list notation etc.)

- [**Scan**](obi/modeling/core/scan.py): takes a single Form as input, an output path and a string for specifying how output files should be stored. Either generate() or run() funcions can then be called on the scan object which then generate the parameter scan (Todo: explain further).

- [**SingleCoordinateMixin**](obi/modeling/core/single.py): (Todo: explain further)


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
- Dependencies to a specific version/branch of another repository can be added to pyproject.toml as `"repo-name @ git+https://github.com/repo-name.git@branch-name"`.
- All issues are tracked on the project board, where tickets can be created and moved appropriately: https://github.com/orgs/openbraininstitute/projects/42/views/1 
- Issues may belong to individual product repositories (i.e. single_cell_lab) or the obi-one repository. This allows us to group the issues by product in the project board.
- "Milestones" are also used for grouping to support sprint development. As issues belong to different repositories we created several generically named milestones (i.e. OBI-ONE Milestone A, OBI-ONE Milestone B, ...) in each product repository. This avoids having to create new milestones everytime a new milestone is begun. Instead we can assign a previously finished milestone (i.e. OBI-ONE Milestone C) to issues associated with the new milestone. 
- The goal of each milestone can be viewed by clicking the "Project details" icon in the top right of the project board.
 
# Acknowledgements
Copyright © 2025 Open Brain Institute

