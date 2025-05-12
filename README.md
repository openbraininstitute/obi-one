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

Generate a virtual environment with obi-one installed, and register it as a Jupyter kernel 
```
make install
```

<br>


# Examples
Example notebooks are available in the [**examples**](examples/) directory

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
make run-local
```

Once launched, the generated endpoints can then be viewed at: http://127.0.0.1:8100/docs


<br>




# Generative GUI:
Once the service has been launched, the generated gui can additionally be launched: https://github.com/openbraininstitute/obi-generative-gui

<br>




# Developer guidelines

## Branches / Pull Requests
- We recommend that any new features are developed on a new branch originating from the **main** branch. 
- The name of the new branch should describe the change being worked on (i.e. **current_stimulus_fix**).
- When multiple developers are working on such a branch it may be preferable to create additioanl branches with a suffix indicating their initials (i.e. **current_stimulus_fix_bfg**).
- Developers should make pull requests into the main branch.

## Linting
- Prior to making pull requests, developers should apply linting (a process that checks that code and code formating are in line with modern standards). To apply linting to the either the whole codebase or specific file run:
`make format` or `make format FILE=obi_one/core/scan.py`. This will make minor automatic changes (removing empty lines etc.) and will list linting errors which suggest where the developer should manually improve the code. 
- For now, developers should use linting to improve the code in the files they are working on / are familiar with, and should be sure that others are not working on the same files to avoid merge conflicts. 
- In the future when we've removed all of the linting errors across the codebase, linting will be required by the CI before a PR can be approved.
- Counts of linting errors by file can also be seen by running `make format_count`.


- Example notebooks/scripts should ideally store output in a directory named **obi-output** that is at the same level as the obi-one repository i.e. outside the respistory.

## Dependencies
- Dependencies to a specific version/branch of another repository can be added to pyproject.toml under [tool.uv.sources]
as `repo_name = { git = "https://github.com/repo_name/snap.git", branch = "branch_name" }`.  

## Issues, Project Board, Milestones
- All issues are tracked on the project board, where tickets can be created and moved appropriately: https://github.com/orgs/openbraininstitute/projects/42/views/1 
- Issues may belong to individual product repositories (i.e. single_cell_lab) or the obi-one repository. This allows us to group the issues by product in the project board.
- "Milestones" are also used for grouping to support sprint development. As issues belong to different repositories we created several generically named milestones (i.e. OBI-ONE Milestone A, OBI-ONE Milestone B, ...) in each product repository. This avoids having to create new milestones everytime a new milestone is begun. Instead we can assign a previously finished milestone (i.e. OBI-ONE Milestone C) to issues associated with the new milestone. 
- The goal of each milestone can be viewed by clicking the "Project details" icon in the top right of the project board.
 
# Acknowledgements
Copyright © 2025 Open Brain Institute

