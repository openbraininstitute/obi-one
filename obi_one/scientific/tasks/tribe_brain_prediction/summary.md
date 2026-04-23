New task: TRIBE v2 Brain Activity Prediction

  Files created

  Task module (obi_one/scientific/tasks/tribe_brain_prediction/):
  - config.py — TribeBrainPredictionScanConfig and TribeBrainPredictionSingleConfig with three
  blocks:
    - Stimulus — accepts exactly one of video_path, audio_path, or text (all scannable via lists)
    - Model — checkpoint ID (defaults to facebook/tribev2), device, cache folder
    - Visualization — output video/timesteps image, colormap, mesh resolution, view angle, stimuli
  overlay, interpolated FPS
  - task.py — TribeBrainPredictionTask that:
    a. Loads the TRIBE v2 model from HuggingFace (or local checkpoint)
    b. Builds events from the stimulus (video extracts audio+words automatically; text is converted
  to speech)
    c. Runs brain activity prediction → (n_timesteps, ~20k vertices) array
    d. Saves: predictions.npy, events.csv, prediction_metadata.json
    e. Generates: brain_activity_timesteps.png (static mosaic) and brain_activity.mp4 (video)
  - __init__.py — public exports

  Tests (tests/obi_one/scientific/tasks/tribe_brain_prediction/):
  - 23 tests covering config creation, validation (exactly-one-stimulus enforcement, single-config
  rejects lists), task instantiation, stimulus type detection, config-task map integration, and union
   registration

  Files modified

  - unions_scan_configs.py — added TribeBrainPredictionScanConfig
  - unions_tasks.py — added TribeBrainPredictionTask
  - config_task_map.py — added TribeBrainPredictionSingleConfig → TribeBrainPredictionTask mapping

  Usage example

  import obi_one as obi

  config = obi.TribeBrainPredictionScanConfig(
      stimulus=obi.TribeBrainPredictionScanConfig.Stimulus(
          video_path="/path/to/video.mp4"
      ),
      visualization=obi.TribeBrainPredictionScanConfig.Visualization(
          n_timesteps=15,
          cmap="fire",
          views="left",
          show_stimuli=True,
      ),
  )