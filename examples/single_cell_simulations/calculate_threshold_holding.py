from bluecellulab import Cell
from bluecellulab.circuit.circuit_access import EmodelProperties
from bluecellulab.simulation.neuron_globals import NeuronGlobals
from bluecellulab.tools import calculate_rheobase
import json


EM_file = "components/EM__emodel=cADpyr__etype=cADpyr__mtype=L5_TPC_A__species=mouse__brain_region=grey__iteration=1372346__13.json"
try:
    # EM_file = f"{emodel_folder_path}/EM__emodel=cADpyr__etype=cADpyr__mtype=L5_TPC_A__species=mouse__brain_region=grey__iteration=1372346__13.json"
    with open(EM_file, "r") as f:
        em_data = json.load(f)
    print("Keys of EModel resource: ", em_data.keys())
except:
    print("EModel files not found.")
    print("If you don't have the file, the threshold and holding current will be calculated ahead")

# set the holding current and threshold current as None
holding_current=None
threshold_current=None

try:
    # if em_data exists, use it to get the currents
    for feat in em_data["features"]:
        if feat["name"]=="SearchHoldingCurrent.soma.v.bpo_holding_current":
            holding_current = feat["value"]

        if feat["name"]=="SearchThresholdCurrent.soma.v.bpo_threshold_current":
            threshold_current = feat["value"]
except NameError:
    # if em_data is not defined, print a message
    print("EModel not found. Threshold and holding currents are not set")

print("Holding_current from EModel File:", holding_current)
print("Threshold_current from EModel File:", threshold_current)

if holding_current is None:
    print("No holding current provided, will set it to 0 nA.")
    holding_current = 0
    
# Variable to decide whether to use `calculate_rheobase()` ahead.
compute_threshold = False
if threshold_current is None:
    compute_threshold = True
    # Threshold current is calculated ahead
    # For preliminary initialization of the `Cell` class, set it to 0
    threshold_current = 0
    print("Setting threshold_current = 0 nA. The notebook will calculate it ahead.")

hoc_file = "components/hocs/model.hoc"
morph_file= "components/morphologies/C060114A5.asc"

emodel_properties = EmodelProperties(threshold_current=threshold_current,
                                     holding_current=holding_current,
                                     AIS_scaler=1.0)
cell = Cell(hoc_file, morph_file, template_format="v6", emodel_properties=emodel_properties)

if compute_threshold:
    print("No threshold current provided, will attempt to compute it.")
    threshold_current = calculate_rheobase(cell)
    print("Threshold current computed:", threshold_current, "nA")