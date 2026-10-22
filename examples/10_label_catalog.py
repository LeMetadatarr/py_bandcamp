"""10_label_catalog — label-level browsing via search_labels.

BandcampLabel objects are produced by parsing search result HTML.
The label detail page is not scraped (BandcampLabel.scrap() is a no-op).
To browse a label's catalog, search by label name and then follow album URLs.
"""
from py_bandcamp import BandCamp
from py_bandcamp.models import BandcampLabel

LABEL_NAME = "season of mist"

print(f"=== search_labels: {LABEL_NAME!r} ===")
entities = list(BandCamp.search_labels(LABEL_NAME))
print(f"  {len(entities)} label results")
for e in entities[:5]:
    print(f"  {e.name}")
    print(f"    location : {e.extra.get('location')}")
    print(f"    url      : {e.extra.get('artist_url')}")
    print(f"    ids      : {e.external_ids}")

# BandcampLabel.from_url constructs a label object without scraping
# (scrap=False — the label detail page is not fetched)
if entities:
    label_url = entities[0].extra.get("artist_url", "")
    if label_url:
        label = BandcampLabel.from_url(label_url)
        print(f"\n  BandcampLabel.from_url({label_url!r})")
        print(f"    name     : {label.name}")
        print(f"    location : {label.location}")
        print(f"    tags     : {label.tags}")

# Label catalog via search_albums scoped to the label name
print(f"\n=== albums attributed to '{LABEL_NAME}' (search) ===")
for i, r in enumerate(BandCamp.search_albums(LABEL_NAME)):
    artist = r.work.credits[0].entity.name if r.work.credits else "?"
    label_ref = r.label.name if r.label else None
    print(f"  [{i+1}] {r.work.title}  by {artist}  label={label_ref}  {r.uri}")
    if i >= 4:
        break
