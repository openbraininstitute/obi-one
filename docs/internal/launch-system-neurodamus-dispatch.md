# Trigger launch-system neurodamus executor publish

After **pin-release** finishes the Docker and PyPI builds on `main` (`workflow_dispatch`), it fire-and-forget starts **`dispatch-neurodamus-executor.yml`** with the release tag. That separate workflow dispatches **`neurodamus-executor-publish`** to **launch-system** with:

```text
client_payload.tag = <obi-one calver release tag>
```

It is not part of the pin job's wait graph, so a failed launch-system trigger or publish does not fail the pin or Docker/PyPI builds. Re-run **Dispatch neurodamus executor publish** manually with the release tag if needed.

Only the real pin on `main` dispatches this (the `pin` job). The thin release→re-dispatch job does not.

This is not wired through `workflow_run`. The main pin is itself started with `GITHUB_TOKEN` from the thin release job, and GitHub suppresses `workflow_run` on completion of bot-dispatched runs.

Launch-system workflow **`publish-neurodamus-runtime.yml`** (see [launch-system PR #228](https://github.com/openbraininstitute/launch-system/pull/228)) then:

- Uses **`client_payload.tag`** as the obi-one half of the image tag.
- Resolves the launch-system half from **`releases/latest`** on `openbraininstitute/launch-system`.
- Builds and pushes `{launch-system}-{obi-one}` (with `-prod` in production).

Launch-system also publishes the same neurodamus executor on **its own GitHub release** (after Publish services), pairing the new launch-system tag with the latest obi-one release. The obi-one dispatch is for rebuilding when **obi-one** releases without a matching launch-system release.

The executor image installs deps from **`neurodamus_image.txt`** / **`.override`** at the obi-one tag (see [obi-one PR #1120](https://github.com/openbraininstitute/obi-one/pull/1120)).

## GitHub App (obi-one repository)

The **obi repo dispatcher** GitHub App must be installed on **`openbraininstitute/obi-one`** (credentials) and **`openbraininstitute/launch-system`** (dispatch target). App permission: **Contents: Read and write** (required for `repository_dispatch`). Credentials live in the obi-one `release` environment:

| Setting | Name |
|---------|------|
| `release` environment variable | `OBI_REPO_DISPATCHER_CLIENT_ID` |
| `release` environment secret | `OBI_REPO_DISPATCHER_PRIVATE_KEY` |

`dispatch-neurodamus-executor.yml` mints a short-lived installation token (scoped to `launch-system`, `permission-contents: write`) via `actions/create-github-app-token` and posts `repos/openbraininstitute/launch-system/dispatches`. The default obi-one `GITHUB_TOKEN` cannot dispatch into private launch-system.
