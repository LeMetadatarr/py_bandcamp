"""03_artist_discography — artist metadata, albums, singles, and band_id."""
from py_bandcamp import BandcampArtist

ARTIST_URL = "https://dopethrone.bandcamp.com"

artist = BandcampArtist.from_url(ARTIST_URL)
print(f"Name     : {artist.name}")
print(f"Genre    : {artist.genre}")
print(f"Location : {artist.location}")
print(f"Image    : {artist.image}")
print(f"Band id  : {artist.band_id}")

print("\n--- albums ---")
albums, singles = artist.get_albums(ARTIST_URL, include_singles=True)
print(f"  {len(albums)} albums, {len(singles)} singles")
for a in albums[:5]:
    print(f"  [album]  {a.title}  {a.url}")
for s in singles[:3]:
    print(f"  [single] {s.title}  {s.url}")

print("\n--- featured album ---")
fa = artist.featured_album
if fa:
    print(f"  {fa.title}  {fa.url}")

print("\n--- featured track ---")
ft = artist.featured_track
if ft:
    print(f"  {ft.title}  {ft.duration}s  stream={ft.stream}")
