import pytest

from obi_one.scientific.library.map_em_synapses._defaults import sonata_config_for


class TestSonataConfigFor:
    def test_single_neuron_config(self):
        cfg = sonata_config_for(
            fn_edges_out="edges.h5",
            fn_nodes_out="nodes.h5",
            edge_populations={"afferent_synapses": {"type": "chemical"}},
            biophysical_population="biophysical_neuron",
        )

        assert cfg["version"] == pytest.approx(2.3)
        assert len(cfg["networks"]["edges"]) == 1
        assert "afferent_synapses" in cfg["networks"]["edges"][0]["populations"]
        assert len(cfg["networks"]["nodes"]) == 1
        assert "biophysical_neuron" in cfg["networks"]["nodes"][0]["populations"]

    def test_multi_neuron_config_with_virtual(self):
        cfg = sonata_config_for(
            fn_edges_out="edges.h5",
            fn_nodes_out="nodes.h5",
            edge_populations={
                "physical": {"type": "chemical"},
                "virtual_afferents": {"type": "chemical"},
            },
            biophysical_population="bio",
            virtual_population="virt",
        )

        assert len(cfg["networks"]["nodes"]) == 2
        node_pops = cfg["networks"]["nodes"]
        assert "bio" in node_pops[0]["populations"]
        assert "virt" in node_pops[1]["populations"]
        assert node_pops[1]["populations"]["virt"]["type"] == "virtual"

    def test_alternate_morphologies(self):
        cfg = sonata_config_for(
            fn_edges_out="edges.h5",
            fn_nodes_out="nodes.h5",
            edge_populations={},
            biophysical_population="bio",
            alternate_morphologies_h5="spiny.h5",
        )

        bio_props = cfg["networks"]["nodes"][0]["populations"]["bio"]
        assert bio_props["alternate_morphologies"]["h5v1"] == "$BASE_DIR/spiny.h5"

    def test_no_edges(self):
        cfg = sonata_config_for(
            fn_edges_out="edges.h5",
            fn_nodes_out="nodes.h5",
            edge_populations={},
            biophysical_population="bio",
        )

        assert len(cfg["networks"]["edges"]) == 0

    def test_custom_morphologies_dir(self):
        cfg = sonata_config_for(
            fn_edges_out="edges.h5",
            fn_nodes_out="nodes.h5",
            edge_populations={},
            biophysical_population="bio",
            morphologies_dir="custom_morphs",
        )

        bio_props = cfg["networks"]["nodes"][0]["populations"]["bio"]
        assert bio_props["morphologies_dir"] == "$BASE_DIR/custom_morphs"
