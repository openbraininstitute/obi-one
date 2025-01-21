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