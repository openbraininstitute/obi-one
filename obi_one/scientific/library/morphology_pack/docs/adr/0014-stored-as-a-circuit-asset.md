# 0014. Stored as the circuit's `circuit_morphology_pack` asset, `.mpack`, `application/octet-stream`

- Status: Accepted
- Date: 2026-10-21, the user's word; the content type changed 2026-10-22

## Context

A pack built while the viewer waits costs a build each first view ([0001](0001-one-pack-built-by-obi-one.md)). Stored once on the circuit, it is fetched as a file. The circuit's assets live in entitycore, whose labels are a closed list: a file's label fixes its content type and, through it, the suffixes it takes. A new label is a migration and a release of its SDK. Assets cannot be replaced under the same id; new content is a new asset.

## Decision

A pack is the circuit's asset of label `circuit_morphology_pack`, a file named `circuit.mpack`, uploaded as `application/octet-stream`. The label is the only marker of a pack: a reader checks the `MPCK` header, not the content type.

The suffix `.mpack` was the user's word on 2026-10-21: `.pack` is Git's packfiles and says nothing of morphologies.

## Alternatives weighed

| Option | What it gave against the chosen | Verdict |
| --- | --- | --- |
| A vendor content type, `application/vnd.obi.morphology-pack`, suffix `.mpack` | A type that names the pack, and a second enum to migrate. Chosen on 2026-10-21 | Replaced 2026-10-22, on entitycore's reviewers' proposal |
| A directory asset with a version in its meta | A directory's label fixes no content type, and its upload can carry a version. The pack is one file, its version in its own header | Planned 2026-10-13, replaced 2026-10-21 |
| A generic label | No new label. No circuit file label takes `application/octet-stream`; only a directory label would have held it | Rejected |

`application/octet-stream` needed one rule in entitycore: a label's suffix is checked only where its content type has suffixes. Before it, a label asking for that type could never take a file.

## Consequences

- Any name passes for the label, so `.mpack` is the uploader's convention. The upload sends the content type explicitly: entitycore guesses a type from the name otherwise, and has no guess for `.mpack`.
- Assets carry `size` and a `sha256_digest`, so a reader can allocate the pack once and check it before keeping it.
- A pack never changes under its asset id. A viewer keeps it a month, keyed by the asset's download URL, and a rebuilt pack is a new asset.
- Only members of a circuit's project may add an asset to it, public or not. That is why a viewer cannot have a public circuit's pack built for it, and why packs are built where the circuit's own assets are ([0015](0015-built-in-the-asset-job.md)).
