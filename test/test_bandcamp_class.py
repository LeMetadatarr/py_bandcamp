"""Tests for the BandCamp class methods — all network calls mocked."""
from unittest.mock import MagicMock, patch
from bs4 import BeautifulSoup

from mediavocab import Release, Entity

from py_bandcamp import BandCamp
from py_bandcamp.models import BandcampTrack, BandcampAlbum, BandcampArtist, BandcampLabel


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _mock_response(text="", status_code=200):
    r = MagicMock()
    r.text = text
    r.content = text.encode()
    r.status_code = status_code
    r.ok = status_code < 400
    return r


def _search_page_html(items_html=""):
    return f'<ul class="results"><li class="searchresult">{items_html}</li></ul>'


def _track_item_html(url="https://a.bandcamp.com/track/t?x=1",
                     name="My Song", subhead="from Album by Artist",
                     released="2023", tags="metal, doom", img="http://img/a.jpg"):
    return f"""
    <div class='itemtype'>track</div>
    <div class='art'><img src='{img}'/></div>
    <div class='heading'><a href='{url}'>{name}</a></div>
    <div class='subhead'>{subhead}</div>
    <div class='released'>released {released}</div>
    <div class='tags'>tags: {tags}</div>"""


def _album_item_html(url="https://a.bandcamp.com/album/lp?x=1",
                     name="Great LP", artist="by Cool Band",
                     length="8 tracks, 40 minutes", released="2020",
                     tags="rock", img="http://img/b.jpg"):
    return f"""
    <div class='itemtype'>album</div>
    <div class='art'><img src='{img}'/></div>
    <div class='heading'><a href='{url}'>{name}</a></div>
    <div class='subhead'>{artist}</div>
    <div class='length'>{length}</div>
    <div class='released'>released {released}</div>
    <div class='tags'>tags: {tags}</div>"""


def _make_search_html(*items_html):
    lis = "".join(f'<li class="searchresult">{h}</li>' for h in items_html)
    return f'<html><ul class="results">{lis}</ul></html>'


# ---------------------------------------------------------------------------
# search()
# ---------------------------------------------------------------------------

def test_search_returns_tracks_and_albums():
    html = _make_search_html(_track_item_html(), _album_item_html())
    with patch("py_bandcamp.requests") as mock_sess:
        mock_sess.get.side_effect = [
            _mock_response(html),
            _mock_response("<html></html>"),  # page 2 empty → stop
        ]
        results = list(BandCamp.search("anything", albums=True, tracks=True,
                                       artists=False, labels=False))
    assert len(results) == 2
    assert all(isinstance(r, Release) for r in results)


def test_search_deduplicates():
    html = _make_search_html(_track_item_html())
    with patch("py_bandcamp.requests") as mock_sess:
        # same result on page 1 and page 2 → should only yield once
        mock_sess.get.side_effect = [
            _mock_response(html),
            _mock_response(html),
            _mock_response("<html></html>"),
        ]
        results = list(BandCamp.search("x", tracks=True, albums=False,
                                       artists=False, max_pages=5))
    assert len(results) == 1


def test_search_stops_at_empty_page():
    with patch("py_bandcamp.requests") as mock_sess:
        mock_sess.get.return_value = _mock_response("<html></html>")
        results = list(BandCamp.search("x"))
    assert results == []


def test_search_max_pages_respected():
    html = _make_search_html(_track_item_html(url="https://a.bandcamp.com/track/t1"),
                             _album_item_html(url="https://a.bandcamp.com/album/l1"))
    call_count = []
    def side_effect(*a, **kw):
        call_count.append(1)
        url = f"https://a.bandcamp.com/track/t{len(call_count)}"
        return _mock_response(_make_search_html(_track_item_html(url=f"{url}?x=1")))

    with patch("py_bandcamp.requests") as mock_sess:
        mock_sess.get.side_effect = side_effect
        list(BandCamp.search("x", tracks=True, albums=False, artists=False,
                             max_pages=3))
    assert len(call_count) == 3


def test_search_tracks_only():
    html = _make_search_html(_track_item_html(), _album_item_html())
    with patch("py_bandcamp.requests") as mock_sess:
        mock_sess.get.side_effect = [
            _mock_response(html),
            _mock_response("<html></html>"),
        ]
        results = list(BandCamp.search_tracks("x"))
    assert all(isinstance(r, Release) for r in results)


def test_search_albums_only():
    html = _make_search_html(_track_item_html(), _album_item_html())
    with patch("py_bandcamp.requests") as mock_sess:
        mock_sess.get.side_effect = [
            _mock_response(html),
            _mock_response("<html></html>"),
        ]
        results = list(BandCamp.search_albums("x"))
    assert all(isinstance(r, Release) for r in results)


