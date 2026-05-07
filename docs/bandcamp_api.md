# py_bandcamp — Developer Reference

py_bandcamp scrapes Bandcamp pages to provide search, streaming, metadata access, and discovery without an official API.

All public `BandCamp` class methods return [`mediavocab`](https://github.com/OpenVoiceOS/mediavocab) objects:

- **track/album methods** (`search_tracks`, `search_albums`, `search_tag`, `get_recommendations`) yield/return `mediavocab.Release`
- **artist/label methods** (`search_artists`, `search_labels`, `get_related_artists`) yield/return `mediavocab.Entity`

---

## BandCamp (main interface)

```python
from py_bandcamp import BandCamp
```

### Search

```python
from mediavocab import Release, Entity

# Search across all types (auto-paginates up to max_pages)
for result in BandCamp.search("black metal", albums=True, tracks=True,
                               artists=True, labels=False, max_pages=10):
    if isinstance(result, Release):
        print(result.work.title, result.uri)
    elif isinstance(result, Entity):
        print(result.name, result.extra.get("artist_url"))

# Single-type convenience wrappers
for release in BandCamp.search_tracks("astronaut problems"):
    artist = release.work.credits[0].entity.name if release.work.credits else ""
    print(release.work.title, artist, release.uri)

for release in BandCamp.search_albums("iii"):
    artist = release.work.credits[0].entity.name if release.work.credits else ""
    print(release.work.title, artist)

for entity in BandCamp.search_artists("Perturbator"):
    print(entity.name, entity.extra.get("genre"), entity.extra.get("location"))

for entity in BandCamp.search_labels("Nuclear Blast"):
    print(entity.name, entity.extra.get("location"))
```

`search()` paginates automatically and yields `Release` or `Entity` instances depending on the result type. Results are deduplicated by URL across pages. `max_pages` (default 10) caps how many Bandcamp pages are fetched.

When only one result type is requested, the Bandcamp `item_type` filter is sent so the results are more precise.

### Tag search

```python
# Search by genre tag (wraps search() with the tag as query)
for release in BandCamp.search_tag("black-metal", albums=True, tracks=True,
                                    artists=True, labels=False, max_pages=5):
    print(release.work.title, release.uri)

# Get all known genre/subgenre tag names
tags = BandCamp.tags()                  # flat list of strings
tags = BandCamp.tags(tag_list=False)    # {"genres": [...], "subgenres": {...}}
print("black-metal" in BandCamp.tags()) # True
```

### Streaming

```python
# Get a direct MP3-128 stream URL for a track page
stream_url = BandCamp.get_stream_url("https://artist.bandcamp.com/track/song")
# Returns the CDN token URL, or the original URL if no stream is available.
# Note: stream URLs are time-limited tokens (~1 hour).

# Batch
urls = BandCamp.get_streams(["https://a.bandcamp.com/track/x",
                              "https://b.bandcamp.com/track/y"])
```

### Recommendations & related artists

```python
# Albums Bandcamp recommends for fans of a given album → list[Release]
for release in BandCamp.get_recommendations("https://artist.bandcamp.com/album/title"):
    artist = release.work.credits[0].entity.name if release.work.credits else ""
    print(release.work.title, artist, release.uri)

# Unique artists extracted from those recommendations → list[Entity]
for entity in BandCamp.get_related_artists("https://artist.bandcamp.com/album/title"):
    print(entity.name, entity.extra.get("artist_url"))
```

Bandcamp populates the "If you like…" section with ~6–8 albums from fans who also
own the current album. Availability depends on the album having enough purchase/fan data.

### Lyrics

```python
lyrics = BandCamp.get_track_lyrics("https://artist.bandcamp.com/track/song")
# Returns the lyrics text, or "lyrics unavailable" if not present.
```

---

## Return types

### Release (tracks and albums)

Returned by `search_tracks`, `search_albums`, `search_tag`, `get_recommendations`.

| Attribute | Type | Description |
|---|---|---|
| `release.uri` | `str` | Canonical Bandcamp permalink (query string stripped) |
| `release.image` | `str` | Artwork URL (`""` when unavailable) |
| `release.stream_mode` | `StreamMode` | Always `StreamMode.ON_DEMAND` |
| `release.codec` / `release.bitrate` / `release.audio_channels` | `str` | `"mp3"` / `"128"` / `"stereo"` — Bandcamp's free streaming preview |
| `release.label` | `EntityRef\|None` | Imprint when `publisher` differs from the artist; `None` for self-released |
| `release.work.title` | `str` | Track or album title |
| `release.work.media_type` | `MediaType` | Always `MediaType.MUSIC` |
| `release.work.runtime` | `float\|None` | Duration in seconds (tracks only; `None` for albums) |
| `release.work.content_genres` | `list[str]` | Bandcamp tags mapped to `GENRE_*` tokens; unknown tags pass through verbatim |
| `release.work.credits[0].entity.name` | `str` | Artist display name |
| `release.work.credits[0].relation_role` | `RelationRole` | `RelationRole.PERFORMER` (tracks) or `RelationRole.CREATOR` (albums) |
| `release.work.tracklist` | `list[Appearance]` | Ordered tracks — populated by `BandCamp.album_to_release(url, include_tracklist=True)`; empty after a plain search |
| `release.release_date` | `IsoDate\|None` | ISO-8601 string ("2024", "2024-09", "2024-09-05"); `None` when unknown |
| `release.license` | `str` | SPDX-style identifier inferred from CC tags or `""` |
| `release.parsed_license` | `License` | Typed view of `release.license`; `parsed_license.is_open()` for filtering |
| `release.external_ids` | `Dict[str, str]` | `bandcamp_track_id`, `bandcamp_album_id`, `bandcamp_band_id`, `bandcamp_track_url`, `bandcamp_album_url`, `bandcamp_band_url` |

### Full-fidelity album conversion

```python
release = BandCamp.album_to_release(album_url, include_tracklist=True)
for appearance in release.work.tracklist:
    print(appearance.position, appearance.work.title, appearance.work.runtime)
```

`BandCamp.track_to_release(url)` is the equivalent for a single track URL.

### Entity (artists and labels)

Returned by `search_artists`, `search_labels`, `get_related_artists`.

| Attribute | Type | Description |
|---|---|---|
| `entity.name` | `str` | Display name |
| `entity.kind` | `EntityKind` | `EntityKind.GROUP` (artists) or `EntityKind.ORGANISATION` (labels) |
| `entity.extra.get("artist_url")` | `str` | Profile URL |
| `entity.extra.get("image")` | `str` | Avatar/logo URL |
| `entity.extra.get("genre")` | `str` | Genre string (artists only) |
| `entity.extra.get("location")` | `str` | Location string ("City, Country") |
| `entity.extra.get("country")` | `str` | Country parsed from `location` (best-effort) |
| `entity.external_ids` | `dict` | `bandcamp_band_id`, `bandcamp_band_url` |

---

## Internal models (power-user access)

The internal scraper classes remain available for loading full album, artist, or track pages directly. They are not part of the primary API — use the `BandCamp` class for search and discovery.

### BandcampTrack

```python
from py_bandcamp import BandcampTrack

# Load from URL (fetches and parses the track page)
track = BandcampTrack.from_url("https://artist.bandcamp.com/track/song")

# Construct without fetching (e.g. from search results)
track = BandcampTrack({"url": "...", "title": "..."}, parse=False)

# Fetch page data later
track.parse_page()
```

| Property | Type | Description |
|---|---|---|
| `url` | `str` | Canonical Bandcamp URL |
| `title` | `str` | Track title |
| `image` | `str\|None` | Album art URL |
| `stream` | `str\|None` | Direct MP3-128 CDN URL |
| `duration` | `int` | Duration in seconds (0 if unavailable) |
| `track_num` | `int\|None` | Track number in album |
| `track_id` | `int\|None` | Bandcamp internal track id |
| `band_id` | `int\|None` | Bandcamp internal band/artist id |
| `album_id` | `int\|None` | Bandcamp internal album id |
| `data` | `dict` | All parsed metadata |
| `album` | `BandcampAlbum\|None` | Album this track belongs to (fetches page) |
| `artist` | `BandcampArtist\|None` | Artist (fetches page) |

`stream` and `duration` are populated after `parse_page()` or `from_url()`.
Search results have `parse=False` by default — call `track.parse_page()` to load them.

---

### BandcampAlbum

```python
from py_bandcamp import BandcampAlbum

album = BandcampAlbum.from_url("https://artist.bandcamp.com/album/lp")

# Construct without scraping
album = BandcampAlbum({"url": "...", "title": "..."}, scrap=False)
```

| Property | Type | Description |
|---|---|---|
| `url` | `str` | Canonical Bandcamp URL |
| `title` | `str` | Album title |
| `image` | `str\|None` | Album art URL |
| `keywords` | `list[str]` | Genre/tag keywords |
| `album_id` | `int\|None` | Bandcamp internal album id |
| `band_id` | `int\|None` | Bandcamp internal band/artist id |
| `tracks` | `list[BandcampTrack]` | Track listing (with `track_num` and `duration_iso`) |
| `featured_track` | `BandcampTrack\|None` | Featured track |
| `artist` | `BandcampArtist\|None` | Artist (fetches page) |
| `releases` | `list[dict]` | Release formats (`format`, `title`, `url`, `image`) |
| `comments` | `list[dict]` | Comments (`author`, `text`, `image`) |
| `recommendations` | `list[BandcampAlbum]` | Albums Bandcamp recommends for fans of this album |
| `related_artists` | `list[BandcampArtist]` | Unique artists from `recommendations` |

Tracks in `album.tracks` have `duration` populated from the ISO 8601 duration
on the album page. They do **not** have stream URLs — call `track.parse_page()`
on individual tracks to load those.

---

### BandcampArtist

```python
from py_bandcamp import BandcampArtist

artist = BandcampArtist.from_url("https://artist.bandcamp.com")
```

| Property | Type | Description |
|---|---|---|
| `url` | `str` | Bandcamp artist URL |
| `name` | `str` | Artist name |
| `genre` | `str\|None` | Genre string |
| `location` | `str\|None` | Location string |
| `tags` | `list[str]` | Tag strings |
| `image` | `str\|None` | Artist image URL |
| `band_id` | `int\|None` | Bandcamp internal band/artist id |
| `albums` | `list[BandcampAlbum]` | Albums (scrapes artist page) |
| `featured_album` | `BandcampAlbum` | First album from `/releases` |
| `featured_track` | `BandcampTrack\|None` | Featured track of the featured album |

---

### BandcampLabel

```python
from py_bandcamp import BandcampLabel

label = BandcampLabel.from_url("https://label.bandcamp.com")
```

| Property | Type | Description |
|---|---|---|
| `url` | `str` | Bandcamp label URL |
| `name` | `str` | Label name |
| `location` | `str\|None` | Location string |
| `tags` | `list[str]` | Tag strings |
| `image` | `str\|None` | Label image URL |

---

## Session / Custom HTTP client

By default a plain `requests.Session` is used. You can replace it with any
session-like object (e.g. one with custom headers, a retry adapter, or a mock):

```python
import requests
from py_bandcamp import set_session

# Custom session with a User-Agent header
s = requests.Session()
s.headers.update({"User-Agent": "my-app/1.0"})
set_session(s)

# Or inject a mock in tests
from unittest.mock import MagicMock
set_session(MagicMock())
```

The session object must implement `.get(url, **kwargs)` returning a response
with `.text`, `.content`, `.ok`, and `.status_code`.
