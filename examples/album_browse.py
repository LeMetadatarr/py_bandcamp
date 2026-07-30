"""Browse an album: metadata, tracks (with duration), releases, comments, artist."""
from py_bandcamp import BandcampAlbum

ALBUM_URL = "https://naxatras.bandcamp.com/album/iii"

print(f"=== BandcampAlbum.from_url ===")
album = BandcampAlbum.from_url(ALBUM_URL)
print(f"  title    : {album.title}")
print(f"  image    : {album.image}")
print(f"  n_tracks : {album.data.get('n_tracks')}")
print(f"  keywords : {album.keywords[:5]}")
assert album.title, "expected a title"

print("\n=== artist ===")
artist = album.artist
if artist:
    print(f"  name={artist.name}  url={artist.url}")

print("\n=== tracks (with duration) ===")
tracks = album.tracks
assert tracks, "expected track list"
for t in tracks:
    print(f"  [{t.track_num}] {t.title}  {t.duration}s")
assert all(t.duration > 0 for t in tracks), "expected all tracks to have duration"

print("\n=== featured track ===")
ft = album.featured_track
if ft:
    print(f"  {ft.title}  {ft.duration}s")

print("\n=== releases ===")
for r in album.releases:
    fmt = r.get("format", "?")
    title = r.get("title", "?")
    print(f"  {fmt} — {title}")

print("\n=== comments ===")
for c in album.comments[:3]:
    print(f"  [{c['author']}] {c['text'][:60]!r}")

print("\nDone.")
