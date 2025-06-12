# Overview

obi-one is a standardized library of functions + workflows for biophysically-detailed brain modeling. The current scope is to:
- Standardize the creation of multi-dimensional parameter scans across different modeling workflows to maximise code reuse for technical aspects such as endpoint generation, reproducibility, and data persistance.
- Seperate scientific modeling functionality from service and database technicalities, to enable fast addition of functionality by scientists.
- Automatically generate FastAPI endpoints which allow for 1) automatic generation of GUIs, 2) integration with LLM agents.
- Allow the same code used in the endpoints to be run in Jupyter Notebooks.
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

Specific modeling use cases are built upon several key classes, which each inherit from [OBIBaseModel](obi_one/core/base.py). OBIBaseModel extends Pydantic's BaseModel (which supports type checking, json serialization and standardized generation of endpoints) to additionally add the type of objects when they are serialized to json. This allows objects referenced in a parent object to be correctly deserialized.

obi-one has the following base classes, which inherit from OBIBaseModel and from which specific functionalities/components inherit:

- [**Form**](obi_one/core/form.py): defines a single modeling use case such as a [SimulationsForm](obi_one/scientific/simulation/simulations.py) for designing a simulation campaign or [CircuitExtractions](obi_one/scientific/circuit_extraction/circuit_extraction.py) for specifying a set of circuit extractions. A Form is composed of one or multiple Blocks (see next), which define the parameterization of a use case. Currently Forms can have both single Blocks and dictionaries of Blocks. Each Form, for example, has its own Initialize Block for specifying the base parameters of the use case. Dictionaries of Blocks of a particular type are used where the Form can accept an unspecified number of this Block type, such as Stimulus Blocks.

- [**Block**](obi_one/core/block.py): defines a component of a Form. Blocks are the components which support the specification of parameters which should be scanned over in the multi-dimensional parameter scan. When using the Form (in a Jupter Notebook for example). Any parameter which is specified as a list is used as a dimension of a multi-dimensional parameter scan when passed to a Scan object (see below).

- [**Scan**](obi_one/core/scan.py): takes a single Form as input, an output path and a string for specifying how output files should be stored. Then the function Scan.execute(processing_method) function can then be called which generates the multiple dimensional scan and calls processing_method.

- [**SingleCoordinateMixin**](obi_one/core/single.py): (Todo)


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

# Logging: 
The package's logging level can be set like this from your script / notebook:
```
L = logging.getLogger(obi.__name__)
L.setLevel(logging.WARNING) 
```

or written to file:
```
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='app.log',  # optional: logs to a file instead of console
    filemode='w'         # optional: overwrite the log file each time
    force=True
)
```

# Contributions:
The goal of OBI-ONE is to build up a standardized modeling library with the community. Please see [**CONTRIBUTIONS.md**](CONTRIBUTIONS.md) for guidelines on how to contribute.
 
# Acknowledgements
Copyright © 2025 Open Brain Institute

