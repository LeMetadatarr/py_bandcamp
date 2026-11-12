"""Tests for models and utils — all network calls mocked."""
import json
from unittest.mock import MagicMock, patch

from py_bandcamp.models import BandcampTrack, BandcampAlbum, BandcampArtist, BandcampLabel
from py_bandcamp.utils import (
    extract_blob, extract_ldjson_blob, get_stream_data,
    _extract_tralbum, _parse_iso_duration,
)


# ---------------------------------------------------------------------------
# shared test data
# ---------------------------------------------------------------------------

TRACK_LD = {
    "@type": "MusicRecording",
    "@id": "https://a.bandcamp.com/track/t",
    "name": "My Track",
    "image": "http://img/art.jpg",
    "keywords": "metal, doom",
    "byArtist": {"@type": "MusicGroup", "name": "Band", "@id": "https://a.bandcamp.com"},
    "inAlbum": {"@type": "MusicAlbum", "name": "LP", "@id": "https://a.bandcamp.com/album/lp"},
    "additionalProperty": [
        {"@type": "PropertyValue", "name": "file_mp3-128", "value": "http://cdn/t.mp3"},
        {"@type": "PropertyValue", "name": "tracknum", "value": 3},
    ],
}

ALBUM_LD = {
    "@type": "MusicAlbum",
    "@id": "https://a.bandcamp.com/album/lp",
    "name": "LP",
    "image": "http://img/art.jpg",
    "keywords": ["rock", "indie"],
    "numTracks": 5,
    "byArtist": {"@type": "MusicGroup", "name": "Band", "@id": "https://a.bandcamp.com"},
    "albumRelease": [
        {"name": "LP Digital", "@id": "https://a.bandcamp.com/album/lp#release",
         "musicReleaseFormat": "DigitalFormat", "image": "http://img/r.jpg",
         "description": "Digital edition"},
    ],
    "track": {
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "item": {
                "@type": "MusicRecording",
                "@id": "https://a.bandcamp.com/track/t1",
                "name": "Track One",
                "duration": "P00H04M33S",
                "additionalProperty": [],
            }},
        ]
    },
    "comment": [
        {"text": "Great album!", "author": {"name": "Fan", "image": "http://img/fan.jpg"}},
        {"text": ["Line one", "Line two"], "author": {"name": "Fan2", "image": None}},
    ],
    "additionalProperty": [
        {"@type": "PropertyValue", "name": "featured_track_num", "value": 1},
    ],
}


def _ld_page(data):
    return f'<html><script type="application/ld+json">{json.dumps(data)}</script></html>'


def _tralbum_page(tralbum, ld_data=None):
    ld = ld_data or TRACK_LD
    blob = json.dumps(tralbum).replace('"', '&quot;')
    return (f'<html><div data-tralbum="{blob}"></div>'
            f'<script type="application/ld+json">{json.dumps(ld)}</script></html>')


def _mock_resp(text, status=200):
    r = MagicMock()
    r.text = text
    r.content = text.encode()
    r.status_code = status
    r.ok = status < 400
    return r


# ---------------------------------------------------------------------------
# utils: _parse_iso_duration (already in test_parsing.py, extras here)
# ---------------------------------------------------------------------------

def test_parse_iso_no_hours():
    from py_bandcamp.utils import _parse_iso_duration
    assert _parse_iso_duration("PT3M45S") == 225


# ---------------------------------------------------------------------------
# utils: extract_blob
# ---------------------------------------------------------------------------

def test_extract_blob_single_quote():
    html = "prefix data-blob='{\"key\": 1}' suffix"
    with patch("py_bandcamp.utils.requests") as m:
        m.get.return_value = _mock_resp(html)
        result = extract_blob("http://x")
    assert result == {"key": 1}


def test_extract_blob_double_quote():
    html = 'prefix data-blob="{&quot;key&quot;: 2}" suffix'
    with patch("py_bandcamp.utils.requests") as m:
        m.get.return_value = _mock_resp(html)
        result = extract_blob("http://x")
    assert result == {"key": 2}


# ---------------------------------------------------------------------------
# utils: extract_ldjson_blob
# ---------------------------------------------------------------------------

def test_extract_ldjson_blob_raw():
    with patch("py_bandcamp.utils.requests") as m:
        m.get.return_value = _mock_resp(_ld_page({"name": "Test"}))
        result = extract_ldjson_blob("http://x")
    assert result["name"] == "Test"


def test_extract_ldjson_blob_clean_strips_at():
    with patch("py_bandcamp.utils.requests") as m:
        m.get.return_value = _mock_resp(_ld_page({"@type": "Thing", "@id": "x"}))
        result = extract_ldjson_blob("http://x", clean=True)
    assert "type" in result and "id" in result
    assert "@type" not in result


