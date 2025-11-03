import pathlib
import tempfile
from contextlib import suppress
from http import HTTPStatus
from typing import Annotated, Final

import neurom as nm
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

import app.endpoints.useful_functions.useful_functions as uf
from app.dependencies.auth import user_verified


class ApiErrorCode:
    BAD_REQUEST = "BAD_REQUEST"


ALLOWED_EXTENSIONS: Final[set[str]] = {".swc", ".h5", ".asc"}
ALLOWED_EXT_STR: Final[str] = ", ".join(ALLOWED_EXTENSIONS)

DEFAULT_NEURITE_DOMAIN: Final[str] = "basal_dendrite"
TARGET_NEURITE_DOMAINS: Final[list[str]] = ["apical_dendrite", "axon"]

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


def _handle_empty_file(file: UploadFile) -> None:
    raise HTTPException(
        status_code=HTTPStatus.BAD_REQUEST,
        detail={
            "code": ApiErrorCode.BAD_REQUEST,
            "detail": f"Uploaded file '{file.filename}' is empty",
        },
    )


def _validate_file_extension(filename: str | None) -> str:
    if not filename:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.BAD_REQUEST,
                "detail": f"File name is missing. Must be one of {ALLOWED_EXT_STR}",
            },
        )

    file_extension = pathlib.Path(filename).suffix.lower()

    if file_extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.BAD_REQUEST,
                "detail": (
                    f"Invalid file extension '{file_extension}'. Must be one of {ALLOWED_EXT_STR}"
                ),  # E501 fix: Line wrapped
            },
        )
    return file_extension


