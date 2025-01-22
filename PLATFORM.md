# 4. Platform

Any **project** created through the platform has a direct correspondence with the proposed **GitHub** project structure, and vice versa. 

Under this organization, the Platform can offer:

- **An entry point for new users to generate projects, parameterize configuration files, build pipelines.** 

    The GUI offers both:
    - Simple form based parameterization of configuration files based on the schema of any OBI-SDK library function.
    - More advanced custom GUI elements for parameterizing configuration files (i.e. existing single cell).

    ---

- **Automatic generation of project GitHub repository. Clear correspondence between code and GUI elements. Version control of user code which has clear correspondence with persistence of generated artifacts.**

    When a user creates a project, a corresponding GitHub repository should be produced.

    Then when a modeling Stage is added in the platform, a corresponding modeling Stage is added to the hierarchy and pipeline of the GitHub repository.

    This is important because there is a need for any modeling functionality offered by the platform (or in a users project) to have a clear correspondence with code that is viewable to the user, as:
        1. Users want to see and understand what they are paying for
        2. Journals demand code to be submitted with a paper.
        3. Journals demand that code is theoretically reusable on other computers.
        4. In case the user finds an issue, we need to know exactly what code/version were used, and very easily navigate this code.

    Morover, we should leverage both the advantages of code (flexibility, version code, extension etc) and a platform (visualisation, management, simplification/usability).

    ---


- **Clear, general and hierarchical organization and navigation of complex multifaceted models.** 

    The hierachical organization of the modeling library and user projects corresponds with easy navigation in the Platform through:
    - Projects
    - Stages
    - Steps, for which there are corresponding:
        - GUI elements
        - Code
        - Artifacts
        - Description of:
            - Building steps
            - Rationale
            - Validations and discrepencies
            - Predictions

    
    This has huge benefits for the communication of models; both for potential users and peer reviewers. 
    
    Currently both groups have to dive into many recent and historic publications and code bases to understand these aspects.

    <img src="explanatory_images/platform_results.png" alt="platform_results" width="65%">

    
---


- **Management/overview of data entities**

    All entities associated with a project are visible and can be managed or genereated through the platform:

    <img src="explanatory_images/platform_artifacts.png" alt="platform_artifacts" width="65%">


---


- **Advanced visualization of model components and simulations**

    Simulations Neuroscience is partly made difficult by the complexity and sheer volume of model components and simulations.
    
    A big advantage of the platform is its capacity to view different elements in three 3-dimensions.

    Particularly useful will be:
        - Visualizing the internal activity of single neurons during single, pairwise or circuit simulations.
        - Visual validation of circuit/simulation elements arrangement. For example, are axons, thalamic fibres, synapse locations, recording electrodes visually correct.
        - Visualization of network activity


