import json

"""
Before running this script, make sure to copy node_sets.json 
to original_node_sets.json so that we don't lose the original
"""

# input_nodeset_file = '/Users/james/Documents/obi/additional_data/O1_data/O1_data/original_node_sets.json'

# with open(input_nodeset_file, 'r') as file:
#     nodeset_dict = json.load(file)

# new_nodeset_dict = nodeset_dict.copy()

# for layer in [[1], [4], [5], [6]]:
#     for hex_nodeset_name in ['hex0', 'hex1']:

#         hex_nodeset = nodeset_dict[hex_nodeset_name]

#         new_hex_nodeset = hex_nodeset.copy()

#         new_hex_nodeset['node_id'] = hex_nodeset['node_id']
#         new_hex_nodeset['layer'] = str(layer[0])

#         print(f"{hex_nodeset_name}_layer{layer[0]}")
#         new_nodeset_dict[f"{hex_nodeset_name}_layer{layer[0]}"] = new_hex_nodeset

# output_nodeset_file = '/Users/james/Documents/obi/additional_data/O1_data/O1_data/node_sets.json'
# with open(output_nodeset_file, 'w') as file:
#     json.dump(new_nodeset_dict, file, indent=4)
