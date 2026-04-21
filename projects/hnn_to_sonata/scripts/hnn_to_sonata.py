"""Convert an hnn_core.Network into a SONATA circuit.

The HNN-core network models (Jones 2009, Law 2021, Kohl 2022 calcium) describe
small cortical columns (L2/3 and L5, pyramidal + basket) with all-to-all
distance-weighted connectivity and procedural cell morphologies.  This module
writes them out in the SONATA circuit format used by the BBP/obi-one tooling:

    <out_dir>/
        circuit_config.json
        node_sets.json
        hnn_neurons/nodes.h5
        hnn_neurons__hnn_neurons__chemical/edges.h5
        cell_templates/<cell_type>.json      (HNN procedural cell spec)
        emodels_hoc/<cell_type>.hoc          (NEURON template rendered from JSON)
        README.md

A single combined node population ("hnn_neurons") holds all four HNN cell
types, distinguished by `mtype`, `etype`, `layer`, `morph_class`, and
`synapse_class`.  A single edge population carries every synaptic contact
between those nodes; receptor type is encoded in `syn_type_id` plus the
HNN-specific string columns `hnn_receptor` / `hnn_loc`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
from voxcell import CellCollection


POPULATION_NAME = "hnn_neurons"
EDGE_POPULATION_NAME = f"{POPULATION_NAME}__{POPULATION_NAME}__chemical"
REGION = "hnn_cortex"
SONATA_VERSION = 2.3

# HNN receptor -> SONATA-ish numeric codes.  Blue-Brain convention groups
# inhibitory receptors in the 100-range; HNN only has ampa/nmda/gabaa/gabab.
RECEPTOR_SYN_TYPE_ID = {
    "ampa": 1,
    "nmda": 2,
    "gabaa": 101,
    "gabab": 102,
}
RECEPTOR_REVERSAL = {"ampa": 0.0, "nmda": 0.0, "gabaa": -80.0, "gabab": -80.0}
RECEPTOR_IS_EXC = {"ampa": True, "nmda": True, "gabaa": False, "gabab": False}

# Coarse SWC-style section type codes for the `afferent_section_type` column.
# -1 flags "loc is a section *group* (proximal/distal)", per HNN semantics.
SECTION_TYPE_CODE = {
    "soma": 1,
    "basal_1": 3, "basal_2": 3, "basal_3": 3,
    "apical_trunk": 4, "apical_1": 4, "apical_2": 4,
    "apical_tuft": 4, "apical_oblique": 4,
}


@dataclass
class CellTypeMeta:
    """Per-HNN-cell-type metadata needed for the SONATA node table."""
    mtype: str
    etype: str
    layer: str
    morph_class: str
    synapse_class: str
    model_template: str


CELL_TYPE_META = {
    "L2_basket": CellTypeMeta(
        mtype="L2_basket", etype="cNAC", layer="2",
        morph_class="INT", synapse_class="INH",
        model_template="hoc:L2_basket",
    ),
    "L2_pyramidal": CellTypeMeta(
        mtype="L2_pyramidal", etype="cADpyr", layer="2",
        morph_class="PYR", synapse_class="EXC",
        model_template="hoc:L2_pyramidal",
    ),
    "L5_basket": CellTypeMeta(
        mtype="L5_basket", etype="cNAC", layer="5",
        morph_class="INT", synapse_class="INH",
        model_template="hoc:L5_basket",
    ),
    "L5_pyramidal": CellTypeMeta(
        mtype="L5_pyramidal", etype="cADpyr", layer="5",
        morph_class="PYR", synapse_class="EXC",
        model_template="hoc:L5_pyramidal",
    ),
}


def _gaussian_weight(distance_um, A, lamtha_um):
    return A * np.exp(-(distance_um ** 2) / (lamtha_um ** 2))


def _expand_loc(loc, cell_obj):
    """HNN `loc` may be a section-group key (proximal/distal) or a section name.

    Returns (canonical_loc_string, list_of_sections).
    """
    if loc in cell_obj.sect_loc:
        return loc, list(cell_obj.sect_loc[loc])
    return loc, [loc]


def build_nodes(net, population_name: str = POPULATION_NAME) -> CellCollection:
    """Build a voxcell.CellCollection from the HNN network."""
    rows = []
    for cell_name, cell_type in net.cell_types.items():
        meta = CELL_TYPE_META[cell_name]
        positions = net.pos_dict[cell_name]
        metadata = cell_type.get("cell_metadata", {})
        measure_dipole = bool(metadata.get("measure_dipole", False))
        for local_idx, pos in enumerate(positions):
            rows.append({
                "x": float(pos[0]),
                "y": float(pos[1]),
                "z": float(pos[2]),
                "mtype": meta.mtype,
                "etype": meta.etype,
                "layer": meta.layer,
                "morph_class": meta.morph_class,
                "synapse_class": meta.synapse_class,
                "model_type": "biophysical",
                "model_template": meta.model_template,
                "morphology": cell_name,
                "region": REGION,
                "hnn_cell_type": cell_name,
                "hnn_local_index": local_idx,
                "hnn_measure_dipole": "true" if measure_dipole else "false",
                "orientation_w": 1.0,
                "orientation_x": 0.0,
                "orientation_y": 0.0,
                "orientation_z": 0.0,
            })

    # Assign SONATA node_ids in HNN GID order (so hnn gid == sonata node_id).
    df_rows = sorted(
        rows,
        key=lambda r: net.gid_ranges[r["hnn_cell_type"]].start + r["hnn_local_index"],
    )
    df = pd.DataFrame(df_rows)
    df.index = pd.RangeIndex(start=1, stop=len(df) + 1, name="node_id")
    cc = CellCollection.from_dataframe(df)
    cc.population_name = population_name
    return cc


def _edges_for_connection(conn, net, inplane_distance: float):
    """Yield per-synapse dicts for one HNN `connectivity` entry."""
    src_type = conn["src_type"]
    tgt_type = conn["target_type"]
    src_cell = net.cell_types[src_type]["cell_object"]
    tgt_cell = net.cell_types[tgt_type]["cell_object"]

    loc_key, target_sections = _expand_loc(conn["loc"], tgt_cell)
    receptor = conn["receptor"]
    nc = conn["nc_dict"]
    A_weight = float(nc["A_weight"])
    A_delay = float(nc["A_delay"])
    lamtha = float(nc["lamtha"])
    gain = float(nc.get("gain", 1.0))
    threshold = float(nc.get("threshold", net.threshold))
    scaled_lamtha = lamtha * inplane_distance

    tau1 = tgt_cell.synapses[receptor]["tau1"]
    tau2 = tgt_cell.synapses[receptor]["tau2"]
    e_rev = tgt_cell.synapses[receptor]["e"]

    src_positions = net.pos_dict[src_type]
    tgt_positions = net.pos_dict[tgt_type]
    src_gid_start = net.gid_ranges[src_type].start
    tgt_gid_start = net.gid_ranges[tgt_type].start

    syn_type_id = RECEPTOR_SYN_TYPE_ID[receptor]
    # Canonical "first" section, used to pick a section_type when loc is a group.
    first_section = target_sections[0]
    section_type_code = SECTION_TYPE_CODE.get(first_section, -1)
    if loc_key in tgt_cell.sect_loc:
        section_type_code = -1  # group placeholder

    for src_gid, tgt_gids in conn["gid_pairs"].items():
        src_idx = src_gid - src_gid_start
        src_pos = src_positions[src_idx]
        for tgt_gid in tgt_gids:
            tgt_idx = tgt_gid - tgt_gid_start
            tgt_pos = tgt_positions[tgt_idx]
            dx = float(tgt_pos[0] - src_pos[0])
            dy = float(tgt_pos[1] - src_pos[1])
            dist = float(np.sqrt(dx * dx + dy * dy))
            gauss = float(np.exp(-(dist ** 2) / (scaled_lamtha ** 2)))
            # Match hnn_core `_calculate_gaussian_weight_delay`.
            weight = A_weight * gauss * gain
            # Delay approaches infinity at gauss->0 (far apart); hnn_core
            # divides A_delay by gauss on-the-fly inside the simulator. We
            # mirror that but clamp to avoid overflow.
            if gauss > 1e-12:
                delay = A_delay / gauss
            else:
                delay = A_delay / 1e-12
            yield {
                "source_node_id": int(src_gid),
                "target_node_id": int(tgt_gid),
                "conductance": float(weight),
                "conductance_scale_factor": 1.0,
                "delay": float(delay),
                "decay_time": float(tau2),
                "rise_time": float(tau1),
                "u_syn": 1.0,
                "depression_time": 0.0,
                "facilitation_time": 0.0,
                "n_rrp_vesicles": 1,
                "spine_length": 0.0,
                "syn_type_id": syn_type_id,
                "afferent_section_type": section_type_code,
                "afferent_section_pos": 0.5,
                "hnn_A_weight": A_weight,
                "hnn_A_delay": A_delay,
                "hnn_lamtha": lamtha,
                "hnn_gain": gain,
                "hnn_threshold": threshold,
                "hnn_receptor": receptor,
                "hnn_loc": loc_key,
                "hnn_target_sections": ",".join(target_sections),
                "hnn_reversal": float(e_rev),
            }


def build_edges_dataframe(net, inplane_distance: float) -> pd.DataFrame:
    edge_rows = []
    for conn in net.connectivity:
        if conn["src_type"] in net.external_drives:
            continue  # skip external-drive connections; they're not intrinsic synapses
        edge_rows.extend(_edges_for_connection(conn, net, inplane_distance))
    return pd.DataFrame(edge_rows)


def _write_source_target_indices(h5_path: str, pop_name: str, n_src: int, n_tgt: int) -> None:
    """Write SONATA-standard indices/{source_to_target,target_to_source} groups."""
    # Keep the import here so the module imports even without brainbuilder on path.
    from brainbuilder.utils.sonata.split_population import _write_indexes
    _write_indexes(h5_path, pop_name, n_src, n_tgt)


def write_edges(edges: pd.DataFrame, out_path: Path, population_name: str,
                source_pop: str, target_pop: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    n_edges = len(edges)
    with h5py.File(out_path, "w") as h5:
        grp_root = h5.create_group(f"edges/{population_name}")
        src = grp_root.create_dataset(
            "source_node_id", data=edges["source_node_id"].to_numpy(dtype="uint64")
        )
        src.attrs["node_population"] = source_pop
        tgt = grp_root.create_dataset(
            "target_node_id", data=edges["target_node_id"].to_numpy(dtype="uint64")
        )
        tgt.attrs["node_population"] = target_pop
        grp_root.create_dataset(
            "edge_type_id", data=-np.ones(n_edges, dtype="int64")
        )
        grp_root.create_dataset(
            "edge_group_id", data=np.zeros(n_edges, dtype="int64")
        )
        grp_root.create_dataset(
            "edge_group_index", data=np.arange(n_edges, dtype="uint64")
        )

        grp0 = grp_root.create_group("0")
        attr_columns = [c for c in edges.columns
                        if c not in ("source_node_id", "target_node_id")]
        for col in attr_columns:
            values = edges[col].values
            if values.dtype == object:
                # string column -> variable-length UTF-8
                grp0.create_dataset(col, data=values.astype("S"),
                                    dtype=h5py.string_dtype(encoding="utf-8"))
            elif np.issubdtype(values.dtype, np.integer):
                grp0.create_dataset(col, data=values.astype("int64"))
            else:
                grp0.create_dataset(col, data=values.astype("float64"))

    # Add indices in a second pass (brainbuilder re-opens the file).
    _write_source_target_indices(str(out_path), population_name,
                                 n_src=int(edges["source_node_id"].nunique()),
                                 n_tgt=int(edges["target_node_id"].nunique()))


def _cell_template_dict(cell_obj, metadata: dict) -> dict:
    """Serialise an hnn_core.Cell into a JSON-friendly dict."""
    sections = {}
    for sec_name, sec in cell_obj.sections.items():
        sections[sec_name] = {
            "L": float(sec.L),
            "diam": float(sec.diam),
            "Ra": float(sec.Ra),
            "cm": float(sec.cm),
            "v0": float(getattr(sec, "v0", -65.0)),
            "syns": list(sec.syns),
            "mechs": {name: {k: float(v) if isinstance(v, (int, float, np.floating)) else v
                             for k, v in params.items()}
                      for name, params in sec.mechs.items()},
            "end_pts": [list(map(float, pt)) for pt in sec.end_pts],
        }
    synapses = {k: {kk: float(vv) for kk, vv in v.items()} for k, v in cell_obj.synapses.items()}
    return {
        "name": cell_obj.name,
        "pos": list(map(float, cell_obj.pos)),
        "sections": sections,
        "synapses": synapses,
        "sect_loc": {k: list(v) for k, v in cell_obj.sect_loc.items()},
        "metadata": dict(metadata),
    }


def write_cell_templates(net, out_dir: Path) -> None:
    templates_dir = out_dir / "cell_templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    for cell_name, cell_type in net.cell_types.items():
        cell_obj = cell_type["cell_object"]
        meta = cell_type.get("cell_metadata", {})
        template = _cell_template_dict(cell_obj, meta)
        (templates_dir / f"{cell_name}.json").write_text(
            json.dumps(template, indent=2, default=str)
        )


def _swc_type_for_section(sec_name: str) -> int:
    if sec_name == "soma":
        return 1
    if sec_name.startswith("basal"):
        return 3
    if sec_name.startswith("apical"):
        return 4
    return 3  # default to basal dendrite


def _cell_to_swc_lines(cell_obj) -> list[str]:
    """Convert an hnn_core Cell into SWC lines.

    Builds one SWC sample per section end-point (two samples per section), with
    parentage following `cell_obj.cell_tree`.  Soma-only cells (baskets) get a
    minimal two-point soma.
    """
    header = [
        "# Auto-generated SWC from hnn_core procedural cell geometry.",
        f"# cell: {cell_obj.name}",
        "# index type x y z radius parent",
    ]

    sections = cell_obj.sections
    tree = cell_obj.cell_tree

    if tree is None:
        # Soma-only cell.
        soma = sections["soma"]
        (x0, y0, z0), (x1, y1, z1) = soma.end_pts
        r = soma.diam / 2.0
        header.append(f"1 1 {x0:.6f} {y0:.6f} {z0:.6f} {r:.6f} -1")
        header.append(f"2 1 {x1:.6f} {y1:.6f} {z1:.6f} {r:.6f} 1")
        return header

    # Full pyramidal: BFS from ('soma', 0).
    node_ids = {}   # (sec, end_idx) -> swc index (1-based)
    parent_of = {}  # swc_index -> parent swc_index (-1 for root)
    coords = {}     # swc_index -> (type_code, x, y, z, radius)
    order = []

    root = ("soma", 0)
    next_id = 1

    def _register(node, parent_swc_id):
        nonlocal next_id
        sec_name, end_idx = node
        sec = sections[sec_name]
        x, y, z = sec.end_pts[end_idx]
        r = sec.diam / 2.0
        swc_id = next_id
        next_id += 1
        node_ids[node] = swc_id
        parent_of[swc_id] = parent_swc_id
        coords[swc_id] = (_swc_type_for_section(sec_name), float(x), float(y), float(z), r)
        order.append(swc_id)

    _register(root, -1)

    # Walk tree breadth-first.
    queue = [root]
    while queue:
        current = queue.pop(0)
        parent_swc = node_ids[current]
        children = tree.get(current, [])
        for child in children:
            if child in node_ids:
                continue
            _register(child, parent_swc)
            queue.append(child)

    for sid in order:
        t, x, y, z, r = coords[sid]
        header.append(f"{sid} {t} {x:.6f} {y:.6f} {z:.6f} {r:.6f} {parent_of[sid]}")
    return header


def write_morphologies(net, out_dir: Path) -> None:
    morph_dir = out_dir / "morphologies" / "swc"
    morph_dir.mkdir(parents=True, exist_ok=True)
    for cell_name, cell_type in net.cell_types.items():
        cell_obj = cell_type["cell_object"]
        lines = _cell_to_swc_lines(cell_obj)
        (morph_dir / f"{cell_name}.swc").write_text("\n".join(lines) + "\n")


def _fmt_num(v) -> str:
    """Compact HOC-friendly number formatting."""
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    return f"{float(v):.10g}"


def _points_close(a, b, atol: float = 1e-6) -> bool:
    return all(abs(float(x) - float(y)) <= atol for x, y in zip(a, b))


def _derive_topology(sections: dict) -> dict:
    """Return {child_section_name: (parent_name, parent_end, child_end)}.

    Parent/child attachment is inferred from shared section end-points: a
    section's start point is matched against every other section's end-points.
    Preference is given to matches against the parent's tip (end_pts[1]) so
    that for a section starting at the origin (e.g. basal_1) we fall through
    to the soma's start (end_pts[0]) only when no tip matches.
    """
    if "soma" not in sections:
        return {}

    result: dict = {}
    names = list(sections.keys())
    for name in names:
        if name == "soma":
            continue
        start = sections[name]["end_pts"][0]
        best = None
        for cand in names:
            if cand == name:
                continue
            cand_end = sections[cand]["end_pts"][1]
            if _points_close(start, cand_end):
                best = (cand, 1, 0)
                break
        if best is None:
            for cand in names:
                if cand == name:
                    continue
                cand_start = sections[cand]["end_pts"][0]
                if _points_close(start, cand_start):
                    best = (cand, 0, 0)
                    break
        if best is None:
            best = ("soma", 1, 0)  # last-resort fallback
        result[name] = best
    return result


def _section_group(name: str) -> str | None:
    if name == "soma":
        return "somatic"
    if name.startswith("apical"):
        return "apical"
    if name.startswith("basal"):
        return "basal"
    return None


def _is_distance_dependent(pval) -> bool:
    """HNN writes distance-dependent params as `[[positions], [values]]`."""
    return (
        isinstance(pval, list)
        and len(pval) == 2
        and isinstance(pval[0], list)
        and isinstance(pval[1], list)
        and len(pval[0]) == len(pval[1])
    )


def _render_cell_hoc(template: dict, hoc_name: str) -> str:
    """Render one JSON cell template into a NEURON HOC template string."""
    sections = template["sections"]
    syn_defs = template.get("synapses", {})
    section_names = list(sections.keys())

    topology = _derive_topology(sections)

    lines: list[str] = []
    lines.append(f"// Auto-generated NEURON template from cell_templates/{hoc_name}.json.")
    lines.append("// Sections, geometry, topology, biophysics, and synapses are resolved")
    lines.append("// from the JSON cell specification produced by scripts/hnn_to_sonata.py.")
    lines.append("")
    lines.append(f"begintemplate {hoc_name}")
    lines.append(f"public {', '.join(section_names)}")
    lines.append("public all, somatic, apical, basal, synlist")
    lines.append("public init")
    lines.append("")
    lines.append("objref all, somatic, apical, basal, synlist, _syn")
    lines.append("")
    lines.append(f"create {', '.join(section_names)}")
    lines.append("")
    lines.append("proc init() {")
    lines.append("    all = new SectionList()")
    lines.append("    somatic = new SectionList()")
    lines.append("    apical = new SectionList()")
    lines.append("    basal = new SectionList()")
    lines.append("    synlist = new List()")
    lines.append("    _geometry()")
    lines.append("    _topology()")
    lines.append("    _biophys()")
    lines.append("    _synapses()")
    lines.append("}")
    lines.append("")

    # --- geometry ----------------------------------------------------------
    lines.append("proc _geometry() {")
    for name in section_names:
        sec = sections[name]
        diam = sec["diam"]
        (x0, y0, z0), (x1, y1, z1) = sec["end_pts"]
        group = _section_group(name)
        lines.append(f"    {name} {{")
        lines.append("        pt3dclear()")
        lines.append(f"        pt3dadd({_fmt_num(x0)}, {_fmt_num(y0)}, {_fmt_num(z0)}, {_fmt_num(diam)})")
        lines.append(f"        pt3dadd({_fmt_num(x1)}, {_fmt_num(y1)}, {_fmt_num(z1)}, {_fmt_num(diam)})")
        lines.append(f"        Ra = {_fmt_num(sec['Ra'])}")
        lines.append(f"        cm = {_fmt_num(sec['cm'])}")
        lines.append("        all.append()")
        if group:
            lines.append(f"        {group}.append()")
        lines.append("    }")
    lines.append("}")
    lines.append("")

    # --- topology ----------------------------------------------------------
    lines.append("proc _topology() {")
    if topology:
        for child in section_names:
            if child not in topology:
                continue
            parent, parent_end, child_end = topology[child]
            lines.append(f"    connect {child}({child_end}), {parent}({parent_end})")
    lines.append("}")
    lines.append("")

    # --- biophysics --------------------------------------------------------
    lines.append("proc _biophys() {")
    for name in section_names:
        sec = sections[name]
        mechs = sec.get("mechs", {})
        if not mechs:
            continue

        scalar_params: list[tuple[str, str, float]] = []
        dd_params: list[tuple[str, str, list, list]] = []
        for mech_name, params in mechs.items():
            for pname, pval in params.items():
                if _is_distance_dependent(pval):
                    dd_params.append((mech_name, pname, pval[0], pval[1]))
                else:
                    scalar_params.append((mech_name, pname, pval))

        required_nseg = max((len(p[2]) for p in dd_params), default=1)

        lines.append(f"    {name} {{")
        if required_nseg > 1:
            lines.append(f"        nseg = {required_nseg}")
        for mech_name in mechs:
            lines.append(f"        insert {mech_name}")
        for _mech, pname, pval in scalar_params:
            lines.append(f"        {pname} = {_fmt_num(pval)}")
        for _mech, pname, positions, values in dd_params:
            for pos, val in zip(positions, values):
                lines.append(f"        {pname}({_fmt_num(pos)}) = {_fmt_num(val)}")
        v0 = sec.get("v0")
        if v0 is not None:
            lines.append(f"        v = {_fmt_num(v0)}")
        lines.append("    }")
    lines.append("}")
    lines.append("")

    # --- synapses ----------------------------------------------------------
    # Each element appended to synlist corresponds to one (section, receptor)
    # pair in the iteration order documented below.
    lines.append("proc _synapses() {")
    lines.append("    // synlist order: (section, receptor)")
    idx = 0
    for name in section_names:
        for receptor in sections[name].get("syns", []):
            syn = syn_defs.get(receptor)
            if syn is None:
                continue
            lines.append(f"    // [{idx}] {name}:{receptor}")
            lines.append(f"    {name} _syn = new Exp2Syn(0.5)")
            lines.append(f"    _syn.tau1 = {_fmt_num(syn['tau1'])}")
            lines.append(f"    _syn.tau2 = {_fmt_num(syn['tau2'])}")
            lines.append(f"    _syn.e = {_fmt_num(syn['e'])}")
            lines.append("    synlist.append(_syn)")
            idx += 1
    lines.append("}")
    lines.append("")
    lines.append(f"endtemplate {hoc_name}")
    return "\n".join(lines) + "\n"


def write_emodel_hoc(out_dir: Path) -> None:
    """Regenerate emodels_hoc/*.hoc from cell_templates/*.json in `out_dir`."""
    templates_dir = out_dir / "cell_templates"
    emodels_dir = out_dir / "emodels_hoc"
    emodels_dir.mkdir(parents=True, exist_ok=True)
    for json_path in sorted(templates_dir.glob("*.json")):
        hoc_name = json_path.stem
        template = json.loads(json_path.read_text())
        hoc_text = _render_cell_hoc(template, hoc_name)
        (emodels_dir / f"{hoc_name}.hoc").write_text(hoc_text)


def write_node_sets(net, out_path: Path) -> None:
    populations = list(net.cell_types.keys())
    pop_all_map = {name: {"mtype": name} for name in populations}
    node_sets = {
        "All": {"population": POPULATION_NAME},
        "Mosaic": ["All"],
        "Excitatory": {"synapse_class": "EXC"},
        "Inhibitory": {"synapse_class": "INH"},
        "Pyramidal": {"morph_class": "PYR"},
        "Basket": {"morph_class": "INT"},
        "Layer2": {"layer": "2"},
        "Layer5": {"layer": "5"},
    }
    node_sets.update(pop_all_map)
    out_path.write_text(json.dumps(node_sets, indent=2))


def write_circuit_config(out_path: Path, population_name: str) -> None:
    config = {
        "manifest": {"$BASE_DIR": "./"},
        "version": SONATA_VERSION,
        "node_sets_file": "$BASE_DIR/node_sets.json",
        "components": {
            "morphologies_dir": "",
            "biophysical_neuron_models_dir": "",
            "point_neuron_models_dir": "",
            "synaptic_models_dir": "",
            "mechanisms_dir": "",
            "templates_dir": "",
        },
        "networks": {
            "nodes": [
                {
                    "nodes_file": f"$BASE_DIR/{population_name}/nodes.h5",
                    "populations": {
                        population_name: {
                            "type": "biophysical",
                            "morphologies_dir": "$BASE_DIR/morphologies/swc",
                            "biophysical_neuron_models_dir": "$BASE_DIR/emodels_hoc",
                            "alternate_morphologies": {},
                        }
                    },
                }
            ],
            "edges": [
                {
                    "edges_file": f"$BASE_DIR/{EDGE_POPULATION_NAME}/edges.h5",
                    "populations": {
                        EDGE_POPULATION_NAME: {"type": "chemical"}
                    },
                }
            ],
        },
    }
    out_path.write_text(json.dumps(config, indent=2))


def write_readme(out_dir: Path, model_name: str, net, n_edges: int) -> None:
    lines = [
        f"# {model_name} (SONATA)",
        "",
        "SONATA export of the HNN-core network model "
        f"`{model_name}`. Node IDs match hnn_core GIDs.",
        "",
        "## Populations",
    ]
    for name, rng in net.gid_ranges.items():
        if name in net.cell_types:
            lines.append(f"- `{name}`: node_ids {rng.start}..{rng.stop - 1} "
                         f"(n={len(rng)})")
    lines += [
        "",
        f"## Edges (intrinsic only): {n_edges}",
        "",
        "Receptor (ampa/nmda/gabaa/gabab) is stored in `hnn_receptor` and "
        "`syn_type_id`.  `conductance` already includes the HNN "
        "`A_weight * exp(-d^2/(lamtha*inplane)^2) * gain` scaling. `delay` is "
        "the on-the-wire per-synapse delay `A_delay / exp(-d^2/(lamtha*inplane)^2)`.",
        "",
        "Procedural cell templates are written to `cell_templates/*.json`. "
        "The matching `emodels_hoc/*.hoc` files are rendered from those JSONs "
        "(geometry via `pt3dadd`, topology from shared section end-points, "
        "biophysics with inserted mechanisms + distance-dependent `gbar` where "
        "present, and per-receptor `Exp2Syn` objects in `synlist`).",
    ]
    (out_dir / "README.md").write_text("\n".join(lines))


def hnn_to_sonata(net, out_dir, model_name: str = "hnn_model"):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    inplane_distance = float(getattr(net, "_inplane_distance", 1.0))

    cc = build_nodes(net)
    nodes_dir = out_dir / POPULATION_NAME
    nodes_dir.mkdir(parents=True, exist_ok=True)
    cc.save_sonata(str(nodes_dir / "nodes.h5"))

    edges = build_edges_dataframe(net, inplane_distance)
    edges_path = out_dir / EDGE_POPULATION_NAME / "edges.h5"
    write_edges(edges, edges_path, EDGE_POPULATION_NAME,
                source_pop=POPULATION_NAME, target_pop=POPULATION_NAME)

    write_node_sets(net, out_dir / "node_sets.json")
    write_circuit_config(out_dir / "circuit_config.json", POPULATION_NAME)
    write_cell_templates(net, out_dir)
    write_morphologies(net, out_dir)
    write_emodel_hoc(out_dir)
    write_readme(out_dir, model_name, net, len(edges))
    n_nodes = int(cc.size()) if callable(getattr(cc, "size", None)) else int(cc.size)
    return {"nodes": n_nodes, "edges": int(len(edges))}


def _regen_hocs(out_root: Path) -> None:
    """Regenerate emodels_hoc/*.hoc from cell_templates/*.json for each circuit."""
    out_root = out_root.resolve()
    circuits = sorted(p.parent for p in out_root.glob("*/cell_templates"))
    if not circuits:
        raise SystemExit(f"No circuit directories found under {out_root}")
    for circuit_dir in circuits:
        write_emodel_hoc(circuit_dir)
        n = len(list((circuit_dir / "emodels_hoc").glob("*.hoc")))
        print(f"[{circuit_dir.name}] regenerated {n} hoc templates")


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-root", default="sonata_circuits",
                        help="Directory in which per-model subfolders are written.")
    parser.add_argument("--model", choices=["jones_2009", "law_2021", "calcium", "all"],
                        default="all")
    parser.add_argument("--mesh", type=int, nargs=2, default=(10, 10),
                        help="(n_pyr_x, n_pyr_y) for the grid of pyramidal cells.")
    parser.add_argument("--regen-hocs", action="store_true",
                        help="Skip full conversion; re-render emodels_hoc/*.hoc from "
                             "existing cell_templates/*.json under --out-root.")
    args = parser.parse_args()

    out_root = Path(args.out_root).resolve()

    if args.regen_hocs:
        _regen_hocs(out_root)
        return

    from hnn_core import jones_2009_model, law_2021_model, calcium_model

    builders = {
        "jones_2009": jones_2009_model,
        "law_2021": law_2021_model,
        "calcium": calcium_model,
    }

    to_build = list(builders) if args.model == "all" else [args.model]
    out_root.mkdir(parents=True, exist_ok=True)

    for name in to_build:
        print(f"[{name}] building hnn_core network...")
        net = builders[name](mesh_shape=tuple(args.mesh))
        out_dir = out_root / name
        stats = hnn_to_sonata(net, out_dir, model_name=name)
        print(f"[{name}] wrote {stats['nodes']} nodes, {stats['edges']} edges "
              f"to {out_dir}")


if __name__ == "__main__":
    main()
