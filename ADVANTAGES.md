# 5. Advantages

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




- We all become experts on and work on a single SDK.
- Gives users a feeling that there is a single learnable codebase that will offer mastery
- A community can be built around this single SDK. Similar to Spikeinterface.
- Impress big Neuroscience players