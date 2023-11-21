from asyncio import create_subprocess_exec
from sys import stdin, stdout, stderr
from typing import TextIO
from tqdm import tqdm


async def build_video(
    output_filename: str,
    webcam_path: str,
    deskshare_path: str | None = None,
    subtitles_path: str | None = None
) -> None:
    input_index = 1
    files = ['-i', webcam_path]
    maps = ['-map', '0:a:0']

    if deskshare_path is not None:
        files.extend(['-i', deskshare_path])
        maps.extend(['-map', f'{input_index}:v:0'])
        input_index += 1
    else:
        maps.extend(['-map', '0:v:0'])

    if subtitles_path is not None:
        files.extend(['-i', subtitles_path])
        maps.extend(['-c:s', 'mov_text', '-map', f'{input_index}:s:0'])
        input_index += 1

    args = ['ffmpeg', '-y', *files, *maps, output_filename]
    await pipe_run(*args)


async def pipe_run(
    program: str,
    *args: str,
    stdin: TextIO = stdin,
    stdout: TextIO = stdout,
    stderr: TextIO = stderr,
) -> None:
    process = await create_subprocess_exec(
        program, *args, stdin=stdin, stdout=stdout, stderr=stderr
    )
    await process.wait()


def progress_bar_factory(size: int, description: str) -> tqdm:
    return tqdm(
        total=size, ascii=' ▖▘▝▗▚▞█', leave=False, desc=description, colour='#b7d121'
    )


async def anone() -> None:
    return None
