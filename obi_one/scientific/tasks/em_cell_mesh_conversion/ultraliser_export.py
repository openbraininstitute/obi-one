"""Child process entry point: reads an OBJ with Ultraliser and writes it as a Draco GLB.

Usage: ``python -m <this module> <obj path> <output directory> <counts json path>``.

Ultraliser ends the whole process with exit code 0 on some errors (``LOG_ERROR`` calls
``exit(EXIT_SUCCESS)``), so the parent judges the result by the files written here, never
by the exit code alone.
"""

import json
import sys
from pathlib import Path


def main(obj_path: str, output_dir: str, counts_path: str) -> None:
    import ultraliser  # ruff: ignore[import-outside-top-level]

    mesh = ultraliser.Mesh(file_name=obj_path, verbose=False)  # ty:ignore[unresolved-attribute]
    Path(counts_path).write_text(
        json.dumps(
            {
                "vertices": mesh.get_number_vertices(),
                "triangles": mesh.get_number_triangles(),
            }
        ),
        encoding="utf-8",
    )

    formats = ultraliser.MeshFormats()  # ty:ignore[unresolved-attribute]
    formats.glb = True
    mesh.export_mesh(prefix=str(Path(output_dir) / "mesh"), export_formats=formats, verbose=False)


if __name__ == "__main__":
    main(*sys.argv[1:])
