# Trigger launch-system neurodamus executor publish

After a successful obi-one release pin and Docker/PyPI builds, `release-pin.yml` dispatches
**`neurodamus-executor-publish`** to **launch-system** with:

```text
client_payload.tag = <obi-one calver release tag>
```

Launch-system workflow **`publish-neurodamus-runtime.yml`** (see
[launch-system PR #228](https://github.com/openbraininstitute/launch-system/pull/228)) then:

- Uses **`client_payload.tag`** as the obi-one half of the image tag.
- Resolves the launch-system half from **`releases/latest`** on `openbraininstitute/launch-system`.
- Builds and pushes `{launch-system}-{obi-one}` (with `-prod` in production).

Launch-system also publishes the same neurodamus executor on **its own GitHub release** (after
Publish services), pairing the new launch-system tag with the latest obi-one release. The obi-one
dispatch is for rebuilding when **obi-one** releases without a matching launch-system release.

The executor image installs deps from **`neurodamus_image.txt`** / **`.override`** at the obi-one
tag (see [obi-one PR #1120](https://github.com/openbraininstitute/obi-one/pull/1120)).

## GitHub App (obi-one repository)

The **obi repo dispatcher** GitHub App must be **installed on `openbraininstitute/launch-system`**
with permission to run workflows (`Actions: Read and write` is enough for `repository_dispatch`).

Configure in obi-one:

| Setting | Name |
|---------|------|
| Repository variable | `OBI_REPO_DISPATCHER_CLIENT_ID` |
| Repository secret | `OBI_REPO_DISPATCHER_PRIVATE_KEY` |

`release-pin.yml` mints a short-lived installation token via `actions/create-github-app-token` and
calls `repos/openbraininstitute/launch-system/dispatches`. The default obi-one `GITHUB_TOKEN`
cannot dispatch into private launch-system.
