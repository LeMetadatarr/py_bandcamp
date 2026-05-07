# py_bandcamp

Python scraper for Bandcamp — search, metadata, stream URL extraction, and discovery.

Returns [`mediavocab`](https://github.com/OpenVoiceOS/mediavocab) `Release` and `Entity` objects for typed, structured metadata.

`mediavocab>=0.1.0` is a hard runtime dependency — every search/recommendation
helper hands back validated `Release` / `Entity` models. There is no dict
fallback.

## Install

```bash
pip install py_bandcamp
```

## Quick start

```python
from py_bandcamp import BandCamp, BandcampTrack, BandcampAlbum, BandcampArtist

# Get a streamable MP3 URL
url = BandCamp.get_stream_url("https://deadunicorn.bandcamp.com/track/astronaut-problems")
print(url)  # https://t4.bcbits.com/stream/...

# Search — returns mediavocab Release objects
for release in BandCamp.search_tracks("astronaut problems"):
    artist = release.work.credits[0].entity.name if release.work.credits else ""
    print(release.work.title, artist, release.uri)

for release in BandCamp.search_albums("black metal"):
    artist = release.work.credits[0].entity.name if release.work.credits else ""
    print(release.work.title, artist)

# Search artists/labels — returns mediavocab Entity objects
for entity in BandCamp.search_artists("Perturbator"):
    print(entity.name, entity.extra.get("genre"), entity.extra.get("location"))

# Browse by genre tag
for release in BandCamp.search_tag("doom-metal", albums=True, tracks=False, max_pages=2):
    print(release.work.title, release.uri)

# Discover related albums and artists from a seed
for release in BandCamp.get_recommendations("https://naxatras.bandcamp.com/album/iii"):
    artist = release.work.credits[0].entity.name if release.work.credits else ""
    print(release.work.title, artist, release.uri)

for entity in BandCamp.get_related_artists("https://naxatras.bandcamp.com/album/iii"):
    print(entity.name, entity.extra.get("artist_url"))
```

### Return types at a glance

**`Release`** — from `search_tracks`, `search_albums`, `search_tag`, `get_recommendations`:

```python
release.uri                                       # canonical Bandcamp permalink (no query string)
release.image                                     # artwork URL ("" when unavailable)
release.work.title                                # track or album title
release.work.media_type                           # MediaType.MUSIC
release.work.runtime                              # duration in seconds (tracks only)
release.work.content_genres                       # list of GENRE_* tokens + raw Bandcamp tags
release.work.credits[0].entity.name               # artist display name (if available)
release.work.credits[0].relation_role             # RelationRole.PERFORMER (tracks) / CREATOR (albums)
release.work.tracklist                            # list[Appearance] — populated by album_to_release(...)
release.release_date                              # IsoDate-validated string or None
release.license                                   # SPDX-style identifier ("CC-BY-SA-4.0") or ""
release.parsed_license.is_open()                  # True for CC*/CC0/PD, False otherwise
release.codec                                     # "mp3" — Bandcamp's free streaming preview
release.bitrate                                   # "128" (kbps)
release.audio_channels                            # "stereo"
release.label                                     # EntityRef for the imprint, or None when self-released
release.external_ids["bandcamp_album_url"]        # full Bandcamp URL for albums
release.external_ids["bandcamp_track_url"]        # full Bandcamp URL for tracks
release.external_ids["bandcamp_band_url"]         # canonical artist root URL
release.external_ids["bandcamp_band_id"]          # numeric artist id
release.external_ids["bandcamp_album_id"]         # numeric album id
release.external_ids["bandcamp_track_id"]         # numeric track id
```

### Full-fidelity album conversion

`BandCamp.search_*` keeps payloads small by skipping the per-album track
fetch. When you want the ordered tracklist, use `album_to_release`:

```python
from py_bandcamp import BandCamp

release = BandCamp.album_to_release(
    "https://naxatras.bandcamp.com/album/iii",
    include_tracklist=True,
)
print(release.work.title, release.release_date)
for appearance in release.work.tracklist:
    print(appearance.position, appearance.work.title, appearance.work.runtime)
```

`BandCamp.track_to_release(url)` is the equivalent for a single track URL.

Minimal end-to-end:

```python
from py_bandcamp import BandCamp

release = next(BandCamp.search("naxatras iii", albums=True, tracks=False, artists=False))
print(release.work.title)
print(release.release_date)
print(release.parsed_license.is_open())
print(release.external_ids["bandcamp_album_url"])
```

**`Entity`** — from `search_artists`, `search_labels`, `get_related_artists`:

```python
entity.name                          # display name
entity.kind                          # EntityKind.PERSON or EntityKind.ORGANISATION
entity.extra.get("artist_url")       # profile URL
entity.extra.get("image")            # avatar URL
entity.extra.get("genre")            # genre string (artists only)
entity.extra.get("location")         # location string
entity.external_ids                  # {"bandcamp_band_id": "..."} (when known)
```

## Power-user: direct model access

The internal scraper models remain available for loading full album/artist pages:

```python
from py_bandcamp import BandcampTrack, BandcampAlbum, BandcampArtist

# Load a track directly (fetches and parses the track page)
track = BandcampTrack.from_url("https://deadunicorn.bandcamp.com/track/astronaut-problems")
print(track.title, track.stream, track.duration)

# Load an album
album = BandcampAlbum.from_url("https://naxatras.bandcamp.com/album/iii")
for t in album.tracks:
    print(t.track_num, t.title, t.duration)

# Load an artist
artist = BandcampArtist.from_url("https://dopethrone.bandcamp.com")
print(artist.name, artist.location)
for album in artist.albums[:3]:
    print(album.title, album.url)
```

## Session injection

By default py_bandcamp uses a plain `requests.Session` with a realistic
`User-Agent`. You can replace it with any session-compatible object
(e.g. one with custom headers, retries, or a cache):

```python
import requests
from py_bandcamp import set_session, BandCamp

session = requests.Session()
session.headers["User-Agent"] = "my-app/1.0"
set_session(session)               # global override

# Or inject per-instance, leaving the global session untouched:
bc = BandCamp(session=session)
list(bc.search_tracks("astronaut problems"))
```

## Bypassing the Bandcamp search bot wall (curl_cffi)

Bandcamp's search endpoint is currently fronted by a Fastly bot challenge
that rejects vanilla `requests` traffic on TLS-fingerprint grounds. The
fix is to route through [`curl_cffi`](https://github.com/lexiforest/curl_cffi),
which impersonates real browser TLS/JA3 fingerprints:

```bash
pip install py-bandcamp[stealth]
export PYBANDCAMP_TRANSPORT=curl_cffi
```

With both in place, `py_bandcamp` automatically builds its default
session via `curl_cffi.requests.Session(impersonate="chrome")`, clearing
the challenge transparently. If `curl_cffi` isn't installed the env var
is ignored and we fall back to plain `requests` so nothing hard-breaks.

You can also build the transport explicitly and inject it:

```python
from py_bandcamp import BandCamp
from py_bandcamp.transport import default_session

bc = BandCamp(session=default_session())
for r in bc.search_tracks("astronaut problems"):
    print(r.work.title)
```

## API

See [docs/bandcamp_api.md](docs/bandcamp_api.md) for the full reference.

## Examples

| Script | What it shows |
|---|---|
| `examples/track_stream.py` | Fetch track metadata, stream URL, lyrics |
| `examples/album_browse.py` | Browse an album: tracks (with duration), releases, comments, artist |
| `examples/artist_browse.py` | Browse an artist: albums, featured album and track |
| `examples/search.py` | Search for tracks, albums, artists, labels, tags |
| `examples/recommendations.py` | Related albums and artists from a seed; genre browsing |
| `examples/release_tracklist.py` | Convert an album URL to a `Release` with full tracklist |

## Notes

- Stream URLs come from the `data-tralbum` attribute on Bandcamp pages (not the ld+json blob).
  They are time-limited tokens — do not cache them for long periods.
- Bandcamp does not provide a public API; this library scrapes HTML and may break if Bandcamp changes its markup.
