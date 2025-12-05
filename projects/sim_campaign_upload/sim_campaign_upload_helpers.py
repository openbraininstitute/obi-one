import json
from pathlib import Path

from entitysdk import models

import obi_one as obi
from obi_one.scientific.blocks.neuron_sets.base import AbstractNeuronSet

# Key mapping in initialize section
_INIT_KEY_MAPPING = {
    "seed": "random_seed",
    "ca": "extracellular_calcium_concentration",
    "sim_duration": "simulation_length",
    "v_init": "v_init",
}

# Global counters for references
_global_refs = {
    "timestamps": {"counter": 0, "label": "Timestamps_"},
    "neuron_sets": {"counter": 0, "label": "NeuronSet_"},
    "stimuli": {"counter": 0, "label": "Stimulus_"},
    "recordings": {"counter": 0, "label": "Recording_"},
    "synaptic_manipulations": {"counter": 0, "label": "SynapticManipulation_"},
}


def get_next_ref_name(block_dict_name: dict) -> str:
    """Returns the next valid reference name for a given block dict."""
    if block_dict_name not in _global_refs:
        msg = f"'{block_dict_name}' references not supported!"
        raise ValueError(msg)
    next_label = _global_refs[block_dict_name]["label"] + str(
        _global_refs[block_dict_name]["counter"]
    )
    _global_refs[block_dict_name]["counter"] += 1
    return next_label


def get_stimulus_timestamps(campaign_config_dict: dict) -> dict:
    """Extracts timestamps for a repetitive stimulus."""
    if not all(
        key in campaign_config_dict["attrs"] for key in ["stim_delay", "stim_rate", "num_stims"]
    ):
        return {}
    timestamps = obi.RegularTimestamps(
        start_time=campaign_config_dict["attrs"]["stim_delay"],
        interval=1e3 / campaign_config_dict["attrs"]["stim_rate"],
        number_of_repetitions=campaign_config_dict["attrs"]["num_stims"],
    )
    # > return {"Stimulus timestamps": timestamps.model_dump()}
    return {get_next_ref_name("timestamps"): timestamps.model_dump()}


def get_sim_length(campaign_config_dict: dict) -> dict:
    """Extracts simulation length for the init section."""
    if "sim_duration" not in campaign_config_dict["attrs"]:
        return {}
    return {_INIT_KEY_MAPPING["sim_duration"]: campaign_config_dict["attrs"]["sim_duration"]}


def get_ca_concentration(campaign_config_dict: dict, scan_params: dict) -> dict:
    """Extracts the Ca value for the init section. May be a scan parameter."""
    if "ca" in scan_params:
        ca = scan_params["ca"]
    elif "ca" in campaign_config_dict["attrs"]:
        ca = campaign_config_dict["attrs"]["ca"]
    else:
        return {}
    return {_INIT_KEY_MAPPING["ca"]: ca}


def get_sim_seed(campaign_config_dict: dict, scan_params: dict) -> dict:
    """Extracts the sim seed for the init section. May be a scan parameter."""
    if "seed" in scan_params:
        seed = scan_params["seed"]
    elif "seed" in campaign_config_dict["attrs"]:
        seed = campaign_config_dict["attrs"]["seed"]
    else:
        return {}
    return {_INIT_KEY_MAPPING["seed"]: seed}


def get_neuron_set_ref(
    neuron_set: str | AbstractNeuronSet, ref_name: str
) -> (AbstractNeuronSet, obi.NeuronSetReference):
    """Returns a reference to a neuron set."""
    if isinstance(neuron_set, str):
        neuron_set = obi.PredefinedNeuronSet(node_set=neuron_set)
    ref = obi.NeuronSetReference(
        type="NeuronSetReference", block_dict_name="neuron_sets", block_name=ref_name
    )
    return neuron_set, ref


def get_sim_neuron_set(campaign_config_dict: dict) -> dict:
    """Extracts the sim neuron set."""
    if "node_set" not in campaign_config_dict["attrs"]:
        return {}
    node_set = campaign_config_dict["attrs"]["node_set"]
    # > ref_name = "Simulation neuron set"
    ref_name = get_next_ref_name("neuron_sets")
    neuron_set, ref = get_neuron_set_ref(node_set, ref_name)
    return {ref_name: neuron_set.model_dump()}, {"node_set": ref.model_dump()}


def get_v_init(sim_config_dicts: list) -> dict:
    """Extracts the init voltage for the init section."""
    v = None
    for idx, cfg_dict in enumerate(sim_config_dicts):
        v_tmp = cfg_dict.get("conditions", {}).get("v_init")
        if idx == 0:
            v = v_tmp
        elif v != v_tmp:
            msg = "V init mismatch!"
            raise ValueError(msg)
    if v is None:
        return {}
    return {_INIT_KEY_MAPPING["v_init"]: v}


