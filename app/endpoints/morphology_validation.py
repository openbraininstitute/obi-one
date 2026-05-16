from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.dependencies.auth import user_verified
from app.dependencies.file import TempDirDep
from app.services import file as file_service, morphology as morphology_service
from app.services.morphology import (
    ALLOWED_EXTENSIONS,
    DEFAULT_SINGLE_POINT_SOMA_BY_EXT,
    run_quality_checks,
)

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


@router.post(
    "/test-neuron-file",
    summary="Validate a morphology and return the conversion to other formats.",
    description=(
        "Validate a morphology in a supported format (.swc, .h5, or .asc), "
        "and return a zip file containing the morphology converted to the other formats. "
        "If validation fails, quality check diagnostics are included in the error response."
    ),
)
def validate_neuron_file(
    file: Annotated[UploadFile, File(description="Neuron file to upload (.swc, .h5, or .asc)")],
    temp_dir: TempDirDep,
    *,
    single_point_soma: Annotated[bool, Query(description="Convert soma to single point")] = False,
) -> FileResponse:
    input_morphology = file_service.save_upload_file(
        upload_file=file,
        output_dir=temp_dir,
        output_stem="input",
        allowed_extensions=ALLOWED_EXTENSIONS,
        force_lower_case=True,
    )

    try:
        morphology_service.load_morphio_morphology(input_morphology, raise_warnings=True)

        morphology_service.validate_soma_diameter(file_path=input_morphology)

        if single_point_soma:
            single_point_soma_by_ext = dict.fromkeys(DEFAULT_SINGLE_POINT_SOMA_BY_EXT, True)
        else:
            single_point_soma_by_ext = DEFAULT_SINGLE_POINT_SOMA_BY_EXT

        morphology = morphology_service.convert_morphology(
            input_file=input_morphology,
            output_dir=input_morphology.parent,
            single_point_soma_by_ext=single_point_soma_by_ext,
        )
    except HTTPException as exc:
        qc = run_quality_checks(input_morphology)
        detail: dict[str, Any] = (
            exc.detail if isinstance(exc.detail, dict) else {"detail": exc.detail}
        )
        detail["quality_checks"] = {
            "ran_to_completion": qc["ran_to_completion"],
            "failed_checks": qc["failed_checks"],
            "passed_checks": qc["passed_checks"],
        }
        raise HTTPException(status_code=exc.status_code, detail=detail) from exc

    zip_file = temp_dir / "morph_archive.zip"
    file_service.create_zip_file(
        input_files=morphology.paths(), output_file=zip_file, delete_input=True
    )

    return FileResponse(
        path=zip_file,
        filename=zip_file.name,
        media_type="application/zip",
    )
