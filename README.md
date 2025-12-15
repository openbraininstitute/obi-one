# OBI-ONE

OBI-ONE is a library of standardized workflows for biophysically-detailed brain modeling, with the following features:
- Integration with a standardized cloud database for neuroscience and computational neuroscience through [**entitysdk**](github.com/openbraininstitute/entitysdk).
- Standardized provenence of workflows.
- Standardized parameter scans across different modeling workflows.
- Corresponding OpenAPI schema and service generated from Pydantic.
- Existing workflows are based on the [**SONATA Standard**](https://github.com/AllenInstitute/sonata) and [**SONATA Extension**](https://sonata-extension.readthedocs.io/en/latest/sonata_simulation.html): standards for specifying biophysical multiscale neuronal network models and simulations.

<br>

[**examples**](examples/) (Jupter notebooks)

[**CONTRIBUTIONS.md**](CONTRIBUTIONS.md)



### Pre-installation
```
brew install uv open-mpi boost cmake
```

### Virtual environment (registered as a Jupyter kernel)
```
make install
```

<br>


## Overview

The [**obi_one**](obi_one/core/) package is split into [**core**](obi_one/core/) and [**scientific**](obi_one/scientific/) code.

[**core**](core/) defines the following important base classes:

- [**ScanConfig**](obi_one/core/scan_config.py)s define configurations for parameter scans of different scientific tasks. For example, the [**CircuitSimulationScanConfig**](obi_one/scientific/simulation/simulations.py) allows a user to specify a parameter scan of simulations of biophysically-detailed brain models.

    - [**Block**](obi_one/core/block.py)s are the main components of ScanConfigs. Parameters in Blocks can be specified as single values or multiple values. Specifying multiple values for a parameter indicates that this parameter is a dimension of the parameter scan.

    - Currently ScanConfigs can have both single Blocks and dictionaries of Blocks. Each ScanConfig, for example, has its own Initialize Block for specifying the base parameters of the use case. Dictionaries of Blocks of a particular type are used where the ScanConfig can accept an unspecified number of this Block type, such as Stimulus Blocks.

- [**ScanGenerationTask**](obi_one/core/scan_generation_task.py) takes as input a ScanConfig and generates the coordinates of the parameter scan. OBI-ONE currently supports: 
    - [**GridScanGenerationTask**](obi_one/core/scan_generation_task.py)
    - [**CoupledScanGenerationTask**](obi_one/core/scan_generation_task.py)

- [**SingleConfig**](obi_one/core/single.py)s are created by a ScanGenerationTask for each coordinate in a parameter scan. SingleConfigs (i.e. [**CircuitSimulationSingleConfig**](obi_one/scientific/simulation/simulations.py)) inherit all parameters from a parent ScanConfig (i.e. [**CircuitSimulationScanConfig**](obi_one/scientific/simulation/simulations.py)), but a [**SingleConfigMixin**](obi_one/core/single.py) enforces that only single values are specified for each parameter. After generating the single coordinates, the 

- [**Task**](obi_one/core/task.py)s are where scientific code is defined, and are run for single points in a parameter space. For example, a CircuitSimulationGenerationTask might generate the SONATA simulation files for a single simulation in a parameter scan.

<br>

[**scientific**](obi_one/scientific/) is composed of the following directories:



<br>


# FAST API Service

Launch the FAST API Serive, with docs viewable at: http://127.0.0.1:8100/docs
```
make run-local
```

<br>

# Acknowledgements
Copyright © 2025 Open Brain Institute