def add_to_dict(key: str, value: dict, cfg_dict: dict) -> None:
    """Adds settings to a config dict. Checks for consistency, if existing."""
    if key in cfg_dict:
        # Already existing, check if identical
        if cfg_dict[key] != value:
            msg = f"{key} mismatch!"
            raise ValueError(msg)
    else:
        cfg_dict[key] = value


def get_soma_recordings(sim_config_dicts: list) -> (dict, dict):
    """Extracts soma recordings."""
    rec_dict = {}
    neuron_set_dict = {}
    for cfg_dict in sim_config_dicts:
        for v in cfg_dict["reports"].values():
            if v["type"] != "compartment":
                msg = "Only compartment reports supported!"
                raise ValueError(msg)
            if v["sections"] != "soma":
                msg = "Only soma reports supported!"
                raise ValueError(msg)

            node_set = v["cells"]
            rec_name = get_next_ref_name("recordings")  # k[0].upper() + k[1:]
            neuron_set, ref = get_neuron_set_ref(
                node_set, get_next_ref_name("neuron_sets")
            )  # f"{rec_name} recording neuron set"
            rec = obi.TimeWindowSomaVoltageRecording(
                neuron_set=ref,
                dt=v["dt"],
                start_time=v["start_time"],
                end_time=v["end_time"],
            )
            add_to_dict(rec_name, rec.model_dump(), rec_dict)
            add_to_dict(ref.block_name, neuron_set.model_dump(), neuron_set_dict)
    return rec_dict, neuron_set_dict


def get_single_timestamp_ref(
    t: float, ref_name: str
) -> (obi.SingleTimestamp, obi.TimestampsReference):
    """Returns a reference to a single timestamp."""
    ts = obi.SingleTimestamp(start_time=t)
    ref = obi.TimestampsReference(
        type="TimestampsReference", block_dict_name="timestamps", block_name=ref_name
    )
    return ts, ref


def get_spike_replays(sim_config_dicts: list, circuit_entity: models.Circuit) -> (dict, dict, dict):
    """Extracts spike replay stimuli."""
    replay_dict = {}
    timestamps_dict = {}
    neuron_set_dict = {}
    for cfg_dict in sim_config_dicts:
        for v in cfg_dict["inputs"].values():
            if not (v["module"] == "synapse_replay" and v["input_type"] == "spikes"):
                continue
            if "nbS1" in circuit_entity.name and "VPM" in v["source"].upper():
                src, src_ref = get_neuron_set_ref(
                    obi.nbS1VPMInputs(), get_next_ref_name("neuron_sets")
                )  # v["source"]
            elif "nbS1" in circuit_entity.name and "POM" in v["source"].upper():
                src, src_ref = get_neuron_set_ref(
                    obi.nbS1POmInputs(), get_next_ref_name("neuron_sets")
                )  # v["source"]
            else:
                msg = "Circuit or projection source not yet implemented!"
                raise NotImplementedError(msg)
            tgt, tgt_ref = get_neuron_set_ref(
                v["node_set"], get_next_ref_name("neuron_sets")
            )  # f"{k} target"
            ts, ts_ref = get_single_timestamp_ref(
                v["delay"], get_next_ref_name("timestamps")
            )  # f"{k} onset"

            replay = obi.scientific.blocks.stimulus.SpikeStimulus(
                source_neuron_set=src_ref, targeted_neuron_set=tgt_ref, timestamps=ts_ref
            )
            replay_name = get_next_ref_name("stimuli")  # k
            add_to_dict(replay_name, replay.model_dump(), replay_dict)
            add_to_dict(ts_ref.block_name, ts.model_dump(), timestamps_dict)
            add_to_dict(src_ref.block_name, src.model_dump(), neuron_set_dict)
            add_to_dict(tgt_ref.block_name, tgt.model_dump(), neuron_set_dict)
    return replay_dict, timestamps_dict, neuron_set_dict


def get_single_param_dict(scan_params: dict) -> dict:
    """Returns the single coordinate scan param dict."""

    def get_loc(k: str) -> list:
        if k in _INIT_KEY_MAPPING:
            return ["initialize", _INIT_KEY_MAPPING[k]]
        return [None, k]  # TODO: Better handling, if not found

    single_params_dict = {
        "type": "SingleCoordinateScanParams",
        "nested_coordinate_subpath_str": ".",
        "scan_params": [
            {
                "type": "SingleValueScanParam",
                "value": v,
                "location_list": get_loc(k),
            }
            for k, v in scan_params.items()
        ],
    }
    return single_params_dict


