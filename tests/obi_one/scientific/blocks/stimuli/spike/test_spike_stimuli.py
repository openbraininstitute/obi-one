import json

import h5py
import numpy as np
import pytest

import obi_one as obi
from obi_one.scientific.blocks.stimuli.spike.base import SpikeStimulus
from obi_one.scientific.blocks.stimuli.spike.sinusoidal_poisson import (
    _draw_inhomogeneous_poisson_interval_ms,
)
from obi_one.scientific.unions.unions_timestamps import TimestampsReference

from tests.utils import CIRCUIT_DIR

CIRCUIT_PATH = str(CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json")
CIRCUIT_NAME = "N_10__top_nodes_dim6"


def _make_circuit():
    return obi.Circuit(name=CIRCUIT_NAME, path=CIRCUIT_PATH)


def _make_timestamps_ref(block):
    """Create a resolved TimestampsReference for unit testing."""
    ref = TimestampsReference(block_name="test")
    ref.block = block
    return ref


def _read_spike_file(path, population):
    with h5py.File(path, "r") as f:
        grp = f[f"spikes/{population}"]
        node_ids = np.array(grp["node_ids"])
        timestamps = np.array(grp["timestamps"])
        assert grp["timestamps"].attrs["units"] == "ms"
    return node_ids, timestamps


# ---------------------------------------------------------------------------
# Unit tests: generate_spikes_by_gid for each stimulus type
# ---------------------------------------------------------------------------


class TestFullySynchronousSpikeStimulus:
    def test_all_gids_spike_at_all_timestamps(self):
        ts_ref = _make_timestamps_ref(
            obi.RegularTimestamps(start_time=100.0, number_of_repetitions=3, interval=100.0)
        )
        stim = obi.FullySynchronousSpikeStimulus(timestamps=ts_ref)
        gids = [0, 1, 2]
        result = stim.generate_spikes_by_gid(gids)

        expected = [100.0, 200.0, 300.0]
        for gid in gids:
            assert sorted(result[gid]) == expected

    def test_timestamp_offset_applied(self):
        ts_ref = _make_timestamps_ref(
            obi.RegularTimestamps(start_time=0.0, number_of_repetitions=2, interval=1000.0)
        )
        stim = obi.FullySynchronousSpikeStimulus(timestamp_offset=50.0, timestamps=ts_ref)
        gids = [5, 10]
        result = stim.generate_spikes_by_gid(gids)

        expected = [50.0, 1050.0]
        for gid in gids:
            assert result[gid] == expected

    def test_single_gid_single_timestamp(self):
        ts_ref = _make_timestamps_ref(obi.SingleTimestamp(start_time=500.0))
        stim = obi.FullySynchronousSpikeStimulus(timestamps=ts_ref)
        result = stim.generate_spikes_by_gid([42])
        assert result[42] == [500.0]

    def test_empty_gids(self):
        ts_ref = _make_timestamps_ref(
            obi.RegularTimestamps(start_time=100.0, number_of_repetitions=2, interval=100.0)
        )
        stim = obi.FullySynchronousSpikeStimulus(timestamps=ts_ref)
        result = stim.generate_spikes_by_gid([])
        assert len(result) == 0


class TestPoissonSpikeStimulus:
    def test_reproducibility_with_same_seed(self):
        stim = obi.PoissonSpikeStimulus(duration=500.0, frequency=10.0, random_seed=42)
        gids = [0, 1, 2]
        r1 = stim.generate_spikes_by_gid(gids)
        r2 = stim.generate_spikes_by_gid(gids)
        for gid in gids:
            assert r1[gid] == r2[gid]

    def test_different_seeds_give_different_spikes(self):
        gids = [0]
        stim_a = obi.PoissonSpikeStimulus(duration=1000.0, frequency=20.0, random_seed=1)
        stim_b = obi.PoissonSpikeStimulus(duration=1000.0, frequency=20.0, random_seed=2)
        r_a = stim_a.generate_spikes_by_gid(gids)
        r_b = stim_b.generate_spikes_by_gid(gids)
        assert r_a[0] != r_b[0]

    def test_spikes_within_time_window(self):
        ts_ref = _make_timestamps_ref(
            obi.RegularTimestamps(start_time=100.0, number_of_repetitions=2, interval=400.0)
        )
        stim = obi.PoissonSpikeStimulus(
            duration=200.0, frequency=10.0, random_seed=0, timestamps=ts_ref
        )
        gids = list(range(5))
        result = stim.generate_spikes_by_gid(gids)
        for gid in gids:
            for t in result[gid]:
                in_window = (100.0 <= t <= 300.0) or (500.0 <= t <= 700.0)
                assert in_window, f"Spike at {t} outside expected windows"

    def test_timestamp_offset_shifts_window(self):
        stim = obi.PoissonSpikeStimulus(
            duration=100.0, frequency=20.0, random_seed=7, timestamp_offset=50.0
        )
        result = stim.generate_spikes_by_gid([0])
        for t in result[0]:
            assert 50.0 <= t <= 150.0

    def test_zero_duration_produces_no_spikes(self):
        stim = obi.PoissonSpikeStimulus(duration=0.0, frequency=10.0, random_seed=0)
        result = stim.generate_spikes_by_gid([0, 1])
        for gid in [0, 1]:
            assert result[gid] == []

    def test_spike_count_scales_with_frequency(self):
        gids = list(range(3))
        stim_low = obi.PoissonSpikeStimulus(duration=2000.0, frequency=5.0, random_seed=10)
        stim_high = obi.PoissonSpikeStimulus(duration=2000.0, frequency=50.0, random_seed=10)
        r_low = stim_low.generate_spikes_by_gid(gids)
        r_high = stim_high.generate_spikes_by_gid(gids)
        total_low = sum(len(v) for v in r_low.values())
        total_high = sum(len(v) for v in r_high.values())
        assert total_high > total_low

    def test_exceeding_max_spikes_raises(self):
        ts_ref = _make_timestamps_ref(
            obi.RegularTimestamps(start_time=0.0, number_of_repetitions=100, interval=1.0)
        )
        stim = obi.PoissonSpikeStimulus(
            duration=5000.0, frequency=50000.0, random_seed=0, timestamps=ts_ref
        )
        with pytest.raises(obi.OBIONEError, match="maximum allowed"):
            stim.generate_spikes_by_gid(list(range(100)))

    def test_multiple_timestamps_produce_spikes_in_each_window(self):
        ts_ref = _make_timestamps_ref(
            obi.RegularTimestamps(start_time=0.0, number_of_repetitions=3, interval=500.0)
        )
        stim = obi.PoissonSpikeStimulus(
            duration=100.0, frequency=50.0, random_seed=99, timestamps=ts_ref
        )
        gids = [0]
        result = stim.generate_spikes_by_gid(gids)

        windows = [(0.0, 100.0), (500.0, 600.0), (1000.0, 1100.0)]
        for start, end in windows:
            count = sum(1 for t in result[0] if start <= t <= end)
            assert count > 0, f"No spikes in window [{start}, {end}]"


class TestSinusoidalPoissonSpikeStimulus:
    def test_reproducibility(self):
        stim = obi.SinusoidalPoissonSpikeStimulus(
            duration=500.0,
            minimum_rate=1.0,
            maximum_rate=20.0,
            modulation_frequency_hz=5.0,
            random_seed=42,
        )
        gids = [0, 1]
        r1 = stim.generate_spikes_by_gid(gids)
        r2 = stim.generate_spikes_by_gid(gids)
        for gid in gids:
            assert r1[gid] == r2[gid]

    def test_spikes_within_time_window(self):
        ts_ref = _make_timestamps_ref(obi.SingleTimestamp(start_time=100.0))
        stim = obi.SinusoidalPoissonSpikeStimulus(
            duration=300.0,
            minimum_rate=1.0,
            maximum_rate=10.0,
            modulation_frequency_hz=2.0,
            random_seed=5,
            timestamps=ts_ref,
        )
        gids = [0]
        result = stim.generate_spikes_by_gid(gids)
        for t in result[0]:
            assert 100.0 <= t <= 400.0

    def test_max_less_than_min_raises(self):
        with pytest.raises(ValueError, match="Maximum rate must be greater"):
            obi.SinusoidalPoissonSpikeStimulus(minimum_rate=20.0, maximum_rate=5.0)

    def test_phase_offset_changes_spike_pattern(self):
        gids = [0]
        stim_0 = obi.SinusoidalPoissonSpikeStimulus(
            duration=1000.0,
            minimum_rate=0.00001,
            maximum_rate=20.0,
            modulation_frequency_hz=2.0,
            phase_degrees=0.0,
            random_seed=42,
        )
        stim_90 = obi.SinusoidalPoissonSpikeStimulus(
            duration=1000.0,
            minimum_rate=0.00001,
            maximum_rate=20.0,
            modulation_frequency_hz=2.0,
            phase_degrees=90.0,
            random_seed=42,
        )
        r0 = stim_0.generate_spikes_by_gid(gids)
        r90 = stim_90.generate_spikes_by_gid(gids)
        assert r0[0] != r90[0]

    def test_exceeding_max_spikes_raises(self):
        ts_ref = _make_timestamps_ref(
            obi.RegularTimestamps(start_time=0.0, number_of_repetitions=100, interval=1.0)
        )
        stim = obi.SinusoidalPoissonSpikeStimulus(
            duration=5000.0,
            minimum_rate=0.00001,
            maximum_rate=50.0,
            modulation_frequency_hz=1.0,
            random_seed=0,
            timestamps=ts_ref,
        )
        with pytest.raises(ValueError, match="maximum allowed"):
            stim.generate_spikes_by_gid(list(range(1000)))

    def test_lambda_t_ms_peak_and_trough(self):
        # At the peak of the sinusoid, lambda should be close to maximum_rate
        # sin(pi/2) = 1 => lambda = min + (max - min) * (1 + 1)/2 = max
        lam_peak = obi.SinusoidalPoissonSpikeStimulus._lambda_t_ms(
            t_ms=0.0,
            minimum_rate=1.0,
            maximum_rate=10.0,
            mod_freq_hz=1.0,
            phase_rad=np.pi / 2,
        )
        assert lam_peak == pytest.approx(10.0, abs=1e-10)

        # sin(-pi/2) = -1 => lambda = min + (max - min) * (-1 + 1)/2 = min
        lam_trough = obi.SinusoidalPoissonSpikeStimulus._lambda_t_ms(
            t_ms=0.0,
            minimum_rate=1.0,
            maximum_rate=10.0,
            mod_freq_hz=1.0,
            phase_rad=-np.pi / 2,
        )
        assert lam_trough == pytest.approx(1.0, abs=1e-10)

    def test_timestamp_offset_applied(self):
        stim = obi.SinusoidalPoissonSpikeStimulus(
            duration=200.0,
            minimum_rate=1.0,
            maximum_rate=20.0,
            modulation_frequency_hz=5.0,
            random_seed=0,
            timestamp_offset=100.0,
        )
        result = stim.generate_spikes_by_gid([0])
        for t in result[0]:
            assert 100.0 <= t <= 300.0


class TestDrawInhomogeneousPoissonIntervalMs:
    def test_zero_rate_raises(self):
        rng = np.random.default_rng(0)
        with pytest.raises(ValueError, match="Maximum lambda must be positive"):
            _draw_inhomogeneous_poisson_interval_ms(rng, 0.0)

    def test_negative_rate_raises(self):
        rng = np.random.default_rng(0)
        with pytest.raises(ValueError, match="Maximum lambda must be positive"):
            _draw_inhomogeneous_poisson_interval_ms(rng, -5.0)

    def test_returns_positive_value(self):
        rng = np.random.default_rng(42)
        for _ in range(100):
            val = _draw_inhomogeneous_poisson_interval_ms(rng, 10.0)
            assert val > 0.0


# ---------------------------------------------------------------------------
# Integration: write_spike_file
# ---------------------------------------------------------------------------


class TestWriteSpikeFile:
    def test_writes_correct_hdf5_structure(self, tmp_path):
        spikes = {0: [10.0, 20.0], 1: [15.0], 2: [5.0, 25.0, 35.0]}
        spike_file = tmp_path / "test_spikes.h5"
        SpikeStimulus.write_spike_file(spikes, spike_file, "NodeA")

        node_ids, timestamps = _read_spike_file(spike_file, "NodeA")
        assert len(node_ids) == 6
        assert len(timestamps) == 6
        # Timestamps should be sorted
        assert np.all(np.diff(timestamps) >= 0)
        # All expected gids present
        assert set(node_ids) == {0, 1, 2}

    def test_empty_spikes(self, tmp_path):
        spike_file = tmp_path / "empty_spikes.h5"
        SpikeStimulus.write_spike_file({}, spike_file, "NodeA")

        node_ids, timestamps = _read_spike_file(spike_file, "NodeA")
        assert len(node_ids) == 0
        assert len(timestamps) == 0

    def test_creates_parent_directories(self, tmp_path):
        spike_file = tmp_path / "nested" / "dir" / "spikes.h5"
        SpikeStimulus.write_spike_file({0: [1.0]}, spike_file, "pop")
        assert spike_file.exists()


# ---------------------------------------------------------------------------
# Integration: full simulation campaign generation with spike stimuli
# ---------------------------------------------------------------------------


def _build_sim_config_with_all_neuron_sets():
    """Build config with all neuron sets explicitly specified."""
    sim_conf = obi.CircuitSimulationScanConfig.empty_config()
    info = obi.Info(campaign_name="SpikeTest", campaign_description="Spike stimuli test")
    sim_conf.set(info, name="info")

    circuit = _make_circuit()
    sim_duration = 3000.0

    sim_neuron_set = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="AllIDs", elements=range(10)))
    sim_conf.add(sim_neuron_set, name="SimNeurons")

    source_neuron_set = obi.IDNeuronSet(
        neuron_ids=obi.NamedTuple(name="SourceIDs", elements=range(5))
    )
    sim_conf.add(source_neuron_set, name="SourceNeurons")

    regular_timestamps = obi.RegularTimestamps(
        start_time=0.0, number_of_repetitions=2, interval=1000.0
    )
    sim_conf.add(regular_timestamps, name="Timestamps")

    poisson = obi.PoissonSpikeStimulus(
        duration=500.0,
        timestamps=regular_timestamps.ref,
        frequency=10.0,
        random_seed=0,
        source_neuron_set=source_neuron_set.ref,
        targeted_neuron_set=sim_neuron_set.ref,
    )
    sim_conf.add(poisson, name="PoissonStim")

    sync = obi.FullySynchronousSpikeStimulus(
        timestamps=regular_timestamps.ref,
        source_neuron_set=source_neuron_set.ref,
        targeted_neuron_set=sim_neuron_set.ref,
    )
    sim_conf.add(sync, name="SyncStim")

    sinusoidal = obi.SinusoidalPoissonSpikeStimulus(
        duration=500.0,
        timestamps=regular_timestamps.ref,
        minimum_rate=1.0,
        maximum_rate=10.0,
        modulation_frequency_hz=5.0,
        random_seed=7,
        source_neuron_set=source_neuron_set.ref,
        targeted_neuron_set=sim_neuron_set.ref,
    )
    sim_conf.add(sinusoidal, name="SinusoidalStim")

    initialize = obi.CircuitSimulationScanConfig.Initialize(
        circuit=circuit, node_set=sim_neuron_set.ref, simulation_length=sim_duration
    )
    sim_conf.set(initialize, name="initialize")

    return sim_conf


