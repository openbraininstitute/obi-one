# Scientific Proposal For General OBI Code Organization - Goals & Proposal
- Here we define the **goals** and an initial **proposal** for a general organization of code and data, which can:
    - **Maximise the scientific utility of the Platform**
    - **Accelerate the field of Simulations Neuroscience**
- The aim is to provide a basis for discussions, iteration and the potential prototyping of a general data and code organization.


# Goals

- **General framework for accelerating the field and forming the basis of the platform.** As the Platform is essentially a code generator, executer and data manager, its utility depends on the structure and strength of the underlying framework, which must support:
    - Iterative refinement
    - Flexibility
    - Description and communication of data/methods
    - Collaboration

- **Generality to decouple the contents that scientists can manage and the technical side managed by the engineering team.** Such a framework can rapidly allow us to collate existing code into usable features.

- **In developing a framework, collate and organize the code and dependencies which will form the basis of a platform. This code can be run by users to generate income before even being accessible in the platform.**

- **Compartmentalization of Modelling into compositional Stages and Steps with standardized interface.** All models are built, validated and used for making predictions in a sequential or parralel series of clearly defined **Modelling Stages** (i.e. neuron morphology generation, neuron placement, connectivity, ..., network activity, ... etc. At each Stage, there can be a combination of the following **Modelling Steps**: building, optimization of parameters, validation/discrepencies with real data, predictions, use cases. Making this clear demarcation of Stages and Steps and standardizing the interface for executing different components is essential to:
    1) The composition of different Stages and Steps for new Projects/Models.
    2) Clear correspondence between code and UI elements.
    3) Naturally communicating/teaching the generic Stages and Steps in Simulations Neuroscience.
    4) Having a clear correspondence between code and GUI functionality.
    5) Reusing code and UI elements for different Steps of the same Stage (for example, validation and predictions from connectivity).
    6) Enables clear seperation of work for **collaborators** and **peer reviewers**.
 
- **Standardization and iteration of the communication of complex multifaceted models (including details, rationale, validations and use cases). Information in this standard format can be rendered in the platform, with the structure of the standard naturally teaching the user about existing models/data and the key parts of Simulations Neuroscience.** Communication is essential to convincing and eductating potential paying users, peer reviewers and the rest of the scientific community about our models and their value. Currently large collections of interelated scientific papers jointly describe details, rationale, validations and use cases, demanding huge time investment to learn at a high level. Standardization of how models and components are communicated is also essential for avoiding re-use in the platform. Moreover, such descriptions take months or years to achieve (historically for papers) through iterative refinement. Moreover, when models build/iterate upon previous models, descriptions should be inherited and adjusted.

- **No repetition of writing between platform communication and paper**

- **Version control of user code which has clear correspondence with persistence of generated artifacts.** Customers paying large sums of money want to access to the exact code they are running because 1) most journals now demand the publication of source code, 2) to understand what it is exactly they might pay for and/or have paid for. Version control of code/generated code is also essential for users.

- **Standardize the organization of code, data and descriptions for use by LLMs.** The standardization of modelling Stages and Steps, with corresponding code and descriptions is well suited for LLMs.

- **A framework for collaboration combining cloud compute and (eventual) burst-out to institution supercomputers.** The development, improvement and use of our models is extremely expensive in terms of compute and human time. Moreover, it remains a highly experimental process: unexpected issues (both engineering and scientific) are very common, meaning that code (including building, optimization, simulation and analysis) must often be rerun many times to attain a relevant result. Many labs and experts around the world have access to compute and may not currently have funds for cloud compute. The peer review process is also highly demanding, with reviewers expecting models to hugely advance the state of the art. For now, the complexity of our models demands a much wider community of neuroscientists to engage in the development and advancent of models, and the development process to be more structured. A compartmental GitHub-based structuring with SQL/AWS persistence would allow simple management of model development and validation, with clear Stages and Steps, some of which could be assigned for burst-out compute across the world.

- **A general GitHub based standard for cloud deployment (and busrt-out to university supercomputers in future) of brain models and analyses, with inherited integration into the platform.** Such a standard could also be used for the models of other groups, with descriptions, rationale etc of different Stages and Steps automatically being rendered in the platform.

- **Reproducibility and impact enabled by cloud deployment.** Being able to publish a paper with code that anyone can easily run and recreate on the cloud would be very attractive to scientists; particularly because citations often come from the ability to extend/re-use work.

- **Potential/eventual generality for any neuroscience use case.** Such an organization of code, compute and persistance would provide a powerful framework for scienctists.

- **Code/configuration files for launching on AWS with each piece of code.** Anyone browsing the code can easily launch it on AWS and start spending $.

- **Confirmation of expected behaviour.** As scientists, we can rerun building, optimizations, simulations etc and verify expected behaviour.

- **High scientific flexibility.** Science advances through trial and error so the platform should enable fast iteration on analyses etc.

- **Users can contribute code to a project or general code library**

- **Maximize code generality/reusability through clear locations for specific and general code.** Code must be re-usable across models and different simulations. Users should also see a path for converting there existing code to a general piece of code that others can re-use.


# Proposal
Taking into account these considerations, we make the following proposal for discussion and iteration. 

The general idea is to have a single SDK for using BBP libraries with AWS, SQL persistance and version control. The SDK can be used both directly by users and by the platform.