# the template is included with the code
TEMPLATE = {
    "data": [
        {
            "id": "00a0c678-1bce-40fa-a28a-2bc44ff36f43",
            "creation_date": "2024-07-24T12:43:55.989031Z",
            "update_date": "2024-07-24T12:43:56.054059Z",
            "entity_id": "e892fa95-c724-457a-8dc6-176f5d6cc5d9",
            "entity_type": "reconstruction_morphology",
            "measurement_kinds": [
                {
                    "structural_domain": "axon",
                    "measurement_items": [{"name": "raw", "unit": "μm", "value": 0.0}],
                    "pref_label": "neurite_max_radial_distance",
                },
                {
                    "structural_domain": "axon",
                    "measurement_items": [{"name": "raw", "unit": "dimensionless", "value": 0.0}],
                    "pref_label": "number_of_sections",
                },
                {
                    "structural_domain": "axon",
                    "measurement_items": [{"name": "raw", "unit": "dimensionless", "value": 0.0}],
                    "pref_label": "number_of_bifurcations",
                },
                {
                    "structural_domain": "axon",
                    "measurement_items": [{"name": "raw", "unit": "dimensionless", "value": 0.0}],
                    "pref_label": "number_of_leaves",
                },
                {
                    "structural_domain": "axon",
                    "measurement_items": [{"name": "raw", "unit": "μm", "value": 0.0}],
                    "pref_label": "total_length",
                },
                {
                    "structural_domain": "axon",
                    "measurement_items": [{"name": "raw", "unit": "μm²", "value": 0.0}],
                    "pref_label": "total_area",
                },
                {
                    "structural_domain": "axon",
                    "measurement_items": [{"name": "raw", "unit": "μm³", "value": 0.0}],
                    "pref_label": "total_volume",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "raw", "unit": "μm", "value": 154.49050903320312}
                    ],
                    "pref_label": "neurite_max_radial_distance",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [{"name": "raw", "unit": "dimensionless", "value": 49.0}],
                    "pref_label": "number_of_sections",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [{"name": "raw", "unit": "dimensionless", "value": 24.0}],
                    "pref_label": "number_of_bifurcations",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [{"name": "raw", "unit": "dimensionless", "value": 25.0}],
                    "pref_label": "number_of_leaves",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "raw", "unit": "μm", "value": 574.7376134395599}
                    ],
                    "pref_label": "total_length",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "raw", "unit": "μm²", "value": 2083.9089844782807}
                    ],
                    "pref_label": "total_area",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "raw", "unit": "μm³", "value": 786.4245895828037}
                    ],
                    "pref_label": "total_volume",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "minimum", "unit": "μm", "value": 1.3708171844482422},
                        {"name": "maximum", "unit": "μm", "value": 65.93452453613281},
                        {"name": "median", "unit": "μm", "value": 8.429391860961914},
                        {"name": "mean", "unit": "μm", "value": 11.729339049786937},
                        {"name": "standard_deviation", "unit": "μm", "value": 10.971337931832881},
                    ],
                    "pref_label": "section_lengths",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "minimum", "unit": "μm", "value": 3.0071189403533936},
                        {"name": "maximum", "unit": "μm", "value": 15.437870025634766},
                        {"name": "median", "unit": "μm", "value": 7.821196556091309},
                        {"name": "mean", "unit": "μm", "value": 9.077946109771728},
                        {"name": "standard_deviation", "unit": "μm", "value": 4.232474823540596},
                    ],
                    "pref_label": "section_term_lengths",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "minimum", "unit": "μm", "value": 1.3708171844482422},
                        {"name": "maximum", "unit": "μm", "value": 65.93452453613281},
                        {"name": "median", "unit": "μm", "value": 11.146228790283203},
                        {"name": "mean", "unit": "μm", "value": 14.491206695636114},
                        {"name": "standard_deviation", "unit": "μm", "value": 14.565197452483643},
                    ],
                    "pref_label": "section_bif_lengths",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "minimum", "unit": "dimensionless", "value": 0.0},
                        {"name": "maximum", "unit": "dimensionless", "value": 7.0},
                        {"name": "median", "unit": "dimensionless", "value": 4.0},
                        {"name": "mean", "unit": "dimensionless", "value": 4.326530612244898},
                        {
                            "name": "standard_deviation",
                            "unit": "dimensionless",
                            "value": 1.7069815237817538,
                        },
                    ],
                    "pref_label": "section_branch_orders",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "minimum", "unit": "dimensionless", "value": 0.0},
                        {"name": "maximum", "unit": "dimensionless", "value": 6.0},
                        {"name": "median", "unit": "dimensionless", "value": 3.5},
                        {"name": "mean", "unit": "dimensionless", "value": 3.4166666666666665},
                        {
                            "name": "standard_deviation",
                            "unit": "dimensionless",
                            "value": 1.6051133570215186,
                        },
                    ],
                    "pref_label": "section_bif_branch_orders",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "minimum", "unit": "dimensionless", "value": 3.0},
                        {"name": "maximum", "unit": "dimensionless", "value": 7.0},
                        {"name": "median", "unit": "dimensionless", "value": 5.0},
                        {"name": "mean", "unit": "dimensionless", "value": 5.2},
                        {
                            "name": "standard_deviation",
                            "unit": "dimensionless",
                            "value": 1.296148139681572,
                        },
                    ],
                    "pref_label": "section_term_branch_orders",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "minimum", "unit": "μm", "value": 51.56536865234375},
                        {"name": "maximum", "unit": "μm", "value": 173.5483956336975},
                        {"name": "median", "unit": "μm", "value": 140.30963134765625},
                        {"name": "mean", "unit": "μm", "value": 129.91002093042647},
                        {"name": "standard_deviation", "unit": "μm", "value": 29.662002754802742},
                    ],
                    "pref_label": "section_path_distances",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {
                            "name": "minimum",
                            "unit": "dimensionless",
                            "value": -0.050027668476104736,
                        },
                        {
                            "name": "maximum",
                            "unit": "dimensionless",
                            "value": 1.9141037460326885e-16,
                        },
                        {
                            "name": "median",
                            "unit": "dimensionless",
                            "value": -3.652493749705474e-18,
                        },
                        {"name": "mean", "unit": "dimensionless", "value": -0.003127515373029262},
                        {
                            "name": "standard_deviation",
                            "unit": "dimensionless",
                            "value": 0.009822788270307671,
                        },
                    ],
                    "pref_label": "section_taper_rates",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "minimum", "unit": "radian", "value": 0.47377522888783696},
                        {"name": "maximum", "unit": "radian", "value": 1.6691038627945671},
                        {"name": "median", "unit": "radian", "value": 1.0642240351058527},
                        {"name": "mean", "unit": "radian", "value": 1.1049163425786215},
                        {
                            "name": "standard_deviation",
                            "unit": "radian",
                            "value": 0.2644924566922347,
                        },
                    ],
                    "pref_label": "local_bifurcation_angles",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "minimum", "unit": "radian", "value": 0.34369608206776314},
                        {"name": "maximum", "unit": "radian", "value": 2.9744974214113533},
                        {"name": "median", "unit": "radian", "value": 0.83795681500925},
                        {"name": "mean", "unit": "radian", "value": 0.9589040666082035},
                        {
                            "name": "standard_deviation",
                            "unit": "radian",
                            "value": 0.5345811618618049,
                        },
                    ],
                    "pref_label": "remote_bifurcation_angles",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "minimum", "unit": "dimensionless", "value": 0.0},
                        {"name": "maximum", "unit": "dimensionless", "value": 0.6875},
                        {"name": "median", "unit": "dimensionless", "value": 0.0},
                        {"name": "mean", "unit": "dimensionless", "value": 0.191940756003256},
                        {
                            "name": "standard_deviation",
                            "unit": "dimensionless",
                            "value": 0.24186326751364615,
                        },
                    ],
                    "pref_label": "partition_asymmetry",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "minimum", "unit": "μm", "value": 0.000329341660395155},
                        {"name": "maximum", "unit": "μm", "value": 0.47013431941007783},
                        {"name": "median", "unit": "μm", "value": 0.0077665873629627945},
                        {"name": "mean", "unit": "μm", "value": 0.05824312263454626},
                        {"name": "standard_deviation", "unit": "μm", "value": 0.11913148623554351},
                    ],
                    "pref_label": "partition_asymmetry_length",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "minimum", "unit": "dimensionless", "value": 0.6121212244033813},
                        {"name": "maximum", "unit": "dimensionless", "value": 1.0},
                        {"name": "median", "unit": "dimensionless", "value": 1.0},
                        {"name": "mean", "unit": "dimensionless", "value": 0.9499309957027435},
                        {
                            "name": "standard_deviation",
                            "unit": "dimensionless",
                            "value": 0.11314455157300414,
                        },
                    ],
                    "pref_label": "sibling_ratios",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "minimum", "unit": "dimensionless", "value": 2.0},
                        {"name": "maximum", "unit": "dimensionless", "value": 4.868290130981099},
                        {"name": "median", "unit": "dimensionless", "value": 2.0},
                        {"name": "mean", "unit": "dimensionless", "value": 2.3007714304487172},
                        {
                            "name": "standard_deviation",
                            "unit": "dimensionless",
                            "value": 0.6733418175667351,
                        },
                    ],
                    "pref_label": "diameter_power_relations",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "minimum", "unit": "μm", "value": 50.63172912597656},
                        {"name": "maximum", "unit": "μm", "value": 154.49050903320312},
                        {"name": "median", "unit": "μm", "value": 109.38362121582031},
                        {"name": "mean", "unit": "μm", "value": 102.34537163559271},
                        {"name": "standard_deviation", "unit": "μm", "value": 28.674482397181823},
                    ],
                    "pref_label": "section_radial_distances",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "minimum", "unit": "μm", "value": 64.33403015136719},
                        {"name": "maximum", "unit": "μm", "value": 154.49050903320312},
                        {"name": "median", "unit": "μm", "value": 113.7708511352539},
                        {"name": "mean", "unit": "μm", "value": 106.60736358642578},
                        {"name": "standard_deviation", "unit": "μm", "value": 29.230186682232286},
                    ],
                    "pref_label": "section_term_radial_distances",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "minimum", "unit": "μm", "value": 50.63172912597656},
                        {"name": "maximum", "unit": "μm", "value": 139.6158905029297},
                        {"name": "median", "unit": "μm", "value": 108.3280029296875},
                        {"name": "mean", "unit": "μm", "value": 97.90579668680827},
                        {"name": "standard_deviation", "unit": "μm", "value": 27.387516588667843},
                    ],
                    "pref_label": "section_bif_radial_distances",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "minimum", "unit": "μm", "value": 98.88428831100464},
                        {"name": "maximum", "unit": "μm", "value": 173.5483956336975},
                        {"name": "median", "unit": "μm", "value": 148.5470039844513},
                        {"name": "mean", "unit": "μm", "value": 138.80657278060914},
                        {"name": "standard_deviation", "unit": "μm", "value": 27.747075702301814},
                    ],
                    "pref_label": "terminal_path_lengths",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "minimum", "unit": "μm³", "value": 0.7123960740046634},
                        {"name": "maximum", "unit": "μm³", "value": 332.46868155897647},
                        {"name": "median", "unit": "μm³", "value": 6.277054895129806},
                        {"name": "mean", "unit": "μm³", "value": 16.04948142005722},
                        {"name": "standard_deviation", "unit": "μm³", "value": 49.988002414361766},
                    ],
                    "pref_label": "section_volumes",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "minimum", "unit": "μm²", "value": 4.523149450881758},
                        {"name": "maximum", "unit": "μm²", "value": 445.99350977741693},
                        {"name": "median", "unit": "μm²", "value": 26.746534607544493},
                        {"name": "mean", "unit": "μm²", "value": 42.52875478527103},
                        {"name": "standard_deviation", "unit": "μm²", "value": 75.35081671776754},
                    ],
                    "pref_label": "section_areas",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "minimum", "unit": "dimensionless", "value": 1.0},
                        {"name": "maximum", "unit": "dimensionless", "value": 1.3238543272018433},
                        {"name": "median", "unit": "dimensionless", "value": 1.0280802249908447},
                        {"name": "mean", "unit": "dimensionless", "value": 1.0482378906133223},
                        {
                            "name": "standard_deviation",
                            "unit": "dimensionless",
                            "value": 0.06718531774708324,
                        },
                    ],
                    "pref_label": "section_tortuosity",
                },
                {
                    "structural_domain": "basal_dendrite",
                    "measurement_items": [
                        {"name": "minimum", "unit": "dimensionless", "value": 1.0},
                        {"name": "maximum", "unit": "dimensionless", "value": 4.0},
                        {"name": "median", "unit": "dimensionless", "value": 1.0},
                        {"name": "mean", "unit": "dimensionless", "value": 1.7551020408163265},
                        {
                            "name": "standard_deviation",
                            "unit": "dimensionless",
                            "value": 0.9154147547757471,
                        },
                    ],
                    "pref_label": "section_strahler_orders",
                },
                {
                    "structural_domain": "apical_dendrite",
                    "measurement_items": [{"name": "raw", "unit": "μm", "value": 0.0}],
                    "pref_label": "neurite_max_radial_distance",
                },
                {
                    "structural_domain": "apical_dendrite",
                    "measurement_items": [{"name": "raw", "unit": "dimensionless", "value": 0.0}],
                    "pref_label": "number_of_sections",
                },
                {
                    "structural_domain": "apical_dendrite",
                    "measurement_items": [{"name": "raw", "unit": "dimensionless", "value": 0.0}],
                    "pref_label": "number_of_bifurcations",
                },
                {
                    "structural_domain": "apical_dendrite",
                    "measurement_items": [{"name": "raw", "unit": "dimensionless", "value": 0.0}],
                    "pref_label": "number_of_leaves",
                },
                {
                    "structural_domain": "apical_dendrite",
                    "measurement_items": [{"name": "raw", "unit": "μm", "value": 0.0}],
                    "pref_label": "total_length",
                },
                {
                    "structural_domain": "apical_dendrite",
                    "measurement_items": [{"name": "raw", "unit": "μm²", "value": 0.0}],
                    "pref_label": "total_area",
                },
                {
                    "structural_domain": "apical_dendrite",
                    "measurement_items": [{"name": "raw", "unit": "μm³", "value": 0.0}],
                    "pref_label": "total_volume",
                },
                {
                    "structural_domain": "neuron_morphology",
                    "measurement_items": [
                        {"name": "raw", "unit": "μm", "value": 154.49050903320312}
                    ],
                    "pref_label": "morphology_max_radial_distance",
                },
                {
                    "structural_domain": "neuron_morphology",
                    "measurement_items": [
                        {"name": "minimum", "unit": "dimensionless", "value": 49.0},
                        {"name": "maximum", "unit": "dimensionless", "value": 49.0},
                        {"name": "median", "unit": "dimensionless", "value": 49.0},
                        {"name": "mean", "unit": "dimensionless", "value": 49.0},
                        {"name": "standard_deviation", "unit": "dimensionless", "value": 0.0},
                    ],
                    "pref_label": "number_of_sections_per_neurite",
                },
                {
                    "structural_domain": "neuron_morphology",
                    "measurement_items": [
                        {"name": "minimum", "unit": "μm", "value": 574.7376134395599},
                        {"name": "maximum", "unit": "μm", "value": 574.7376134395599},
                        {"name": "median", "unit": "μm", "value": 574.7376134395599},
                        {"name": "mean", "unit": "μm", "value": 574.7376134395599},
                        {"name": "standard_deviation", "unit": "μm", "value": 0.0},
                    ],
                    "pref_label": "total_length_per_neurite",
                },
                {
                    "structural_domain": "neuron_morphology",
                    "measurement_items": [
                        {"name": "minimum", "unit": "μm²", "value": 2083.9089844782807},
                        {"name": "maximum", "unit": "μm²", "value": 2083.9089844782807},
                        {"name": "median", "unit": "μm²", "value": 2083.9089844782807},
                        {"name": "mean", "unit": "μm²", "value": 2083.9089844782807},
                        {"name": "standard_deviation", "unit": "μm²", "value": 0.0},
                    ],
                    "pref_label": "total_area_per_neurite",
                },
                {
                    "structural_domain": "neuron_morphology",
                    "measurement_items": [
                        {"name": "raw", "unit": "μm", "value": 66.69000244140625}
                    ],
                    "pref_label": "total_height",
                },
                {
                    "structural_domain": "neuron_morphology",
                    "measurement_items": [
                        {"name": "raw", "unit": "μm", "value": 155.34999084472656}
                    ],
                    "pref_label": "total_width",
                },
                {
                    "structural_domain": "neuron_morphology",
                    "measurement_items": [{"name": "raw", "unit": "μm", "value": 4.75}],
                    "pref_label": "total_depth",
                },
                {
                    "structural_domain": "neuron_morphology",
                    "measurement_items": [{"name": "raw", "unit": "dimensionless", "value": 1.0}],
                    "pref_label": "number_of_neurites",
                },
                {
                    "structural_domain": "soma",
                    "measurement_items": [
                        {"name": "raw", "unit": "μm²", "value": 1218.140871757005}
                    ],
                    "pref_label": "soma_surface_area",
                },
                {
                    "structural_domain": "soma",
                    "measurement_items": [
                        {"name": "raw", "unit": "μm", "value": 9.845637133329614}
                    ],
                    "pref_label": "soma_radius",
                },
            ],
        }
    ],
    "pagination": {"page": 1, "page_size": 100, "total_items": 1},
    "facets": None,
}

