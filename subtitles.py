from dataclasses import dataclass
from datetime import timedelta
from math import ceil, modf
from typing import Iterable, Sequence


__INT_32_MAX_VALUE = 2**31 - 1
MAX_VALID_MP4_DURATION = timedelta(microseconds=__INT_32_MAX_VALUE)


@dataclass(frozen=True, eq=True)
class SubtitlesEntry:
    text: str
    start_time: timedelta
    end_time: timedelta

    def __str__(self) -> str:
        return f'{SubtitlesEntry.__to_srt_format(self.start_time)} --> {SubtitlesEntry.__to_srt_format(self.end_time)}\n{self.text}'

    @staticmethod
    def to_srt(entries: Iterable['SubtitlesEntry']) -> str:
        str_entries = (f'{number}\n{entry}' for number, entry in enumerate(entries, 1))
        return '\n\n'.join(str_entries)

    @staticmethod
    def __to_srt_format(delta: timedelta) -> str:
        hours, remainder1 = divmod(delta.total_seconds(), 3600)
        minutes, remainder2 = divmod(remainder1, 60)
        milliseconds, seconds = modf(remainder2)
        return f'{int(hours):02}:{int(minutes):02}:{int(seconds):02},{f"{milliseconds:.3f}"[2:]}'


def apply_mp4_fixes(
    entries: Sequence[SubtitlesEntry],
    recording_duration: timedelta | None = None,
    gape_placeholder: str = '\xa0',
) -> Sequence[SubtitlesEntry]:
    result = []
    for entry in __fill_gapes(entries, gape_placeholder):
        result.extend(__split_entry(entry))

    if result and recording_duration is not None:
        result[-1] = SubtitlesEntry(
            result[-1].text,
            result[-1].start_time,
            min(result[-1].end_time, recording_duration),
        )

    return result


def __split_entry(entry: SubtitlesEntry) -> Iterable[SubtitlesEntry]:
    duration = entry.end_time - entry.start_time
    if duration <= MAX_VALID_MP4_DURATION:
        yield entry
        return

    parts = ceil(duration / MAX_VALID_MP4_DURATION)
    duration_per_one = duration / parts

    for i in range(parts - 1):
        start_time = entry.start_time + duration_per_one * i
        end_time = start_time + duration_per_one

        yield SubtitlesEntry(entry.text, start_time, end_time)

    start_time = entry.start_time + duration_per_one * (parts - 1)
    yield SubtitlesEntry(entry.text, start_time, entry.end_time)


def __fill_gapes(
    entries: Sequence[SubtitlesEntry], gape_placeholder: str = '\xa0'
) -> Iterable[SubtitlesEntry]:
    if len(entries) < 2:
        return entries

    entries = [SubtitlesEntry(gape_placeholder, timedelta(0), timedelta(0)), *entries]
    for i in range(len(entries) - 1):
        previous_entry = entries[i]
        current_entry = entries[i + 1]

        gape_duration = current_entry.start_time - previous_entry.end_time
        if gape_duration > MAX_VALID_MP4_DURATION:
            yield SubtitlesEntry(
                gape_placeholder, previous_entry.end_time, current_entry.start_time
            )

        yield SubtitlesEntry(
            current_entry.text, current_entry.start_time, current_entry.end_time
        )
