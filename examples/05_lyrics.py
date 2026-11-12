"""05_lyrics — fetch and print track lyrics.

Returns "lyrics unavailable" when Bandcamp has no lyrics for the track.
Lyrics are scraped from the div.lyricsText element on the track page.
"""
from py_bandcamp import BandCamp

TRACKS = [
    "https://deadunicorn.bandcamp.com/track/astronaut-problems",
]

for url in TRACKS:
    print(f"=== {url} ===")
    lyrics = BandCamp.get_track_lyrics(url)
    print(lyrics[:500])
    print()
