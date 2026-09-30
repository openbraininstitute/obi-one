# Launch-script Dependencies

The scripts under [**launch_scripts/**](https://github.com/openbraininstitute/obi-one/tree/main/launch_scripts) run as tasks in the [launch-system](https://github.com/openbraininstitute/launch-system).
Each task installs a requirements file from `launch_scripts/<task>/dependencies/`.
The tools that manage these files are in `launch_scripts/tools/`.

Each requirements file has two versions:

- **`*.in`**: the source of truth. Edit this to add or change dependencies.
- **`*.txt`**: generated from the `*.in` and fully pinned. Do not edit by hand. The launch-system installs from it at task run time.

## TL;DR for task developers

- **Change a task's dependencies:** edit its `*.in` (never the `*.txt`), run `make compile-launch-deps FILE=<path to the .in>`, and commit both files.
- **Add a task:** create `launch_scripts/<task>/dependencies/<name>.in` with a bare `obi-one[<extras>]` line (no version) plus any extra packages, compile it as above, and commit both files. Tasks run by `launch_scripts/launch_task_for_single_config_asset/main.py` use `_obi_one_code("<name>.txt")` in `app/mappings.py`.
- **Change obi-one's own dependencies** (`pyproject.toml`): also run `make compile-launch-deps`, or `check-launch-deps` fails in CI.
- **Private packages** (CodeArtifact, e.g. `ultraliser`): add them to `PRIVATE_PACKAGES` in `launch_scripts/tools/launch_deps_compile.py` and set the CodeArtifact credentials before compiling (see [Compiling](#compiling)).
- **Don't touch the obi-one pin** (`obi-one[...]==X` in the `*.txt`): the release workflow updates it, and compiling keeps it.
- **Test a task against your branch's obi-one code:** see [Testing a task against an obi-one feature branch](#testing-a-task-against-an-obi-one-feature-branch), and revert the `*.txt` edit before merging.

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

`obi-one` itself is resolved from the local checkout, so its closure matches the current source, but it is not pinned by the resolver. Its line is written with the release pin found in the committed `*.txt` files (`obi-one[extras]==X` after release `X`, bare before the first release), and compiling keeps that pin. Only the release workflow changes it (see below). The obi-one lines of the `*.in` files must stay bare.

Some tasks depend on private packages from AWS CodeArtifact (currently `ultraliser`, used by `skeletonization` and `mesh_lod_generation`). The CodeArtifact index is used only for files that require a package listed in `PRIVATE_PACKAGES` (`launch_deps_compile.py`), directly or in their compiled `.txt`: it proxies PyPI but sends no caching headers, so using it everywhere makes every run slow. Add new private packages to that list. Compiling or checking these files needs `UV_INDEX_OBI_CODEARTIFACT_USERNAME=aws` and `UV_INDEX_OBI_CODEARTIFACT_PASSWORD` set to a CodeArtifact token (`aws codeartifact get-authorization-token --domain openbraininstitute --query authorizationToken --output text`).

## Checking

```bash
make check-launch-deps
```

CI runs the same check (`.github/workflows/check-launch-deps.yml`). Like `make check-deps`, it fails only when a committed `*.txt` is **inconsistent** with its `*.in` (or obi-one's requirements), not merely because newer upstream versions exist. If it reports stale files, run `make compile-launch-deps` and commit the result.

It resolves every task, including the private ones. Without CodeArtifact access, pass `FILE=<path>` to check only public tasks, or run `uv run python launch_scripts/tools/launch_deps_compile.py --check --skip-unresolvable` to skip, with a warning, any task that cannot be resolved.

## Releases

Launch jobs check out the release tag `X`, whose requirements pin obi-one to that release:

1. A maintainer creates release `X` from the GitHub UI as usual (calver `YYYY.M.N`, e.g. `2026.9.15`), targeting `main` HEAD. This creates tag `X` at `main` HEAD, and nothing is built yet.
2. The release triggers `.github/workflows/release-pin.yml`, which re-dispatches itself on `main`: the job that uses the release App key must run workflow code from `main`, not from the tagged commit.
3. The dispatched run first runs `check-launch-deps` on tag `X`, since the release fixes that commit's closure. It then checks that tag `X` is `main` HEAD, runs `launch_deps_pin.py --version X` to rewrite every obi-one line of `launch_scripts/*/dependencies/*.txt` to `obi-one[extras]==X`, and verifies that nothing else changed. It commits the result on `main` and moves tag `X` to that commit, in one atomic push with the `obi-one-release` GitHub App token (a bypass actor of the `main` ruleset).
4. It then dispatches the Docker (`publish.yml`) and PyPI (`publish-pypi.yml`) builds on tag `X` and waits for them. Both run only on a release tag whose obi-one lines are pinned to it (`launch_deps_pin.py --check`).
5. The service running version `X` submits jobs with `ref=tag:X` (`release_tag_ref` in `obi_one/utils/versions.py`), so the executor installs the obi-one `X` wheel together with the closure frozen at `X`. A dev build (e.g. `2026.9.15-3-g49a1641-dirty`) uses the tag of its last release.

Pinning only the obi-one line is consistent because `check-launch-deps` keeps `main`'s closure in sync with obi-one's requirements, so the closure committed at `X` was compiled against `X`'s source. Between releases, `main` keeps the pin of the last release.

Nothing should be merged to `main` while a release is running: the workflow fails if tag `X` is no longer `main` HEAD.

The workflow needs the `release` environment (deployment restricted to `main`), with the variable `RELEASE_APP_CLIENT_ID` and the secret `RELEASE_APP_PRIVATE_KEY` of the `obi-one-release` GitHub App. Don't allow tags in that environment: a tag-triggered run uses the workflow files of the tagged commit.

To try the pin locally, then revert it (this discards any local change to those files):

```bash
make pin-launch-deps VERSION=2026.9.15
git restore 'launch_scripts/*/dependencies/*.txt'
```

If `release-pin.yml` fails, the release is published but nothing is built, and tag `X` may still point at the unpinned commit. Fix the cause and re-run the failed run, or run the workflow on `main` from the Actions tab with the release tag as input: if the tag is already pinned, it only dispatches the builds. If only a build failed, re-run that build. If `check-launch-deps` fails on tag `X`, delete release `X` and its tag, fix `main` and release again.

## Testing a task against an obi-one feature branch

The launch-system executor clones obi-one from GitHub at the submitted `ref`, not from your local working copy, so any change it should use must be committed and pushed.
Without further changes, a job on a branch commit installs the branch's task script and requirements but the obi-one wheel of the last release, since branches keep `main`'s pin.

To also use the branch's obi-one library code:

1. On your feature branch, edit the task's `*.txt` obi-one line to a git reference, e.g. `obi-one[connectivity] @ git+https://github.com/openbraininstitute/obi-one.git@<branch-or-sha>`.
2. Commit and push, then submit the job with `ref=commit:<40-hex sha>` of that commit.
3. **Revert the `*.txt` edit before merging.** `make check-launch-deps` and CI flag it as stale, and the release workflow would fail, since `launch_deps_pin.py` refuses to pin an obi-one line that is neither bare nor pinned to a release.
