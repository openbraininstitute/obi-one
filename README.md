# OBI-SDK + Platform Integration - Scientific Proposal
Here we define an initial **proposal** for a general organization of code, data and the Platform, which can:
- **Maximise the scientific utility of the Platform**
- **Accelerate the field of Simulations Neuroscience**

The aim is to provide a basis for discussions, iteration and potential prototyping.

The general idea is to have a single SDK for using BBP libraries with AWS, SQL persistance and version control of user code. The SDK can be used through code, through the platform or by LLMs.

The goal is to create a straightforward correspondence between user code and content in the platform, in order to leverage the advantages of both.

---


The SDK is organized into two main parts:

- [1. Modeling Library](./MODELING_LIBRARY.md)
- [2. Core Operations](./CORE_OPERATIONS.md)

User projects can then be created through code (forking an existing example) or through the platform.

- [3. Example User Project (CODE)](./EXAMPLE_USER_PROJECT.md)
- [4. Example User Project (PLATFORM)](./PLATFORM.md)

This organization offers the following advantages:

- [5. Advantages](./ADVANTAGES.md)
