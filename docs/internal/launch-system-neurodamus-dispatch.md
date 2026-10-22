# Trigger launch-system neurodamus executor publish

After a successful obi-one release pin and build, `release-pin.yml` dispatches
`neurodamus-executor-publish` to **launch-system** with `client_payload.tag` set to the obi-one
calver. Launch-system resolves its own release via `releases/latest` and builds
`{launch-system}-{obi-one}`.

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

