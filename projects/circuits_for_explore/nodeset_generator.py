import json

"""
Before running this script, make sure to copy node_sets.json 
to original_node_sets.json so that we don't lose the original
"""

input_nodeset_file = '/Users/pokorny/Data/nbS1-O1-beta/original_node_sets.json'

with open(input_nodeset_file, 'r') as file:
    nodeset_dict = json.load(file)

new_nodeset_dict = nodeset_dict.copy()

prefix = "nbS1"
postfix = "-beta"  # (Optional)

layer_as_str = False  # For backward compatibility (default: True)

all_nodeset_names = []

for layer in [[], [1], [2, 3], [4], [5], [6]]:
    for hex_nodeset_name in ['hex0', 'hex1', 'hex2', 'hex3', 'hex4', 'hex5', 'hex6']:

        hex_nodeset = nodeset_dict[hex_nodeset_name]

        new_hex_nodeset = hex_nodeset.copy()

        new_hex_nodeset['node_id'] = hex_nodeset['node_id']

        nodeset_key = f"{prefix}-{hex_nodeset_name.upper()}{postfix}"

        if len(layer):
            layer_list = []
            layer_str = ''
            for l in layer:
                layer_str += str(l)
                layer_list.append(str(l) if layer_as_str else l)

            new_hex_nodeset['layer'] = layer_list
            # print(new_hex_nodeset['layer'])
            nodeset_key += f"-L{layer_str}"

        all_nodeset_names.append(nodeset_key)
        print(nodeset_key)

        new_nodeset_dict[nodeset_key] = new_hex_nodeset

print(all_nodeset_names)

output_nodeset_file = '/Users/pokorny/Data/nbS1-O1-beta/node_sets.json'
with open(output_nodeset_file, 'w') as file:
    json.dump(new_nodeset_dict, file, indent=4)
