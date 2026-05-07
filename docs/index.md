# py_bandcamp

Python scraper for Bandcamp — metadata, stream URLs, search, and discovery.

## Overview

py_bandcamp scrapes Bandcamp album, track, and artist pages and converts the
results into typed [`mediavocab`](https://github.com/OpenVoiceOS/mediavocab)
`Release` and `Entity` objects. It requires no Bandcamp API key. Stream URL
extraction, recommendations, tag browse, and free-text search are all
supported.

## Key classes

| Class | Purpose | Source |
|---|---|---|
| `BandCamp` | Main facade — search, convert, stream | `py_bandcamp/__init__.py:367` |
| `BandcampAlbum` | Scrape an album page | `py_bandcamp/models.py:263` |
| `BandcampTrack` | Scrape a track page | `py_bandcamp/models.py:13` |
| `BandcampArtist` | Scrape an artist page | `py_bandcamp/models.py:590` |
| `BandcampSingle` | `/track/` release as a one-track album | `py_bandcamp/models.py:204` |
| `BandcampLabel` | Label metadata from search results | `py_bandcamp/models.py:532` |

## Contents

- [Installation & quick start](../README.md#install)
- [Getting started](getting-started.md)
- [Model reference](models.md)
- [Search and discovery](search-and-discovery.md)
- [mediavocab converters](converters.md)
- [Transport / curl_cffi](transport.md)
