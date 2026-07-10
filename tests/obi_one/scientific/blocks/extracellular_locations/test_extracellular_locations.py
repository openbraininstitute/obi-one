import numpy as np
import pytest
from pydantic import TypeAdapter, ValidationError

import obi_one as obi


def _as_array(locations):
    return np.asarray(locations, dtype=float)


def _npx_local(n_electrodes=96):
    probe = obi.Neuropixels1ExtracellularLocations(n_electrodes=n_electrodes)
    return _as_array(probe.get_local_electrode_xyz_locations())


class TestLinearExtracellularLocations:
    def test_local_locations_along_y_axis(self):
        """Local electrodes lie on the +Y axis, origin-relative and evenly spaced."""
        probe = obi.LinearExtracellularLocations(n_electrodes=5, spacing=20.0)
        local = _as_array(probe.get_local_electrode_xyz_locations())
        assert local.shape == (5, 3)
        assert np.allclose(local[:, 0], 0.0)
        assert np.allclose(local[:, 2], 0.0)
        assert np.allclose(local[0], [0.0, 0.0, 0.0])
        assert np.allclose(local[:, 1], np.arange(5) * 20.0)

    def test_spacing_respected(self):
        probe = obi.LinearExtracellularLocations(n_electrodes=8, spacing=37.5)
        local = _as_array(probe.get_local_electrode_xyz_locations())
        steps = np.linalg.norm(np.diff(local, axis=0), axis=1)
        assert np.allclose(steps, 37.5)

    def test_n_electrodes_count(self):
        probe = obi.LinearExtracellularLocations(n_electrodes=32)
        assert len(probe.get_local_electrode_xyz_locations()) == 32

    def test_local_independent_of_placement(self):
        """Local coordinates depend only on the pattern, not on origin or rotations."""
        default = obi.LinearExtracellularLocations(n_electrodes=6, spacing=10.0)
        moved = obi.LinearExtracellularLocations(
            n_electrodes=6,
            spacing=10.0,
            origin_x=100.0,
            origin_y=-50.0,
            origin_z=5.0,
            rotation_x=10.0,
            rotation_z=30.0,
        )
        assert np.allclose(
            _as_array(default.get_local_electrode_xyz_locations()),
            _as_array(moved.get_local_electrode_xyz_locations()),
        )


class TestNeuropixels1ExtracellularLocations:
    def test_default_electrode_count(self):
        probe = obi.Neuropixels1ExtracellularLocations()
        assert probe.n_electrodes == 384
        assert len(probe.get_local_electrode_xyz_locations()) == 384

    def test_all_sites_unique(self):
        """Every electrode maps to a distinct position (regression: no overlapping sites)."""
        local = _npx_local(n_electrodes=384)
        unique = {tuple(np.round(p, 6)) for p in local}
        assert len(unique) == 384

    def test_imec_geometry(self):
        """imec NP1.0: four columns at 16 um pitch, 32 um within-row, 16 um stagger, 20 um rows."""
        local = _npx_local(n_electrodes=96)
        columns = sorted({round(x, 3) for x in local[:, 0]})
        assert columns == [-24.0, -8.0, 8.0, 24.0]

        within_row = [abs(local[2 * r, 0] - local[2 * r + 1, 0]) for r in range(5)]
        assert np.allclose(within_row, 32.0)

        assert local[2, 1] - local[0, 1] == pytest.approx(20.0)

        row0_min = min(local[0, 0], local[1, 0])
        row1_min = min(local[2, 0], local[3, 0])
        assert abs(row1_min - row0_min) == pytest.approx(16.0)

    def test_centred_on_origin(self):
        """Origin is the centre-top of the shank: local X is symmetric about 0."""
        local = _npx_local(n_electrodes=96)
        assert local[:, 0].mean() == pytest.approx(0.0)
        assert local[:, 0].min() == pytest.approx(-24.0)
        assert local[:, 0].max() == pytest.approx(24.0)

    def test_local_is_planar(self):
        """The local layout lies in the X-Y plane (Z = 0); rotations are applied in world space."""
        assert np.allclose(_npx_local(n_electrodes=96)[:, 2], 0.0)

    def test_default_span(self):
        """384 electrodes span ~3.82 mm (192 rows x 20 um)."""
        local = _npx_local(n_electrodes=384)
        assert local[:, 1].max() - local[:, 1].min() == pytest.approx(3820.0)

    def test_local_independent_of_placement(self):
        """Local layout depends on n_electrodes only, not on origin or rotations."""
        moved = obi.Neuropixels1ExtracellularLocations(
            n_electrodes=64,
            origin_x=10.0,
            origin_y=20.0,
            origin_z=30.0,
            rotation_x=10.0,
            rotation_y=20.0,
            rotation_z=30.0,
        )
        assert np.allclose(
            _npx_local(n_electrodes=64),
            _as_array(moved.get_local_electrode_xyz_locations()),
        )


