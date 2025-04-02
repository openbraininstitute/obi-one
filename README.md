# Installation

```
cd obi-one
uv venv
source .venv/bin/activate
uv sync
uv pip install -e .
python -m ipykernel install --user --name=.venv --display-name "Python (.venv)"
```

# Developer guidelines

- We recommend that any new features are developed on a new branch originating from the **dev** branch. 
- The name of the new branch should describe the change being worked on (i.e. **current_stimulus_fix**). 
- When multiple developers are working on such a branch it may be preferable to create additioanl branches with a suffix indicating their initials (i.e. **current_stimulus_fix_bfg**).
- Developers should make pull requests into the dev branch. The pull request can be merged by the developer who created it if the changes are small and unlikely to affect other parts of the codebase. Otherwise, if the changes might affect other parts of the codebase or the developer would like a second opinion, the developer can request for another developer to review the pull request.
- Example notebooks/scripts should ideally store output in a directory named **obi-output** that is at the same level as the obi-one repository i.e. outside the respistory.
- All issues are tracked on the project board, where tickets can be created and moved appropriately: https://github.com/orgs/openbraininstitute/projects/42/views/1 

# Examples
- Example notebooks are available in the examples/ directory 


# Launching the FAST API Service
To launch the FAST API service simply call:
```
uvicorn examples.launch_service_example:app --reload
```

Once launched, the generated endpoints can then be viewed at: http://127.0.0.1:8000/docs


# Generative GUI:
Once the service has been launched, the generated gui can additionally be launched: https://github.com/openbraininstitute/obi-generative-gui