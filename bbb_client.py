from aiofiles import open as aopen
from aiofiles.threadpool.binary import AsyncBufferedIOBase
from aiohttp import ClientResponse, ClientSession
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, AsyncIterable, Callable, NamedTuple, Sequence, overload
from urllib.parse import urlparse, urljoin
import os.path as path
import re
import xml.etree.ElementTree as ET


@dataclass(frozen=True, eq=True)
class BbbMetadata:
    name: str
    start_time_utc: datetime
    end_time_utc: datetime
    participants: int
    subject_name: str
    subject_code: str
    duration: timedelta
    size: int
    playback_url: str

    @property
    def start_time(self) -> datetime:
        return self.start_time_utc.astimezone()

    @property
    def end_time(self) -> datetime:
        return self.end_time_utc.astimezone()

    @overload
    @staticmethod
    def from_xml(xml: ET.Element) -> 'BbbMetadata':
        ...

    @overload
    @staticmethod
    def from_xml(xml: str) -> 'BbbMetadata':
        ...

    @staticmethod
    def from_xml(xml) -> 'BbbMetadata':
        if isinstance(xml, str):
            xml = ET.fromstring(xml)

        meta = BbbMetadata.__find_in_xml(xml, 'meta')
        playback = BbbMetadata.__find_in_xml(xml, 'playback')

        start_time = datetime.utcfromtimestamp(
            int(BbbMetadata.__find_in_xml(xml, 'start_time').text or '0') / 1000
        )
        end_time = datetime.utcfromtimestamp(
            int(BbbMetadata.__find_in_xml(xml, 'end_time').text or '0') / 1000
        )
        participants = int(BbbMetadata.__find_in_xml(xml, 'participants').text or '0')

        context_name = BbbMetadata.__find_in_xml(meta, 'bbb-context-name').text or ''
        context_label = BbbMetadata.__find_in_xml(meta, 'bbb-context-label').text or ''
        recording_name = (
            BbbMetadata.__find_in_xml(meta, 'bbb-recording-name').text or ''
        )

        duration = timedelta(
            milliseconds=int(
                BbbMetadata.__find_in_xml(playback, 'duration').text or '0'
            )
        )
        size = int(BbbMetadata.__find_in_xml(playback, 'size').text or '0')
        link = BbbMetadata.__find_in_xml(playback, 'link').text or ''

        return BbbMetadata(
            recording_name,
            start_time,
            end_time,
            participants,
            context_name,
            context_label,
            duration,
            size,
            link
        )

    @staticmethod
    def __find_in_xml(xml: ET.Element, tag: str) -> ET.Element:
        element = xml.find(tag)
        if element is None:
            raise ValueError(f'Unable to find "{tag}" in the xml.')

        return element


@dataclass(frozen=True, eq=True)
class BbbChatEntry:
    name: str
    message: str
    timestamp: timedelta

    @overload
    @staticmethod
    def from_xml(xml: ET.Element) -> Sequence['BbbChatEntry']:
        ...

    @overload
    @staticmethod
    def from_xml(xml: str) -> Sequence['BbbChatEntry']:
        ...

    @staticmethod
    def from_xml(xml) -> Sequence['BbbChatEntry']:
        if isinstance(xml, str):
            xml = ET.fromstring(xml)

        chat = []
        for chattimeline in xml.iterfind('chattimeline'):
            in_time = timedelta(seconds=int(chattimeline.attrib['in']))
            name = chattimeline.attrib['name']
            message = chattimeline.attrib['message']
            chat.append(BbbChatEntry(name, message, in_time))

        return chat


class BbbFileEntry:
    _filename: str
    _response: ClientResponse

    def __init__(self, filename: str, response: ClientResponse) -> None:
        self._filename = filename
        self._response = response

    @property
    def extension(self) -> str:
        return self._filename

    @overload
    async def copy_to(
        self,
        destination: AsyncBufferedIOBase,
        progress_factory: Callable[[int], Any] | None = None,
        buffer_size: int = 4096
    ) -> AsyncBufferedIOBase:
        ...

    @overload
    async def copy_to(
        self,
        destination: str,
        progress_factory: Callable[[int], Any] | None = None,
        buffer_size: int = 4096
    ) -> str:
        ...

    async def copy_to(
        self, destination, progress_factory=None, buffer_size=4096
    ) -> str | AsyncBufferedIOBase | None:
        match destination:
            case str():
                fullname = path.join(destination, self._filename)
                async with aopen(fullname, 'wb') as file:
                    await BbbFileEntry.__copy_to(
                        self._response, file, progress_factory, buffer_size
                    )
                return fullname
            case AsyncBufferedIOBase():
                await BbbFileEntry.__copy_to(
                    self._response, destination, progress_factory, buffer_size
                )
                return destination

    def close(self) -> None:
        self._response.close()

    async def __aenter__(self) -> 'BbbFileEntry':
        return self

    async def __aexit__(self, *_) -> None:
        self.close()

    @staticmethod
    async def __copy_to(
        source: ClientResponse,
        destination: AsyncBufferedIOBase,
        progress_factory: Callable[[int], Any] | None = None,
        buffer_size: int = 4096,
    ) -> None:
        size = int(source.headers['content-length'])
        content = source.content

        progress_bar = progress_factory(size) if progress_factory else None
        handle_progress = progress_bar.update if progress_bar else lambda _: _

        try:
            async for data in content.iter_chunked(buffer_size):
                await destination.write(data)
                handle_progress(buffer_size)
        finally:
            if progress_bar is not None:
                progress_bar.close()


class BbbPoint(NamedTuple):
    x: int
    y: int


