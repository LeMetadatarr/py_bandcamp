"""Search Bandcamp for tracks, albums, artists, labels, and by tag."""
from mediavocab import Release, Entity

from py_bandcamp import BandCamp

print("=== search_tracks: 'astronaut problems' ===")
for i, release in enumerate(BandCamp.search_tracks("astronaut problems")):
    artist = release.work.credits[0].entity.name if release.work.credits else ""
    print(f"  [{i+1}] {release.work.title}  artist={artist}  url={release.uri}")
    if i >= 2: break

print("\n=== search_albums: 'iii' ===")
for i, release in enumerate(BandCamp.search_albums("iii")):
    artist = release.work.credits[0].entity.name if release.work.credits else ""
    print(f"  [{i+1}] {release.work.title}  artist={artist}  url={release.uri}")
    if i >= 2: break

print("\n=== search_artists: 'Perturbator' ===")
for i, entity in enumerate(BandCamp.search_artists("Perturbator")):
    genre = entity.extra.get("genre", "")
    location = entity.extra.get("location", "")
    url = entity.extra.get("artist_url", "")
    print(f"  [{i+1}] {entity.name}  genre={genre}  location={location}  url={url}")
    if i >= 2: break

print("\n=== search_labels: 'season of mist' ===")
for i, entity in enumerate(BandCamp.search_labels("season of mist")):
    location = entity.extra.get("location", "")
    url = entity.extra.get("artist_url", "")
    print(f"  [{i+1}] {entity.name}  location={location}  url={url}")
    if i >= 2: break

print("\n=== search (mixed): 'electric wizard' ===")
for i, result in enumerate(BandCamp.search("electric wizard", albums=True, tracks=True,
                                            artists=True, labels=False)):
    if isinstance(result, Release):
        print(f"  [{i+1}] Release  {result.work.title}  url={result.uri}")
    elif isinstance(result, Entity):
        print(f"  [{i+1}] Entity   {result.name}  url={result.extra.get('artist_url', '')}")
    if i >= 4: break

print("\n=== search_tag: 'doom-metal' ===")
for i, release in enumerate(BandCamp.search_tag("doom-metal", albums=True, tracks=False,
                                                 artists=False, max_pages=1)):
    print(f"  [{i+1}] {release.work.title}  url={release.uri}")
    if i >= 2: break

print("\n=== tags() ===")
tags = BandCamp.tags()
print(f"  {len(tags)} tags total. Sample: {tags[:6]}")
assert "black-metal" in tags, "expected black-metal in tag list"
assert "doom" in tags, "expected doom in tag list"
print("  OK")

print("\nDone.")
