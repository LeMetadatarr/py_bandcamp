"""06_recommendations — "If you like…" albums and related artists from a seed."""
from py_bandcamp import BandCamp, BandcampAlbum

SEED = "https://naxatras.bandcamp.com/album/iii"


def _artist(release):
    return release.work.credits[0].entity.name if release.work.credits else "?"


print(f"=== recommended albums for {SEED} ===")
recs = BandCamp.get_recommendations(SEED)
print(f"  {len(recs)} results")
for r in recs[:6]:
    print(f"  {r.work.title!r}  by {_artist(r)}  {r.uri}")

print(f"\n=== related artists ===")
artists = BandCamp.get_related_artists(SEED)
print(f"  {len(artists)} unique artists")
for a in artists[:6]:
    print(f"  {a.name}  {a.extra.get('artist_url')}")

print(f"\n=== album.recommendations (model property) ===")
album = BandcampAlbum.from_url(SEED)
for rec in album.recommendations[:4]:
    print(f"  {rec.title}  {rec.url}")

print(f"\n=== album.related_artists (model property) ===")
for a in album.related_artists[:4]:
    print(f"  {a.name}  {a.url}")
