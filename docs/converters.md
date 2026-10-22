# mediavocab converters

`BandCamp.album_to_release` and `BandCamp.track_to_release` convert raw
Bandcamp scraper models into fully typed
[`mediavocab`](https://github.com/TigreGotico/mediavocab) objects.

All search helpers (`search_*`, `get_recommendations`) call the internal
`_album_to_release` / `_track_to_release` functions automatically. You only
call the public converters directly when you already hold a raw model object.

---

## `BandCamp.album_to_release`: `py_bandcamp/__init__.py:492`

```python
from py_bandcamp import BandCamp

release = BandCamp.album_to_release(
    "https://naxatras.bandcamp.com/album/iii",
    include_tracklist=True,   # default True, triggers track iteration
)
```

Accepts a URL string or a `BandcampAlbum` instance.
`include_tracklist=False` skips per-track iteration. Use this in search or
recommendation loops where the tracklist isn't needed.

### Release fields: album

```python
release.uri                              # "https://naxatras.bandcamp.com/album/iii"
release.image                            # artwork URL or ""
release.stream_mode                      # StreamMode.ON_DEMAND
release.codec                            # "mp3"
release.bitrate                          # "128"  (kbps)
release.audio_channels                   # "stereo"
release.release_date                     # "2018-08-17" (IsoDate string) or None
release.license                          # License object (.identifier "CC-BY-SA-4.0") or None (from CC tags only)
release.license.is_open() if release.license else False  # True for CC* / CC0 / PD

release.work.title                       # "III"
release.work.media_type                  # MediaType.MUSIC
release.work.content_genres              # ["stoner-rock", "doom-metal", ...]
release.work.credits[0].entity.name      # "Naxatras"
release.work.credits[0].relation_role    # RelationRole.CREATOR
release.work.tracklist                   # list[Appearance], populated when include_tracklist=True

release.label                            # EntityRef(name="...", kind=EntityKind.ORGANISATION)
                                         # None when publisher == artist (self-released)

release.external_ids["bandcamp_album_id"]   # numeric album id string
release.external_ids["bandcamp_band_id"]    # numeric band id string
release.external_ids["bandcamp_album_url"]  # canonical album URL
release.external_ids["bandcamp_band_url"]   # artist root URL
```

### Tracklist entries (`Appearance`)

```python
for a in release.work.tracklist:
    a.position          # int track number
    a.disc              # 1 (Bandcamp has no multi-disc concept)
    a.work.title        # track title
    a.work.runtime      # float seconds or None
    a.work.external_ids["bandcamp_track_id"]   # numeric track id string (when known)
    a.work.external_ids["bandcamp_track_url"]  # track URL (when known)
```

`_album_to_release`: `py_bandcamp/__init__.py:209`

---

## `BandCamp.track_to_release`: `py_bandcamp/__init__.py:503`

```python
from py_bandcamp import BandCamp

release = BandCamp.track_to_release(
    "https://deadunicorn.bandcamp.com/track/astronaut-problems"
)
```

Accepts a URL string or a `BandcampTrack` instance.

### Release fields: track

```python
release.uri                              # canonical track URL
release.image                            # artwork URL or ""
release.work.title                       # track title
release.work.runtime                     # float seconds or None
release.work.credits[0].relation_role    # RelationRole.PERFORMER
release.codec                            # "mp3" when stream URL is present, else ""
release.bitrate                          # "128" when stream URL is present, else ""
release.audio_channels                   # "stereo" when stream URL is present, else ""

release.external_ids["bandcamp_track_id"]
release.external_ids["bandcamp_track_url"]
release.external_ids["bandcamp_band_id"]
release.external_ids["bandcamp_band_url"]
release.external_ids["bandcamp_album_id"]   # only when track belongs to an album
```

`_track_to_release`: `py_bandcamp/__init__.py:156`

---

## Genre mapping: `py_bandcamp/__init__.py:35`

Bandcamp tags are normalised to `mediavocab.taxonomy.genre` `GENRE_*` tokens
where a mapping exists. Tags without a mapping pass through verbatim so no
information is lost. Common aliases (`hip-hop`, `r&b`, `dnb`, `edm`) are
handled by `_GENRE_ALIASES`.

## License inference: `py_bandcamp/__init__.py:74`

`release.license` is populated only when Bandcamp keyword tags contain a
recognisable Creative Commons marker (`cc-by`, `cc-by-sa`, `cc0`, etc.).
No CC hint → empty string. Bandcamp does not assert All-Rights-Reserved
in machine-readable form so the library does not guess it.

## Label / publisher: `py_bandcamp/__init__.py:274`

`release.label` is set to an `EntityRef` for the ld+json `publisher` field
when `publisher != artist`. Self-released albums (the common case) have
`release.label = None`.

## Entity converters

`_artist_to_entity`: `py_bandcamp/__init__.py:290`
`_label_to_entity`: `py_bandcamp/__init__.py:314`

Both are called automatically by `search_artists` / `search_labels` /
`get_related_artists`. They populate `entity.extra` with `artist_url`,
`image`, `location`, `country` (parsed from `"City, Country"` format), and
`genre` (artists only).

---
[← Search and discovery](search-and-discovery.md) · [Home](index.md) · [Transport / curl_cffi →](transport.md)
