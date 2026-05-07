# py_bandcamp

Python scraper for Bandcamp — fetch album/track/artist metadata, stream URLs,
lyrics, recommendations, and search results. Returns
[`mediavocab`](https://github.com/OpenVoiceOS/mediavocab) `Release` and
`Entity` objects; there is no dict fallback.

## Install

```bash
pip install py_bandcamp
```

For search pages protected by Fastly's JS bot challenge, add the stealth extra:

```bash
pip install "py_bandcamp[stealth]"
export PYBANDCAMP_TRANSPORT=curl_cffi
```

## Quick start

```python
from py_bandcamp import BandCamp

# Album → mediavocab Release with full tracklist
release = BandCamp.album_to_release(
    "https://naxatras.bandcamp.com/album/iii",
    include_tracklist=True,
)
print(release.work.title, release.release_date)
for a in release.work.tracklist:
    print(a.position, a.work.title, a.work.runtime)

# Direct MP3-128 stream URL for a track
url = BandCamp.get_stream_url(
    "https://deadunicorn.bandcamp.com/track/astronaut-problems"
)
print(url)  # https://t4.bcbits.com/stream/...

# Search — yields Release objects
for release in BandCamp.search_albums("black metal"):
    artist = release.work.credits[0].entity.name if release.work.credits else ""
    print(release.work.title, artist, release.uri)
```

## Public API

### `BandCamp` — main facade (`py_bandcamp/__init__.py`)

| Method | Returns | Notes |
|---|---|---|
| `BandCamp.album_to_release(url, include_tracklist=True)` | `Release` | Fetches album page; tracklist populated when `include_tracklist=True` |
| `BandCamp.track_to_release(url)` | `Release` | Fetches track page |
| `BandCamp.get_stream_url(url)` | `str` | Direct MP3-128 CDN token URL (time-limited) |
| `BandCamp.get_streams(urls)` | `list[str]` | Batch of `get_stream_url` |
| `BandCamp.get_track_lyrics(url)` | `str` | Lyrics text or `"lyrics unavailable"` |
| `BandCamp.get_recommendations(url)` | `list[Release]` | "If you like…" albums |
| `BandCamp.get_related_artists(url)` | `list[Entity]` | Unique artists from recommendations |
| `BandCamp.search(name, ...)` | `Iterator[Release\|Entity]` | Paginated; auto-deduplicates |
| `BandCamp.search_tracks(name)` | `Iterator[Release]` | |
| `BandCamp.search_albums(name)` | `Iterator[Release]` | |
| `BandCamp.search_artists(name)` | `Iterator[Entity]` | |
| `BandCamp.search_labels(name)` | `Iterator[Entity]` | |
| `BandCamp.search_tag(tag, ...)` | `Iterator[Release\|Entity]` | Tag/genre browse |
| `BandCamp.tags(tag_list=True)` | `list[str]` or `dict` | All known Bandcamp genre tags |

### Internal scraper models (`py_bandcamp/models.py`)

| Class | `from_url` | Key properties |
|---|---|---|
| `BandcampAlbum` | yes | `title`, `tracks`, `artist`, `recommendations`, `album_id`, `band_id` |
| `BandcampTrack` | yes | `title`, `stream`, `duration`, `track_id`, `band_id`, `album_id` |
| `BandcampArtist` | yes | `name`, `albums`, `band_id`, `location`, `genre` |
| `BandcampSingle` | yes | `title`, `artist`, `tracks` (one-element list) |
| `BandcampLabel` | yes | `name`, `location`, `tags` |

### mediavocab converters (`py_bandcamp/__init__.py`)

| Function | Input → Output |
|---|---|
| `BandCamp.album_to_release(album_or_url)` | `BandcampAlbum\|str` → `Release` |
| `BandCamp.track_to_release(track_or_url)` | `BandcampTrack\|str` → `Release` |

Search helpers (`search_*`, `get_recommendations`) call the internal
converters automatically — you only call them directly when you already hold
a raw model object.

## Search caveat — Fastly JS challenge

Bandcamp's `/search` endpoint is fronted by a Fastly bot challenge that
rejects vanilla `requests` TLS fingerprints. Static HTML parsing (tag browse,
album/track page fetches) is unaffected. For live keyword search install the
`[stealth]` extra and set `PYBANDCAMP_TRANSPORT=curl_cffi` (see
[docs/transport.md](docs/transport.md)). Playwright is not required.

## mediavocab integration

`BandCamp.album_to_release` and `BandCamp.track_to_release` return a fully
typed `mediavocab.Release`. Key fields:

```python
release.uri                            # canonical URL (query string stripped)
release.work.title                     # album or track title
release.work.credits[0].entity.name    # artist name
release.work.content_genres            # GENRE_* tokens + raw Bandcamp tags
release.work.tracklist                 # list[Appearance] (album_to_release only)
release.release_date                   # ISO-8601 string or None
release.license                        # SPDX string e.g. "CC-BY-SA-4.0" or ""
release.codec / .bitrate / .audio_channels  # "mp3" / "128" / "stereo"
release.label                          # EntityRef or None (self-released)
release.external_ids                   # bandcamp_album_id/track_id/band_id + URLs
```

See [docs/converters.md](docs/converters.md) for the full field walk-through.

## Pluggable session + `PYBANDCAMP_TRANSPORT`

```python
import requests
from py_bandcamp import set_session, BandCamp

# Global override
s = requests.Session()
s.headers["User-Agent"] = "my-app/1.0"
set_session(s)

# Per-instance (leaves global session untouched)
bc = BandCamp(session=s)
list(bc.search_tracks("doom metal"))
```

`PYBANDCAMP_TRANSPORT=curl_cffi` makes `default_session()` return a
`curl_cffi.requests.Session(impersonate="chrome")`. Falls back silently to
plain `requests` if `curl_cffi` is not installed.

## Examples

| Script | What it demonstrates |
|---|---|
| [`examples/01_quickstart.py`](examples/01_quickstart.py) | Fetch one album by URL |
| [`examples/02_track_details.py`](examples/02_track_details.py) | Track metadata, stream URL, lyrics |
| [`examples/03_artist_discography.py`](examples/03_artist_discography.py) | Artist albums, singles, band_id |
| [`examples/04_get_streams.py`](examples/04_get_streams.py) | Batch stream URL extraction |
| [`examples/05_lyrics.py`](examples/05_lyrics.py) | Fetch and print track lyrics |
| [`examples/06_recommendations.py`](examples/06_recommendations.py) | "If you like…" albums + related artists |
| [`examples/07_search_static.py`](examples/07_search_static.py) | Tag browse (works without curl_cffi) |
| [`examples/08_to_mediavocab.py`](examples/08_to_mediavocab.py) | Full Release/Entity field walk-through |
| [`examples/09_custom_session.py`](examples/09_custom_session.py) | Inject session, optional curl_cffi |
| [`examples/10_label_catalog.py`](examples/10_label_catalog.py) | Label-level browsing |

## Docs

- [Getting started](docs/getting-started.md)
- [Model reference](docs/models.md)
- [Search and discovery](docs/search-and-discovery.md)
- [mediavocab converters](docs/converters.md)
- [Transport / curl_cffi](docs/transport.md)

## Notes

- Stream URLs are time-limited CDN tokens — do not cache them.
- Bandcamp has no public API; this library scrapes HTML and may break on markup changes.

## License

Apache 2.0