def _check_spike_file_ids_and_bounds(sim_dir, stim_name, pop, expected_source_ids, t_max):
    ids, ts = _read_spike_file(sim_dir / f"{stim_name}_spikes.h5", pop)
    assert len(ids) > 0
    assert set(ids).issubset(expected_source_ids)
    assert np.all(ts >= 0.0)
    assert np.all(ts <= t_max)
    return ids, ts


class TestSimulationCampaignWithAllSpikeTypes:
    def test_generates_and_validates_spike_files(self, tmp_path):
        sim_conf = _build_sim_config_with_all_neuron_sets()
        validated = sim_conf.validated_config()

        scan = obi.GridScanGenerationTask(
            form=validated,
            output_root=tmp_path / "all_types_scan",
            coordinate_directory_option="ZERO_INDEX",
        )
        scan.execute()
        obi.run_tasks_for_generated_scan(scan)

        source_ids = set(range(5))
        for instance in scan.single_configs:
            sim_dir = tmp_path / scan.output_root / str(instance.idx)

            # Verify simulation_config.json was written
            with (sim_dir / "simulation_config.json").open() as f:
                cfg = json.load(f)

            # All three stimuli should be in inputs
            for stim_name in ["PoissonStim", "SyncStim", "SinusoidalStim"]:
                assert stim_name in cfg["inputs"]
                stim_cfg = cfg["inputs"][stim_name]
                assert stim_cfg["module"] == "synapse_replay"
                assert stim_cfg["input_type"] == "spikes"
                assert stim_cfg["delay"] == 0.0  # noqa: RUF069
                assert stim_cfg["duration"] == 3000.0  # noqa: RUF069
                assert stim_cfg["node_set"] == "SimNeurons"

            pop = instance.initialize.circuit.default_population_name

            # Check Poisson and Sinusoidal spike files
            _check_spike_file_ids_and_bounds(sim_dir, "PoissonStim", pop, source_ids, 1500.0)
            _check_spike_file_ids_and_bounds(sim_dir, "SinusoidalStim", pop, source_ids, 1500.0)

            # Check Sync spike file
            sync_ids, sync_ts = _read_spike_file(sim_dir / "SyncStim_spikes.h5", pop)
            assert len(sync_ids) > 0
            assert set(sync_ids).issubset(source_ids)
            assert set(sync_ts) == {0.0, 1000.0}