class TestGridExtracellularLocations:
    def test_default_is_10x10_grid(self):
        """The default is a 10x10 grid of 100 electrodes."""
        array = obi.GridExtracellularLocations()
        assert array.grid_rows == 10
        assert array.grid_columns == 10
        local = _as_array(array.get_local_electrode_xyz_locations())
        assert local.shape == (100, 3)

    def test_grid_offsets(self):
        """Columns run along local X (x_offset) and rows along local Y (y_offset)."""
        array = obi.GridExtracellularLocations(
            grid_rows=4, grid_columns=5, x_offset=300.0, y_offset=500.0
        )
        local = _as_array(array.get_local_electrode_xyz_locations())
        assert local.shape == (20, 3)
        xs = np.unique(np.round(local[:, 0], 6))
        ys = np.unique(np.round(local[:, 1], 6))
        assert len(xs) == 5
        assert len(ys) == 4
        assert np.allclose(np.diff(xs), 300.0)
        assert np.allclose(np.diff(ys), 500.0)
        assert np.allclose(local[:, 2], 0.0)

    def test_grid_lies_in_xy_plane(self):
        """The grid lies in the local X-Y plane (Z = 0) and spans both X and Y."""
        local = _as_array(obi.GridExtracellularLocations().get_local_electrode_xyz_locations())
        assert np.allclose(local[:, 2], 0.0)
        assert np.ptp(local[:, 0]) > 0.0
        assert np.ptp(local[:, 1]) > 0.0

    def test_grid_centred_on_origin(self):
        """The grid is centred on the local origin (symmetric in X and Y)."""
        local = _as_array(obi.GridExtracellularLocations().get_local_electrode_xyz_locations())
        assert local[:, 0].mean() == pytest.approx(0.0)
        assert local[:, 1].mean() == pytest.approx(0.0)

    def test_default_footprint(self):
        """A default 10x10 grid at 400 um offsets spans 3600 um in X and Y."""
        local = _as_array(obi.GridExtracellularLocations().get_local_electrode_xyz_locations())
        assert np.ptp(local[:, 0]) == pytest.approx(3600.0)
        assert np.ptp(local[:, 1]) == pytest.approx(3600.0)

    def test_local_independent_of_placement(self):
        default = obi.GridExtracellularLocations()
        moved = obi.GridExtracellularLocations(
            origin_x=100.0,
            origin_y=-50.0,
            origin_z=5.0,
            rotation_x=10.0,
            rotation_y=20.0,
            rotation_z=30.0,
        )
        assert np.allclose(
            _as_array(default.get_local_electrode_xyz_locations()),
            _as_array(moved.get_local_electrode_xyz_locations()),
        )

    def test_global_transform_preserves_grid_shape(self):
        """A rigid placement leaves the inter-electrode distances unchanged."""
        array = obi.GridExtracellularLocations(
            grid_rows=4,
            grid_columns=4,
            origin_x=1000.0,
            origin_y=2000.0,
            origin_z=-500.0,
            rotation_x=20.0,
            rotation_y=30.0,
            rotation_z=40.0,
        )
        local = _as_array(array.get_local_electrode_xyz_locations())
        world = _as_array(array.get_global_electrode_xyz_locations())
        assert world.shape == local.shape
        for i, j in [(0, 1), (0, 4), (3, 12), (0, 15)]:
            assert np.linalg.norm(world[i] - world[j]) == pytest.approx(
                np.linalg.norm(local[i] - local[j])
            )


