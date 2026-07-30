"""02_track_details — track metadata, stream URL, and lyrics via BandcampTrack."""
from py_bandcamp import BandCamp, BandcampTrack

TRACK_URL = "https://deadunicorn.bandcamp.com/track/astronaut-problems"

# --- low-level scraper model ---
track = BandcampTrack.from_url(TRACK_URL)
print(f"Title     : {track.title}")
print(f"Duration  : {track.duration}s")
print(f"Track num : {track.track_num}")
print(f"Track id  : {track.track_id}")
print(f"Band id   : {track.band_id}")
print(f"Album id  : {track.album_id}")
print(f"Image     : {track.image}")
print(f"Stream    : {track.stream}")

print("\n--- parent album ---")
album = track.album
if album:
    print(f"  {album.title}  {album.url}")

print("\n--- parent artist ---")
artist = track.artist
if artist:
    print(f"  {artist.name}  {artist.url}")

# --- mediavocab Release ---
print("\n--- mediavocab Release ---")
release = BandCamp.track_to_release(TRACK_URL)
print(f"  title   : {release.work.title}")
print(f"  runtime : {release.work.runtime}s")
print(f"  codec   : {release.codec} / {release.bitrate} kbps / {release.audio_channels}")
print(f"  ids     : {sorted(release.external_ids)}")

# --- direct stream URL ---
print("\n--- stream URL ---")
url = BandCamp.get_stream_url(TRACK_URL)
print(f"  {url}")

# --- lyrics ---
print("\n--- lyrics ---")
lyrics = BandCamp.get_track_lyrics(TRACK_URL)
print(f"  {lyrics[:120]!r}")