# ---------------------------------------------------------------------------
# Simulation campaigns with missing neuron sets (default neuron set behaviour)
# ---------------------------------------------------------------------------


def _build_config_no_source_neuron_set():
    """Config where spike stimuli have no source_neuron_set (should default to AllNeurons)."""
    sim_conf = obi.CircuitSimulationScanConfig.empty_config()
    info = obi.Info(campaign_name="NoSource", campaign_description="Test missing source")
    sim_conf.set(info, name="info")

    circuit = _make_circuit()
    sim_duration = 1000.0

    target_set = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="TargetIDs", elements=range(10)))
    sim_conf.add(target_set, name="TargetNeurons")

    regular_timestamps = obi.RegularTimestamps(
        start_time=0.0, number_of_repetitions=1, interval=500.0
    )
    sim_conf.add(regular_timestamps, name="Timestamps")

    poisson = obi.PoissonSpikeStimulus(
        duration=200.0,
        timestamps=regular_timestamps.ref,
        frequency=10.0,
        random_seed=0,
        source_neuron_set=None,
        targeted_neuron_set=target_set.ref,
    )
    sim_conf.add(poisson, name="PoissonNoSource")

    sync = obi.FullySynchronousSpikeStimulus(
        timestamps=regular_timestamps.ref,
        source_neuron_set=None,
        targeted_neuron_set=target_set.ref,
    )
    sim_conf.add(sync, name="SyncNoSource")

    initialize = obi.CircuitSimulationScanConfig.Initialize(
        circuit=circuit, node_set=target_set.ref, simulation_length=sim_duration
    )
    sim_conf.set(initialize, name="initialize")

    return sim_conf


