# OBI-SDK + Repo + Platform Integration - Scientific Proposal
Here we define an initial **proposal** for a general organization of code, data and the Platform, which can:
- **Maximise the scientific utility of the Platform**
- **Accelerate the field of Simulations Neuroscience**

Everything related to design and engineering is simply a rough non-expert outline. The aim is to provide a basis for discussions, iteration and potential prototyping. The general idea is to have a single SDK for performing BBP modeling with AWS, SQL persistance and version control of user code, which can be used through code, the platform or by LLMs. Moreover, the goal is to create a clear correspondence between artifacts, user code and Platform functionality.

# Goals

Scientifically, we hope to find a solution which:
- **Decouples contents (managed by scientists) and the engineering side to confer high scientific flexibility.**
- **Builds upon the hierarchical compartmentalization of Modelling into Stages** (i.e. neuron placement, connectivity, ..., network activity) and **Steps** (i.e. building, optimization, validation, predictions) to:
    - Confer a structure which **inherently educates the user in the Stages and Steps of Simulations Neuroscience**, and is inherently **designed for distributed peer review** of these types of models.
    - **Create projects/models which correspond with a single GitHub repository defining models as compositions of different Stages and Steps.** 
    - **Allows descriptions, code, tests, article text, notebooks, artifacts for single Stages and Steps to be collated in this hierarchical structure using version controlled code/AWS persistance, which can be navigated and viewed in the platform.** 
    - **All artifacts correspond directly with version controlled code.**
    - **Projects can be built directly from the Platform or as code in a repository, but always have a correspondence in both to leverage the advantages of both.** 
    - **Optimizes communication/description of complex multifaceted models: users can work on descriptions in this hierarchy/GitHub repo which are automatically rendered in the platform**.
    - **Allows reuse of code and UI elements for different Steps of the same Stage.**
    - **Create a GitHub based framework/standard for collaborative development of brain models and analyses using a combination of cloud compute and (eventual) burst-out to institution supercomputers, with inherited integration into the platform.** The development, improvement and use of our models is extremely expensive (compute and human time) and experimental. Unexpected issues (both engineering and scientific) are very common; code is often rerun many times to attain relevant results. Many labs have access to compute and currently don't have funds for cloud compute. The peer review process is also highly demanding, new work should greatly advance the state of the art. Currently, the complexity of our models demands a much wider community of neuroscientists to engage in a more structured model development process. A compartmental GitHub-based structuring with SQL/AWS persistence would allow simple management of model development and validation, with clear Stages and Steps, some of which could be assigned for AWS cloud or burst-out compute across the world. Standardization would allow other groups to enter their models into the platform, with descriptions automatically being rendered in the platform.

- **Standardizes persistence, organization of descriptions and the execution of any modeling functionality (in to such a compartmental structure for example) can enable:**
    - **Automated testing of scientific code.**
    - **Easy use of wide functionality for users.**
    - **Eventual generality for any neuroscience use case.**
    - **Encourages/enables code generality/reusability through clear location and hierarchical organization for general code.**
    - **Standardize the organization of code, data and descriptions for use by LLMs.**
    - **Code and files for launching on AWS stored together** meaning anyone browsing the code can easily launch it on AWS and start spending $.

- Creates a **single community driven SDK** such as "spikeinterface", "DeepLabCut", "CEBRA" to confer the following benefits: 
    - A single easy to use and learnable codebase that will offer mastery - important to convincing users to invest time, 
    - All OBI engineers and scientists collaborate and become experts in a single high quality code base, 
    - **A clear and standardized path for users to convert their existing code to a general piece of code that others can re-use in different contexts.**
    - A community can be built around this single SDK, 
    - A single easy to use codebase that can gain an identity to impress neuroscientists and large neuroscience institutes.

- **Enables reproducibility, extensibility and impact through repository code and cloud deployment.**
- Allows us to **collate and organize the code and dependencies which will underly the platform.**
- **Eliminates repetition of writing between communication of model in platform and paper writing.**



---

# Proposal
The SDK is organized into two main parts:

- [1. Modeling Library (click)](./MODELING_LIBRARY.md)
- [2. Core Operations (click)](./CORE_OPERATIONS.md)

User projects can then be created through code (forking an existing example) or through the platform.

- [3. Example User Project - CODE (click)](./EXAMPLE_USER_PROJECT.md)
- [4. Example User Project - PLATFORM (click)](./PLATFORM.md)

<!-- This organization offers the following additional advantages:

- [5. Advantages](./ADVANTAGES.md) -->
