# 3. Example User Project (with GitHub + Paper generation)

- **Example/user projects use a similar structure to the modeling library**, with a seperation into Stages and Steps, and one or multiple pipelines.**

    ![example1](explanatory_images/example1.png)


---

- **Each user project corresponds with a version controlled repository (i.e. GitHub):**

    <img src="explanatory_images/github1.png" alt="github1" width="50%">

---


- **Configuration, latex and resource files are organized with a similar hierarchical structure to that of the modeling library:**

    <img src="explanatory_images/example2.png" alt="example2" width="20%">

    Here **the Step configuration file can point to the SDK function**:
    ```yaml
    function: obi-sdk/modeling/neuron_placement/validate/basic_neuron_placement_validation/validate_neuron_placement.py
    branch: main
    commit: HEAD
    params: 
        output_data: ./neuron_placment/validate/basic_neuron_placement
        proportion_of_cells: 0.2
   ```

---

- **Maintaining DESCRIPTIONS within this hierarchical structure allows users to write the paper in the Platform/GitHub repo as they go.**

    The hierarchy confers a natural and optimal organization of the paper based on our experience of peer review, with corresponding code for each step.

    <img src="explanatory_images/paper1.png" alt="paper1" width="30%">

---

- **Users can also add custom code within the project** and reference these functions rather than those in the SDK:

    <img src="explanatory_images/example3.png" alt="example3" width="30%">

    The configuration file can then reference these custom function rather than functions in the SDK:
    ```yaml
    function: rat_nbs1/modeling/neuron_placement/validate/basic_neuron_placement_validation/perform_neuron_placement_custom.py
    branch: main
    commit: HEAD
    params: 
        output_data: ./neuron_placment/validate/basic_neuron_placement
        proportion_of_cells: 0.2
   ```

---

- **Custom code could also be added in forks of the SDK**, which could be pulled into the main branch later.

---

- **Input and output artifacts for each function all comply with our SQL schema.** It might be beneficial to store the schema in the same repository so that users can add functionality without having to sync two seperate repositories (syncing seperate repos may seem challenging / risky to low/medium skill git users):


---

- **By default, artifacts are stored with meta-data referencing the code, branch, commit, and position in the Stages and Steps hierarchy.**

---
