from typing import get_args

import pytest
from pydantic import ValidationError

from obi_one.scientific.tasks.tribe_brain_prediction import (
    TribeBrainPredictionScanConfig,
    TribeBrainPredictionSingleConfig,
    TribeBrainPredictionTask,
)
from obi_one.scientific.unions.config_task_map import (
    _config_tasks_map,
    get_configs_task_type,
)
from obi_one.scientific.unions.unions_scan_configs import ScanConfigsUnion
from obi_one.scientific.unions.unions_tasks import TasksUnion


class TestTribeBrainPredictionScanConfig:
    def test_create_with_video(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.touch()
        config = TribeBrainPredictionScanConfig(
            stimulus=TribeBrainPredictionScanConfig.Stimulus(video_path=video),
        )
        assert config.stimulus.video_path == video
        assert config.stimulus.audio_path is None
        assert config.stimulus.text is None

    def test_create_with_audio(self, tmp_path):
        audio = tmp_path / "test.wav"
        audio.touch()
        config = TribeBrainPredictionScanConfig(
            stimulus=TribeBrainPredictionScanConfig.Stimulus(audio_path=audio),
        )
        assert config.stimulus.audio_path == audio

    def test_create_with_text(self):
        config = TribeBrainPredictionScanConfig(
            stimulus=TribeBrainPredictionScanConfig.Stimulus(text="To be or not to be."),
        )
        assert config.stimulus.text == "To be or not to be."

    def test_rejects_no_stimulus(self):
        with pytest.raises(ValidationError, match="Exactly one"):
            TribeBrainPredictionScanConfig(
                stimulus=TribeBrainPredictionScanConfig.Stimulus(),
            )

    def test_rejects_multiple_stimuli(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.touch()
        with pytest.raises(ValidationError, match="Exactly one"):
            TribeBrainPredictionScanConfig(
                stimulus=TribeBrainPredictionScanConfig.Stimulus(
                    video_path=video,
                    text="Hello",
                ),
            )

    def test_default_model_config(self):
        config = TribeBrainPredictionScanConfig(
            stimulus=TribeBrainPredictionScanConfig.Stimulus(text="Hello"),
        )
        assert config.model.checkpoint == "facebook/tribev2"
        assert config.model.device == "auto"

    def test_default_visualization_config(self):
        config = TribeBrainPredictionScanConfig(
            stimulus=TribeBrainPredictionScanConfig.Stimulus(text="Hello"),
        )
        assert config.visualization.cmap == "fire"
        assert config.visualization.mesh == "fsaverage5"
        assert config.visualization.output_video is True
        assert config.visualization.output_timesteps_image is True
        assert config.visualization.show_stimuli is True

    def test_custom_visualization(self):
        config = TribeBrainPredictionScanConfig(
            stimulus=TribeBrainPredictionScanConfig.Stimulus(text="Hello"),
            visualization=TribeBrainPredictionScanConfig.Visualization(
                cmap="hot",
                mesh="fsaverage4",
                n_timesteps=10,
                views="dorsal",
                output_video=False,
            ),
        )
        assert config.visualization.cmap == "hot"
        assert config.visualization.mesh == "fsaverage4"
        assert config.visualization.n_timesteps == 10
        assert config.visualization.views == "dorsal"
        assert config.visualization.output_video is False

    def test_scan_config_class_variables(self):
        assert TribeBrainPredictionScanConfig.name == "TRIBE v2 Brain Activity Prediction"
        assert TribeBrainPredictionScanConfig.single_coord_class_name == (
            "TribeBrainPredictionSingleConfig"
        )

    def test_video_path_scannable(self, tmp_path):
        v1 = tmp_path / "a.mp4"
        v2 = tmp_path / "b.mp4"
        v1.touch()
        v2.touch()
        config = TribeBrainPredictionScanConfig(
            stimulus=TribeBrainPredictionScanConfig.Stimulus(video_path=[v1, v2]),
        )
        assert config.stimulus.video_path == [v1, v2]

    def test_text_scannable(self):
        config = TribeBrainPredictionScanConfig(
            stimulus=TribeBrainPredictionScanConfig.Stimulus(
                text=["Hello world", "Goodbye world"],
            ),
        )
        assert len(config.stimulus.text) == 2


class TestTribeBrainPredictionSingleConfig:
    def test_single_config_creation(self):
        config = TribeBrainPredictionSingleConfig(
            stimulus=TribeBrainPredictionSingleConfig.Stimulus(text="To be or not to be."),
        )
        assert config.stimulus.text == "To be or not to be."

    def test_single_config_rejects_list_video(self, tmp_path):
        v1 = tmp_path / "a.mp4"
        v2 = tmp_path / "b.mp4"
        v1.touch()
        v2.touch()
        with pytest.raises(TypeError, match="must not be a list"):
            TribeBrainPredictionSingleConfig(
                stimulus=TribeBrainPredictionSingleConfig.Stimulus(
                    video_path=[v1, v2],
                ),
            )

    def test_single_config_rejects_list_text(self):
        with pytest.raises(TypeError, match="must not be a list"):
            TribeBrainPredictionSingleConfig(
                stimulus=TribeBrainPredictionSingleConfig.Stimulus(
                    text=["Hello", "World"],
                ),
            )


class TestTribeBrainPredictionTask:
    def test_task_creation(self):
        config = TribeBrainPredictionSingleConfig(
            stimulus=TribeBrainPredictionSingleConfig.Stimulus(text="To be or not to be."),
        )
        task = TribeBrainPredictionTask(config=config)
        assert task.config is config

    def test_task_type_field(self):
        config = TribeBrainPredictionSingleConfig(
            stimulus=TribeBrainPredictionSingleConfig.Stimulus(
                text="Hello",
            ),
        )
        task = TribeBrainPredictionTask(config=config)
        assert task.type == "TribeBrainPredictionTask"

    def test_get_stimulus_type_text(self):
        config = TribeBrainPredictionSingleConfig(
            stimulus=TribeBrainPredictionSingleConfig.Stimulus(text="Hello"),
        )
        task = TribeBrainPredictionTask(config=config)
        assert task._get_stimulus_type() == "text"

    def test_get_stimulus_type_video(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.touch()
        config = TribeBrainPredictionSingleConfig(
            stimulus=TribeBrainPredictionSingleConfig.Stimulus(video_path=video),
        )
        task = TribeBrainPredictionTask(config=config)
        assert task._get_stimulus_type() == "video"

    def test_get_stimulus_type_audio(self, tmp_path):
        audio = tmp_path / "test.wav"
        audio.touch()
        config = TribeBrainPredictionSingleConfig(
            stimulus=TribeBrainPredictionSingleConfig.Stimulus(audio_path=audio),
        )
        task = TribeBrainPredictionTask(config=config)
        assert task._get_stimulus_type() == "audio"


class TestConfigTaskMapIntegration:
    def test_config_task_map_has_entry(self):
        assert TribeBrainPredictionSingleConfig in _config_tasks_map
        assert _config_tasks_map[TribeBrainPredictionSingleConfig] is TribeBrainPredictionTask

    def test_get_configs_task_type(self):
        config = TribeBrainPredictionSingleConfig(
            stimulus=TribeBrainPredictionSingleConfig.Stimulus(text="Hello"),
        )
        assert get_configs_task_type(config) is TribeBrainPredictionTask


class TestUnionsIntegration:
    def test_scan_config_in_union(self):
        union_types = get_args(get_args(ScanConfigsUnion)[0])
        type_names = [t.__name__ for t in union_types]
        assert "TribeBrainPredictionScanConfig" in type_names

    def test_task_in_union(self):
        union_types = get_args(get_args(TasksUnion)[0])
        type_names = [t.__name__ for t in union_types]
        assert "TribeBrainPredictionTask" in type_names
