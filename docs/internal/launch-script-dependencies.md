# Launch-script Dependencies

The scripts under [**launch_scripts/**](https://github.com/openbraininstitute/obi-one/tree/main/launch_scripts) run as tasks in the [launch-system](https://github.com/openbraininstitute/launch-system).
Each task installs a requirements file from `launch_scripts/<task>/dependencies/`, also when its script lives elsewhere (e.g. the brian2 simulation runs `obi_one/scientific/library/simulation/brian2/simulate_brian2.py` with `launch_scripts/launch_brian2_simulation/dependencies/default.txt`).
The tools that manage these files are in `launch_scripts/tools/`.

Each requirements file has two versions:

- **`*.in`**: the source of truth. Edit this to add or change dependencies.
- **`*.txt`**: generated from the `*.in` and fully pinned. Do not edit by hand. The launch-system installs from it at task run time.

## Compiling

```bash
# Compile all launch-script requirements
make compile-launch-deps

# Compile a single .in file or a directory only
make compile-launch-deps FILE=launch_scripts/launch_task_for_single_config_asset/dependencies/circuit_extraction.in

# Upgrade the whole transitive closure to the latest versions (FILE also accepted)
make upgrade-launch-deps
```

This runs `uv pip compile` for the runtime platform (**linux/amd64, Python 3.12**) and pins the full transitive closure, compiling the files in parallel (`launch_deps_compile.py --jobs N`, default up to 8).
Like `make compile-deps`, `compile-launch-deps` **preserves the versions already pinned**, changing a pin only when the `*.in` (or obi-one's own requirements) forces it; `entitysdk` is the exception and is always upgraded to its latest version.

`obi-one` itself is left **unpinned** in the compiled files on every branch, including `main`: its closure is resolved from the local checkout, and the obi-one line is pinned only in the release's launch tag (see below).

Some tasks depend on private packages from AWS CodeArtifact (currently `ultraliser`, used by `skeletonization` and `mesh_lod_generation`). The CodeArtifact index is used only for files that require a package listed in `PRIVATE_PACKAGES` (`launch_deps_compile.py`), directly or in their compiled `.txt`: it proxies PyPI but sends no caching headers, so using it everywhere makes every run slow. Add new private packages to that list. Compiling or checking these files needs `UV_INDEX_OBI_CODEARTIFACT_USERNAME=aws` and `UV_INDEX_OBI_CODEARTIFACT_PASSWORD` set to a CodeArtifact token (`aws codeartifact get-authorization-token --domain openbraininstitute --query authorizationToken --output text`).

## Checking

```bash
make check-launch-deps
```

CI runs the same check (`.github/workflows/check-launch-deps.yml`). Like `make check-deps`, it fails only when a committed `*.txt` is **inconsistent** with its `*.in` (or obi-one's requirements), not merely because newer upstream versions exist. If it reports stale files, run `make compile-launch-deps` and commit the result.

It resolves every task, including the private ones. Without CodeArtifact access, pass `FILE=<path>` to check only public tasks, or run `uv run python launch_scripts/tools/launch_deps_compile.py --check --skip-unresolvable` to skip, with a warning, any task that cannot be resolved.

## Releases and launch tags

Launch jobs do not check out the release tag `X` itself but its **launch tag** `launch-X`, whose requirements pin obi-one to that release:

1. A maintainer creates release `X` from the GitHub UI as usual (calver `YYYY.M.N`, e.g. `2026.9.15`). This tags `main` and triggers the Docker and PyPI workflows.
2. The same event triggers `.github/workflows/launch-tag.yml`. It checks out `X`, runs `launch_deps_pin.py --version X` to rewrite every bare `obi-one[extras]` line of `launch_scripts/*/dependencies/*.txt` to `obi-one[extras]==X`, verifies that nothing else changed, commits the result as a child of `X`, and pushes only the annotated tag `launch-X`. The commit is on no branch, so `main` stays unpinned and `git describe` is unaffected.
3. The service running version `X` submits jobs with `ref=tag:launch-X` (`launch_ref` in `obi_one/utils/versions.py`), so the executor installs the obi-one `X` wheel together with the closure frozen at `X`. A dev build (e.g. `2026.9.15-3-g49a1641-dirty`) uses the launch tag of its last release.

Pinning only the obi-one line is consistent because `check-launch-deps` keeps `main`'s closure in sync with obi-one's requirements, so the closure committed at `X` was compiled against `X`'s source.

**Launch tags must never be edited, moved or deleted**: every job of that release depends on them. The workflow refuses to overwrite an existing one.

To try the pin locally, then revert it:

```bash
make pin-launch-deps VERSION=2026.9.15
git checkout -- 'launch_scripts/*/dependencies/*.txt'
```

If `launch-tag.yml` fails, the jobs of release `X` fail at checkout until `launch-X` exists; GitHub notifies the author of the release. Fix the cause and re-run the failed job, or run the workflow manually from the Actions tab with the release tag as input.

## Pinning a task to a specific obi-one version

By default each task checks out the launch tag of the running service version.
To keep a task on an older, known-good release, add it to `PINNED_OBI_ONE_VERSIONS` in `app/mappings.py`:

```python
PINNED_OBI_ONE_VERSIONS: dict[TaskType, str] = TypeAdapter(
    dict[TaskType, ReleaseVersion]
).validate_python({
    TaskType.some_task: "2026.9.15",
})
```

The task then checks out `tag:launch-2026.9.15`, so its script, requirements and obi-one wheel all come from that release.
Values must be plain release versions (validated at import), and the release must have a launch tag, i.e. it must have been created after the launch-tag workflow was introduced.
Only tasks running code from the obi-one repository can be pinned.

## Testing a task against an obi-one feature branch

The launch-system executor clones obi-one from GitHub at the submitted `ref`, not from your local working copy, so any change it should use must be committed and pushed.
Without further changes, a job on a branch commit installs the branch's task script and requirements but the latest obi-one release from the package index, since obi-one is unpinned on branches.

To also use the branch's obi-one library code:

1. On your feature branch, edit the task's `*.txt` obi-one line to a git reference, e.g. `obi-one[connectivity] @ git+https://github.com/openbraininstitute/obi-one.git@<branch-or-sha>`.
2. Commit and push, then submit the job with `ref=commit:<40-hex sha>` of that commit.
3. **Revert the `*.txt` edit before merging.** `make check-launch-deps` and CI flag it as stale, and the launch-tag workflow would fail at release time, since `launch_deps_pin.py` refuses to pin a non-bare obi-one line.