# ---------------------------------------------------------------------------
# utils: _extract_tralbum
# ---------------------------------------------------------------------------

def test_extract_tralbum_present():
    data = {"trackinfo": [{"duration": 120, "file": {"mp3-128": "http://cdn/t.mp3"}}]}
    html = f'<div data-tralbum="{json.dumps(data).replace(chr(34), "&quot;")}"></div>'
    result = _extract_tralbum(html)
    assert result["trackinfo"][0]["duration"] == 120


def test_extract_tralbum_absent():
    assert _extract_tralbum("<html>no tralbum</html>") == {}


# ---------------------------------------------------------------------------
# utils: get_stream_data
# ---------------------------------------------------------------------------

def test_get_stream_data_from_ldjson():
    with patch("py_bandcamp.utils.requests") as m:
        m.get.return_value = _mock_resp(_ld_page(TRACK_LD))
        result = get_stream_data("https://a.bandcamp.com/track/t")
    assert result["stream"] == "http://cdn/t.mp3"
    assert result["title"] == "My Track"
    assert result["artist"] == "Band"
    assert result["album_name"] == "LP"


def test_get_stream_data_from_tralbum_fallback():
    ld = {
        "@type": "MusicRecording", "@id": "https://a.bandcamp.com/track/t",
        "name": "T", "image": None, "keywords": [],
        "byArtist": {"name": "B"}, "inAlbum": {"name": "A"},
        "additionalProperty": [],
    }
    tralbum = {"trackinfo": [{"file": {"mp3-128": "http://cdn/fallback.mp3"}, "duration": 100}]}
    with patch("py_bandcamp.utils.requests") as m:
        m.get.return_value = _mock_resp(_tralbum_page(tralbum, ld))
        result = get_stream_data("https://a.bandcamp.com/track/t")
    assert result["stream"] == "http://cdn/fallback.mp3"


def test_get_stream_data_404_raises():
    import pytest
    with patch("py_bandcamp.utils.requests") as m:
        m.get.return_value = _mock_resp("not found", status=404)
        with pytest.raises(ValueError, match="HTTP 404"):
            get_stream_data("https://a.bandcamp.com/track/gone")


def test_get_stream_data_no_ldjson_raises():
    import pytest
    with patch("py_bandcamp.utils.requests") as m:
        m.get.return_value = _mock_resp("<html>nothing</html>")
        with pytest.raises(ValueError, match="No ld\\+json"):
            get_stream_data("https://a.bandcamp.com/track/t")


# ---------------------------------------------------------------------------
# models: BandcampTrack.get_track_data (makes its own requests.get)
# ---------------------------------------------------------------------------

def test_track_get_track_data():
    tralbum = {"trackinfo": [{"file": {"mp3-128": "http://cdn/t.mp3"}, "duration": 234.5}]}
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _mock_resp(_tralbum_page(tralbum))
        data = BandcampTrack.get_track_data("https://a.bandcamp.com/track/t")
    assert data["title"] == "My Track"
    assert data["file_mp3-128"] == "http://cdn/t.mp3"
    assert data["duration_secs"] == 234


def test_track_get_track_data_404_raises():
    import pytest
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _mock_resp("not found", status=404)
        with pytest.raises(ValueError, match="HTTP 404"):
            BandcampTrack.get_track_data("https://a.bandcamp.com/track/gone")


def test_track_get_track_data_surfaces_canonical_ids():
    tralbum = {
        "id": 1234567,
        "current": {"id": 1234567, "type": "t", "band_id": 99, "album_id": 4242},
        "trackinfo": [{
            "track_id": 1234567,
            "file": {"mp3-128": "http://cdn/t.mp3"},
            "duration": 120,
        }],
    }
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _mock_resp(_tralbum_page(tralbum))
        t = BandcampTrack({"url": "https://a.bandcamp.com/track/t"})
    assert t.item_id == 1234567
    assert t.track_id == 1234567
    assert t.band_id == 99
    assert t.album_id == 4242


def test_track_parse_page_populates_stream_and_duration():
    tralbum = {"trackinfo": [{"file": {"mp3-128": "http://cdn/t.mp3"}, "duration": 180.0}]}
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _mock_resp(_tralbum_page(tralbum))
        t = BandcampTrack({"url": "https://a.bandcamp.com/track/t"})
    assert t.title == "My Track"
    assert t.stream == "http://cdn/t.mp3"
    assert t.duration == 180
    assert t.track_num == 3


