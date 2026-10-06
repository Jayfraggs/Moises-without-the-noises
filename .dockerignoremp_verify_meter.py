from backend.audio.meter import TimeSig, BeatGrid, detect_time_signature, build_beat_grid, BeatGridEntry


def make_beat_times(bpm: float, duration_s: float, start_s: float = 0.0):
    beat_interval = 60.0 / bpm
    times = []
    t = start_s
    while t < start_s + duration_s:
        times.append(round(t, 6))
        t += beat_interval
    return times


def make_downbeat_times(beat_times, beats_per_measure):
    return [beat_times[i] for i in range(0, len(beat_times), beats_per_measure)]

# TimeSig basics
assert TimeSig(4, 4).beats_per_measure() == 4
assert TimeSig(3, 4).ticks_per_measure() == 72
assert TimeSig(6, 8).ticks_per_measure() == 144

beat_times = make_beat_times(120.0, 16 * (60.0 / 120.0))
downbeats = make_downbeat_times(beat_times, 4)
assert detect_time_signature(beat_times, downbeats) == (TimeSig(4, 4), False)
assert detect_time_signature(beat_times, []) == (TimeSig(4, 4), True)
assert detect_time_signature(beat_times, [beat_times[0]]) == (TimeSig(4, 4), True)

# build grid checks
grid = build_beat_grid(beat_times, downbeats, TimeSig(4, 4))
assert len(grid.entries) == len(beat_times)
assert grid.entries[0].measure_number == 1
assert grid.entries[3].measure_number == 1
assert grid.entries[4].measure_number == 2
assert grid.entries[0].beat_in_measure == 1
assert grid.entries[1].beat_in_measure == 2
assert grid.entries[3].beat_in_measure == 4
assert grid.entries[0].is_downbeat is True
assert grid.entries[4].is_downbeat is True
assert abs(grid.entries[0].tempo_bpm - 120.0) < 5
assert len(grid.tempo_map) >= 1

# method checks
entry = grid.get_beat_at_time(beat_times[2] + 0.1)
assert entry is not None
assert grid.get_beat_at_time(-1.0).beat_index == 0
assert grid.get_beat_at_time(beat_times[-1] + 10.0).beat_index == len(beat_times) - 1
range_value = grid.get_measure_range(1)
assert range_value is not None
assert range_value[0] == beat_times[0]
assert range_value[1] >= range_value[0]
assert grid.to_dict()["beats"][0] == beat_times[0]
assert "bpm" in grid.to_dict()

# 3/4 detect
beat_times_3 = make_beat_times(120.0, 12 * (60.0 / 120.0))
downbeats_3 = make_downbeat_times(beat_times_3, 3)
assert detect_time_signature(beat_times_3, downbeats_3) == (TimeSig(3, 4), False)

# noisem case
noisy = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5]
for i in range(1, len(noisy)-1, 4):
    noisy[i] += 0.02
assert detect_time_signature(noisy, [0.0, 4.0, 8.0, 12.0]) == (TimeSig(4, 4), False)

print('meter_OK')