def _build_config_no_target_neuron_set():
    """Config where spike stimuli have no targeted_neuron_set (should default to AllNeurons)."""
    sim_conf = obi.CircuitSimulationScanConfig.empty_config()
    info = obi.Info(campaign_name="NoTarget", campaign_description="Test missing target")
    sim_conf.set(info, name="info")

    circuit = _make_circuit()
    sim_duration = 1000.0

    source_set = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="SourceIDs", elements=range(5)))
    sim_conf.add(source_set, name="SourceNeurons")

    regular_timestamps = obi.RegularTimestamps(
        start_time=0.0, number_of_repetitions=1, interval=500.0
    )
    sim_conf.add(regular_timestamps, name="Timestamps")

    poisson = obi.PoissonSpikeStimulus(
        duration=200.0,
        timestamps=regular_timestamps.ref,
        frequency=10.0,
        random_seed=0,
        source_neuron_set=source_set.ref,
        targeted_neuron_set=None,
    )
    sim_conf.add(poisson, name="PoissonNoTarget")

    initialize = obi.CircuitSimulationScanConfig.Initialize(
        circuit=circuit, simulation_length=sim_duration
    )
    sim_conf.set(initialize, name="initialize")

    return sim_conf


def _build_config_no_neuron_sets_at_all():
    """Config where spike stimuli have neither source nor target neuron sets."""
    sim_conf = obi.CircuitSimulationScanConfig.empty_config()
    info = obi.Info(campaign_name="NoNeuronSets", campaign_description="Test no neuron sets")
    sim_conf.set(info, name="info")

    circuit = _make_circuit()
    sim_duration = 1000.0

    regular_timestamps = obi.RegularTimestamps(
        start_time=0.0, number_of_repetitions=1, interval=500.0
    )
    sim_conf.add(regular_timestamps, name="Timestamps")

    poisson = obi.PoissonSpikeStimulus(
        duration=200.0,
        timestamps=regular_timestamps.ref,
        frequency=10.0,
        random_seed=0,
    )
    sim_conf.add(poisson, name="PoissonDefault")

    sync = obi.FullySynchronousSpikeStimulus(
        timestamps=regular_timestamps.ref,
    )
    sim_conf.add(sync, name="SyncDefault")

    sinusoidal = obi.SinusoidalPoissonSpikeStimulus(
        duration=200.0,
        timestamps=regular_timestamps.ref,
        minimum_rate=1.0,
        maximum_rate=10.0,
        modulation_frequency_hz=5.0,
        random_seed=0,
    )
    sim_conf.add(sinusoidal, name="SinusoidalDefault")

    initialize = obi.CircuitSimulationScanConfig.Initialize(
        circuit=circuit, simulation_length=sim_duration
    )
    sim_conf.set(initialize, name="initialize")

    return sim_conf


