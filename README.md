# 🧿 BBBDownloader
Python script for downloading meetings recordings from BBB service.

## Usage
```
BBBDownloader [-h] [-d] [-c] [-s] [-o OUTPUT] url

positional arguments:
  url                   URL to the meeting

options:
  -h, --help            show this help message and exit
  -d, --no-deskshare    do not append deskshare video to the output file
  -c, --no-chat         do not append chat subtitles to the output file
  -s, --no-ssl          ignore SSL errors when conecting to the server
  -o OUTPUT, --output OUTPUT
                        override the output filename
```
