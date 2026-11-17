"""Download hoc, morphology and mechanisms for the ME-model build."""

import concurrent.futures
from dataclasses import dataclass
from pathlib import Path

import entitysdk
from entitysdk.downloaders.cell_morphology import MORPHOLOGY_CONTENT_TYPES, download_morphology
from entitysdk.downloaders.emodel import download_hoc
from entitysdk.downloaders.ion_channel_model import download_ion_channel_mechanism
from entitysdk.exception import StagingError
from entitysdk.models import CellMorphology, EModel
from entitysdk.utils.filesystem import create_dir

DOWNLOAD_CONCURRENCY = 8


@dataclass(frozen=True)
class StagedMEModel:
    """Local paths needed to calibrate and validate the build."""

    hoc_path: Path
    morphology_path: Path
    mechanisms_dir: Path


def stage_memodel(
    db_client: entitysdk.Client,
    morphology: CellMorphology,
    emodel: EModel,
    output_dir: Path,
) -> StagedMEModel:
    """Download hoc, one morphology format and mechanisms from the build inputs.

    Morphology preference is asc, then swc, then h5; only the first available format is downloaded.
    The caller must pass an e-model that already includes ``ion_channel_models``.
    """
    hoc_dir = output_dir / "hoc"
    morphology_dir = output_dir / "morphology"
    mechanisms_dir = create_dir(output_dir / "mechanisms")
    ion_channels = list(emodel.ion_channel_models or [])

    with concurrent.futures.ThreadPoolExecutor(max_workers=DOWNLOAD_CONCURRENCY) as executor:
        hoc_future = executor.submit(download_hoc, db_client, emodel, hoc_dir)
        morphology_future = executor.submit(
            _download_first_morphology, db_client, morphology, morphology_dir
        )
        mechanism_futures = [
            executor.submit(download_ion_channel_mechanism, db_client, ic, mechanisms_dir)
            for ic in ion_channels
        ]
        hoc_path = hoc_future.result()
        morphology_path = morphology_future.result()
        for future in mechanism_futures:
            future.result()

    if not hoc_path.exists():
        msg = f"HOC file does not exist: {hoc_path}"
        raise StagingError(msg)

    return StagedMEModel(
        hoc_path=hoc_path,
        morphology_path=morphology_path,
        mechanisms_dir=mechanisms_dir,
    )


def _download_first_morphology(
    db_client: entitysdk.Client,
    morphology: CellMorphology,
    morphology_dir: Path,
) -> Path:
    present = {asset.content_type for asset in morphology.assets}
    for file_type, content_type in MORPHOLOGY_CONTENT_TYPES.items():
        if content_type in present:
            return download_morphology(db_client, morphology, morphology_dir / file_type, file_type)
    msg = f"No morphology file found for morphology {morphology.id}"
    raise StagingError(msg)
