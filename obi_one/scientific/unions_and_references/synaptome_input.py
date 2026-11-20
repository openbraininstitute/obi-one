from obi_one.scientific.from_id.circuit_from_id import MEModelWithSynapsesCircuitFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID

# What Build Synaptome starts from: a bare ME-model, or a synaptome (a single-cell circuit) that has
# synapses. An input without `type` is read as an ME-model, as saved configs from before were.
SynaptomeInput = MEModelFromID | MEModelWithSynapsesCircuitFromID
