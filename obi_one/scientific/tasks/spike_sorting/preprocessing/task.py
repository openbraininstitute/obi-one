class SpikeSortingTask(Task):
    """SpikeSortingPreprocessing."""

    title: ClassVar[str] = "Multi Electrode Recording Postprocessing"
    description: ClassVar[str] = "Spike sorting preprocessing configuration."

    single_config: SpikeSortingSingleConfig

    _pipeline_dict: dict = {}

    def _add_job_dispatch_dict(self):
        d = {}
        d["no-split-segments"] = not self.single_config.setup_advanced.split_segments
        d["no-split-groups"] = not self.single_config.setup.advanced.split_groups
        d["debug"] = not self.single_config.setup_recording.test_mode
        d["debug_duration"] = self.single_config.setup_recording.test_mode_duration
        d["skip_timestamps_check"] = self.single_config.setup_advanced.skip_timestamps_check
        d["multi_session_data"] = self.single_config.setup_advanced.multi_session_data
        d["min_recording_duration"] = self.single_config.setup_advanced.min_recording_duration
        d["input"] = (
            "nwb"  # Which 'loader' to use (aind | spikeglx | openephys | nwb | spikeinterface)
        )

        spikeinterface_info = {}

        # REQUIRED e.g. 'plexon', 'neuralynx', 'intan' etc.
        spikeinterface_info["reader_type"] = "plexon"

        # OPTIONAL e.g. {'folder': '/path/to/folder'}
        spikeinterface_info["reader_kwargs"] = {}

        # OPTIONAL string or list of strings with the stream names to load (e.g. 'AP' or ['AP', 'LFP']).
        spikeinterface_info["keep_stream_substrings"] = "AP"

        # OPTIONAL string (or list of strings) with substrings used to skip streams (e.g. 'NIDQ' or ['USB', 'EVENTS']).
        spikeinterface_info["skip_stream_substrings"] = []

        # OPTIONAL: probe_paths (optional): string or dict the probe paths to a ProbeInterface JSON file (e.g. '/path/to/probe.json'). If a dict is provided, the key is the stream name and the value is the probe path. If reader_kwargs is not provided, the reader will be created with default parameters. The probe_path is required if the reader doesn't load the probe automatically.
        spikeinterface_info["probe_paths"] = None

        # WRITE spikeinterface_info to json

        # Add path to params
        d["spikeinterface_info"] = "PATH_TO_SPIKEINTERFACE_INFO_JSON"

        self._pipeline_dict["job_dispatch"] = d

    def _add_preprocessing_dict(self):
        d = {}

        d["job_kwargs"] = {"chunk_duration": "1s", "progress_bar": False, "mp_context": "spawn"}

    def execute(self):
        self._add_job_dispatch_dict()

        self._pipeline_dict["preprocessing"] = self.single_config.dictionary_representation()
