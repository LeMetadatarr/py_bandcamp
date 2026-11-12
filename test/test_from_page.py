"""The parsers that work on a page already fetched, so a caller can fetch it with its own transport."""
import json
from unittest.mock import patch

from py_bandcamp import BandCamp
from py_bandcamp.models import BandcampAlbum, BandcampArtist

URL = "https://a.bandcamp.com/album/lp"
LD = {"@type": "MusicAlbum", "@id": URL, "name": "LP", "datePublished": "27 Mar 2020 00:00:00 GMT", "keywords": "rock, indie",
      "byArtist": {"@type": "MusicGroup", "name": "B", "@id": "https://a.bandcamp.com"},
      "track": {"itemListElement": [{"@type": "ListItem", "position": 1, "item": {"@id": "https://a.bandcamp.com/track/t1", "name": "T1",
                                                                                  "duration": "P00H03M00S", "additionalProperty": []}}]}}
PAGE = f'<html><script type="application/ld+json">{json.dumps(LD)}</script></html>'
SEARCH = ('<li class="searchresult"><div class="itemtype">ALBUM</div><div class="heading"><a href="https://a.bandcamp.com/album/x?from=s">X</a></div>'
          '<div class="subhead">by B</div></li>'
          '<li class="searchresult"><div class="itemtype">TRACK</div><div class="heading"><a href="https://a.bandcamp.com/track/y?from=s">Y</a></div>'
          '<div class="subhead">from X by B</div></li>'
          '<li class="searchresult"><div class="itemtype">ARTIST</div><div class="heading"><a href="https://a.bandcamp.com?from=s">B</a></div></li>')


def test_album_data_from_a_fetched_page_makes_no_request():
    with patch("py_bandcamp.models.requests") as m:
        data = BandcampAlbum.data_from_page(PAGE, URL)
    assert not m.get.called
    assert (data["title"], data["artist"], data["keywords"], data["datePublished"]) == ("LP", "B", ["rock", "indie"], "27 Mar 2020 00:00:00 GMT")


def test_tracks_from_a_fetched_page_makes_no_request():
    with patch("py_bandcamp.models.requests") as m:
        tracks = BandcampAlbum.tracks_from_page(PAGE, URL)
    assert not m.get.called
    assert [(t.title, t.url, t.duration) for t in tracks] == [("T1", "https://a.bandcamp.com/track/t1", 180)]


def test_get_tracks_and_get_album_data_still_fetch_the_url():
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value.text = PAGE
        assert BandcampAlbum.get_album_data(URL)["title"] == "LP"
        assert [t.title for t in BandcampAlbum.get_tracks(URL)] == ["T1"]
    assert [c.args[0] for c in m.get.call_args_list] == [URL, URL]


def test_albums_from_an_artist_page_already_fetched():
    page = ('<a href="/album/one"><div class="art"><img src="i.jpg"></div><p class="title">One</p></a>'
            '<a href="/track/two"><p class="title">Two</p></a>')
    albums, singles = BandcampArtist.albums_from_page(page, "https://a.bandcamp.com", include_singles=True)
    assert [(a.title, a.url) for a in albums] == [("One", "https://a.bandcamp.com/album/one")]
    assert [s.url for s in singles] == ["https://a.bandcamp.com/track/two"]


def test_parse_search_page_returns_only_the_kinds_asked_for_in_page_order():
    def kinds(**kw):
        return [type(x).__name__ for x in BandCamp.parse_search_page(SEARCH, **kw)]
    assert kinds() == ["BandcampAlbum", "BandcampTrack", "BandcampArtist"]
    assert kinds(albums=False, artists=False) == ["BandcampTrack"]
    assert kinds(tracks=False, artists=False) == ["BandcampAlbum"]
    assert kinds(albums=False, tracks=False, artists=False) == []
    assert BandCamp.parse_search_page(SEARCH.encode(), tracks=False, artists=False)[0].url == "https://a.bandcamp.com/album/x"


def test_search_still_yields_releases_and_skips_repeats_across_pages():
    with patch("py_bandcamp.requests") as m:
        m.get.return_value.content = SEARCH.encode()
        out = list(BandCamp.search("x", max_pages=2))
    assert [r.work.title for r in out if hasattr(r, "work")] == ["X", "y"]
    assert m.get.call_count == 2
