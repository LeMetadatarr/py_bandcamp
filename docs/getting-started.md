# Getting started

## Install

```bash
pip install py_bandcamp
```

For live keyword search (blocked by Fastly's JS challenge on plain `requests`):

```bash
pip install "py_bandcamp[stealth]"
export PYBANDCAMP_TRANSPORT=curl_cffi
```

See [transport.md](transport.md) for details.

## Fetch an album

```python
from py_bandcamp import BandCamp

release = BandCamp.album_to_release(
    "https://naxatras.bandcamp.com/album/iii",
    include_tracklist=True,
)
print(release.work.title, release.release_date)
for a in release.work.tracklist:
    print(a.position, a.work.title, a.work.runtime)
```

`BandCamp.album_to_release`: `py_bandcamp/__init__.py:492`

## Fetch a track

```python
from py_bandcamp import BandCamp

release = BandCamp.track_to_release(
    "https://deadunicorn.bandcamp.com/track/astronaut-problems"
)
print(release.work.title, release.codec, release.bitrate)
```

`BandCamp.track_to_release`: `py_bandcamp/__init__.py:503`

## Get a stream URL

```python
from py_bandcamp import BandCamp

url = BandCamp.get_stream_url(
    "https://deadunicorn.bandcamp.com/track/astronaut-problems"
)
# https://t4.bcbits.com/stream/...  (time-limited token, ~1 hour)
```

`BandCamp.get_stream_url`: `py_bandcamp/__init__.py:696`

## Browse by tag

```python
from py_bandcamp import BandCamp

for release in BandCamp.search_tag("doom-metal", albums=True, tracks=False, max_pages=1):
    print(release.work.title, release.uri)
```

Tag browse queries the search endpoint, so it needs the `curl_cffi` transport
where Bandcamp serves the bot challenge.

---
[Home](index.md) · [Model reference →](models.md)
