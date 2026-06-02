"""Emodels validations."""

from pathlib import Path


BUILTIN_NEURON_MECHANISMS = [
    "pas",
    "hh",
]

def check_structure(hoc_path: str|Path) -> None:
    """Checks that the hoc file is a valid hoc template.
    
    It must contain `begintemplate` and `endtemplate`.
    """
    with open(hoc_path, "r") as f:
        hoc_content = f.read()
    
    template_name = None
    for line in hoc_content.splitlines():
        line = line.strip()
        splitted_line = line.split()
        if len(splitted_line) == 2 and splitted_line[0] == "begintemplate":
            template_name = splitted_line[1]
            break
    
    assert template_name is not None, f"Could not find 'begintemplate' in {hoc_path}"
    assert f"endtemplate {template_name}" in hoc_content, f"Could not find 'endtemplate {template_name}' in {hoc_path}"


def check_mechanisms(hoc_path:str|Path, expected_suffixes: set[str]) -> None:
    """Checks that the mechanisms declared in the hoc file are the ones we expect."""
    with open(hoc_path, "r") as f:
        hoc_content = f.read()
    
    declared_mechanisms = set()
    for line in hoc_content.splitlines():
        line = line.strip()
        splitted_line = line.split()
        if len(splitted_line) == 2 and splitted_line[0] == "insert":
            mechanism = splitted_line[1]
            declared_mechanisms.add(mechanism)
    
    for suffix in declared_mechanisms:
        assert suffix in expected_suffixes or suffix in BUILTIN_NEURON_MECHANISMS, f"Declared mechanism '{suffix}' in {hoc_path} is not in expected suffixes {expected_suffixes}"

# `v5`` expects template to be initialized with (gid, morph_path), `bluepyopt` expects (morph_dir, morph_fname) and `v6` expects (gid, morph_dir, morph_fname)
# I think we should enforce v6 for consistency, at least for circuit customization, but I should check first if all our hoc files are already v6
# -> maybe will need a discussion with darshan, ilkan, and other scientists
def bluecellulab_initializable(hoc_path: str|Path, morphology_path: str|Path, template_format="v6", holding_current=0.0, threshold_current=0.0) -> None:
    """Checks that the hoc file can be initialized in bluecellulab.
    
    Expects mechanisms to be already compiled.
    """
    # load bluecellulab module inside of function, because loading it outside can bring errors
    # if the mechanisms were not yet compiled when the library is loaded.
    from bluecellulab import Cell
    from bluecellulab.circuit.circuit_access.definition import EmodelProperties


    emodel_properties = EmodelProperties(holding_current=holding_current, threshold_current=threshold_current)  # for v6 compatibility
    _ = Cell(template_path=hoc_path, morphology_path=morphology_path, template_format=template_format, emodel_properties=emodel_properties)  # raises error if not compatible