def _build_config_no_node_set_on_initialize():
    """Config where initialize.node_set is None (should use default AllNeurons)."""
    sim_conf = obi.CircuitSimulationScanConfig.empty_config()
    info = obi.Info(campaign_name="NoNodeSet", campaign_description="Test missing node_set")
    sim_conf.set(info, name="info")

    circuit = _make_circuit()
    sim_duration = 1000.0

    source_set = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="SourceIDs", elements=range(3)))
    sim_conf.add(source_set, name="SourceNeurons")

    regular_timestamps = obi.RegularTimestamps(
        start_time=0.0, number_of_repetitions=1, interval=500.0
    )
    sim_conf.add(regular_timestamps, name="Timestamps")

    sync = obi.FullySynchronousSpikeStimulus(
        timestamps=regular_timestamps.ref,
        source_neuron_set=source_set.ref,
    )
    sim_conf.add(sync, name="SyncStim")

    # node_set=None should trigger default AllNeurons
    initialize = obi.CircuitSimulationScanConfig.Initialize(
        circuit=circuit, node_set=None, simulation_length=sim_duration
    )
    sim_conf.set(initialize, name="initialize")

    return sim_conf


class TestSimCampaignMissingSourceNeuronSet:
    def test_defaults_to_all_neurons(self, tmp_path):
        sim_conf = _build_config_no_source_neuron_set()
        validated = sim_conf.validated_config()

        scan = obi.GridScanGenerationTask(
            form=validated,
            output_root=tmp_path / "no_source_scan",
            coordinate_directory_option="ZERO_INDEX",
        )
        scan.execute()
        obi.run_tasks_for_generated_scan(scan)

        for instance in scan.single_configs:
            sim_dir = tmp_path / scan.output_root / str(instance.idx)
            pop = instance.initialize.circuit.default_population_name

            # Poisson: source should default to AllNeurons
            poisson_ids, _poisson_ts = _read_spike_file(sim_dir / "PoissonNoSource_spikes.h5", pop)
            assert len(poisson_ids) > 0
            all_ids = set(instance.initialize.circuit.sonata_circuit.nodes[pop].ids())
            assert set(poisson_ids).issubset(all_ids)

            # Sync: source should default to AllNeurons
            sync_ids, _sync_ts = _read_spike_file(sim_dir / "SyncNoSource_spikes.h5", pop)
            assert set(sync_ids) == all_ids

            # Target node_set should be TargetNeurons
            with (sim_dir / "simulation_config.json").open() as f:
                cfg = json.load(f)
            assert cfg["inputs"]["PoissonNoSource"]["node_set"] == "TargetNeurons"
            assert cfg["inputs"]["SyncNoSource"]["node_set"] == "TargetNeurons"


