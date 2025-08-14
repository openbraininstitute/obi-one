from bluecellulab import Cell
from bluecellulab.circuit.circuit_access import EmodelProperties
from bluecellulab.simulation.neuron_globals import NeuronGlobals
from bluecellulab.tools import calculate_rheobase
import json

def get_threshold_and_holding_current(hoc_file=None, morph_file=None, EM_file=None):
    """
    Retrieve the threshold and holding current from the EModel resource or calculate them if not available.
    :param hoc_file: Path to the HOC file.
    :param morph_file: Path to the morphology file.
    :param EM_file: Path to the EModel JSON file.
    :return: Tuple of threshold current and holding current.
    """

    try:
        # EM_file is set by the script in create_nodes_file.py
        # EM_file = "components/EM__emodel=cADpyr__etype=cADpyr__mtype=L5_TPC_A__species=mouse__brain_region=grey__iteration=1372346__13.json"
        with open(EM_file, "r") as f:
            em_data = json.load(f)
        print("Keys of EModel resource: ", em_data.keys())
    except:
        print("EModel file not found.")
        print("If you don't have the file, the threshold and holding current will be calculated ahead")

    holding_current = None
    threshold_current = None

    try:
        for feat in em_data["features"]:
            if feat["name"] == "SearchHoldingCurrent.soma.v.bpo_holding_current":
                holding_current = feat["value"]

            if feat["name"] == "SearchThresholdCurrent.soma.v.bpo_threshold_current":
                threshold_current = feat["value"]
    except NameError:
        print("EModel not found. Threshold and holding currents are not set")

    if holding_current is None:
        print("No holding current provided, will set it to 0 nA.")
        holding_current = 0

    compute_threshold = False
    if threshold_current is None:
        compute_threshold = True
        threshold_current = 0
        print("Setting threshold_current = 0 nA. The notebook will calculate it ahead.")

    if compute_threshold:
        # These are set by the script in create_nodes_file.py
        # hoc_file = "components/hocs/model.hoc"
        # morph_file = "components/morphologies/C060114A5.asc"

        emodel_properties = EmodelProperties(threshold_current=threshold_current,
                                             holding_current=holding_current,
                                             AIS_scaler=1.0)
        cell = Cell(hoc_file, morph_file, template_format="v6", emodel_properties=emodel_properties)

        print("No threshold current provided, will attempt to compute it.")
        threshold_current = calculate_rheobase(cell)
        print("Threshold current computed:", threshold_current, "nA")

    return threshold_current, holding_current

# threshold_current, holding_current = get_threshold_and_holding_current()

# hoc_file = "components/hocs/model.hoc"
# morph_file= "components/morphologies/C060114A5.asc"

# emodel_properties = EmodelProperties(threshold_current=threshold_current,
#                                      holding_current=holding_current,
#                                      AIS_scaler=1.0)
# cell = Cell(hoc_file, morph_file, template_format="v6", emodel_properties=emodel_properties)