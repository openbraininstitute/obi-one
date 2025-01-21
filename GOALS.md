# Goals

- **General framework for accelerating the field and forming the basis of the platform.** As the Platform is essentially a code generator, executer and data manager, its utility depends on the structure and strength of the underlying framework, which must support:
    - Iterative refinement
    - Flexibility
    - Description and communication of data/methods
    - Collaboration



- **Compartmentalization of Modelling into compositional Stages and Steps with standardized interface.** All models are built, validated and used for making predictions in a sequential or parralel series of clearly defined **Modelling Stages** (i.e. neuron morphology generation, neuron placement, connectivity, ..., network activity, ... etc. At each Stage, there can be a combination of the following **Modelling Steps**: building, optimization of parameters, validation/discrepencies with real data, predictions, use cases. Making this clear demarcation of Stages and Steps and standardizing the interface for executing different components is essential to:
    1) The composition of different Stages and Steps for new Projects/Models.
    2) Clear correspondence between code and UI elements.
    3) Naturally communicating/teaching the generic Stages and Steps in Simulations Neuroscience.
    4) Having a clear correspondence between code and GUI functionality.
    5) Reusing code and UI elements for different Steps of the same Stage (for example, validation and predictions from connectivity).
    6) Enables clear seperation of work for **collaborators** and **peer reviewers**.
 
- **Standardization and iteration of the communication of complex multifaceted models (including details, rationale, validations and use cases). Information in this standard format can be rendered in the platform, with the structure of the standard naturally teaching the user about existing models/data and the key parts of Simulations Neuroscience.** Communication is essential to convincing and eductating potential paying users, peer reviewers and the rest of the scientific community about our models and their value. Currently large collections of interelated scientific papers jointly describe details, rationale, validations and use cases, demanding huge time investment to learn at a high level. Standardization of how models and components are communicated is also essential for avoiding re-use in the platform. Moreover, such descriptions take months or years to achieve (historically for papers) through iterative refinement. Moreover, when models build/iterate upon previous models, descriptions should be inherited and adjusted.


- **Version control of user code which has clear correspondence with persistence of generated artifacts.** Customers paying large sums of money want to access to the exact code they are running because 1) most journals now demand the publication of source code, 2) to understand what it is exactly they might pay for and/or have paid for. Version control of code/generated code is also essential for users.














- **Users can contribute code to a project or general code library**

