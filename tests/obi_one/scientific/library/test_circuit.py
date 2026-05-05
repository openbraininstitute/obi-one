from types import SimpleNamespace

import pytest

from obi_one.scientific.library import circuit as test_module


class _FakePopulation:
    def __init__(self, pop_type: str, node_ids=None, source=None, target=None, name=None):
        self.type = pop_type
        self.name = name
        self._node_ids = node_ids or []
        self.source = source
        self.target = target

    def ids(self):
        return self._node_ids


class _FakeNodes:
    def __init__(self, populations: dict[str, _FakePopulation], node_sets: dict):
        self._pops = populations
        self.population_names = list(populations.keys())
        self.node_sets = SimpleNamespace(content=node_sets)

    def __getitem__(self, key: str) -> _FakePopulation:
        return self._pops[key]


class _FakeEdges:
    def __init__(self, populations: dict[str, _FakePopulation]):
        self._pops = populations
        self.population_names = list(populations.keys())

    def __getitem__(self, key: str) -> _FakePopulation:
        return self._pops[key]


class _FakeSnapCircuit:
    def __init__(self, path: str, *, nodes: _FakeNodes, edges: _FakeEdges):
        self.path = path
        self.nodes = nodes
        self.edges = edges
        self.node_sets = nodes.node_sets


class _FakeConnectivityMatrix:
    def __init__(self, *, is_multigraph: bool, vertices=None):
        self.is_multigraph = is_multigraph
        self.vertices = vertices or {"node_ids": []}
        self._compressed = False

    def compress(self):
        out = _FakeConnectivityMatrix(is_multigraph=False, vertices=self.vertices)
        out._compressed = True
        return out


@pytest.fixture
def fake_snap_circuit(monkeypatch):
    def fake_circuit_factory(path: str):
        nodes = _FakeNodes(
            populations={
                "bio": _FakePopulation("biophysical", node_ids=[1, 2, 3]),
                "virt": _FakePopulation("virtual", node_ids=[9]),
                "point": _FakePopulation("point_neuron", node_ids=[7]),
            },
            node_sets={"All": {}, "Foo": {}},
        )
        edges = _FakeEdges(
            populations={
                "e_bio": _FakePopulation(
                    "edges",
                    source=_FakePopulation("biophysical", name="bio"),
                    target=_FakePopulation("biophysical", name="bio"),
                ),
                "e_point": _FakePopulation(
                    "edges",
                    source=_FakePopulation("point_neuron", name="point"),
                    target=_FakePopulation("biophysical", name="bio"),
                ),
                "e_virt": _FakePopulation(
                    "edges",
                    source=_FakePopulation("virtual", name="virt"),
                    target=_FakePopulation("biophysical", name="bio"),
                ),
            }
        )
        return _FakeSnapCircuit(path, nodes=nodes, edges=edges)

    class _FakeConnectivityMatrixType:
        @staticmethod
        def from_h5(_path):
            return _FakeConnectivityMatrix(is_multigraph=False, vertices={"node_ids": [1, 2, 3]})

    class _FakeNumpyTesting:
        @staticmethod
        def assert_array_equal(a, b):
            if list(a) != list(b):
                msg = "arrays not equal"
                raise AssertionError(msg)

    monkeypatch.setattr(test_module.snap, "Circuit", fake_circuit_factory, raising=True)
    monkeypatch.setattr(
        test_module, "ConnectivityMatrix", _FakeConnectivityMatrixType, raising=True
    )
    monkeypatch.setattr(test_module.np, "testing", _FakeNumpyTesting, raising=True)
    return test_module


def test_str_and_directory(fake_snap_circuit, tmp_path):
    cfg = tmp_path / "circuit_config.json"
    cfg.write_text("{}")
    c = fake_snap_circuit.Circuit(name="c1", path=str(cfg))
    assert str(c) == "c1"
    assert c.directory == tmp_path


def test_sonata_circuit_property(fake_snap_circuit, tmp_path):
    cfg = tmp_path / "circuit_config.json"
    cfg.write_text("{}")
    c = fake_snap_circuit.Circuit(name="c1", path=str(cfg))
    sc = c.sonata_circuit
    assert sc.path == str(cfg)


