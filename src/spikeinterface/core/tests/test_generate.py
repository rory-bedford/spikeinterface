import pytest
import psutil

import numpy as np

from spikeinterface.core import load_extractor, extract_waveforms
from spikeinterface.core.generate import (generate_recording, generate_sorting, NoiseGeneratorRecording, generate_recording_by_size, 
                                          InjectTemplatesRecording, generate_single_fake_waveform, generate_templates,
                                          generate_channel_locations, generate_unit_locations, generate_ground_truth_recording,
                                          )


from spikeinterface.core.core_tools import convert_bytes_to_str

from spikeinterface.core.testing import check_recordings_equal

strategy_list = ["tile_pregenerated", "on_the_fly"]


def test_generate_recording():
    # TODO even this is extenssivly tested in all other function
    pass

def test_generate_sorting():
    # TODO even this is extenssivly tested in all other function
    pass

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


@pytest.mark.parametrize("strategy", strategy_list)
def test_noise_generator_memory(strategy):
    # Test that get_traces does not consume more memory than allocated.

    bytes_to_MiB_factor = 1024**2
    relative_tolerance = 0.05  # relative tolerance of 5 per cent

    sampling_frequency = 30000  # Hz
    durations = [2.0]
    dtype = np.dtype("float32")
    num_channels = 384
    seed = 0

    num_samples = int(durations[0] * sampling_frequency)
    # Around 100 MiB  4 bytes per sample * 384 channels * 30000  samples * 2 seconds duration
    expected_trace_size_MiB = dtype.itemsize * num_channels * num_samples / bytes_to_MiB_factor

    initial_memory_MiB = measure_memory_allocation() / bytes_to_MiB_factor
    lazy_recording = NoiseGeneratorRecording(
        num_channels=num_channels,
        sampling_frequency=sampling_frequency,
        durations=durations,        
        dtype=dtype,
        seed=seed,
        strategy=strategy,
    )

    memory_after_instanciation_MiB = measure_memory_allocation() / bytes_to_MiB_factor
    expected_memory_usage_MiB = initial_memory_MiB
    if strategy == "tile_pregenerated":
        expected_memory_usage_MiB += 50  # 50 MiB for the white noise generator

    ratio = memory_after_instanciation_MiB * 1.0 / expected_memory_usage_MiB
    assertion_msg = (
        f"Memory after instantation is {memory_after_instanciation_MiB} MiB and is {ratio:.2f} times"
        f"the expected memory usage of {expected_memory_usage_MiB} MiB."
    )
    assert ratio <= 1.0 + relative_tolerance, assertion_msg

    traces = lazy_recording.get_traces()
    expected_traces_shape = (int(durations[0] * sampling_frequency), num_channels)

    traces_size_MiB = traces.nbytes / bytes_to_MiB_factor
    assert traces_size_MiB == expected_trace_size_MiB
    assert traces.shape == expected_traces_shape

    memory_after_traces_MiB = measure_memory_allocation() / bytes_to_MiB_factor

    expected_memory_usage_MiB = memory_after_instanciation_MiB + traces_size_MiB
    ratio = memory_after_traces_MiB * 1.0 / expected_memory_usage_MiB
    assertion_msg = (
        f"Memory after loading traces is {memory_after_traces_MiB} MiB and is {ratio:.2f} times"
        f"the expected memory usage of {expected_memory_usage_MiB} MiB."
    )
    assert ratio <= 1.0 + relative_tolerance, assertion_msg


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
        sampling_frequency=30000.,
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
    sampling_frequency = 30000.
    ms_before = 1.
    ms_after = 3.
    wf = generate_single_fake_waveform(ms_before=ms_before, ms_after=ms_after, sampling_frequency=sampling_frequency)

    # import matplotlib.pyplot as plt
    # times = np.arange(wf.size) / sampling_frequency * 1000 - ms_before
    # fig, ax = plt.subplots()
    # ax.plot(times, wf)
    # ax.axvline(0)
    # plt.show()

def test_generate_templates():

    rng = np.random.default_rng(seed=0)

    num_chans = 12
    num_columns = 1
    num_units = 10
    margin_um= 15.
    channel_locations = generate_channel_locations(num_chans, num_columns, 20.)
    unit_locations = generate_unit_locations(num_units, channel_locations, margin_um, rng)

    
    sampling_frequency = 30000.
    ms_before = 1.
    ms_after = 3.
    templates = generate_templates(channel_locations, unit_locations, sampling_frequency, ms_before, ms_after,
            upsample_factor=None,
            seed=42,
            dtype="float32",
        )
    assert templates.ndim == 3
    assert templates.shape[2] == num_chans
    assert templates.shape[0] == num_units


    # templates = generate_templates(channel_locations, unit_locations, sampling_frequency, ms_before, ms_after,
    #         upsample_factor=3,
    #         seed=42,
    #         dtype="float32",
    #     )
    # assert templates.ndim == 4
    # assert templates.shape[2] == num_chans
    # assert templates.shape[0] == num_units
    # assert templates.shape[3] == 3


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
    ms_after = 1.9
    nbefore = int(ms_before * sampling_frequency)
    upsample_factor = 3

    # generate some sutff
    rec_noise = generate_recording(num_channels=num_channels, durations=durations, sampling_frequency=sampling_frequency, mode="lazy", seed=42)
    channel_locations = rec_noise.get_channel_locations()
    sorting = generate_sorting(num_units=num_units, durations=durations, sampling_frequency=sampling_frequency, firing_rates=1., seed=42)
    units_locations = generate_unit_locations(num_units, channel_locations, margin_um=10., seed=42)
    templates_3d = generate_templates(channel_locations, units_locations, sampling_frequency, ms_before, ms_after, seed=42, upsample_factor=None)
    templates_4d = generate_templates(channel_locations, units_locations, sampling_frequency, ms_before, ms_after, seed=42, upsample_factor=upsample_factor)

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
    rec3 = InjectTemplatesRecording(sorting, templates_4d, nbefore=nbefore, parent_recording=rec_noise, upsample_vector=upsample_vector)


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
    # strategy = "tile_pregenerated"
    # strategy = "on_the_fly"
    # test_noise_generator_memory(strategy)
    # test_noise_generator_under_giga()
    # test_noise_generator_correct_shape(strategy)
    # test_noise_generator_consistency_across_calls(strategy, 0, 5)
    # test_noise_generator_consistency_across_traces(strategy, 0, 1000, 10)
    # test_noise_generator_consistency_after_dump(strategy, None)
    # test_generate_recording()
    # test_generate_single_fake_waveform()
    # test_generate_templates()
    # test_inject_templates()
    test_generate_ground_truth_recording()

