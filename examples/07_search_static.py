"""07_search_static — tag and genre browse (no curl_cffi required).

Bandcamp's /search endpoint is blocked by a Fastly JS challenge for vanilla
requests traffic. Tag browse, album/track page fetches, and recommendations
are NOT affected. This example uses only those unblocked paths.

For keyword search with curl_cffi, see 09_custom_session.py.
"""
from py_bandcamp import BandCamp

# All known genre/subgenre tag names (fetches bandcamp.com/tags)
tags = BandCamp.tags()
print(f"Total tags known: {len(tags)}")
print(f"Sample: {tags[:8]}")
print()

# Browse by tag — yields Release objects page by page
for tag in ("doom-metal", "black-metal"):
    print(f"=== tag: {tag!r} (1 page) ===")
    for i, r in enumerate(BandCamp.search_tag(tag, albums=True, tracks=False,
                                               artists=False, max_pages=1)):
        artist = r.work.credits[0].entity.name if r.work.credits else "?"
        print(f"  [{i+1}] {r.work.title!r}  by {artist}  {r.uri}")
        if i >= 4:
            break
    print()
