"""04_get_streams — extract MP3-128 stream URLs from track pages.

Stream URLs are time-limited CDN tokens (roughly 1 hour). Do not cache them.
"""
from py_bandcamp import BandCamp

TRACKS = [
    "https://deadunicorn.bandcamp.com/track/astronaut-problems",
]

# Single URL
url = BandCamp.get_stream_url(TRACKS[0])
print(f"Single stream URL:\n  {url}\n")

# Batch
urls = BandCamp.get_streams(TRACKS)
print(f"Batch ({len(urls)} results):")
for track_url, stream_url in zip(TRACKS, urls):
    print(f"  {track_url}")
    print(f"  -> {stream_url}")

# Stream URL from a track page via BandcampAlbum.tracks
# (tracks parsed from album pages do NOT include stream URLs —
#  call parse_page() to load them)
from py_bandcamp import BandcampAlbum

ALBUM_URL = "https://naxatras.bandcamp.com/album/iii"
album = BandcampAlbum.from_url(ALBUM_URL)
tracks = album.tracks
print(f"\nAlbum '{album.title}' — {len(tracks)} tracks")
print("Fetching stream URL for track 1 via parse_page():")
t = tracks[0]
t.parse_page()
print(f"  stream: {t.stream}")
