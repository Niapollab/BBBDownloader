from aiohttp import ClientSession, TCPConnector
from argparse import ArgumentParser
from asyncio import gather, run
from bbb_client import BbbClient
from chat_conversion import build_chat_subtitles
from dataclasses import dataclass
from tempfile import TemporaryDirectory
from utils import anone, build_video, progress_bar_factory


@dataclass(frozen=True, eq=True)
class DownloadArgs:
    url: str
    no_deskshare: bool = False
    no_chat: bool = False
    no_ssl: bool = False
    output: str | None = None


def parse_arguments() -> DownloadArgs:
    parser = ArgumentParser(
        'BBBDownloader',
        description='Python script for downloading meetings recordings from BBB service.'
    )

    parser.add_argument(
        '-d',
        '--no-deskshare',
        action='store_true',
        help='do not append deskshare video to the output file'
    )
    parser.add_argument(
        '-c',
        '--no-chat',
        action='store_true',
        help='do not append chat subtitles to the output file'
    )
    parser.add_argument(
        '-s',
        '--no-ssl',
        action='store_true',
        help='ignore SSL errors when conecting to the server'
    )
    parser.add_argument('-o', '--output', help='override the output filename')
    parser.add_argument('url', nargs=1, help='URL to the meeting')

    args = parser.parse_args()
    return DownloadArgs(
        args.url[0], args.no_deskshare, args.no_chat, args.no_ssl, args.output
    )


async def main(args: DownloadArgs) -> None:
    with TemporaryDirectory() as temp_dir:
        use_ssl = not args.no_ssl
        async with ClientSession(connector=TCPConnector(ssl=use_ssl)) as session:
            async with BbbClient(args.url, session) as client:
                metadata = await client.get_metadata()
                output_filename = (
                    args.output
                    or f'{metadata.subject_name}. {metadata.name} - {metadata.start_time:%d.%m.%y}.mp4'
                )

                webcam = await client.get_webcam()
                if webcam is None:
                    raise ValueError('Unable to download webcam from remote server.')

                deskshare = None if args.no_deskshare else await client.get_deskshare()

                try:
                    webcam_task = webcam.copy_to(
                        temp_dir, lambda x: progress_bar_factory(x, 'webcams')
                    )
                    deskshare_task = (
                        deskshare.copy_to(
                            temp_dir, lambda x: progress_bar_factory(x, 'deskshare')
                        )
                        if deskshare is not None
                        else anone()
                    )
                    subtitles_task = (
                        anone()
                        if args.no_chat
                        else build_chat_subtitles(client, temp_dir, metadata.duration)
                    )

                    parts = await gather(webcam_task, deskshare_task, subtitles_task)
                    await build_video(output_filename, *parts)
                finally:
                    if webcam is not None:
                        webcam.close()

                    if deskshare is not None:
                        deskshare.close()


if __name__ == '__main__':
    args = parse_arguments()
    run(main(args))