def test_node_sets(fake_snap_circuit, tmp_path):
    cfg = tmp_path / "circuit_config.json"
    cfg.write_text("{}")
    c = fake_snap_circuit.Circuit(name="c1", path=str(cfg))
    assert set(c.node_sets) == {"All", "Foo"}


def test_get_node_population_names_filters(fake_snap_circuit):
    c = fake_snap_circuit.snap.Circuit("x")
    assert "virt" in fake_snap_circuit.Circuit.get_node_population_names(c)
    assert "virt" not in fake_snap_circuit.Circuit.get_node_population_names(c, incl_virtual=False)
    assert "point" not in fake_snap_circuit.Circuit.get_node_population_names(c, incl_point=False)


def test_default_population_name_cases(fake_snap_circuit, monkeypatch):
    c = fake_snap_circuit.snap.Circuit("x")
    assert fake_snap_circuit.Circuit._default_population_name(c) == "bio"

    def fake_get_node_pop_names(_c, *, incl_virtual=True, incl_point=True):  # noqa: ARG001
        if not incl_point:
            return []
        return []

    monkeypatch.setattr(
        fake_snap_circuit.Circuit,
        "get_node_population_names",
        staticmethod(fake_get_node_pop_names),
    )
    assert fake_snap_circuit.Circuit._default_population_name(c) is None

    def fake_get_node_pop_names2(_c, *, incl_virtual=True, incl_point=True):  # noqa: ARG001
        return ["a", "b"]

    monkeypatch.setattr(
        fake_snap_circuit.Circuit,
        "get_node_population_names",
        staticmethod(fake_get_node_pop_names2),
    )
    with pytest.raises(ValueError, match="Default node population unknown"):
        fake_snap_circuit.Circuit._default_population_name(c)


def test_get_edge_population_names_filters(fake_snap_circuit):
    c = fake_snap_circuit.snap.Circuit("x")
    assert "e_virt" in fake_snap_circuit.Circuit.get_edge_population_names(c)
    assert "e_virt" not in fake_snap_circuit.Circuit.get_edge_population_names(
        c, incl_virtual=False
    )
    assert "e_point" not in fake_snap_circuit.Circuit.get_edge_population_names(c, incl_point=False)


def test_default_edge_population_name_cases(fake_snap_circuit, monkeypatch):
    c = fake_snap_circuit.snap.Circuit("x")
    assert fake_snap_circuit.Circuit._default_edge_population_name(c) == "e_bio"

    def fake_get_edge_pop_names(_c, *, incl_virtual=True, incl_point=True):  # noqa: ARG001
        return []

    monkeypatch.setattr(
        fake_snap_circuit.Circuit,
        "get_edge_population_names",
        staticmethod(fake_get_edge_pop_names),
    )
    assert fake_snap_circuit.Circuit._default_edge_population_name(c) is None

    # Add fake edge populations "a" and "b" both intrinsic to "bio" (default node pop)
    c.edges._pops["a"] = _FakePopulation(
        "edges",
        source=_FakePopulation("biophysical", name="bio"),
        target=_FakePopulation("biophysical", name="bio"),
    )
    c.edges._pops["b"] = _FakePopulation(
        "edges",
        source=_FakePopulation("biophysical", name="bio"),
        target=_FakePopulation("biophysical", name="bio"),
    )

    def fake_get_edge_pop_names2(_c, *, incl_virtual=True, incl_point=True):  # noqa: ARG001
        return ["a", "b"]

    monkeypatch.setattr(
        fake_snap_circuit.Circuit,
        "get_edge_population_names",
        staticmethod(fake_get_edge_pop_names2),
    )
    with pytest.raises(ValueError, match="Default edge population unknown"):
        fake_snap_circuit.Circuit._default_edge_population_name(c)


