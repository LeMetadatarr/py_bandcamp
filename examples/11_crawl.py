from py_bandcamp import BandCamp

seen = set()
for entity in BandCamp.crawl(["https://enslaved.bandcamp.com"], max_artists=5, seen=seen):
    print(entity.name, entity.extra.get("artist_url"))
# resume from same seen set
for entity in BandCamp.crawl(["https://neurosis.bandcamp.com"], max_artists=5, seen=seen):
    print(entity.name)
