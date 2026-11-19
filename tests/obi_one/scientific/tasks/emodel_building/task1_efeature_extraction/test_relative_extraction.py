"""Relative (% of rheobase) extraction run for real through bluepyefe and BluePyEModel.

Two synthetic cells with different rheobases are extracted at 150% and 250% of
their own rheobase. The output must hold ``ThresholdBasedProtocol``s backed by the
RMP, input-resistance, holding and threshold current targets, so that
optimisation and validation stimulate each e-model relative to its own threshold.
"""

import json
from unittest.mock import Mock, patch

import pytest

from obi_one.scientific.library.recording_summary import compute_recording_summary
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks.protocol_and_feature_selection import (  # ruff: ignore[line-too-long]
    SelectEFeaturesByProtocol,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks.settings import (
    Settings,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.efeatures import (  # ruff: ignore[line-too-long]
    MeanFrequencyFeature,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.protocols import (  # ruff: ignore[line-too-long]
    IDRestProtocol,
    IDThreshProtocol,
    IVProtocol,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
    EXTRACTED_FEATURES_FILENAME,
    TARGETS_CONFIG_RELPATH,
    EModelEFeatureExtractionTask,
    RecordingInput,
)

from tests.obi_one.scientific.library.spiking_nwb import TOFF_MS, TON_MS, write_spiking_nwb

pytest.importorskip("bluepyemodel")

RHEOBASES_NA = {"cell_a": 0.2, "cell_b": 0.3}
PRE_PROTOCOLS = {"RMPProtocol", "SearchHoldingCurrent", "RinProtocol", "SearchThresholdCurrent"}


@pytest.fixture(scope="module")
def extracted(tmp_path_factory):
    """Run the extraction task once on two cells; return the output directory."""
    tmp_path = tmp_path_factory.mktemp("relative_extraction")
    downloaded = []
    for name, rheobase in RHEOBASES_NA.items():
        sweeps = {
            "IDthresh": [rheobase * f for f in (0.5, 0.75, 1.0, 1.25, 1.5)],
            "IV": [rheobase * f for f in (-0.4, -0.2, 0.0)],
            "IDrest": [rheobase * f for f in (1.5, 2.5)],
        }
        path = write_spiking_nwb(tmp_path / f"{name}.nwb", sweeps, rheobase_na=rheobase)
        downloaded.append(
            RecordingInput(
                path=path, ljp=0.0, summary=compute_recording_summary(path), recording_id=name
            )
        )

    config = Mock()
    config.coordinate_output_root = tmp_path / "out"
    config.coordinate_output_root.mkdir()
    config.efeatures_by_protocol.selection = SelectEFeaturesByProtocol(
        protocols=(
            IDThreshProtocol(),
            IVProtocol(),
            IDRestProtocol(
                extraction_amplitudes=((150.0, False), (250.0, True)),
                features=(MeanFrequencyFeature(),),
            ),
        )
    )
    config.settings = Settings(amplitude_mode="relative", rin_amplitude=-40.0)
    task = EModelEFeatureExtractionTask.model_construct(config=config)
    with patch.object(
        EModelEFeatureExtractionTask, "_download_recordings", return_value=downloaded
    ):
        return task.execute(db_client=None)


@pytest.fixture(scope="module")
def features(extracted):
    return json.loads((extracted / EXTRACTED_FEATURES_FILENAME).read_text())


def test_protocols_are_threshold_based_and_named_in_percent(features):
    protocols = {p["name"]: p for p in features["protocols"]}

    assert set(protocols) == {"IDrest_150.0", "IDrest_250.0"}
    assert {p["protocol_type"] for p in protocols.values()} == {"ThresholdBasedProtocol"}
    assert protocols["IDrest_250.0"]["validation"] is True
    assert protocols["IDrest_150.0"]["stimuli"][0]["thresh_perc"] == pytest.approx(150.0, abs=1.0)


def test_each_cell_is_matched_at_its_own_rheobase(features):
    """Both cells' 150% sweeps (0.3 and 0.45 nA) feed the 150% target."""
    mean_frequency = next(
        f
        for f in features["efeatures"]
        if f["protocol_name"] == "IDrest_150.0" and f["efel_feature_name"] == "mean_frequency"
    )
    assert mean_frequency["sample_size"] == len(RHEOBASES_NA)


def test_threshold_based_targets_are_present(features):
    efeatures = features["efeatures"]

    assert {f["protocol_name"] for f in efeatures} >= PRE_PROTOCOLS
    threshold = next(f for f in efeatures if f["efel_feature_name"] == "bpo_threshold_current")
    assert threshold["mean"] == pytest.approx(sum(RHEOBASES_NA.values()) / len(RHEOBASES_NA))


def test_validation_stage_accepts_the_features(extracted):
    from obi_one.scientific.tasks.emodel_building.task3_emodel_validation.staging import (  # ruff: ignore[import-outside-top-level]
        check_threshold_search_targets,
    )

    check_threshold_search_targets(extracted / EXTRACTED_FEATURES_FILENAME)


def test_optimisation_stimulates_relative_to_the_model_threshold(features):
    """BluePyEModel's evaluator scales the step with the e-model's threshold current."""
    from bluepyemodel.evaluation.evaluator import (  # ruff: ignore[import-outside-top-level]
        define_threshold_based_optimisation_protocol,
    )
    from bluepyemodel.evaluation.fitness_calculator_configuration import (  # ruff: ignore[import-outside-top-level]
        FitnessCalculatorConfiguration,
    )

    configuration = FitnessCalculatorConfiguration(
        efeatures=features["efeatures"], protocols=features["protocols"]
    )
    runner, _ = define_threshold_based_optimisation_protocol(
        configuration, include_validation_protocols=True
    )

    assert set(runner.protocols) >= PRE_PROTOCOLS
    stimulus = runner.protocols["IDrest_150.0"].stimuli[0]
    stimulus.threshold_current = 0.4
    assert stimulus.amplitude == pytest.approx(0.6, rel=0.01)


def test_files_metadata_carry_the_detected_timing(extracted):
    """Each file's timing comes from its summary, not from bluepyefe's detection."""
    configuration = json.loads((extracted / TARGETS_CONFIG_RELPATH).read_text())
    for file in configuration["files"]:
        for protocol in ("IDthresh", "IV", "IDrest"):
            entry = file["ecodes"][protocol]
            assert (entry["ton"], entry["toff"]) == pytest.approx((TON_MS, TOFF_MS))
