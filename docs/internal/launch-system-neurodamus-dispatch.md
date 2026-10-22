# Trigger launch-system neurodamus executor publish

After a successful obi-one release pin and build, `release-pin.yml` dispatches
`neurodamus-executor-publish` to **launch-system** with `client_payload.tag` set to the obi-one
calver. Launch-system resolves its own release via `releases/latest` and builds
`{launch-system}-{obi-one}`.

## Secret (obi-one repository)

Create **`LAUNCH_SYSTEM_DISPATCH_TOKEN`**: a fine-grained PAT or classic PAT that can
**trigger workflows** on `openbraininstitute/launch-system` (Actions: write; Contents: read
is enough for `repository_dispatch`).

The default `GITHUB_TOKEN` in obi-one **cannot** dispatch into a private launch-system repo.

Until the secret is configured, the release-pin step logs a warning and skips dispatch;
launch-system can still be triggered from its own release or via manual workflow dispatch.
