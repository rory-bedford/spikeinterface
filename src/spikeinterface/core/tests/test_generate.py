import pytest
import psutil

import numpy as np

from spikeinterface.core import load_extractor, extract_waveforms
from spikeinterface.core.generate import (
    generate_recording,
    generate_sorting,
    NoiseGeneratorRecording,
    generate_recording_by_size,
    InjectTemplatesRecording,
    generate_single_fake_waveform,
    generate_templates,
    generate_channel_locations,
    generate_unit_locations,
    generate_ground_truth_recording,
)


from spikeinterface.core.core_tools import convert_bytes_to_str

from spikeinterface.core.testing import check_recordings_equal

strategy_list = ["tile_pregenerated", "on_the_fly"]


def test_generate_recording():
    # TODO even this is extensively tested in all other functions
    pass


def test_generate_sorting():
    # TODO even this is extensively tested in all other functions
    pass


def test_generate_sorting_with_spikes_on_borders():
    num_spikes_on_borders = 10
    border_size_samples = 10
    segment_duration = 10
    for nseg in [1, 2, 3]:
        sorting = generate_sorting(
            durations=[segment_duration] * nseg,
            sampling_frequency=30000,
            num_units=10,
            add_spikes_on_borders=True,
            num_spikes_per_border=num_spikes_on_borders,
            border_size_samples=border_size_samples,
        )
        # check that segments are correctly sorted
        all_spikes = sorting.to_spike_vector()
        np.testing.assert_array_equal(all_spikes["segment_index"], np.sort(all_spikes["segment_index"]))

        spikes = sorting.to_spike_vector(concatenated=False)
        # at least num_border spikes at borders for all segments
        for spikes_in_segment in spikes:
            # check that sample indices are correctly sorted within segments
            np.testing.assert_array_equal(spikes_in_segment["sample_index"], np.sort(spikes_in_segment["sample_index"]))
            num_samples = int(segment_duration * 30000)
            assert np.sum(spikes_in_segment["sample_index"] < border_size_samples) >= num_spikes_on_borders
            assert (
                np.sum(spikes_in_segment["sample_index"] >= num_samples - border_size_samples) >= num_spikes_on_borders
            )


def measure_memory_allocation(measure_in_process: bool = True) -> float:
    """
    A local utility to measure memory allocation at a specific point in time.
    Can measure either the process resident memory or system wide memory available

    Uses psutil package.

    Parameters
    ----------
    measure_in_process : bool, True by default
        Mesure memory allocation in the current process only, if false then measures at the system
        level.
    """

    if measure_in_process:
        process = psutil.Process()
        memory = process.memory_info().rss
    else:
        mem_info = psutil.virtual_memory()
        memory = mem_info.total - mem_info.available

    return memory


def test_noise_generator_memory():
    # Test that get_traces does not consume more memory than allocated.

    bytes_to_MiB_factor = 1024**2
    relative_tolerance = 0.05  # relative tolerance of 5 per cent

    sampling_frequency = 30000  # Hz
    noise_block_size = 60_000
    durations = [20.0]
    dtype = np.dtype("float32")
    num_channels = 384
    seed = 0
    num_samples = int(durations[0] * sampling_frequency)

    # case 1 preallocation of noise use one noise block 88M for 60000 sample of 384
    before_instanciation_MiB = measure_memory_allocation() / bytes_to_MiB_factor
    rec1 = NoiseGeneratorRecording(
        num_channels=num_channels,
        sampling_frequency=sampling_frequency,
        durations=durations,
        dtype=dtype,
        seed=seed,
        strategy="tile_pregenerated",
        noise_block_size=noise_block_size,
    )
    after_instanciation_MiB = measure_memory_allocation() / bytes_to_MiB_factor
    memory_usage_MiB = after_instanciation_MiB - before_instanciation_MiB
    expected_allocation_MiB = dtype.itemsize * num_channels * noise_block_size / bytes_to_MiB_factor
    ratio = expected_allocation_MiB / expected_allocation_MiB
    assert (
        ratio <= 1.0 + relative_tolerance
    ), f"NoiseGeneratorRecording with 'tile_pregenerated' wrong memory {memory_usage_MiB} instead of {expected_allocation_MiB}"

    # case 2: no preallocation very few memory (under 2 MiB)
    before_instanciation_MiB = measure_memory_allocation() / bytes_to_MiB_factor
    rec2 = NoiseGeneratorRecording(
        num_channels=num_channels,
        sampling_frequency=sampling_frequency,
        durations=durations,
        dtype=dtype,
        seed=seed,
        strategy="on_the_fly",
        noise_block_size=noise_block_size,
    )
    after_instanciation_MiB = measure_memory_allocation() / bytes_to_MiB_factor
    memory_usage_MiB = after_instanciation_MiB - before_instanciation_MiB
    assert memory_usage_MiB < 2, f"NoiseGeneratorRecording with 'on_the_fly wrong memory  {memory_usage_MiB}MiB"


