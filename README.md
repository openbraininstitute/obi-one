# OBI-ONE

OBI-ONE is a standardized library of workflows for biophysically-detailed brain modeling, with the following features:
- Integration with a standardized cloud database for neuroscience and computational neuroscience through [**entitysdk**](github.com/openbraininstitute/entitysdk).
- Standardized provenence of workflows.
- Standardized parameter scans across different modeling workflows.
- Corresponding OpenAPI schema and service generated from Pydantic

<br>

# Installation


Pre-installation
```
brew install uv open-mpi boost cmake
```

Virtual environment (registered as a Jupyter kernel)
```
make install
```

<br>


# Examples
Notebooks are available in [**examples/**](examples/)

<br>


# Technical Overview / Glossary

The package is split into [**core/**](core/) and [**scientific/**](scientific/) code.

[**core/**](core/) defines the follow key classes:

- [**ScanConfig**](obi_one/core/scan_config.py): defines configurations for specific modeling use cases such as a [CircuitSimulationScanConfig](obi_one/scientific/simulation/simulations.py).  A Form is composed of one or multiple Blocks (see next), which define the parameterization of a use case. Currently Forms can have both single Blocks and dictionaries of Blocks. Each Form, for example, has its own Initialize Block for specifying the base parameters of the use case. Dictionaries of Blocks of a particular type are used where the Form can accept an unspecified number of this Block type, such as Stimulus Blocks.
- [**Block**](obi_one/core/block.py): defines a component of a ScanConfig. Blocks are the components which support the specification of parameters which should be scanned over in the multi-dimensional parameter scan. When using the Form (in a Jupter Notebook for example). Any parameter which is specified as a list is used as a dimension of a multi-dimensional parameter scan when passed to a Scan object (see below).
- [**SingleConfig**](obi_one/core/single.py):
- [**Task**](obi_one/core/task.py):
- [**ScanGenerationTask**](obi_one/core/scan_generation_task.py): is an example task which takes a single ScanConfig as input, an output path and a string for specifying how output files should be stored. Then the function scan.execute() function can then be called which generates the multiple dimensional scan


<br>


# FAST API Service

Launch the FAST API Serive, with docs viewable at: http://127.0.0.1:8100/docs
```
make run-local
```

<br>

# Contributions
Please see [**CONTRIBUTIONS.md**](CONTRIBUTIONS.md) for guidelines on how to contribute.
 
# Acknowledgements
Copyright © 2025 Open Brain Institute