class TestSimCampaignMissingTargetNeuronSet:
    def test_defaults_to_all_neurons(self, tmp_path):
        sim_conf = _build_config_no_target_neuron_set()
        validated = sim_conf.validated_config()

        scan = obi.GridScanGenerationTask(
            form=validated,
            output_root=tmp_path / "no_target_scan",
            coordinate_directory_option="ZERO_INDEX",
        )
        scan.execute()
        obi.run_tasks_for_generated_scan(scan)

        for instance in scan.single_configs:
            sim_dir = tmp_path / scan.output_root / str(instance.idx)
            pop = instance.initialize.circuit.default_population_name

            # Source should use the explicit SourceNeurons
            poisson_ids, _ = _read_spike_file(sim_dir / "PoissonNoTarget_spikes.h5", pop)
            source_ids = set(range(5))
            assert set(poisson_ids).issubset(source_ids)

            # Target should default to "Default: All Biophysical Neurons"
            with (sim_dir / "simulation_config.json").open() as f:
                cfg = json.load(f)
            assert (
                cfg["inputs"]["PoissonNoTarget"]["node_set"] == "Default: All Biophysical Neurons"
            )


class TestSimCampaignNoNeuronSetsAtAll:
    def test_all_defaults_applied(self, tmp_path):
        sim_conf = _build_config_no_neuron_sets_at_all()
        validated = sim_conf.validated_config()

        scan = obi.GridScanGenerationTask(
            form=validated,
            output_root=tmp_path / "no_nsets_scan",
            coordinate_directory_option="ZERO_INDEX",
        )
        scan.execute()
        obi.run_tasks_for_generated_scan(scan)

        default_nset = "Default: All Biophysical Neurons"

        for instance in scan.single_configs:
            sim_dir = tmp_path / scan.output_root / str(instance.idx)
            pop = instance.initialize.circuit.default_population_name

            with (sim_dir / "simulation_config.json").open() as f:
                cfg = json.load(f)

            # All stimuli should use default neuron set as node_set target
            for stim_name in ["PoissonDefault", "SyncDefault", "SinusoidalDefault"]:
                assert cfg["inputs"][stim_name]["node_set"] == default_nset

            # node_set at top level should be default
            assert cfg["node_set"] == default_nset

            # All spike files should exist and contain valid data
            all_ids = set(instance.initialize.circuit.sonata_circuit.nodes[pop].ids())

            for stim_name in ["PoissonDefault", "SyncDefault", "SinusoidalDefault"]:
                spike_file = sim_dir / f"{stim_name}_spikes.h5"
                assert spike_file.exists()
                ids, _ts = _read_spike_file(spike_file, pop)
                assert len(ids) > 0
                assert set(ids).issubset(all_ids)

            # node_sets.json should contain the default neuron set
            with (sim_dir / "node_sets.json").open() as f:
                node_sets = json.load(f)
            assert default_nset in node_sets


