# Scientific Proposal For General OBI Code Organization - Goals & Proposal
- Here we define an initial **proposal** for a general organization of code and data, which can:
    - **Maximise the scientific utility of the Platform**
    - **Accelerate the field of Simulations Neuroscience**
- The aim is to provide a basis for discussions, iteration and the potential prototyping of a general data and code organization.
- The general idea is to have a single SDK for using BBP libraries with AWS, SQL persistance and version control of user code. The SDK can be used both directly by users and by the platform.

## OBI-SDK
OBI-SDK organized by:
- A **library of modeling code organized hierarchically by modeling stage (i.e. neuron placement, network activity etc), and modeling steps (i.e. perform, validate, predict)**. Each modeling step can have **multiple substeps or alternative approaches** each defined by a single function in its own subdirectory, and each with a corresponding schema for parameterization:

    ![modeling](explanatory_images/new/modeling.png)


- **Standardization allows any step to be launched in the same way**: passing a **parameters** configuration file and a **resources** configuration file to a python script which then makes a call to the rest API, for example:
   ```bash
    run_aws.py \
    modeling/neuron_placement/validate/basic_neuron_placement_validation/functionality/validate_neuron_placement_example.yaml \
    modeling/neuron_placement/validate/basic_neuron_placement_validation/resources/aws_example.yaml
   ```
   where the **parameters** configuration file specifies the **parameters, git branch/commit** and exact **function** to be run:
   ```yaml
   function: ./validate_neuron_placement.py
   branch: main
   commit: HEAD
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

    Calling **run_aws** might **commit and push** existing code (if required) and **call the rest API** (PUSH, passing the two configuration files). The **service** then **launches the function** using the correct **commit for each step** and the **specified / appropriate resource.**


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


- **For a Step: configuration, latex and resource files are organized with a similar hierarchical structure to that of the modeling library:**

    ![example2](explanatory_images/new/example2.png)

    Here **the Step configuration file can point to the SDK function**:
    ```yaml
    function: obi-sdk/modeling/neuron_placement/validate/basic_neuron_placement_validation/validate_neuron_placement.py
    branch: main
    commit: HEAD
    params: 
        output_data: ./neuron_placment/validate/basic_neuron_placement
        proportion_of_cells: 0.2
   ```

- **Users can also add custom code within the project and reference these functions rather than those in the SDK:**

    ![example3](explanatory_images/new/example3.png)

    The configuration file can then reference these custom function rather than functions in the SDK:
    ```yaml
    function: rat_nbs1/modeling/neuron_placement/validate/basic_neuron_placement_validation/perform_neuron_placement_custom.py
    branch: main
    commit: HEAD
    params: 
        output_data: ./neuron_placment/validate/basic_neuron_placement
        proportion_of_cells: 0.2
   ```

- **Custom code could also be added in forks of the SDK, which could be pulled into the main branch later.**

- **As has been seen, tests and descriptions (rationale/descriptions/results) for different Steps can also be organized in the same hierarchical structure (both in the SDK and project).** Maintaining descriptions within this structure allows users to write the paper as they go. Keeping a clear seperation of different modeling Stages and Steps would create a paper optimally organized based on our experience of peer review, with corresponding code for each step.

- **Input and output artifacts for each function all comply with our SQL schema.** It might be beneficial to store the schema in the same repository so that users can add functionality without having to sync two seperate repositories (syncing seperate repos may seem challenging / risky to low/medium skill git users):

- **By default, artifacts are stored with meta-data referencing the code, branch, commit, and position in the Stages and Steps hierarchy.**

- **Template Jupyter Notebooks could be stored in the same hierchical structure of Stages and Steps, and maintained as part of the SDK.**

- **Notebooks could also be generated automatically for library or user functions.**


## Platform

Any **project** created through the platform has a direct correspondence with the proposed **GitHub** project structure, and vice versa. 

Under this organization, the Platform can offer:

- **An entry point for new users to generate projects and parameterize configuration files.** Through the GUI they can create projects and gradually build up pipelines of functions. The GUI offers both 1) simple form based parameterization of configuration files based on the schema of any OBI-SDK library function and 2) more advanced custom GUI elements for parameterizing configuration files (i.e. existing single cell).

- **Clear, general and hierarchical organization and navigation of complex multifaceted models. The hierachical organization of the underlying GitHub repository corresponds with easy navigation through the platform to code, rationale, description of methods and results for all validations, predictions and building steps.** This has huge benefits for the communication of models; both for potential users and peer reviewers. Currently both groups have to dive into many recent and historic publications, to understand the building steps, rational, validations and predictions made with our models.


- **Management/visualisation of data entities**

- **Clear correspondence between code and GUI elements.**

- **Automatic generation of project GitHub repository.**



## Advantages

Such an organization has a number of additional advantages:

- **Generality to decouple the contents that scientists can manage and the technical side managed by the engineering team.** Such a framework can rapidly allow us to collate existing code into usable features.

- **High scientific flexibility.**

- **Reproducibility and impact enabled by cloud deployment.** Being able to publish a paper with code that anyone can easily run and recreate on the cloud would be very attractive to scientists; particularly because citations often come from the ability to extend/re-use work.

- **Standardize the organization of code, data and descriptions for use by LLMs.** The standardization of modelling Stages and Steps, with corresponding code and descriptions is well suited for LLMs.

- **In developing a framework, collate and organize the code and dependencies which will form the basis of a platform. This code can be run by users to generate income before even being accessible in the platform.**

- **A framework for collaboration combining cloud compute and (eventual) burst-out to institution supercomputers.** The development, improvement and use of our models is extremely expensive in terms of compute and human time. Moreover, it remains a highly experimental process: unexpected issues (both engineering and scientific) are very common, meaning that code (including building, optimization, simulation and analysis) must often be rerun many times to attain a relevant result. Many labs and experts around the world have access to compute and may not currently have funds for cloud compute. The peer review process is also highly demanding, with reviewers expecting models to hugely advance the state of the art. For now, the complexity of our models demands a much wider community of neuroscientists to engage in the development and advancent of models, and the development process to be more structured. A compartmental GitHub-based structuring with SQL/AWS persistence would allow simple management of model development and validation, with clear Stages and Steps, some of which could be assigned for burst-out compute across the world.

- **A general GitHub based standard for cloud deployment (and busrt-out to university supercomputers in future) of brain models and analyses, with inherited integration into the platform.** Such a standard could also be used for the models of other groups, with descriptions, rationale etc of different Stages and Steps automatically being rendered in the platform.

- **Simple framework for automated testing of expected behaviour.** As scientists, we can rerun building, optimizations, simulations etc and verify expected behaviour.

- **Potential/eventual generality for any neuroscience use case.** Such an organization of code, compute and persistance would provide a powerful framework for scienctists.

- **Encourages/enables code generality/reusability through clear location and hierarchical organization for general code.** Users should also see a path for converting there existing code to a general piece of code that others can re-use across models and different simulations. 

- **No repetition of writing between platform communication and paper**

- **Code/configuration files for launching on AWS with each piece of code.** Anyone browsing the code can easily launch it on AWS and start spending $.
