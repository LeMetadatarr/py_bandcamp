# Model reference

All scraper models live in `py_bandcamp/models.py`. They are constructed by
fetching and parsing Bandcamp pages — not by calling a public API.

---

## BandcampAlbum — `models.py:263`

```python
from py_bandcamp import BandcampAlbum

album = BandcampAlbum.from_url("https://naxatras.bandcamp.com/album/iii")
# Equivalent: BandcampAlbum({"url": "..."})  # scrap=True by default
```

| Property | Type | Notes |
|---|---|---|
| `url` | `str` | Canonical Bandcamp URL |
| `title` | `str` | Album title |
| `image` | `str\|None` | Artwork URL |
| `keywords` | `list[str]` | Genre/tag keywords from ld+json |
| `album_id` | `int\|None` | Numeric album id from `data-tralbum` |
| `band_id` | `int\|None` | Numeric band/artist id |
| `tracks` | `list[BandcampTrack]` | Track listing with `duration` and `track_num`; no stream URLs |
| `featured_track` | `BandcampTrack\|None` | Track at `featured_track_num` index |
| `artist` | `BandcampArtist\|None` | From `byArtist` in ld+json (extra fetch) |
| `releases` | `list[dict]` | Physical/digital release formats (`format`, `title`, `url`, `image`) |
| `comments` | `list[dict]` | `author`, `text`, `image` |
| `recommendations` | `list[BandcampAlbum]` | "If you like…" albums (scrapes `#recommendations_container`) |
| `related_artists` | `list[BandcampArtist]` | Unique artists from recommendations |

`BandcampAlbum.get_tracks` — `models.py:388` parses both ld+json and
`data-tralbum` to merge numeric IDs with structured track data.

Tracks returned by `album.tracks` have `duration` from ISO 8601 on the album
page but no `stream` URL. Call `track.parse_page()` on individual tracks to
load stream URLs.

---

## BandcampTrack — `models.py:13`

```python
from py_bandcamp import BandcampTrack

track = BandcampTrack.from_url("https://deadunicorn.bandcamp.com/track/astronaut-problems")
# Equivalent: BandcampTrack({"url": "..."})  # parse=True by default
```

| Property | Type | Notes |
|---|---|---|
| `url` | `str` | Canonical Bandcamp URL |
| `title` | `str` | Track title |
| `image` | `str\|None` | Album art URL |
| `stream` | `str\|None` | Direct MP3-128 CDN URL — time-limited |
| `duration` | `int` | Seconds; 0 if unavailable |
| `track_num` | `int\|None` | Position in album |
| `track_id` | `int\|None` | Bandcamp internal track id |
| `band_id` | `int\|None` | Bandcamp internal band/artist id |
| `album_id` | `int\|None` | Album this track belongs to (if any) |
| `album` | `BandcampAlbum\|None` | Parent album (extra fetch via `inAlbum`) |
| `artist` | `BandcampArtist\|None` | Artist (extra fetch via `byArtist`) |

`BandcampTrack.get_track_data` — `models.py:118` parses ld+json and
`data-tralbum` to extract stream URL, numeric IDs, and duration.

---

## BandcampArtist — `models.py:590`

```python
from py_bandcamp import BandcampArtist

artist = BandcampArtist.from_url("https://dopethrone.bandcamp.com")
```

| Property | Type | Notes |
|---|---|---|
| `url` | `str` | Artist root URL |
| `name` | `str` | Artist name |
| `genre` | `str\|None` | Genre string |
| `location` | `str\|None` | Location string ("City, Country") |
| `image` | `str\|None` | Artist image |
| `band_id` | `int\|None` | Scraped from `/releases` page (`item_sellers` dict key) |
| `albums` | `list[BandcampAlbum]` | Scrapes artist root page |
| `featured_album` | `BandcampAlbum` | First entry from `/releases` |
| `featured_track` | `BandcampTrack\|None` | Featured track of the featured album |

`BandcampArtist.get_albums` — `models.py:685` accepts `include_singles=True`
to also return `BandcampSingle` objects for `/track/` hrefs.

`BandcampArtist._scrap_band_id` — `models.py:599` makes an extra GET to
`<artist_url>/releases` to extract the numeric band id from `item_sellers`.

---

## BandcampSingle — `models.py:204`

A `/track/` release treated as a one-track album.

```python
from py_bandcamp.models import BandcampSingle

single = BandcampSingle.from_url("https://artist.bandcamp.com/track/song")
```

| Property | Type | Notes |
|---|---|---|
| `url` | `str` | Track page URL |
| `title` | `str` | Track title |
| `artist` | `str\|None` | Artist name string |
| `image` | `str\|None` | Artwork URL |
| `tracks` | `list[BandcampTrack]` | Always a single-element list |

---

## BandcampLabel — `models.py:532`

Label objects are produced by `BandCamp.search_labels` parsing search result
HTML. `BandcampLabel.scrap()` is a no-op (no label detail page is scraped).

```python
from py_bandcamp.models import BandcampLabel

label = BandcampLabel.from_url("https://label.bandcamp.com")
```

| Property | Type | Notes |
|---|---|---|
| `url` | `str` | Label root URL |
| `name` | `str` | Label name |
| `location` | `str\|None` | Location string |
| `tags` | `list[str]` | Tag strings |
| `image` | `str\|None` | Label image URL |