def generate_obi_config(
    sim_campaign: dict,
    campaign_config_dict: dict,
    sim_config_dicts: list,
    scan_params: dict,
    circuit_entity: models.Circuit,
    coordinate_idx: int | None = None,
) -> dict:
    """Generates the full obi-one scan or single coordinate config dict."""
    if coordinate_idx is None:
        # Scan config
        cfg_type = "CircuitSimulationScanConfig"
        single_dict = {}
    else:
        # Single coordinate config
        if any(isinstance(val, list) for val in scan_params.values()):
            msg = "No lists possible in single coordinate config!"
            raise ValueError(msg)
        cfg_type = "CircuitSimulationSingleConfig"
        single_dict = {
            "idx": coordinate_idx,
            "coordinate_output_root": f"./{coordinate_idx}",
            "scan_output_root": "./",
            "single_coordinate_scan_params": get_single_param_dict(scan_params),
        }

    sim_neuron_set, sim_neuron_set_ref = get_sim_neuron_set(campaign_config_dict)
    recordings, rec_neuron_sets = get_soma_recordings(sim_config_dicts)
    stim_timestamps = get_stimulus_timestamps(campaign_config_dict)
    spk_replays, spk_timestamps, spk_neuron_sets = get_spike_replays(
        sim_config_dicts, circuit_entity
    )
    obi_one_config = {
        "type": cfg_type,
        "info": {
            "type": "Info",
            "campaign_name": sim_campaign["campaign_name"],
            "campaign_description": sim_campaign["campaign_description"],
        },
        **single_dict,
        "initialize": {
            "type": "CircuitSimulationScanConfig.Initialize",
            "circuit": {"type": "CircuitFromID", "id_str": str(circuit_entity.id)},
            **get_sim_length(campaign_config_dict),  # TODO: Currently limited to 5000ms
            **get_ca_concentration(campaign_config_dict, scan_params),
            **get_v_init(sim_config_dicts),
            **get_sim_seed(campaign_config_dict, scan_params),
            **sim_neuron_set_ref,
        },
        "neuron_sets": sim_neuron_set | rec_neuron_sets | spk_neuron_sets,
        "timestamps": stim_timestamps | spk_timestamps,
        "recordings": recordings,
        "stimuli": spk_replays,  # TODO: Generic spike replay stimulus currently not supported
        "synaptic_manipulations": {},
    }
    return obi_one_config


def generate_scan_config(
    sim_campaign: dict,
    campaign_config_dict: dict,
    sim_config_dicts: list,
    scan_params: dict,
    circuit_entity: models.Circuit,
    *,
    validate_config: bool = False,
    save_path: Path | None = None,
) -> (dict, Path | None):
    """Generates an obi-one grid scan scan config dict and .json file."""
    scan_cfg = generate_obi_config(
        sim_campaign,
        campaign_config_dict,
        sim_config_dicts,
        scan_params,
        circuit_entity,
        coordinate_idx=None,
    )
    obi_one_scan = {
        "type": "GridScanGenerationTask",
        "output_root": ".",
        "form": scan_cfg,
        "coordinate_directory_option": "ZERO_INDEX",
    }
    if validate_config:
        obi.deserialize_obi_object_from_json_data(obi_one_scan)
    if save_path:
        obi_one_scan_file = save_path / "obi_one_scan.json"
        with obi_one_scan_file.open("w") as f:
            json.dump(obi_one_scan, f, indent=4)
    else:
        obi_one_scan_file = None
    return obi_one_scan, obi_one_scan_file


def generate_coordinate_configs(
    sim_campaign: dict,
    campaign_config_dict: dict,
    sim_config_dicts: list,
    single_scan_params: list,
    circuit_entity: models.Circuit,
    *,
    validate_config: bool = False,
    save_path: Path | None = None,
) -> (list, list):
    """Generates a list of obi-one single scan config dicts and .json files."""
    obi_one_coords = []
    obi_one_coords_files = []
    for idx, scan_params in enumerate(single_scan_params):
        coord_cfg = generate_obi_config(
            sim_campaign,
            campaign_config_dict,
            sim_config_dicts,
            scan_params,
            circuit_entity,
            coordinate_idx=idx,
        )
        if validate_config:
            obi.deserialize_obi_object_from_json_data(coord_cfg)
        if save_path:
            coords_path = save_path / str(idx)
            coords_path.mkdir(parents=True)
            coords_file = coords_path / "obi_one_coordinate.json"
            with coords_file.open("w") as f:
                json.dump(coord_cfg, f, indent=4)
        else:
            coords_file = None
        obi_one_coords.append(coord_cfg)
        obi_one_coords_files.append(coords_file)
    return obi_one_coords, obi_one_coords_files
