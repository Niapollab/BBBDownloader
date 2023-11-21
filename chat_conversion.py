from aiofiles import open as aopen
from bbb_client import BbbChatEntry, BbbClient
from collections import defaultdict
from datetime import timedelta
from os import path
from subtitles import SubtitlesEntry, apply_mp4_fixes
from typing import Iterable, Sequence


async def build_chat_subtitles(
    client: BbbClient, destination: str, recording_duration: timedelta
) -> str | None:
    CHAT_ENTRY_MAX_DURATION = timedelta(seconds=3)

    chat = await client.get_chat()

    subtitles = to_subtitles(chat, CHAT_ENTRY_MAX_DURATION)
    subtitles = apply_mp4_fixes(subtitles, recording_duration)
    if not subtitles:
        return None

    filename = path.join(destination, 'subtitles.srt')
    content = SubtitlesEntry.to_srt(subtitles)

    async with aopen(filename, 'w', encoding='utf-8') as file:
        await file.write(content)

    return filename


def to_subtitles(
    entries: Iterable[BbbChatEntry], max_duration: timedelta
) -> Sequence[SubtitlesEntry]:
    groups = defaultdict(list)
    for entry in entries:
        groups[entry.timestamp].append(entry)

    values = [*groups.values()]
    if not values:
        return []

    result = []
    for i in range(len(values) - 1):
        current_group = values[i]
        next_group = values[i + 1]

        current_segment_time = current_group[0].timestamp
        next_segment_time = next_group[0].timestamp

        duration = min(max_duration, next_segment_time - current_segment_time)
        result.extend(__split_group(current_group, duration))

    current_group = values[-1]
    current_segment_time = current_group[0].timestamp
    result.extend(__split_group(current_group, max_duration))

    return result


def __split_group(
    group: Sequence[BbbChatEntry], duration: timedelta
) -> Iterable[SubtitlesEntry]:
    size = len(group)
    part = duration / size

    start_time = group[0].timestamp
    current_time = start_time
    for i in range(size - 1):
        current = group[i]
        end_time = current_time + part

        yield SubtitlesEntry(__build_text(current), current_time, end_time)
        current_time = end_time

    current = group[-1]
    yield SubtitlesEntry(__build_text(current), current_time, start_time + duration)


def __build_text(entry: BbbChatEntry) -> str:
    return f'{entry.name}: {entry.message}'
