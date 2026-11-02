"""Shared column names and defaults for EM synapse mapping."""

# Synapse location columns (micrometers)
C_P_LOCS = ["synapse_x", "synapse_y", "synapse_z"]

# Columns of edge / segment tables
C_SEG_S = ["start_x", "start_y", "start_z"]
C_SEG_S_F = [*C_SEG_S, "start_d"]
C_SEG_E = ["end_x", "end_y", "end_z"]
C_SEG_E_F = [*C_SEG_E, "end_d"]
C_SPINE_MESH = "spine_morphology"
C_SPINE_ID = "spine_id"
C_SP_INDEX = "spine_sharing_id"
C_SHARING_ID = "spine_sharing_id"
C_PSD_ID = "spine_psd_id"
C_ROTATION = ["spine_rotation_x", "spine_rotation_y", "spine_rotation_z", "spine_rotation_w"]
C_TRANSLATION = ["afferent_surface_x", "afferent_surface_y", "afferent_surface_z"]
C_CENTER = ["center_x", "center_y", "center_z"]
C_SURFACE = ["surface_x", "surface_y", "surface_z"]
C_CAVE_ID_IN = "id"
C_CAVE_ID_OUT = "cave_id"

# Columns of morphology dataframes
STR_SEC_ID = "section_id"
STR_SEG_ID = "segment_id"
STR_SEG_OFF = "segment_offset"
STR_SEC_OFF = "section_pos"

# Afferent / efferent prefixes and directed column set
PF_AFF = "afferent_"
PF_EFF = "efferent_"
WITH_DIR = C_CENTER + C_SURFACE + C_P_LOCS + [STR_SEC_ID, STR_SEG_ID, STR_SEG_OFF, STR_SEC_OFF]

# Morphology-with-spines HDF5 group names
GRP_EDGES = "edges"
GRP_MORPH = "morphology"
GRP_SPINES = "spines"
GRP_MESHES = "meshes"
GRP_SKELETONS = "skeletons"
GRP_SOMA = "soma"
GRP_VERTICES = "vertices"
GRP_TRIANGLES = "triangles"
GRP_OFFSETS = "offsets"

# Defaults for spine-related properties of non-spine synapses
V_FALLBACK = "_NONE"
V_DTYPE_DICT = {"float64": 0.0, "float32": 0.0, "int64": -1, "int32": -1}
V_COLNAME_DICT: dict[str, object] = {}

# SONATA edge node id columns
STR_PRE_NODE = "pre_node_id"
STR_POST_NODE = "post_node_id"

# Node property library threshold for string encoding
MAX_COUNT_LIBRARY = 50

DEFAULT_NODE_SPECS = {
    "Portion 65 of the IARPA MICrONS dataset": {
        "synapse_class": {
            "table": "aibs_metamodel_mtypes_v661_v2",
            "column": "classification_system",
            "default": "extrinsic_neuron",
        },
        "mtype": {
            "table": "aibs_metamodel_mtypes_v661_v2",
            "column": "cell_type",
            "default": "extrinsic_neuron",
        },
        "volume": {"table": "aibs_metamodel_mtypes_v661_v2", "column": "volume", "default": -1},
        "status_axon": {
            "table": "proofreading_status_and_strategy",
            "column": "status_axon",
            "default": False,
        },
        "status_dendrite": {
            "table": "proofreading_status_and_strategy",
            "column": "status_dendrite",
            "default": False,
        },
        "layer": {"table": None, "default": "N/A"},
        "etype": {"table": None, "default": "N/A"},
        "__position": {"table": "aibs_metamodel_mtypes_v661_v2", "column": "pt_position"},
    }
}

SYNAPTOME_SONATA_CONFIG = {
    "components": {
        "biophysical_neuron_models_dir": "",
        "mechanisms_dir": "",
        "morphologies_dir": "",
        "point_neuron_models_dir": "",
        "synaptic_models_dir": "",
        "templates_dir": "",
    },
    "networks": {"edges": [], "nodes": []},
    "node_sets_file": "$BASE_DIR/node_sets.json",
    "version": 2.3,
    "manifest": {"$BASE_DIR": "./"},
}
