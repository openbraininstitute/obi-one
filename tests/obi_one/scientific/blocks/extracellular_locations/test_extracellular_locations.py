import numpy as np
import pytest
from pydantic import TypeAdapter, ValidationError

import obi_one as obi


def _as_array(locations):
    return np.asarray(locations, dtype=float)


def _npx_local(n_electrodes=96, axial_rotation=0.0):
    probe = obi.Neuropixels1ExtracellularLocations(
        n_electrodes=n_electrodes, axial_rotation=axial_rotation
    )
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
        """Local coordinates depend only on the pattern, not on origin or direction."""
        default = obi.LinearExtracellularLocations(n_electrodes=6, spacing=10.0)
        moved = obi.LinearExtracellularLocations(
            n_electrodes=6,
            spacing=10.0,
            origin_x=100.0,
            origin_y=-50.0,
            origin_z=5.0,
            direction_x=1.0,
            direction_y=2.0,
            direction_z=3.0,
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

    def test_default_span(self):
        """384 electrodes span ~3.82 mm (192 rows x 20 um)."""
        local = _npx_local(n_electrodes=384)
        assert local[:, 1].max() - local[:, 1].min() == pytest.approx(3820.0)

    def test_local_independent_of_placement(self):
        """Local layout depends on n_electrodes/axial_rotation only, not origin or direction."""
        moved = obi.Neuropixels1ExtracellularLocations(
            n_electrodes=64,
            origin_x=10.0,
            origin_y=20.0,
            origin_z=30.0,
            direction_x=1.0,
            direction_y=1.0,
            direction_z=1.0,
        )
        assert np.allclose(
            _npx_local(n_electrodes=64),
            _as_array(moved.get_local_electrode_xyz_locations()),
        )


class TestAxialRotation:
    def test_default_rotation_is_planar(self):
        """axial_rotation defaults to 0; the layout lies in the X-Y plane (Z = 0)."""
        probe = obi.Neuropixels1ExtracellularLocations(n_electrodes=96)
        assert probe.axial_rotation == pytest.approx(0.0)
        assert np.allclose(_npx_local(n_electrodes=96)[:, 2], 0.0)

    def test_rotation_is_rigid(self):
        """Rolling preserves each site's distance from the long axis, its y, and the site count."""
        base = _npx_local(n_electrodes=96)
        base_radius = np.hypot(base[:, 0], base[:, 2])
        for angle in (30.0, 90.0, 180.0, 360.0):
            rolled = _npx_local(n_electrodes=96, axial_rotation=angle)
            assert np.allclose(base_radius, np.hypot(rolled[:, 0], rolled[:, 2]))
            assert np.allclose(base[:, 1], rolled[:, 1])
            assert len({tuple(np.round(p, 6)) for p in rolled}) == 96

    def test_rotation_90_moves_width_into_z(self):
        """At 90 degrees the columns stand up along Z, symmetric about the origin."""
        local = _npx_local(n_electrodes=96, axial_rotation=90.0)
        assert np.allclose(local[:, 0], 0.0, atol=1e-9)
        assert local[:, 2].min() == pytest.approx(-24.0)
        assert local[:, 2].max() == pytest.approx(24.0)

    def test_rotation_360_equals_0(self):
        assert np.allclose(_npx_local(48, 0.0), _npx_local(48, 360.0), atol=1e-9)


class TestUtahArrayExtracellularLocations:
    def test_default_is_10x10_grid(self):
        """The classic Utah array is a 10x10 grid of 100 electrodes."""
        array = obi.UtahArrayExtracellularLocations()
        assert array.grid_rows == 10
        assert array.grid_columns == 10
        local = _as_array(array.get_local_electrode_xyz_locations())
        assert local.shape == (100, 3)

    def test_grid_pitch(self):
        """Columns run along local X and rows along local Z, one pitch apart."""
        array = obi.UtahArrayExtracellularLocations(
            grid_rows=4, grid_columns=5, electrode_pitch=400.0
        )
        local = _as_array(array.get_local_electrode_xyz_locations())
        assert local.shape == (20, 3)
        xs = np.unique(np.round(local[:, 0], 6))
        zs = np.unique(np.round(local[:, 2], 6))
        assert len(xs) == 5
        assert len(zs) == 4
        assert np.allclose(np.diff(xs), 400.0)
        assert np.allclose(np.diff(zs), 400.0)

    def test_tips_lie_in_plane_at_shank_length(self):
        """All recording tips share one +Y (the shank length); the grid spans local X and Z."""
        array = obi.UtahArrayExtracellularLocations(shank_length=1500.0)
        local = _as_array(array.get_local_electrode_xyz_locations())
        assert np.allclose(local[:, 1], 1500.0)
        assert np.ptp(local[:, 0]) > 0.0
        assert np.ptp(local[:, 2]) > 0.0

    def test_grid_centred_on_y_axis(self):
        """The tip grid is centred on the local +Y axis (symmetric in X and Z)."""
        local = _as_array(obi.UtahArrayExtracellularLocations().get_local_electrode_xyz_locations())
        assert local[:, 0].mean() == pytest.approx(0.0)
        assert local[:, 2].mean() == pytest.approx(0.0)

    def test_default_footprint(self):
        """A 10x10 grid at 400 um pitch spans 3600 um (the classic 4 mm array) in X and Z."""
        local = _as_array(obi.UtahArrayExtracellularLocations().get_local_electrode_xyz_locations())
        assert np.ptp(local[:, 0]) == pytest.approx(3600.0)
        assert np.ptp(local[:, 2]) == pytest.approx(3600.0)

    def test_local_independent_of_placement(self):
        default = obi.UtahArrayExtracellularLocations()
        moved = obi.UtahArrayExtracellularLocations(
            origin_x=100.0,
            origin_y=-50.0,
            origin_z=5.0,
            direction_x=1.0,
            direction_y=2.0,
            direction_z=3.0,
        )
        assert np.allclose(
            _as_array(default.get_local_electrode_xyz_locations()),
            _as_array(moved.get_local_electrode_xyz_locations()),
        )

    def test_global_transform_preserves_grid_shape(self):
        """A rigid placement leaves the inter-electrode distances unchanged."""
        array = obi.UtahArrayExtracellularLocations(
            grid_rows=4,
            grid_columns=4,
            origin_x=1000.0,
            origin_y=2000.0,
            origin_z=-500.0,
            direction_x=0.3,
            direction_y=1.0,
            direction_z=-0.5,
        )
        local = _as_array(array.get_local_electrode_xyz_locations())
        world = _as_array(array.get_global_electrode_xyz_locations())
        assert world.shape == local.shape
        for i, j in [(0, 1), (0, 4), (3, 12), (0, 15)]:
            assert np.linalg.norm(world[i] - world[j]) == pytest.approx(
                np.linalg.norm(local[i] - local[j])
            )


class TestGlobalTransform:
    def test_default_direction_is_translation(self):
        """With the default (0, 1, 0) direction, global = local + origin."""
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

    def test_direction_is_rigid_rotation(self):
        """A diagonal direction preserves the configured spacing (no sqrt(3) inflation)."""
        probe = obi.LinearExtracellularLocations(
            n_electrodes=4, spacing=10.0, direction_x=1.0, direction_y=1.0, direction_z=1.0
        )
        world = _as_array(probe.get_global_electrode_xyz_locations())
        steps = np.linalg.norm(np.diff(world, axis=0), axis=1)
        assert np.allclose(steps, 10.0)

    def test_direction_orients_along_unit_vector(self):
        """Electrodes advance along the normalised direction from the origin."""
        probe = obi.LinearExtracellularLocations(
            n_electrodes=3, spacing=10.0, direction_x=0.0, direction_y=0.0, direction_z=2.0
        )
        world = _as_array(probe.get_global_electrode_xyz_locations())
        assert np.allclose(world, [[0, 0, 0], [0, 0, 10], [0, 0, 20]])

    def test_transform_preserves_pairwise_distances(self):
        """Applying origin and direction is a rigid motion (distances preserved)."""
        probe = obi.Neuropixels1ExtracellularLocations(
            n_electrodes=32,
            origin_x=5.0,
            origin_y=-3.0,
            origin_z=2.0,
            direction_x=1.0,
            direction_y=2.0,
            direction_z=-1.0,
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

    def test_linear_global_follows_unit_direction(self):
        """Linear electrode i sits at origin + i * spacing * unit(direction), for any direction."""
        direction = np.array([1.0, 2.0, -2.0])
        origin = np.array([7.0, -1.0, 4.0])
        probe = obi.LinearExtracellularLocations(
            n_electrodes=6,
            spacing=15.0,
            origin_x=origin[0],
            origin_y=origin[1],
            origin_z=origin[2],
            direction_x=direction[0],
            direction_y=direction[1],
            direction_z=direction[2],
        )
        world = _as_array(probe.get_global_electrode_xyz_locations())
        unit = direction / np.linalg.norm(direction)
        expected = origin + np.outer(np.arange(6) * 15.0, unit)
        assert np.allclose(world, expected)

    def test_direction_magnitude_invariance(self):
        """Only the direction's orientation matters, not its magnitude."""
        common = {
            "n_electrodes": 8,
            "spacing": 12.0,
            "origin_x": 1.0,
            "origin_y": 2.0,
            "origin_z": 3.0,
        }
        unit_probe = obi.LinearExtracellularLocations(
            direction_x=1.0, direction_y=2.0, direction_z=-2.0, **common
        )
        scaled_probe = obi.LinearExtracellularLocations(
            direction_x=5.0, direction_y=10.0, direction_z=-10.0, **common
        )
        assert np.allclose(
            _as_array(unit_probe.get_global_electrode_xyz_locations()),
            _as_array(scaled_probe.get_global_electrode_xyz_locations()),
        )

    def test_neuropixels_identity_for_default_placement(self):
        """Default direction (0, 1, 0) with zero origin leaves the 2D layout unchanged."""
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


class TestZeroDirectionValidator:
    def test_default_direction_ok(self):
        obi.LinearExtracellularLocations()
        obi.Neuropixels1ExtracellularLocations()

    def test_all_zero_direction_rejected(self):
        with pytest.raises(ValidationError, match="must not all be zero"):
            obi.LinearExtracellularLocations(direction_x=0.0, direction_y=0.0, direction_z=0.0)

    def test_all_zero_direction_rejected_neuropixels(self):
        with pytest.raises(ValidationError, match="must not all be zero"):
            obi.Neuropixels1ExtracellularLocations(direction_x=0, direction_y=0, direction_z=0)

    def test_single_nonzero_component_ok(self):
        probe = obi.LinearExtracellularLocations(direction_x=0.0, direction_y=0.0, direction_z=1.0)
        assert probe.direction_z == pytest.approx(1.0)

    def test_negative_zero_counts_as_zero(self):
        with pytest.raises(ValidationError, match="must not all be zero"):
            obi.LinearExtracellularLocations(direction_x=-0.0, direction_y=0.0, direction_z=-0.0)

    def test_sweep_reaching_zero_vector_rejected(self):
        with pytest.raises(ValidationError, match="must not all be zero"):
            obi.LinearExtracellularLocations(
                direction_x=[0.0, 1.0], direction_y=[0.0], direction_z=[0.0]
            )

    def test_sweep_with_nonzero_component_ok(self):
        probe = obi.LinearExtracellularLocations(
            direction_x=[0.0, 1.0], direction_y=[1.0], direction_z=[0.0, 1.0]
        )
        assert probe.direction_y == [1.0]


class TestParameterSweepConstraints:
    def test_n_electrodes_min(self):
        with pytest.raises(ValidationError):
            obi.LinearExtracellularLocations(n_electrodes=0)

    def test_spacing_positive(self):
        with pytest.raises(ValidationError):
            obi.LinearExtracellularLocations(spacing=0.0)

    def test_axial_rotation_below_range(self):
        with pytest.raises(ValidationError):
            obi.Neuropixels1ExtracellularLocations(axial_rotation=-1.0)

    def test_axial_rotation_above_range(self):
        with pytest.raises(ValidationError):
            obi.Neuropixels1ExtracellularLocations(axial_rotation=361.0)

    def test_sweep_lists_accepted(self):
        """Constrained fields accept parameter-sweep lists (regression)."""
        obi.LinearExtracellularLocations(n_electrodes=[8, 16], spacing=[10.0, 20.0])
        obi.Neuropixels1ExtracellularLocations(n_electrodes=[8, 16], axial_rotation=[0.0, 90.0])
        obi.UtahArrayExtracellularLocations(grid_rows=[8, 10], electrode_pitch=[300.0, 400.0])

    def test_sweep_list_element_constraints_enforced(self):
        with pytest.raises(ValidationError):
            obi.LinearExtracellularLocations(n_electrodes=[8, 0])
        with pytest.raises(ValidationError):
            obi.LinearExtracellularLocations(spacing=[10.0, -1.0])
        with pytest.raises(ValidationError):
            obi.Neuropixels1ExtracellularLocations(axial_rotation=[0.0, 400.0])

    def test_utah_grid_min(self):
        with pytest.raises(ValidationError):
            obi.UtahArrayExtracellularLocations(grid_rows=0)
        with pytest.raises(ValidationError):
            obi.UtahArrayExtracellularLocations(grid_columns=0)

    def test_utah_pitch_and_shank_constraints(self):
        with pytest.raises(ValidationError):
            obi.UtahArrayExtracellularLocations(electrode_pitch=0.0)
        with pytest.raises(ValidationError):
            obi.UtahArrayExtracellularLocations(shank_length=-1.0)


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

    def test_discriminated_parse_utah(self):
        adapter = TypeAdapter(obi.ExtracellularLocationsUnion)
        block = adapter.validate_python(
            {"type": "UtahArrayExtracellularLocations", "grid_rows": 8, "grid_columns": 8}
        )
        assert isinstance(block, obi.UtahArrayExtracellularLocations)
        assert block.grid_rows == 8


class TestXYZExtracellularLocations:
    def test_stores_locations(self):
        block = obi.XYZExtracellularLocations(xyz_locations=((1.0, 2.0, 3.0), (4.0, 5.0, 6.0)))
        assert block.xyz_locations == ((1.0, 2.0, 3.0), (4.0, 5.0, 6.0))