# ---------------------------------------------------------------------------
# models: BandcampTrack.get_album / get_artist (use extract_ldjson_blob → utils.requests)
# ---------------------------------------------------------------------------

def test_track_get_album():
    ld = {"@type": "MusicRecording", "name": "T",
          "inAlbum": {"@type": "MusicAlbum", "name": "LP",
                      "@id": "https://a.bandcamp.com/album/lp"},
          "additionalProperty": []}
    mock_resp = _mock_resp(_ld_page(ld))
    with patch("py_bandcamp.utils.requests") as mu, \
         patch("py_bandcamp.models.requests") as mm:
        mu.get.return_value = mock_resp
        mm.get.return_value = mock_resp
        album = BandcampTrack.get_album("https://a.bandcamp.com/track/t")
    assert isinstance(album, BandcampAlbum)
    assert album.url == "https://a.bandcamp.com/album/lp"


def test_track_get_album_none_when_missing():
    ld = {"@type": "MusicRecording", "name": "T", "additionalProperty": []}
    with patch("py_bandcamp.utils.requests") as m:
        m.get.return_value = _mock_resp(_ld_page(ld))
        assert BandcampTrack.get_album("https://a.bandcamp.com/track/t") is None


def test_track_get_artist():
    ld = {"@type": "MusicRecording", "name": "T",
          "byArtist": {"@type": "MusicGroup", "name": "Band",
                       "@id": "https://a.bandcamp.com"},
          "additionalProperty": []}
    with patch("py_bandcamp.utils.requests") as m:
        m.get.return_value = _mock_resp(_ld_page(ld))
        artist = BandcampTrack.get_artist("https://a.bandcamp.com/track/t")
    assert isinstance(artist, BandcampArtist)
    assert artist.name == "Band"


def test_track_get_artist_none_when_missing():
    ld = {"@type": "MusicRecording", "name": "T", "additionalProperty": []}
    with patch("py_bandcamp.utils.requests") as m:
        m.get.return_value = _mock_resp(_ld_page(ld))
        assert BandcampTrack.get_artist("https://a.bandcamp.com/track/t") is None


# ---------------------------------------------------------------------------
# models: BandcampAlbum static methods (use extract_ldjson_blob → utils.requests)
# ---------------------------------------------------------------------------

ALBUM_TRALBUM = {
    "id": 112233,
    "current": {"id": 112233, "band_id": 445566},
    "trackinfo": [{"track_num": 1, "track_id": 778899}],
}


def test_album_get_album_data():
    page = _tralbum_page(ALBUM_TRALBUM, ld_data=ALBUM_LD)
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _mock_resp(page)
        data = BandcampAlbum.get_album_data("https://a.bandcamp.com/album/lp")
    assert data["title"] == "LP"
    assert data["n_tracks"] == 5
    assert data["featured_track_num"] == 1
    assert data["album_id"] == 112233
    assert data["item_id"] == 112233
    assert data["band_id"] == 445566


def test_album_get_tracks():
    page = _tralbum_page(ALBUM_TRALBUM, ld_data=ALBUM_LD)
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _mock_resp(page)
        tracks = BandcampAlbum.get_tracks("https://a.bandcamp.com/album/lp")
    assert len(tracks) == 1
    assert isinstance(tracks[0], BandcampTrack)
    assert tracks[0].title == "Track One"
    assert tracks[0].track_num == 1
    assert tracks[0].duration == 273  # 4m33s
    assert tracks[0].track_id == 778899
    assert tracks[0].album_id == 112233
    assert tracks[0].band_id == 445566


def test_album_get_tracks_empty_when_no_track_key():
    ld = dict(ALBUM_LD)
    ld.pop("track")
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _mock_resp(_ld_page(ld))
        assert BandcampAlbum.get_tracks("https://a.bandcamp.com/album/lp") == []


def test_album_get_releases():
    with patch("py_bandcamp.utils.requests") as m:
        m.get.return_value = _mock_resp(_ld_page(ALBUM_LD))
        releases = BandcampAlbum.get_releases("https://a.bandcamp.com/album/lp")
    assert len(releases) == 1
    assert releases[0]["format"] == "DigitalFormat"
    assert releases[0]["title"] == "LP Digital"


def test_album_get_comments_str_and_list():
    with patch("py_bandcamp.utils.requests") as m:
        m.get.return_value = _mock_resp(_ld_page(ALBUM_LD))
        comments = BandcampAlbum.get_comments("https://a.bandcamp.com/album/lp")
    assert comments[0]["text"] == "Great album!"
    assert isinstance(comments[1]["text"], str)
    assert "Line one" in comments[1]["text"]