def test_connectivity_matrix_none_raises(fake_snap_circuit, tmp_path):
    cfg = tmp_path / "circuit_config.json"
    cfg.write_text("{}")
    c = fake_snap_circuit.Circuit(name="c1", path=str(cfg), matrix_path=None)
    with pytest.raises(FileNotFoundError, match="Connectivity matrix has not been found"):
        _ = c.connectivity_matrix


def test_connectivity_matrix_compresses_multigraph(monkeypatch):
    created = {"compressed": False}

    def fake_circuit_factory(path: str):
        nodes = _FakeNodes(
            populations={"bio": _FakePopulation("biophysical", node_ids=[1])},
            node_sets={"All": {}},
        )
        edges = _FakeEdges(populations={})
        return _FakeSnapCircuit(path, nodes=nodes, edges=edges)

    class _FakeConnectivityMatrixType:
        @staticmethod
        def from_h5(_path):
            m = _FakeConnectivityMatrix(is_multigraph=True, vertices={"node_ids": [1]})

            def compress():
                created["compressed"] = True
                return _FakeConnectivityMatrix(is_multigraph=False, vertices=m.vertices)

            m.compress = compress
            return m

    class _FakeNumpyTesting:
        @staticmethod
        def assert_array_equal(a, b):
            if list(a) != list(b):
                msg = "arrays not equal"
                raise AssertionError(msg)

    monkeypatch.setattr(test_module.snap, "Circuit", fake_circuit_factory, raising=True)
    monkeypatch.setattr(
        test_module, "ConnectivityMatrix", _FakeConnectivityMatrixType, raising=True
    )
    monkeypatch.setattr(test_module.np, "testing", _FakeNumpyTesting, raising=True)

    c = test_module.Circuit(name="c1", path="x", matrix_path="m.h5")
    _ = c.connectivity_matrix
    assert created["compressed"] is True


def test_init_validates_connectivity_matrix_node_ids(monkeypatch):
    def fake_circuit_factory(path: str):
        nodes = _FakeNodes(
            populations={"bio": _FakePopulation("biophysical", node_ids=[1, 2])},
            node_sets={"All": {}},
        )
        edges = _FakeEdges(populations={})
        return _FakeSnapCircuit(path, nodes=nodes, edges=edges)

    class _FakeConnectivityMatrixType:
        @staticmethod
        def from_h5(_path):
            return _FakeConnectivityMatrix(is_multigraph=False, vertices={"node_ids": [99]})

    class _FakeNumpyTesting:
        @staticmethod
        def assert_array_equal(a, b):
            if list(a) != list(b):
                msg = "arrays not equal"
                raise AssertionError(msg)

    monkeypatch.setattr(test_module.snap, "Circuit", fake_circuit_factory, raising=True)
    monkeypatch.setattr(
        test_module, "ConnectivityMatrix", _FakeConnectivityMatrixType, raising=True
    )
    monkeypatch.setattr(test_module.np, "testing", _FakeNumpyTesting, raising=True)

    with pytest.raises(AssertionError):
        test_module.Circuit(name="c1", path="x", matrix_path="m.h5")


def test_mechanisms_dir_validations(fake_snap_circuit, tmp_path):
    cfg = tmp_path / "circuit_config.json"
    cfg.write_text("{}")
    c = fake_snap_circuit.Circuit(name="c1", path=str(cfg))

    mod_dir = tmp_path / fake_snap_circuit.CIRCUIT_MOD_DIR
    with pytest.raises(FileNotFoundError):
        _ = c.mechanisms_dir

    mod_dir.write_text("nope")
    with pytest.raises(NotADirectoryError):
        _ = c.mechanisms_dir

    mod_dir.unlink()
    mod_dir.mkdir()
    assert c.mechanisms_dir == mod_dir


def test_mechanisms_dir_for_subclass(fake_snap_circuit, tmp_path):
    class Other(fake_snap_circuit.Circuit):
        type: str = "Circuit"

    cfg = tmp_path / "circuit_config.json"
    cfg.write_text("{}")
    c = Other(name="c1", path=str(cfg))

    mech_dir = tmp_path / "mechanisms"
    mech_dir.mkdir()
    assert c.mechanisms_dir == mech_dir
