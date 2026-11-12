"""Browse an artist: albums list, featured album and track."""
from py_bandcamp import BandcampArtist

ARTIST_URL = "https://dopethrone.bandcamp.com"

print(f"=== BandcampArtist.from_url ===")
artist = BandcampArtist.from_url(ARTIST_URL)
print(f"  name    : {artist.name}")
print(f"  genre   : {artist.genre}")
print(f"  location: {artist.location}")
print(f"  tags    : {artist.tags}")
print(f"  image   : {artist.image}")

print("\n=== albums ===")
albums = artist.albums
print(f"  {len(albums)} albums")
for a in albums[:4]:
    print(f"  {a.title}  {a.url}")
assert albums, "expected at least one album"

print("\n=== featured album ===")
fa = artist.featured_album
if fa:
    print(f"  {fa.title}  {fa.url}")

print("\n=== featured track ===")
ft = artist.featured_track
if ft:
    print(f"  {ft.title}  {ft.duration}s  stream={ft.stream}")

print("\nDone.")