## OBI-SDK
OBI-SDK organized by:
- A **library of modeling code organized by modeling stage (i.e. neuron placement, network activity etc), and modeling steps (i.e. perform, validate, predict)**. Each modeling step can have **multiple substeps or alternative approaches** each defined by a single function in its own subdirectory, and each with a corresponding schema for parameterization:

    ![modeling](explanatory_images/new/modeling.png)


- **Standardization allows any step to be launched in the same way**: passing a **parameters** configuration file and a **resources** configuration file:
   ```bash
    run_aws.py \
    modeling/neuron_placement/validate/basic_neuron_placement_validation/functionality/validate_neuron_placement_example.yaml \
    modeling/neuron_placement/validate/basic_neuron_placement_validation/resources/aws_example.yaml
   ```
   where the **parameters** configuration file specifies the parameters and exact function to be run:
   ```yaml
   function: ./validate_neuron_placement.py
   params: 
    output_data: ./neuron_placment/validate/basic_neuron_placement
    proportion_of_cells: 0.2
   ```
   and the **resources** configuration file specifies the aws resources:
   ```yaml
   nodes: 1
   cores_per_node: 4
   persistance_root: openbluebrain.s3.us-west-2.amazonaws.com.....
   project: sscx_v2
   user: smith
   ```



- **Sequences of stages and steps can then be defined in pipeline configuration files** which point to different stage/step configuration files:
    ```yaml
    project: "SSCx_v2"
    aws_persistance_root: ""

    stages:
        neuron_placement: 
            perform: ...
            validate:
                basic_neuron_placement_validation:
                    root: "./modeling/neuron_placement/validate/basic_neuron_placement_validation/"
                    functionality: functionality/validate_neuron_placement_example.yaml
                    resources: resources/aws_example.yaml
            predict: ...

        connectivity:
            peform: ...
            validate: ...
            predict: ...
   ```

- **Example/user projects use a similar structure to the modeling library, with a seperation into Stages and Steps, and one or multiple pipelines.**

    ![example1](explanatory_images/new/example1.png)


- **Then for a single Step: configuration files, latex files and resource parameterizations keep a single structure to that of the modeling library:**

    ![example2](explanatory_images/new/example2.png)

    Here the Step configuration file could point to the sdk function:
    ```yaml
    function: obi-sdk/modeling/neuron_placement/validate/basic_neuron_placement_validation/validate_neuron_placement.py
    params: 
        output_data: ./neuron_placment/validate/basic_neuron_placement
        proportion_of_cells: 0.2
   ```

- **Users can also add custom code within this structure:**

    ![example3](explanatory_images/new/example3.png)

    And point to these functions rather the SDK in the configuration file:
    ```yaml
    function: rat_nbs1/modeling/neuron_placement/validate/basic_neuron_placement_validation/perform_neuron_placement_custom.py
    params: 
        output_data: ./neuron_placment/validate/basic_neuron_placement
        proportion_of_cells: 0.2
   ```

- **Custom code could also be collated in forks of the SDK, which would allow pull requests to be made into the main branch later.**

- **As has been seen, tests and descriptions (rationale/descriptions/results) for different Steps can also be organized in the same hierarchical structure (both in the SDK and project).**


- **Input and output artifacts for each function all comply with our new SQL schema.** It might be beneficial to store the schema in the same repository so that users can add functionality without having to sync two seperate repositories (syncing seperate repos may seem challenging / risky to low/medium skill git users):

- **Artifacts produced by a project are then stored with the same organization into Stages and Steps.**

- **All persistance and usage of artifacts is standardized**

# Platform

The platform then has a direct correspondence with the version controlled modeling library and each project



<!--
## OBI Interface
- Single Python API for using functionality of all OBI Libraries
- Library of functions which return persistable 
- Jupyter notebooks generated automatically to display
-->

<!--
## OBI Libraries
OBI Libraries are the OBI maintained libraries / packages i.e. Neuron, CoreNeuron, BlueETL, BluepySnap, etc.
-->

 
<!--
## OBI Project Examples
1) [OBI Project Examples](./OBI-Project-Examples) contains a list of configurations files for different OBI Templates
2) Projects have high level json configs defining (serial and parallel) order of Stages (which are in subdirectories)
3) Each Stage has a json config defining (serial and parallel) order of Steps
4) Each Step has a json config defining the parameters of its code
-->

As an example of a project we consider the rat nbS1. We begin by assuming that everything can be d


 
<!--
## OBI Code Templates
1) [OBI Code Templates](./OBI-Code-Templates) are generalizable pieces of code which use code in OBI Libraries (and beyond) for building, optimizing parameters, validating and characterizing discrepencies with laboratory data, making predictions, and running other use cases.

2) Templates read in parameters or contain placeholders (e.g. for notebooks), for input and output data paths and other parameters. These are populated by values from configuration files (json).

3) Templates exist with example configuration files and the necessary AWS scripts for launching them.

4) Templates exist with 

5) Templates are organized by Modelling Stage (i.e. neuron morphology generation, neuron placement, connectivity, ..., network activity, ... etc.) and Modelling Step (i.e. building, optimization of parameters, validation/discrepencies with real data, predictions, use cases), 

6) Templates are compositional...

7) Similar to the concept of bbp-workflow perhaps, except code functions are 
-->



<!--
## OBI User Projects
[OBI User Projects](./OBI-User-Projects)

1) Each User has a set of Projects, with each Project being a seperate GitHub repository.

2) User Projects may be forks of Templates or Examples.

## OBI Platform
[OBI Platform](./OBI-Platform) 

## OBI Database and Persistence
[OBI Database and Persistence](./OBI-Database-and-Persistence) is the Everything is built on top of a database
-->

