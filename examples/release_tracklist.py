"""Convert a Bandcamp album URL to a fully-populated mediavocab Release
and iterate the ordered tracklist.

This is the high-fidelity path: ``BandCamp.album_to_release`` fetches the
album page, walks every track, and emits a single ``Release`` whose
``work.tracklist`` is a list of ``Appearance`` entries — one per track,
in order, with title and runtime per track. Ideal for archival /
indexing workflows.
"""
from py_bandcamp import BandCamp

ALBUM_URL = "https://naxatras.bandcamp.com/album/iii"

release = BandCamp.album_to_release(ALBUM_URL, include_tracklist=True)

print(f"=== {release.work.title} ===")
print(f"  uri          : {release.uri}")
print(f"  release_date : {release.release_date}")
print(f"  artist       : "
      f"{release.work.credits[0].entity.name if release.work.credits else '?'}")
print(f"  label        : {release.label.name if release.label else '(self-released)'}")
print(f"  genres       : {release.work.content_genres[:5]}")
print(f"  audio        : "
      f"{release.codec} / {release.bitrate} kbps / {release.audio_channels}")
print(f"  ids          : {sorted(release.external_ids)}")

print("\n=== tracklist ===")
for appearance in release.work.tracklist:
    runtime = f"{appearance.work.runtime:.0f}s" if appearance.work.runtime else "?"
    print(f"  [{appearance.position}] {appearance.work.title}  ({runtime})")

assert release.work.tracklist, "expected a non-empty tracklist"
print("\nDone.")