def test_noise_generator_under_giga():
    # Test that the recording has the correct size in memory when calling smaller than 1 GiB
    # This is a week test that only measures the size of the traces and not the  memory used
    recording = generate_recording_by_size(full_traces_size_GiB=0.5)
    recording_total_memory = convert_bytes_to_str(recording.get_memory_size())
    assert recording_total_memory == "512.00 MiB"

    recording = generate_recording_by_size(full_traces_size_GiB=0.3)
    recording_total_memory = convert_bytes_to_str(recording.get_memory_size())
    assert recording_total_memory == "307.20 MiB"

    recording = generate_recording_by_size(full_traces_size_GiB=0.1)
    recording_total_memory = convert_bytes_to_str(recording.get_memory_size())
    assert recording_total_memory == "102.40 MiB"


@pytest.mark.parametrize("strategy", strategy_list)
def test_noise_generator_correct_shape(strategy):
    # Test that the recording has the correct size in shape
    sampling_frequency = 30000  # Hz
    durations = [1.0]
    dtype = np.dtype("float32")
    num_channels = 2
    seed = 0

    lazy_recording = NoiseGeneratorRecording(
        num_channels=num_channels,
        sampling_frequency=sampling_frequency,
        durations=durations,
        dtype=dtype,
        seed=seed,
        strategy=strategy,
    )

    num_frames = lazy_recording.get_num_frames(segment_index=0)
    assert num_frames == sampling_frequency * durations[0]

    traces = lazy_recording.get_traces()

    assert traces.shape == (num_frames, num_channels)


@pytest.mark.parametrize("strategy", strategy_list)
@pytest.mark.parametrize(
    "start_frame, end_frame",
    [
        (0, None),
        (0, 80),
        (20_000, 30_000),
        (0, 30_000),
        (15_000, 30_0000),
    ],
)
def test_noise_generator_consistency_across_calls(strategy, start_frame, end_frame):
    # Calling the get_traces twice should return the same result
    sampling_frequency = 30000  # Hz
    durations = [2.0]
    dtype = np.dtype("float32")
    num_channels = 2
    seed = 0

    lazy_recording = NoiseGeneratorRecording(
        num_channels=num_channels,
        sampling_frequency=sampling_frequency,
        durations=durations,
        dtype=dtype,
        seed=seed,
        strategy=strategy,
    )

    traces = lazy_recording.get_traces(start_frame=start_frame, end_frame=end_frame)
    same_traces = lazy_recording.get_traces(start_frame=start_frame, end_frame=end_frame)
    assert np.allclose(traces, same_traces)