class BbbSize(NamedTuple):
    width: int
    height: int


class BbbSlideEntry(BbbFileEntry):
    _start_timestamp: timedelta
    _end_timestamp: timedelta
    _size: BbbSize
    _position: BbbPoint

    def __init__(
        self,
        filename: str,
        response: ClientResponse,
        start_timestamp: timedelta,
        end_timestamp: timedelta,
        size: BbbSize,
        position: BbbPoint
    ) -> None:
        super().__init__(filename, response)
        self._start_timestamp = start_timestamp
        self._end_timestamp = end_timestamp
        self._size = size
        self._position = position

    @property
    def start_timestamp(self) -> timedelta:
        return self._start_timestamp

    @property
    def end_timestamp(self) -> timedelta:
        return self._end_timestamp

    @property
    def size(self) -> BbbSize:
        return self._size

    @property
    def position(self) -> tuple[int, int]:
        return self._position

    @overload
    @staticmethod
    async def from_xml(
        xml: ET.Element, base_address: str, session: ClientSession | None = None
    ) -> 'BbbSlideEntry':
        ...

    @overload
    @staticmethod
    async def from_xml(
        xml: str, base_address: str, session: ClientSession | None = None
    ) -> 'BbbSlideEntry':
        ...

    @staticmethod
    async def from_xml(xml, base_address, session=None) -> 'BbbSlideEntry':
        if isinstance(xml, str):
            xml = ET.fromstring(xml)

        exit_session = session is None
        session = session or ClientSession()

        try:
            href = next((k for k in xml.attrib.keys() if 'href' in k), None)
            if href is None:
                raise ValueError('Unable to find "href" in the xml.')

            url = urljoin(base_address, xml.attrib[href])
            filename = path.basename(url)

            response = await session.get(url)
            if not response.ok:
                response.close()
                raise ValueError(
                    'Unable to get response stream from the remote server.'
                )

            in_time = timedelta(seconds=float(xml.attrib['in']))
            out_time = timedelta(seconds=float(xml.attrib['out']))

            width = int(xml.attrib['width'])
            height = int(xml.attrib['height'])

            x = int(xml.attrib['x'])
            y = int(xml.attrib['y'])

            return BbbSlideEntry(
                filename,
                response,
                in_time,
                out_time,
                BbbSize(width, height),
                BbbPoint(x, y)
            )
        finally:
            if exit_session:
                session.close()


class BbbClient:
    AVAILABLE_VIDEO_EXTENSIONS: Sequence[str] = ['.mp4', '.webm']
    ID_PATTERN = re.compile(r'\w{40}-\d+')

    _base_address: str
    _id: str
    _exit_session: bool
    _session: ClientSession

    def __init__(self, meeting_url: str, session: ClientSession | None = None) -> None:
        parse_result = urlparse(meeting_url)
        self._base_address = f'{parse_result.scheme}://{parse_result.netloc}'

        id = BbbClient.ID_PATTERN.search(meeting_url)
        if id is None:
            raise ValueError(f'Unable to find id in the url "{meeting_url}".')
        self._id = id[0]

        self._exit_session = session is None
        self._session = session or ClientSession()

    async def get_metadata(self) -> BbbMetadata:
        url = self._build_url(f'presentation/{self._id}/metadata.xml')
        xml = await self._get_xml(url)
        return BbbMetadata.from_xml(xml)

    async def get_chat(self) -> Sequence[BbbChatEntry]:
        url = self._build_url(f'presentation/{self._id}/slides_new.xml')
        xml = await self._get_xml(url)
        return BbbChatEntry.from_xml(xml)

    async def enumerate_deskshares(self) -> AsyncIterable[BbbFileEntry]:
        for extension in BbbClient.AVAILABLE_VIDEO_EXTENSIONS:
            filename = f'deskshare{extension}'
            url = self._build_url(f'presentation/{self._id}/deskshare/{filename}')

            response = await self._session.get(url)
            if not response.ok:
                response.close()
                continue

            yield BbbFileEntry(filename, response)

    async def get_deskshare(self) -> BbbFileEntry | None:
        async for deskshare in self.enumerate_deskshares():
            return deskshare

        return None

    async def enumerate_webcams(self) -> AsyncIterable[BbbFileEntry]:
        for extension in BbbClient.AVAILABLE_VIDEO_EXTENSIONS:
            filename = f'webcams{extension}'
            url = self._build_url(f'presentation/{self._id}/video/{filename}')

            response = await self._session.get(url)
            if not response.ok:
                response.close()
                continue

            yield BbbFileEntry(filename, response)

    async def get_webcam(self) -> BbbFileEntry | None:
        async for webcam in self.enumerate_webcams():
            return webcam

        return None

    async def enumerate_slides(self) -> AsyncIterable[BbbSlideEntry]:
        slide_base_address = self._build_url(f'presentation/{self._id}/')
        url = urljoin(f'{slide_base_address}', 'shapes.svg')

        xml = await self._get_xml(url)
        for image in xml:
            try:
                yield await BbbSlideEntry.from_xml(
                    image, slide_base_address, self._session
                )
            except Exception:
                continue

    async def get_slide(self) -> BbbSlideEntry | None:
        async for slide in self.enumerate_slides():
            return slide

        return None

    async def close(self) -> None:
        if self._exit_session:
            await self._session.close()

    async def _get_xml(self, url: str) -> ET.Element:
        async with self._session.get(self._build_url(url)) as response:
            return ET.fromstring(await response.content.read())

    def _build_url(self, path: str) -> str:
        return urljoin(self._base_address, path)

    async def __aenter__(self) -> 'BbbClient':
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()