def test_album_get_artist():
    with patch("py_bandcamp.utils.requests") as m:
        m.get.return_value = _mock_resp(_ld_page(ALBUM_LD))
        artist = BandcampAlbum.get_artist("https://a.bandcamp.com/album/lp")
    assert isinstance(artist, BandcampArtist)
    assert artist.name == "Band"


def test_album_featured_track():
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _mock_resp(_ld_page(ALBUM_LD))
        album = BandcampAlbum({"url": "https://a.bandcamp.com/album/lp"})
        ft = album.featured_track  # must be inside patch — triggers get_tracks()
    assert ft is not None
    assert ft.title == "Track One"


def test_album_featured_track_none_when_no_tracks():
    ld = dict(ALBUM_LD)
    ld.pop("track")
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _mock_resp(_ld_page(ld))
        album = BandcampAlbum({"url": "https://a.bandcamp.com/album/lp"})
        ft = album.featured_track
    assert ft is None


# ---------------------------------------------------------------------------
# models: BandcampArtist.get_albums (uses models.requests directly)
# ---------------------------------------------------------------------------

def test_artist_band_id_from_releases_dict():
    """Artist root page lacks ``item_sellers`` but ``/releases`` has it as a
    single-key dict whose key IS the band id."""
    artist_root = """<html><body><div id="band-name-location">
        <span class="title">Acme</span>
        <span class="location">Lisbon</span></div></body></html>"""
    releases_html = (
        '<html><body><div data-blob=\'{"item_sellers":'
        '{"2099893691":{"id":2099893691,"name":"Acme"}}}\'></div></body></html>'
    )
    with patch("py_bandcamp.models.requests") as mm:
        mm.get.side_effect = [
            _mock_resp(artist_root),     # artist root (scrap)
            _mock_resp(releases_html),   # /releases (band_id pull)
        ]
        artist = BandcampArtist({"url": "https://acme.bandcamp.com/"})
    assert artist.name == "Acme"
    assert artist.band_id == 2099893691
    assert artist.item_id == artist.band_id


def test_artist_band_id_handles_missing_sellers():
    """If ``/releases`` has no ``item_sellers``, ``band_id`` is None — not an
    exception."""
    artist_root = """<html><body><div id="band-name-location">
        <span class="title">Acme</span></div></body></html>"""
    empty_blob = '<html><body><div data-blob=\'{}\'></div></body></html>'
    with patch("py_bandcamp.models.requests") as mm:
        mm.get.side_effect = [_mock_resp(artist_root), _mock_resp(empty_blob)]
        artist = BandcampArtist({"url": "https://acme.bandcamp.com/"})
    assert artist.band_id is None
    assert artist.item_id is None


def test_artist_get_albums():
    artist_html = """<html><body>
    <a href="/album/lp1">
      <p class="title">Great LP</p>
      <div class="art"><img src="http://img/art.jpg"/></div>
    </a>
    <a href="/album/lp2">
      <p class="title">Another LP</p>
      <div class="art"><img src="http://img/art2.jpg"/></div>
    </a>
    <a href="/bio">no title</a>
    </body></html>"""
    # BandcampAlbum.__init__ with scrap=True calls extract_ldjson_blob (utils.requests)
    # for each album, so mock both
    with patch("py_bandcamp.models.requests") as mm, \
         patch("py_bandcamp.utils.requests") as mu:
        mm.get.return_value = _mock_resp(artist_html)
        mu.get.return_value = _mock_resp(_ld_page(ALBUM_LD))
        albums = BandcampArtist.get_albums("https://a.bandcamp.com")
    assert len(albums) == 2
    assert albums[0].title == "Great LP"   # title comes from artist page HTML
    assert "lp1" in albums[0].url


def test_artist_get_albums_missing_img():
    artist_html = """<html><body>
    <a href="/album/lp1"><p class="title">LP</p><div class="art"></div></a>
    </body></html>"""
    with patch("py_bandcamp.models.requests") as mm, \
         patch("py_bandcamp.utils.requests") as mu:
        mm.get.return_value = _mock_resp(artist_html)
        mu.get.return_value = _mock_resp(_ld_page(ALBUM_LD))
        albums = BandcampArtist.get_albums("https://a.bandcamp.com")
    assert len(albums) == 1


# ---------------------------------------------------------------------------
# session: set_session
# ---------------------------------------------------------------------------

def test_set_session():
    from py_bandcamp import set_session
    import py_bandcamp.session as sess
    original = sess.SESSION
    mock = MagicMock()
    set_session(mock)
    assert sess.SESSION is mock
    set_session(original)