@pytest.mark.parametrize("strategy", strategy_list)
@pytest.mark.parametrize(
    "start_frame, end_frame, extra_samples",
    [
        (0, 1000, 10),
        (0, 20_000, 10_000),
        (1_000, 2_000, 300),
        (250, 750, 800),
        (10_000, 25_000, 3_000),
        (0, 60_000, 10_000),
    ],
)
def test_noise_generator_consistency_across_traces(strategy, start_frame, end_frame, extra_samples):
    # Test that the generated traces behave like true arrays. Calling a larger array and then slicing it should
    # give the same result as calling the slice directly
    sampling_frequency = 30000  # Hz
    durations = [10.0]
    dtype = np.dtype("float32")
    num_channels = 2
    seed = start_frame + end_frame + extra_samples  # To make sure that the seed is different for each test

    lazy_recording = NoiseGeneratorRecording(
        num_channels=num_channels,
        sampling_frequency=sampling_frequency,
        durations=durations,
        dtype=dtype,
        seed=seed,
        strategy=strategy,
    )

    traces = lazy_recording.get_traces(start_frame=start_frame, end_frame=end_frame)
    end_frame_larger_array = end_frame + extra_samples
    larger_traces = lazy_recording.get_traces(start_frame=start_frame, end_frame=end_frame_larger_array)
    equivalent_trace_from_larger_traces = larger_traces[:-extra_samples, :]  # Remove the extra samples
    assert np.allclose(traces, equivalent_trace_from_larger_traces)


@pytest.mark.parametrize("strategy", strategy_list)
@pytest.mark.parametrize("seed", [None, 42])
def test_noise_generator_consistency_after_dump(strategy, seed):
    # test same noise after dump even with seed=None
    rec0 = NoiseGeneratorRecording(
        num_channels=2,
        sampling_frequency=30000.0,
        durations=[2.0],
        dtype="float32",
        seed=seed,
        strategy=strategy,
    )
    traces0 = rec0.get_traces()

    rec1 = load_extractor(rec0.to_dict())
    traces1 = rec1.get_traces()

    assert np.allclose(traces0, traces1)


def test_generate_recording():
    # check the high level function
    rec = generate_recording(mode="lazy")
    rec = generate_recording(mode="legacy")


def test_generate_single_fake_waveform():
    sampling_frequency = 30000.0
    ms_before = 1.0
    ms_after = 3.0
    wf = generate_single_fake_waveform(ms_before=ms_before, ms_after=ms_after, sampling_frequency=sampling_frequency)

    # import matplotlib.pyplot as plt
    # times = np.arange(wf.size) / sampling_frequency * 1000 - ms_before
    # fig, ax = plt.subplots()
    # ax.plot(times, wf)
    # ax.axvline(0)
    # plt.show()


def test_generate_templates():
    seed = 0

    num_chans = 12
    num_columns = 1
    num_units = 10
    margin_um = 15.0
    channel_locations = generate_channel_locations(num_chans, num_columns, 20.0)
    unit_locations = generate_unit_locations(num_units, channel_locations, margin_um, seed)

    sampling_frequency = 30000.0
    ms_before = 1.0
    ms_after = 3.0

    # standard case
    templates = generate_templates(
        channel_locations,
        unit_locations,
        sampling_frequency,
        ms_before,
        ms_after,
        upsample_factor=None,
        seed=42,
        dtype="float32",
    )
    assert templates.ndim == 3
    assert templates.shape[2] == num_chans
    assert templates.shape[0] == num_units

    # play with params
    templates = generate_templates(
        channel_locations,
        unit_locations,
        sampling_frequency,
        ms_before,
        ms_after,
        upsample_factor=None,
        seed=42,
        dtype="float32",
        unit_params=dict(alpha=np.ones(num_units) * 8000.0),
        unit_params_range=dict(smooth_ms=(0.04, 0.05)),
    )

    # upsampling case
    templates = generate_templates(
        channel_locations,
        unit_locations,
        sampling_frequency,
        ms_before,
        ms_after,
        upsample_factor=3,
        seed=42,
        dtype="float32",
    )
    assert templates.ndim == 4
    assert templates.shape[2] == num_chans
    assert templates.shape[0] == num_units
    assert templates.shape[3] == 3

    # import matplotlib.pyplot as plt
    # fig, ax = plt.subplots()
    # for u in range(num_units):
    #     ax.plot(templates[u, :, ].T.flatten())
    # for f in range(templates.shape[3]):
    #     ax.plot(templates[0, :, :, f].T.flatten())
    # plt.show()


