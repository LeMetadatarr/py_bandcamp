"""08_to_mediavocab — full Release and Entity field walk-through.

Shows every field populated by album_to_release and track_to_release,
including tracklist Appearance entries and external_ids.
"""
from py_bandcamp import BandCamp

ALBUM_URL = "https://naxatras.bandcamp.com/album/iii"
TRACK_URL = "https://deadunicorn.bandcamp.com/track/astronaut-problems"

# --- Album Release ---
print("=" * 60)
print("ALBUM → Release")
print("=" * 60)
r = BandCamp.album_to_release(ALBUM_URL, include_tracklist=True)

print(f"uri              : {r.uri}")
print(f"image            : {r.image}")
print(f"stream_mode      : {r.stream_mode}")
print(f"codec            : {r.codec}")
print(f"bitrate          : {r.bitrate}")
print(f"audio_channels   : {r.audio_channels}")
print(f"release_date     : {r.release_date}")
print(f"license          : {r.license!r}")
print(f"license open     : {r.license.is_open() if r.license else False}")
print(f"label            : {r.label.name if r.label else None}")

w = r.work
print(f"work.title       : {w.title}")
print(f"work.media_type  : {w.media_type}")
print(f"work.genres      : {w.content_genres}")

if w.credits:
    c = w.credits[0]
    print(f"credit.name      : {c.entity.name}")
    print(f"credit.kind      : {c.entity.kind}")
    print(f"credit.role      : {c.relation_role}")
    print(f"credit.section   : {c.section}")

print(f"external_ids keys: {sorted(r.external_ids)}")
for k, v in sorted(r.external_ids.items()):
    print(f"  {k}: {v}")

print(f"\ntracklist ({len(w.tracklist)} tracks):")
for a in w.tracklist:
    runtime = f"{a.work.runtime:.0f}s" if a.work.runtime else "?"
    tid = a.work.external_ids.get("bandcamp_track_id", "")
    print(f"  [{a.position}] {a.work.title}  {runtime}  disc={a.disc}  track_id={tid}")

# --- Track Release ---
print()
print("=" * 60)
print("TRACK → Release")
print("=" * 60)
t = BandCamp.track_to_release(TRACK_URL)

print(f"uri              : {t.uri}")
print(f"work.title       : {t.work.title}")
print(f"work.runtime     : {t.work.runtime}s")
print(f"codec            : {t.codec}")
print(f"bitrate          : {t.bitrate}")
print(f"audio_channels   : {t.audio_channels}")
print(f"external_ids     : {dict(sorted(t.external_ids.items()))}")

if t.work.credits:
    print(f"credit.name      : {t.work.credits[0].entity.name}")
    print(f"credit.role      : {t.work.credits[0].relation_role}")
