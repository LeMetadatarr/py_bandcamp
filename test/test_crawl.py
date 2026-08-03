"""Unit tests for BandCamp.crawl() — no live network calls."""
from unittest.mock import MagicMock, patch

from mediavocab import Entity

from py_bandcamp import BandCamp
from py_bandcamp.models import BandcampArtist


def _make_artist(name, url, albums=None, is_label=False):
    """Build a BandcampArtist stub without network access."""
    data = {"name": name, "url": url}
    if is_label:
        data["is_label"] = True
    a = BandcampArtist(data, scrap=False)
    a._albums = albums or []
    return a


def _make_album(url, related=None):
    from py_bandcamp.models import BandcampAlbum
    alb = BandcampAlbum({"url": url, "album_name": "Album"}, scrap=False)
    alb._related = related or []
    return alb


def test_crawl_yields_entity():
    artist = _make_artist("Enslaved", "https://enslaved.bandcamp.com")

    with patch("py_bandcamp.BandcampArtist") as MockArtist:
        instance = MagicMock()
        instance.name = "Enslaved"
        instance.url = "https://enslaved.bandcamp.com"
        instance.data = {"name": "Enslaved", "url": "https://enslaved.bandcamp.com"}
        instance.band_id = None
        instance.image = None
        instance.location = None
        instance.genre = None
        instance.albums = []
        MockArtist.return_value = instance

        results = list(BandCamp.crawl(["https://enslaved.bandcamp.com"], max_artists=1))

    assert len(results) == 1
    assert isinstance(results[0], Entity)
    assert results[0].name == "Enslaved"


def test_crawl_max_artists():
    urls = [f"https://band{i}.bandcamp.com" for i in range(10)]

    def make_instance(data, scrap):
        url = data["url"]
        m = MagicMock()
        m.name = url.split("//")[1].split(".")[0]
        m.url = url
        m.data = {"name": m.name, "url": url}
        m.band_id = None
        m.image = None
        m.location = None
        m.genre = None
        m.albums = []
        return m

    with patch("py_bandcamp.BandcampArtist", side_effect=make_instance):
        results = list(BandCamp.crawl(urls, max_artists=2))

    assert len(results) == 2


def test_crawl_seen_set_prevents_revisit():
    seen = {"https://enslaved.bandcamp.com"}

    with patch("py_bandcamp.BandcampArtist") as MockArtist:
        results = list(BandCamp.crawl(["https://enslaved.bandcamp.com"], seen=seen))

    MockArtist.assert_not_called()
    assert results == []


def test_crawl_expands_related():
    related_url = "https://imonolith.bandcamp.com"

    def make_instance(data, scrap):
        url = data["url"]
        m = MagicMock()
        m.name = url.split("//")[1].split(".")[0]
        m.url = url
        m.data = {"name": m.name, "url": url}
        m.band_id = None
        m.image = None
        m.location = None
        m.genre = None
        if url == "https://enslaved.bandcamp.com":
            from py_bandcamp.models import BandcampAlbum
            alb = BandcampAlbum({"url": "https://enslaved.bandcamp.com/album/below-the-lights",
                                  "album_name": "Below The Lights"}, scrap=False)
            related = MagicMock()
            related.url = related_url
            related.name = "imonolith"
            alb._related_artists_cache = [related]
            m.albums = [alb]
        else:
            m.albums = []
        return m

    # ``related_artists`` is a property on the *class*, so it can only be
    # stubbed there. Do it via a scoped ``patch.object`` (auto-restoring)
    # instead of a raw assignment — a bare ``type(alb).related_artists = ...``
    # leaks the stub onto every ``BandcampAlbum`` instance for the rest of
    # the test session, causing order-dependent failures elsewhere.
    from py_bandcamp.models import BandcampAlbum as _BandcampAlbum
    with patch("py_bandcamp.BandcampArtist", side_effect=make_instance), \
         patch.object(_BandcampAlbum, "related_artists",
                       new=property(lambda self: list(getattr(self, "_related_artists_cache", [])))):
        results = list(BandCamp.crawl(["https://enslaved.bandcamp.com"], max_artists=2))

    visited_names = [e.name for e in results]
    assert "enslaved" in visited_names
    assert "imonolith" in visited_names


def test_crawl_expands_related_does_not_leak_class_stub():
    """Regression test for a test-order flake: stubbing ``related_artists``
    on the ``BandcampAlbum`` class (needed because it's a property, so it
    can't be set on an instance) must not survive past the ``with`` block.
    A prior version used a bare ``type(alb).related_artists = property(...)``
    assignment with no teardown, which permanently replaced the property for
    every ``BandcampAlbum`` for the rest of the test session — any later
    test touching ``.related_artists`` on an unrelated album got back a
    leaked ``MagicMock`` instead of its own data, failing only when tests
    ran in an order that put such a test after this one (e.g. under
    ``pytest-randomly``).
    """
    from py_bandcamp.models import BandcampAlbum

    original_property = BandcampAlbum.related_artists
    test_crawl_expands_related()
    assert BandcampAlbum.related_artists is original_property

    album = BandcampAlbum({"url": "https://someoneelse.bandcamp.com/album/x"}, scrap=False)
    assert album.related_artists == []


def test_crawl_label_expands_roster():
    label_url = "https://relapserecords.bandcamp.com"
    roster_url = "https://yob.bandcamp.com"

    def make_instance(data, scrap):
        url = data["url"]
        m = MagicMock()
        m.name = url.split("//")[1].split(".")[0]
        m.url = url
        m.data = {"name": m.name, "url": url,
                  "is_label": url == label_url or None}
        m.band_id = None
        m.image = None
        m.location = None
        m.genre = None
        m.albums = []
        return m

    roster_entity = MagicMock(spec=Entity)
    roster_entity.name = "YOB"
    roster_entity.extra = {"artist_url": roster_url}

    with patch("py_bandcamp.BandcampArtist", side_effect=make_instance), \
         patch.object(BandCamp, "get_label_artists", return_value=iter([roster_entity])):
        results = list(BandCamp.crawl([label_url], max_artists=2))

    visited_names = [e.name for e in results]
    assert any("relapserecords" in n for n in visited_names)
    assert any("yob" in n for n in visited_names)
