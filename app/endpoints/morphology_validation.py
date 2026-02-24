from http import HTTPStatus
from pathlib import Path
from typing import Annotated

import morphio
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from neurom.exceptions import NeuroMError
from neurom import load_morphology

from app.dependencies.auth import user_verified
from app.dependencies.file import TempDirDep
from app.errors import ApiErrorCode
from app.services import file as file_service, morphology as morphology_service
from app.services.morphology import ALLOWED_EXTENSIONS, DEFAULT_SINGLE_POINT_SOMA_BY_EXT

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


def _validate_morphology_content(file_path: Path) -> None:
    """
    Attempts to load the morphology using NeuroM/MorphIO and captures
    specific parsing or structural errors to return to the user.
    """
    morphio.set_raise_warnings(True)
    
    try:
        load_morphology(file_path)
        
        if not morphology_service.validate_soma_diameter(file_path=file_path):
            raise ValueError("Unrealistic soma diameter detected.")
            
    except (morphio.MorphioError, NeuroMError, ValueError) as e:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Morphology validation failed: {str(e)}",
            },
        )
    finally:
        # Reset to avoid affecting other parts of the application
        morphio.set_raise_warnings(False)


@router.post(
    "/test-neuron-file",
    summary="Validate a morphology and return the conversion to other formats.",
    description=(
        "Validate a morphology in a supported format (.swc, .h5, or .asc), "
        "and return a zip file containing the morphology converted to the other formats."
    ),
)
def validate_neuron_file(
    file: Annotated[UploadFile, File(description="Neuron file to upload (.swc, .h5, or .asc)")],
    temp_dir: TempDirDep,
    *,
    single_point_soma: Annotated[bool, Query(description="Convert soma to single point")] = False,
) -> FileResponse:
    # 1. Save the uploaded file to a temporary location
    input_morphology = file_service.save_upload_file(
        upload_file=file,
        output_dir=temp_dir,
        output_stem="input",
        allowed_extensions=ALLOWED_EXTENSIONS,
        force_lower_case=True,
    )

    # 2. Validate the file content (NeuroM loading + Soma diameter)
    _validate_morphology_content(input_morphology)

    # 3. Handle conversion logic
    if single_point_soma:
        single_point_soma_by_ext = dict.fromkeys(DEFAULT_SINGLE_POINT_SOMA_BY_EXT, True)
    else:
        single_point_soma_by_ext = DEFAULT_SINGLE_POINT_SOMA_BY_EXT

    morphology = morphology_service.convert_morphology(
        input_file=input_morphology,
        output_dir=input_morphology.parent,
        single_point_soma_by_ext=single_point_soma_by_ext,
    )

    # 4. Create and return the zip archive
    zip_file = temp_dir / "morph_archive.zip"
    file_service.create_zip_file(input_files=morphology, output_file=zip_file, delete_input=True)

    return FileResponse(
        path=zip_file,
        filename=zip_file.name,
        media_type="application/zip",
    )