_analysis_dict_base = uf.create_analysis_dict(TEMPLATE)
analysis_dict = dict(_analysis_dict_base)

if DEFAULT_NEURITE_DOMAIN in analysis_dict:
    default_analysis = analysis_dict[DEFAULT_NEURITE_DOMAIN]
    for domain in TARGET_NEURITE_DOMAINS:
        analysis_dict[domain] = default_analysis


def _run_morphology_analysis(morphology_path: str) -> dict:
    try:
        neuron = nm.load_morphology(morphology_path)

        results_dict = uf.build_results_dict(analysis_dict, neuron)

        metrics_filename = f"M_metrics_{pathlib.Path(morphology_path).stem}.json"
        filled = uf.fill_json(TEMPLATE, results_dict, entity_id=metrics_filename)

        return filled["data"][0]["measurement_kinds"]

    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": "MORPHOLOGY_ANALYSIS_ERROR",
                "detail": f"Error during morphology analysis: {e!s}",
            },
        ) from e


@router.post(
    "/morphology-metrics-calculation",
    summary="Calculate morphology metrics.",
    description="Performs analysis on a neuron file (.swc, .h5, or .asc).",
)
async def morphology_metrics_calculation(
    file: Annotated[UploadFile, File(description="Neuron file to upload (.swc, .h5, or .asc)")],
) -> dict:
    file_extension = _validate_file_extension(file.filename)
    content = await file.read()

    if not content:
        _handle_empty_file(file)

    temp_file_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
            temp_file.write(content)
            temp_file_path = temp_file.name

        measurement_list = _run_morphology_analysis(temp_file_path)

        return {"measurement_kinds": measurement_list}

    finally:
        if temp_file_path:
            with suppress(OSError):
                pathlib.Path(temp_file_path).unlink()
