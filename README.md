# py_bandcamp

py_bandcamp is a Python scraper for Bandcamp. It fetches album, track, and
artist metadata, stream URLs, lyrics, recommendations, and search results.

It returns [`mediavocab`](https://github.com/OpenVoiceOS/mediavocab) `Release`
and `Entity` objects for typed, structured metadata.

`mediavocab>=1.0.0` is a hard runtime dependency. Every search and
recommendation helper returns validated `Release` or `Entity` models. There is
no dict fallback.

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
from py_bandcamp import BandCamp, BandcampTrack, BandcampAlbum, BandcampArtist

# Get a streamable MP3 URL
url = BandCamp.get_stream_url("https://deadunicorn.bandcamp.com/track/astronaut-problems")
print(url)  # https://t4.bcbits.com/stream/...

# Search: returns mediavocab Release objects
for release in BandCamp.search_tracks("astronaut problems"):
    artist = release.work.credits[0].entity.name if release.work.credits else ""
    print(release.work.title, artist, release.uri)

for release in BandCamp.search_albums("black metal"):
    artist = release.work.credits[0].entity.name if release.work.credits else ""
    print(release.work.title, artist)

# Search artists/labels: returns mediavocab Entity objects
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

**`Release`**, from `search_tracks`, `search_albums`, `search_tag`, `get_recommendations`:

```python
release.uri                                       # canonical Bandcamp permalink (no query string)
release.image                                     # artwork URL ("" when unavailable)
release.work.title                                # track or album title
release.work.media_type                           # MediaType.MUSIC
release.work.runtime                              # duration in seconds (tracks only)
release.work.content_genres                       # list of GENRE_* tokens + raw Bandcamp tags
release.work.credits[0].entity.name               # artist display name (if available)
release.work.credits[0].relation_role             # RelationRole.PERFORMER (tracks) / CREATOR (albums)
release.work.tracklist                            # list[Appearance], populated by album_to_release(...)
release.release_date                              # IsoDate-validated string or None
release.license                                   # License object (.identifier "CC-BY-SA-4.0") or None
release.license.is_open() if release.license else False   # True for CC*/CC0/PD, False otherwise
release.codec                                     # "mp3", Bandcamp's free streaming preview
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
fetch. To get the ordered tracklist, use `album_to_release`:

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

# Search: yields Release objects
for release in BandCamp.search_albums("black metal"):
    artist = release.work.credits[0].entity.name if release.work.credits else ""
    print(release.work.title, artist, release.uri)
```

## Public API

### `BandCamp`: main facade (`py_bandcamp/__init__.py`)

| Method | Returns | Notes |
|---|---|---|
| `BandCamp.album_to_release(url, include_tracklist=True)` | `Release` | Fetches album page. Tracklist populated when `include_tracklist=True` |
| `BandCamp.track_to_release(url)` | `Release` | Fetches track page |
| `BandCamp.get_stream_url(url)` | `str` | Direct MP3-128 CDN token URL (time-limited) |
| `BandCamp.get_streams(urls)` | `list[str]` | Batch of `get_stream_url` |
| `BandCamp.get_track_lyrics(url)` | `str` | Lyrics text or `"lyrics unavailable"` |
| `BandCamp.get_recommendations(url)` | `list[Release]` | "If you like…" albums |
| `BandCamp.get_related_artists(url)` | `list[Entity]` | Unique artists from recommendations |
| `BandCamp.search(name, ...)` | `Iterator[Release\|Entity]` | Paginated. Auto-deduplicates |
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
converters automatically. You only call them directly when you already hold
a raw model object.

## Search caveat: Fastly JS challenge

Bandcamp's `/search` endpoint sits behind a Fastly bot challenge that rejects
vanilla `requests` TLS fingerprints. Static HTML parsing, such as tag browse
and album or track page fetches, is unaffected. For live keyword search,
install the `[stealth]` extra and set `PYBANDCAMP_TRANSPORT=curl_cffi` (see
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
release.license                        # License object (.identifier "CC-BY-SA-4.0") or None
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
`curl_cffi.requests.Session(impersonate="chrome")`. If `curl_cffi` is not
installed, it falls back silently to plain `requests`.

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
| [`examples/11_crawl.py`](examples/11_crawl.py) | Frontier crawling via related-artist BFS |

## Frontier crawling

`BandCamp.crawl()` walks the Bandcamp artist graph through album
recommendation links ("fans also bought") without touching the
Cloudflare-protected search endpoint. Pass a `seen` set to resume across
multiple calls:

```python
from py_bandcamp import BandCamp

seen = set()
for entity in BandCamp.crawl(["https://enslaved.bandcamp.com"], max_artists=5, seen=seen):
    print(entity.name, entity.extra.get("artist_url"))
# resume: already-visited URLs are skipped
for entity in BandCamp.crawl(["https://neurosis.bandcamp.com"], max_artists=5, seen=seen):
    print(entity.name)
```

## Docs

- [Getting started](docs/getting-started.md)
- [Model reference](docs/models.md)
- [Search and discovery](docs/search-and-discovery.md)
- [mediavocab converters](docs/converters.md)
- [Transport / curl_cffi](docs/transport.md)

## Notes

- Stream URLs are time-limited CDN tokens. Do not cache them.
- Bandcamp has no public API. This library scrapes HTML and may break on markup changes.

## Related projects

- [mediavocab](https://github.com/OpenVoiceOS/mediavocab): the typed `Release` and `Entity` schema this library returns.
- [ovos-ocp-bandcamp-plugin](https://github.com/OpenVoiceOS/ovos-ocp-bandcamp-plugin): OCP media plugin built on py_bandcamp.
- [ovos-skill-bandcamp](https://github.com/OpenVoiceOS/ovos-skill-bandcamp): OVOS voice skill built on py_bandcamp.
- [bandcamp-ma-provider](https://github.com/TigreGotico/bandcamp-ma-provider): Music Assistant provider built on py_bandcamp.

## License

Apache 2.0
