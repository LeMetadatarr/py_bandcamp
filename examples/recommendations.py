"""Discover related albums and artists from a seed album or by genre/tag."""
from py_bandcamp import BandCamp, BandcampAlbum

SEED_ALBUM = "https://naxatras.bandcamp.com/album/iii"


def _credit_name(release):
    return release.work.credits[0].entity.name if release.work.credits else "?"


print(f"=== recommendations for {SEED_ALBUM} ===")
recs = BandCamp.get_recommendations(SEED_ALBUM)
print(f"  {len(recs)} recommended albums")
for r in recs[:5]:
    print(f"  {r.work.title!r}  by {_credit_name(r)}  {r.uri}")
assert recs, "expected at least one recommendation"

print("\n=== related artists ===")
artists = BandCamp.get_related_artists(SEED_ALBUM)
print(f"  {len(artists)} unique artists")
for a in artists[:5]:
    print(f"  {a.name}  {a.extra.get('artist_url')}")
assert artists, "expected at least one related artist"

print("\n=== browse by genre/tag: 'doom-metal' ===")
for i, r in enumerate(BandCamp.search_tag("doom-metal", albums=True, tracks=False,
                                           artists=False, max_pages=1)):
    print(f"  [{i+1}] {r.work.title!r}  {r.uri}")
    if i >= 4:
        break

print("\n=== album.recommendations property ===")
album = BandcampAlbum.from_url(SEED_ALBUM)
recs2 = album.recommendations
print(f"  {len(recs2)} recommended albums via property")
assert recs2

print("\n=== album.related_artists property ===")
related = album.related_artists
print(f"  {len(related)} related artists via property")
for a in related[:3]:
    print(f"  {a.name}  {a.url}")

print("\nDone.")