class TestUTAHArrayExtracellularLocations:
    def test_fixed_10x10_400um_grid(self):
        """The Utah array is a fixed 10x10 grid at 400 um spacing, flat in the local X-Y plane."""
        array = obi.UTAHArrayExtracellularLocations()
        local = _as_array(array.get_local_electrode_xyz_locations())
        assert local.shape == (100, 3)
        xs = np.unique(np.round(local[:, 0], 6))
        ys = np.unique(np.round(local[:, 1], 6))
        assert len(xs) == 10
        assert len(ys) == 10
        assert np.allclose(np.diff(xs), 400.0)
        assert np.allclose(np.diff(ys), 400.0)
        assert np.ptp(local[:, 0]) == pytest.approx(3600.0)
        assert np.ptp(local[:, 1]) == pytest.approx(3600.0)
        assert np.allclose(local[:, 2], 0.0)

    def test_grid_configuration_is_fixed(self):
        """The grid dimensions and spacing are fixed, not constructor parameters."""
        dumped = obi.UTAHArrayExtracellularLocations().model_dump()
        assert "grid_rows" not in dumped
        assert "x_offset" not in dumped
        with pytest.raises(ValidationError):
            obi.UTAHArrayExtracellularLocations(grid_rows=5)

    def test_placement_inherited_and_applied(self):
        """Origin and rotations are inherited from the base and applied in world space."""
        array = obi.UTAHArrayExtracellularLocations(
            origin_x=1000.0, origin_y=2000.0, origin_z=-500.0, rotation_z=90.0
        )
        assert {"rotation_x", "rotation_y", "rotation_z"} <= set(array.model_dump())
        world = _as_array(array.get_global_electrode_xyz_locations())
        assert world.shape == (100, 3)
        # the centred grid keeps its centroid at the origin under any rotation.
        assert np.allclose(world.mean(axis=0), [1000.0, 2000.0, -500.0])


class TestGlobalTransform:
    def test_default_rotation_is_translation(self):
        """With the default (zero) rotations, global = local + origin."""
        probe = obi.LinearExtracellularLocations(
            n_electrodes=4, spacing=10.0, origin_x=100.0, origin_y=200.0, origin_z=300.0
        )
        local = _as_array(probe.get_local_electrode_xyz_locations())
        world = _as_array(probe.get_global_electrode_xyz_locations())
        assert np.allclose(world, local + np.array([100.0, 200.0, 300.0]))

    def test_origin_applied_once(self):
        """Electrode 0 sits exactly at the origin (origin is not applied twice)."""
        probe = obi.LinearExtracellularLocations(
            n_electrodes=3, spacing=10.0, origin_x=1.0, origin_y=2.0, origin_z=3.0
        )
        world = _as_array(probe.get_global_electrode_xyz_locations())
        assert np.allclose(world[0], [1.0, 2.0, 3.0])

    def test_rotation_orients_the_array(self):
        """rotation_z = 90 turns the +Y linear array onto -X; rotation_x = 90 onto +Z."""
        z90 = obi.LinearExtracellularLocations(n_electrodes=3, spacing=10.0, rotation_z=90.0)
        assert np.allclose(
            _as_array(z90.get_global_electrode_xyz_locations()),
            [[0, 0, 0], [-10, 0, 0], [-20, 0, 0]],
        )
        x90 = obi.LinearExtracellularLocations(n_electrodes=3, spacing=10.0, rotation_x=90.0)
        assert np.allclose(
            _as_array(x90.get_global_electrode_xyz_locations()),
            [[0, 0, 0], [0, 0, 10], [0, 0, 20]],
        )

    def test_rotation_is_rigid(self):
        """A rotation preserves the configured spacing (rigid motion, no inflation)."""
        probe = obi.LinearExtracellularLocations(
            n_electrodes=4, spacing=10.0, rotation_x=30.0, rotation_z=60.0
        )
        world = _as_array(probe.get_global_electrode_xyz_locations())
        steps = np.linalg.norm(np.diff(world, axis=0), axis=1)
        assert np.allclose(steps, 10.0)

    def test_transform_preserves_pairwise_distances(self):
        """Applying origin and rotations is a rigid motion (distances preserved)."""
        probe = obi.Neuropixels1ExtracellularLocations(
            n_electrodes=32,
            origin_x=5.0,
            origin_y=-3.0,
            origin_z=2.0,
            rotation_x=20.0,
            rotation_y=30.0,
            rotation_z=10.0,
        )
        local = _as_array(probe.get_local_electrode_xyz_locations())
        world = _as_array(probe.get_global_electrode_xyz_locations())
        assert np.allclose(
            np.linalg.norm(local - local[0], axis=1),
            np.linalg.norm(world - world[0], axis=1),
        )

    def test_single_values_required(self):
        """get_global_electrode_xyz_locations requires single values, not sweep lists."""
        probe = obi.Neuropixels1ExtracellularLocations(n_electrodes=[8, 16])
        with pytest.raises(TypeError):
            probe.get_global_electrode_xyz_locations()

    def test_identity_for_default_placement(self):
        """Default (zero) rotations with zero origin leave the local layout unchanged."""
        probe = obi.Neuropixels1ExtracellularLocations(n_electrodes=64)
        local = _as_array(probe.get_local_electrode_xyz_locations())
        world = _as_array(probe.get_global_electrode_xyz_locations())
        assert np.allclose(world, local)

    def test_global_count_matches_local(self):
        for probe in (
            obi.LinearExtracellularLocations(n_electrodes=7, spacing=10.0),
            obi.Neuropixels1ExtracellularLocations(n_electrodes=50),
        ):
            n_local = len(probe.get_local_electrode_xyz_locations())
            n_global = len(probe.get_global_electrode_xyz_locations())
            assert n_global == n_local


