"""Fetch track metadata, stream URL, and lyrics."""
from py_bandcamp import BandCamp, BandcampTrack

TRACK_URL = "https://deadunicorn.bandcamp.com/track/astronaut-problems"

print(f"=== BandcampTrack.from_url ===")
track = BandcampTrack.from_url(TRACK_URL)
print(f"  title    : {track.title}")
print(f"  duration : {track.duration}s")
print(f"  track_num: {track.track_num}")
print(f"  image    : {track.image}")
print(f"  stream   : {track.stream}")
assert track.title, "expected a title"
assert track.stream, "expected a stream URL"

print("\n=== BandCamp.get_stream_url ===")
url = BandCamp.get_stream_url(TRACK_URL)
print(f"  {url}")
assert url.startswith("https://"), "expected https stream URL"

print("\n=== BandCamp.get_streams (batch) ===")
urls = BandCamp.get_streams([TRACK_URL])
print(f"  {urls[0]}")
assert len(urls) == 1

print("\n=== artist from track page ===")
artist = track.artist
if artist:
    print(f"  name={artist.name}  url={artist.url}")
else:
    print("  (none)")

print("\n=== album from track page ===")
album = track.album
if album:
    print(f"  title={album.title}  url={album.url}")
else:
    print("  (none)")

print("\n=== get_track_lyrics ===")
lyrics = BandCamp.get_track_lyrics(TRACK_URL)
print(f"  result: {lyrics[:60]!r}")

print("\nDone.")
