"""01_quickstart — fetch one album by URL and print its metadata."""
from py_bandcamp import BandCamp

ALBUM_URL = "https://naxatras.bandcamp.com/album/iii"

release = BandCamp.album_to_release(ALBUM_URL, include_tracklist=True)

artist = release.work.credits[0].entity.name if release.work.credits else "(unknown)"
label = release.label.name if release.label else "(self-released)"

print(f"Title        : {release.work.title}")
print(f"Artist       : {artist}")
print(f"Label        : {label}")
print(f"Released     : {release.release_date}")
print(f"Genres       : {release.work.content_genres[:5]}")
print(f"License      : {release.license or '(none)'}")
print(f"Open license : {release.license_model.is_open() if release.license_model else False}")
print(f"Audio        : {release.codec} / {release.bitrate} kbps / {release.audio_channels}")
print(f"Album URL    : {release.uri}")
print(f"Image        : {release.image}")
print()
print(f"Tracklist ({len(release.work.tracklist)} tracks):")
for a in release.work.tracklist:
    runtime = f"{a.work.runtime:.0f}s" if a.work.runtime else "?"
    print(f"  [{a.position}] {a.work.title}  ({runtime})")
