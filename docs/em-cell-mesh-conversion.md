---
tags:
  - contribute-and-fix-data
---

# EM Cell Mesh Conversion

`POST /declared/em-cell-mesh/{entity_id}/convert` launches a job that converts the OBJ surface
mesh of a draft `EMCellMesh` to a Draco-compressed GLB with pylmesh, at full resolution. The
conversion is free. The generic `POST /declared/task/launch` refuses this task type with a 400.

## Lifecycle

The mesh stays `draft` while it is converted, and ends in one of two states:

| Result | Assets | `lifecycle_status` |
| --- | --- | --- |
| Converted | the GLB only; the OBJ is deleted | `active` |
| Failed | none; the OBJ is deleted | `disqualified` |

There is no retry. A job that is killed or times out is settled by the failure callback, which
finds the mesh through the activity's `used` entities. A mesh that is not `draft` is never
changed, by the job or by the failure callback.

If the launch fails before the job reaches the launch system, the endpoint settles the mesh
itself and returns a 500. If the job may have been submitted (the launch system did not answer,
for example), the endpoint returns a 500 but leaves the mesh to the job and the failure callback.

## Requests that are refused

The endpoint returns a 409 when the mesh:

- is not `draft`,
- already has a GLB surface mesh,
- does not have exactly one fully uploaded OBJ surface mesh, or
- has a conversion that is created, pending or running.

Two calls at the same time can still both launch a job.

## OBJ requirements

pylmesh does not check its input, so the job scans the OBJ first and disqualifies the mesh when:

- a face does not have exactly three vertices (polygons are not triangulated),
- a face index is zero, negative or past the last vertex,
- a vertex does not have three finite coordinates, or
- pylmesh reads a different number of vertices or faces than the scan.

## Resources

4 vCPU, 30 GB of memory, 30 GB of disk and 45 minutes, sized for a 6 GB OBJ (about 140M
triangles). pylmesh is single-threaded.