def test_inject_templates():
    num_channels = 4
    num_units = 3
    durations = [5.0, 2.5]
    sampling_frequency = 20000.0
    ms_before = 0.9
    ms_after = 2.2
    nbefore = int(ms_before * sampling_frequency)
    upsample_factor = 3

    # generate some sutff
    rec_noise = generate_recording(
        num_channels=num_channels, durations=durations, sampling_frequency=sampling_frequency, mode="lazy", seed=42
    )
    channel_locations = rec_noise.get_channel_locations()
    sorting = generate_sorting(
        num_units=num_units, durations=durations, sampling_frequency=sampling_frequency, firing_rates=1.0, seed=42
    )
    units_locations = generate_unit_locations(num_units, channel_locations, margin_um=10.0, seed=42)
    templates_3d = generate_templates(
        channel_locations, units_locations, sampling_frequency, ms_before, ms_after, seed=42, upsample_factor=None
    )
    templates_4d = generate_templates(
        channel_locations,
        units_locations,
        sampling_frequency,
        ms_before,
        ms_after,
        seed=42,
        upsample_factor=upsample_factor,
    )

    # Case 1: parent_recording = None
    rec1 = InjectTemplatesRecording(
        sorting,
        templates_3d,
        nbefore=nbefore,
        num_samples=[rec_noise.get_num_frames(seg_ind) for seg_ind in range(rec_noise.get_num_segments())],
    )

    # Case 2: with parent_recording
    rec2 = InjectTemplatesRecording(sorting, templates_3d, nbefore=nbefore, parent_recording=rec_noise)

    # Case 3: with parent_recording + upsample_factor
    rng = np.random.default_rng(seed=42)
    upsample_vector = rng.integers(0, upsample_factor, size=sorting.to_spike_vector().size)
    rec3 = InjectTemplatesRecording(
        sorting, templates_4d, nbefore=nbefore, parent_recording=rec_noise, upsample_vector=upsample_vector
    )

    for rec in (rec1, rec2, rec3):
        assert rec.get_traces(end_frame=600, segment_index=0).shape == (600, 4)
        assert rec.get_traces(start_frame=100, end_frame=600, segment_index=1).shape == (500, 4)
        assert rec.get_traces(start_frame=rec_noise.get_num_frames(0) - 200, segment_index=0).shape == (200, 4)

        # Check dumpability
        saved_loaded = load_extractor(rec.to_dict())
        check_recordings_equal(rec, saved_loaded, return_scaled=False)


def test_generate_ground_truth_recording():
    rec, sorting = generate_ground_truth_recording(upsample_factor=None)
    assert rec.templates.ndim == 3

    rec, sorting = generate_ground_truth_recording(upsample_factor=2)
    assert rec.templates.ndim == 4


if __name__ == "__main__":
    strategy = "tile_pregenerated"
    # strategy = "on_the_fly"
    # test_noise_generator_memory()
    # test_noise_generator_under_giga()
    # test_noise_generator_correct_shape(strategy)
    # test_noise_generator_consistency_across_calls(strategy, 0, 5)
    # test_noise_generator_consistency_across_traces(strategy, 0, 1000, 10)
    # test_noise_generator_consistency_after_dump(strategy, None)
    # test_generate_recording()
    # test_generate_single_fake_waveform()
    # test_generate_templates()
    # test_inject_templates()
    # test_generate_ground_truth_recording()
    test_generate_sorting_with_spikes_on_borders()
