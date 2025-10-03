## Linting
- Linting should be applied prior to making pull requests by running:
`make format` or `make format FILE=obi_one/core/scan.py`. This will make minor automatic changes (removing empty lines etc.) and will list linting errors with suggestions of how they can be fixed. 
- Linting should be used to improve code in the files being worked on or familiar to the developer. To avoid merge conflicts they should be sure that others are not working on the same files. 
- In the future when all linting errors have been resolved, linting will be required by the CI before a PR can be approved.
- Counts of linting errors by file can also be seen by running `make format_count` and counts of the types of errors with `make format_types`.

## Output files
- Example notebooks/scripts should ideally store output in a directory named **obi-output** that is at the same level as the obi-one repository i.e. outside the respistory.

## Dependencies
- Dependencies to a specific version/branch of another repository can be added to pyproject.toml under [tool.uv.sources]
as `repo_name = { git = "https://github.com/repo_name/snap.git", branch = "branch_name" }`.  

## Issues, Project Board, Milestones
- All issues are tracked on the project board, where tickets can be created and moved appropriately: https://github.com/orgs/openbraininstitute/projects/42/views/1 
- Issues may belong to individual product repositories (i.e. single_cell_lab) or the obi-one repository. This allows us to group the issues by product in the project board.
- "Milestones" are also used for grouping to support sprint development. As issues belong to different repositories we created several generically named milestones (i.e. OBI-ONE Milestone A, OBI-ONE Milestone B, ...) in each product repository. This avoids having to create new milestones everytime a new milestone is begun. Instead we can assign a previously finished milestone (i.e. OBI-ONE Milestone C) to issues associated with the new milestone. 
- The goal of each milestone can be viewed by clicking the "Project details" icon in the top right of the project board.


# Logging: 
The package's logging level can be set like this from your script / notebook:
```
L = logging.getLogger(obi.__name__)
L.setLevel(logging.WARNING) 
```

or written to file:
```
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='app.log',  # optional: logs to a file instead of console
    filemode='w'         # optional: overwrite the log file each time
    force=True
)
```