# py_bandcamp: API reference

## `BandCamp.crawl(seeds, *, albums_per_artist=3, max_artists=0, seen=None)`

```python
@classmethod
def crawl(
    cls,
    seeds: list,
    *,
    albums_per_artist: int = 3,
    max_artists: int = 0,
    seen: set | None = None,
) -> Iterator[Entity]:
```

Generator classmethod. Performs a breadth-first search over the Bandcamp artist
graph starting from *seeds* and yields `mediavocab.Entity` for each discovered
artist.

**Discovery strategy**: for each artist URL dequeued from the frontier:

1. Fetches the artist page (`BandcampArtist`, `scrap=True`).
2. Yields an `Entity` for that artist.
3. Fetches up to `albums_per_artist` albums and scrapes their
   `related_artists` (the "fans also bought" widget) to expand the frontier.
4. If `artist.data["is_label"]` is truthy, calls `BandCamp.get_label_artists(url)`
   and enqueues every roster member URL.

Relies exclusively on artist-subdomain pages, which are not behind the
Cloudflare bot challenge that protects `bandcamp.com/search`.

**Parameters**

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `seeds` | `list[str]` | none | Bandcamp artist or label URLs to start from |
| `albums_per_artist` | `int` | `3` | Albums checked per artist when expanding via recommendations |
| `max_artists` | `int` | `0` | Stop after this many entities yielded. `0` means unlimited |
| `seen` | `set \| None` | `None` | Mutable URL set shared across calls for resumability, mutated in-place |

**Returns**: `Iterator[mediavocab.Entity]`

**Example**

```python
from py_bandcamp import BandCamp

seen = set()
for entity in BandCamp.crawl(["https://enslaved.bandcamp.com"], max_artists=10, seen=seen):
    print(entity.name, entity.extra.get("artist_url"))
# Pass the same seen set to resume without revisiting already-visited URLs
for entity in BandCamp.crawl(["https://neurosis.bandcamp.com"], max_artists=10, seen=seen):
    print(entity.name)
```

---

This file previously listed all public methods. See the split docs instead:

- [Model reference](models.md)
- [Search and discovery](search-and-discovery.md)
- [mediavocab converters](converters.md)
- [Transport / curl_cffi](transport.md)
- [Getting started](getting-started.md)
- [Index](index.md)

---
[Home](index.md)