class TestParameterSweepConstraints:
    def test_n_electrodes_min(self):
        with pytest.raises(ValidationError):
            obi.LinearExtracellularLocations(n_electrodes=0)

    def test_spacing_positive(self):
        with pytest.raises(ValidationError):
            obi.LinearExtracellularLocations(spacing=0.0)

    def test_rotation_range(self):
        """Rotations are bound to [0, 360) degrees."""
        with pytest.raises(ValidationError):
            obi.LinearExtracellularLocations(rotation_x=-1.0)
        with pytest.raises(ValidationError):
            obi.LinearExtracellularLocations(rotation_z=360.0)
        with pytest.raises(ValidationError):
            obi.Neuropixels1ExtracellularLocations(rotation_y=360.0)

    def test_sweep_lists_accepted(self):
        """Constrained and rotation fields accept parameter-sweep lists (regression)."""
        obi.LinearExtracellularLocations(n_electrodes=[8, 16], spacing=[10.0, 20.0])
        obi.Neuropixels1ExtracellularLocations(n_electrodes=[8, 16], rotation_z=[0.0, 90.0])
        obi.GridExtracellularLocations(grid_rows=[8, 10], x_offset=[300.0, 400.0])

    def test_sweep_list_element_constraints_enforced(self):
        with pytest.raises(ValidationError):
            obi.LinearExtracellularLocations(n_electrodes=[8, 0])
        with pytest.raises(ValidationError):
            obi.LinearExtracellularLocations(spacing=[10.0, -1.0])
        with pytest.raises(ValidationError):
            obi.Neuropixels1ExtracellularLocations(rotation_y=[0.0, 400.0])

    def test_grid_dims_min(self):
        with pytest.raises(ValidationError):
            obi.GridExtracellularLocations(grid_rows=0)
        with pytest.raises(ValidationError):
            obi.GridExtracellularLocations(grid_columns=0)

    def test_grid_offset_constraints(self):
        with pytest.raises(ValidationError):
            obi.GridExtracellularLocations(x_offset=0.0)
        with pytest.raises(ValidationError):
            obi.GridExtracellularLocations(y_offset=0.0)


class TestExtracellularLocationsUnion:
    def test_discriminated_parse_neuropixels(self):
        adapter = TypeAdapter(obi.ExtracellularLocationsUnion)
        block = adapter.validate_python(
            {"type": "Neuropixels1ExtracellularLocations", "n_electrodes": 96}
        )
        assert isinstance(block, obi.Neuropixels1ExtracellularLocations)
        assert block.n_electrodes == 96

    def test_discriminated_parse_linear(self):
        adapter = TypeAdapter(obi.ExtracellularLocationsUnion)
        block = adapter.validate_python({"type": "LinearExtracellularLocations", "spacing": 15.0})
        assert isinstance(block, obi.LinearExtracellularLocations)
        assert block.spacing == pytest.approx(15.0)

    def test_discriminated_parse_grid(self):
        adapter = TypeAdapter(obi.ExtracellularLocationsUnion)
        block = adapter.validate_python(
            {"type": "GridExtracellularLocations", "grid_rows": 8, "grid_columns": 8}
        )
        assert isinstance(block, obi.GridExtracellularLocations)
        assert block.grid_rows == 8

    def test_discriminated_parse_utah(self):
        adapter = TypeAdapter(obi.ExtracellularLocationsUnion)
        block = adapter.validate_python({"type": "UTAHArrayExtracellularLocations"})
        assert isinstance(block, obi.UTAHArrayExtracellularLocations)
        assert len(block.get_local_electrode_xyz_locations()) == 100


class TestXYZExtracellularLocations:
    def test_stores_locations(self):
        block = obi.XYZExtracellularLocations(xyz_locations=((1.0, 2.0, 3.0), (4.0, 5.0, 6.0)))
        assert block.xyz_locations == ((1.0, 2.0, 3.0), (4.0, 5.0, 6.0))