def test_search_artists_only():
    artist_html = """
    <div class='itemtype'>artist</div>
    <div class='art'><img src='http://img/a.jpg'/></div>
    <div class='heading'><a href='https://a.bandcamp.com?x=1'>Band</a></div>
    <div class='subhead'>Oslo, Norway</div>
    <div class='genre'>genre: metal</div>
    <div class='tags'>tags: metal</div>"""
    html = _make_search_html(artist_html)
    with patch("py_bandcamp.requests") as mock_sess:
        mock_sess.get.side_effect = [
            _mock_response(html),
            _mock_response("<html></html>"),
        ]
        results = list(BandCamp.search_artists("x"))
    assert all(isinstance(r, Entity) for r in results)


def test_search_labels_only():
    label_html = """
    <div class='itemtype'>label</div>
    <div class='art'></div>
    <div class='heading'><a href='https://label.bandcamp.com?x=1'>My Label</a></div>
    <div class='subhead'>New York</div>"""
    html = _make_search_html(label_html)
    with patch("py_bandcamp.requests") as mock_sess:
        mock_sess.get.side_effect = [
            _mock_response(html),
            _mock_response("<html></html>"),
        ]
        results = list(BandCamp.search_labels("x"))
    assert all(isinstance(r, Entity) for r in results)


# ---------------------------------------------------------------------------
# search_tag
# ---------------------------------------------------------------------------

def test_search_tag_delegates_to_search():
    html = _make_search_html(_album_item_html())
    with patch("py_bandcamp.requests") as mock_sess:
        mock_sess.get.side_effect = [
            _mock_response(html),
            _mock_response("<html></html>"),
        ]
        results = list(BandCamp.search_tag("black-metal"))
    assert len(results) >= 1


# ---------------------------------------------------------------------------
# get_stream_url / get_streams
# ---------------------------------------------------------------------------

def test_get_stream_url_returns_stream():
    with patch("py_bandcamp.get_stream_data") as m:
        m.return_value = {"stream": "http://cdn/t.mp3"}
        assert BandCamp.get_stream_url("https://a.bandcamp.com/track/t") == "http://cdn/t.mp3"


def test_get_stream_url_fallback():
    with patch("py_bandcamp.get_stream_data") as m:
        m.return_value = {}
        url = "https://a.bandcamp.com/track/t"
        assert BandCamp.get_stream_url(url) == url


def test_get_streams_list():
    with patch("py_bandcamp.get_stream_data") as m:
        m.return_value = {"stream": "http://cdn/t.mp3"}
        result = BandCamp.get_streams(["https://a.bandcamp.com/track/t",
                                       "https://b.bandcamp.com/track/s"])
    assert len(result) == 2


def test_get_streams_single_string():
    with patch("py_bandcamp.get_stream_data") as m:
        m.return_value = {"stream": "http://cdn/t.mp3"}
        result = BandCamp.get_streams("https://a.bandcamp.com/track/t")
    assert len(result) == 1


# ---------------------------------------------------------------------------
# get_track_lyrics
# ---------------------------------------------------------------------------

def test_get_track_lyrics_found():
    html = '<html><div class="lyricsText">Some words here</div></html>'
    with patch("py_bandcamp.requests") as m:
        m.get.return_value = _mock_response(html)
        assert BandCamp.get_track_lyrics("https://a.bandcamp.com/track/t") == "Some words here"


def test_get_track_lyrics_unavailable():
    with patch("py_bandcamp.requests") as m:
        m.get.return_value = _mock_response("<html><body>no lyrics</body></html>")
        assert BandCamp.get_track_lyrics("https://a.bandcamp.com/track/t") == "lyrics unavailable"


# ---------------------------------------------------------------------------
# tags()
# ---------------------------------------------------------------------------

def test_tags_returns_flat_list():
    blob = """<div data-blob='{"signup_params":{"genres":["rock","metal"],
        "subgenres":{"rock":[{"norm_name":"indie"}],"metal":[]}}}'></div>"""
    with patch("py_bandcamp.extract_blob") as m:
        m.return_value = {
            "signup_params": {
                "genres": ["rock", "metal"],
                "subgenres": {
                    "rock": [{"norm_name": "indie"}],
                    "metal": []
                }
            }
        }
        tags = BandCamp.tags()
    assert "rock" in tags
    assert "metal" in tags
    assert "indie" in tags


def test_tags_returns_dict():
    with patch("py_bandcamp.extract_blob") as m:
        m.return_value = {
            "signup_params": {
                "genres": ["rock"],
                "subgenres": {"rock": [{"norm_name": "indie"}]}
            }
        }
        result = BandCamp.tags(tag_list=False)
    assert "genres" in result
    assert "subgenres" in result