class TestSimCampaignMissingInitializeNodeSet:
    def test_defaults_node_set_on_initialize(self, tmp_path):
        sim_conf = _build_config_no_node_set_on_initialize()
        validated = sim_conf.validated_config()

        scan = obi.GridScanGenerationTask(
            form=validated,
            output_root=tmp_path / "no_init_nset",
            coordinate_directory_option="ZERO_INDEX",
        )
        scan.execute()
        obi.run_tasks_for_generated_scan(scan)

        default_nset = "Default: All Biophysical Neurons"

        for instance in scan.single_configs:
            sim_dir = tmp_path / scan.output_root / str(instance.idx)

            with (sim_dir / "simulation_config.json").open() as f:
                cfg = json.load(f)

            # Top-level node_set should be the default
            assert cfg["node_set"] == default_nset

            # Sync target neuron set should also default
            assert cfg["inputs"]["SyncStim"]["node_set"] == default_nset


# ---------------------------------------------------------------------------
# Parameter sweep with spike stimuli
# ---------------------------------------------------------------------------


class TestSpikeStimParameterSweep:
    def test_poisson_frequency_sweep(self, tmp_path):
        sim_conf = obi.CircuitSimulationScanConfig.empty_config()
        info = obi.Info(campaign_name="Sweep", campaign_description="Frequency sweep")
        sim_conf.set(info, name="info")

        circuit = _make_circuit()

        neuron_set = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="IDs", elements=range(10)))
        sim_conf.add(neuron_set, name="Neurons")

        ts = obi.RegularTimestamps(start_time=0.0, number_of_repetitions=1, interval=500.0)
        sim_conf.add(ts, name="Timestamps")

        # Sweep over two frequencies
        poisson = obi.PoissonSpikeStimulus(
            duration=500.0,
            timestamps=ts.ref,
            frequency=[5.0, 50.0],
            random_seed=0,
            source_neuron_set=neuron_set.ref,
            targeted_neuron_set=neuron_set.ref,
        )
        sim_conf.add(poisson, name="PoissonSweep")

        initialize = obi.CircuitSimulationScanConfig.Initialize(
            circuit=circuit, node_set=neuron_set.ref, simulation_length=1000.0
        )
        sim_conf.set(initialize, name="initialize")

        validated = sim_conf.validated_config()

        scan = obi.GridScanGenerationTask(
            form=validated,
            output_root=tmp_path / "freq_sweep",
            coordinate_directory_option="ZERO_INDEX",
        )
        assert len(scan.multiple_value_parameters()) == 1
        assert len(scan.coordinate_parameters()) == 2
        scan.execute()
        obi.run_tasks_for_generated_scan(scan)

        # Compare spike counts between low and high frequency
        pop = circuit.default_population_name
        spike_counts = []
        for instance in scan.single_configs:
            sim_dir = tmp_path / scan.output_root / str(instance.idx)
            ids, _ = _read_spike_file(sim_dir / "PoissonSweep_spikes.h5", pop)
            spike_counts.append(len(ids))

        # Higher frequency should produce more spikes
        assert spike_counts[1] > spike_counts[0]
