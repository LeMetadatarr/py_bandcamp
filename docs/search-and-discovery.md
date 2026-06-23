# Search and discovery

## Keyword search

All search methods are on `BandCamp` (`py_bandcamp/__init__.py:430`). They
paginate automatically and deduplicate results by URL across pages.

```python
from py_bandcamp import BandCamp

# Mixed search — yields Release or Entity depending on result type
for result in BandCamp.search("electric wizard", albums=True, tracks=True,
                               artists=True, labels=False, max_pages=5):
    print(type(result).__name__, result)

# Single-type helpers
for release in BandCamp.search_tracks("astronaut problems"):
    print(release.work.title, release.uri)

for release in BandCamp.search_albums("black metal"):
    print(release.work.title)

for entity in BandCamp.search_artists("Perturbator"):
    print(entity.name, entity.extra.get("genre"))

for entity in BandCamp.search_labels("season of mist"):
    print(entity.name, entity.extra.get("location"))
```

When only one result type is requested, `search()` sends Bandcamp's
`item_type` filter parameter (`t` / `a` / `b`) for more precise results.

### Bot challenge caveat

Bandcamp's `/search` endpoint is fronted by a Fastly JS challenge. With
plain `requests` the HTML response is likely a challenge page, not results.
Install `[stealth]` and set `PYBANDCAMP_TRANSPORT=curl_cffi` to bypass it.
See [transport.md](transport.md).

Tag browse (`search_tag`) and direct page fetches (`album_to_release`, etc.)
are **not** affected by the search challenge.

---

## Tag browse

```python
# Normalises spaces to hyphens automatically
for release in BandCamp.search_tag("doom-metal", albums=True, tracks=False,
                                    artists=False, max_pages=2):
    print(release.work.title, release.uri)

# All known genre and subgenre tag names
tags = BandCamp.tags()                 # flat list[str]
tags_dict = BandCamp.tags(tag_list=False)  # {"genres": [...], "subgenres": {...}}
```

`BandCamp.search_tag` — `py_bandcamp/__init__.py:399`
`BandCamp.tags` — `py_bandcamp/__init__.py:386`

---

## Recommendations

```python
from py_bandcamp import BandCamp, BandcampAlbum

# "If you like…" section — list[Release]
recs = BandCamp.get_recommendations("https://naxatras.bandcamp.com/album/iii")
for r in recs:
    print(r.work.title, r.uri)

# Unique artists from those recommendations — list[Entity]
artists = BandCamp.get_related_artists("https://naxatras.bandcamp.com/album/iii")
for a in artists:
    print(a.name, a.extra.get("artist_url"))

# Via the model directly
album = BandcampAlbum.from_url("https://naxatras.bandcamp.com/album/iii")
for rec in album.recommendations:      # list[BandcampAlbum]
    print(rec.title, rec.url)
for a in album.related_artists:        # list[BandcampArtist]
    print(a.name, a.url)
```

`BandCamp.get_recommendations` — `py_bandcamp/__init__.py:506`
`BandcampAlbum.get_recommendations` — `py_bandcamp/models.py:438`

Bandcamp populates the recommendations widget only for albums with enough
fan/purchase data; `get_recommendations` returns an empty list when the
widget is absent.
