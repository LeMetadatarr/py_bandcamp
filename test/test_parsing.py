"""Unit tests for HTML parsing helpers using minimal fake HTML fragments."""
from unittest.mock import MagicMock, patch
from bs4 import BeautifulSoup

from py_bandcamp import BandCamp
from py_bandcamp.models import BandcampTrack, BandcampAlbum, BandcampArtist, BandcampLabel
from py_bandcamp.utils import get_props


# ---------------------------------------------------------------------------
# utils
# ---------------------------------------------------------------------------

def test_parse_iso_duration():
    from py_bandcamp.utils import _parse_iso_duration
    assert _parse_iso_duration("P00H11M17S") == 677
    assert _parse_iso_duration("PT3M45S") == 225
    assert _parse_iso_duration("P1H02M33S") == 3753
    assert _parse_iso_duration("") == 0
    assert _parse_iso_duration(None) == 0


def test_get_props_empty():
    assert get_props({}) == {}


def test_get_props_missing_key():
    # should not raise even when additionalProperty is absent
    assert get_props({"name": "foo"}) == {}


def test_get_props_returns_values():
    d = {
        "additionalProperty": [
            {"name": "file_mp3-128", "value": "http://example.com/track.mp3"},
            {"name": "tracknum", "value": 3},
        ]
    }
    result = get_props(d)
    assert result["file_mp3-128"] == "http://example.com/track.mp3"
    assert result["tracknum"] == 3


def test_get_props_filtered():
    d = {
        "additionalProperty": [
            {"name": "file_mp3-128", "value": "http://example.com/t.mp3"},
            {"name": "tracknum", "value": 1},
        ]
    }
    result = get_props(d, props=["tracknum"])
    assert "tracknum" in result
    assert "file_mp3-128" not in result


# ---------------------------------------------------------------------------
# model constructors (no network)
# ---------------------------------------------------------------------------

def test_bandcamp_track_no_parse():
    t = BandcampTrack({"url": "https://artist.bandcamp.com/track/song",
                       "track_name": "Song", "image": "http://img"}, parse=False)
    assert t.url == "https://artist.bandcamp.com/track/song"
    assert str(t) == "https://artist.bandcamp.com/track/song"


def test_bandcamp_track_missing_url_raises():
    import pytest
    with pytest.raises(ValueError):
        BandcampTrack({"track_name": "No URL"}, parse=False)


def test_bandcamp_album_no_scrap():
    a = BandcampAlbum({"url": "https://artist.bandcamp.com/album/lp",
                       "title": "LP"}, scrap=False)
    assert a.url == "https://artist.bandcamp.com/album/lp"
    assert "LP" in a.title


def test_bandcamp_label_no_scrap():
    lb = BandcampLabel({"url": "https://label.bandcamp.com",
                        "name": "Label X", "tags": ["metal"]}, scrap=False)
    assert lb.url == "https://label.bandcamp.com"
    assert lb.tags == ["metal"]


def test_bandcamp_artist_no_scrap():
    ar = BandcampArtist({"url": "https://artist.bandcamp.com",
                         "name": "Artist Y", "genre": "rock"}, scrap=False)
    assert ar.url == "https://artist.bandcamp.com"
    assert ar.genre == "rock"


def test_bandcamp_label_from_url():
    lb = BandcampLabel.from_url("https://label.bandcamp.com")
    assert isinstance(lb, BandcampLabel)
    assert lb.url == "https://label.bandcamp.com"


def test_bandcamp_artist_from_url():
    ar = BandcampArtist.from_url("https://artist.bandcamp.com")
    assert isinstance(ar, BandcampArtist)
    assert ar.url == "https://artist.bandcamp.com"


# ---------------------------------------------------------------------------
# BandCamp._parse_* helpers (HTML fragment tests)
# ---------------------------------------------------------------------------

def _make_track_item(subhead="from My Album by Cool Artist"):
    html = f"""
    <li class="searchresult">
      <div class="itemtype">track</div>
      <div class="art"><img src="http://img/art.jpg"/></div>
      <div class="heading"><a href="https://a.bandcamp.com/track/t?from=search">Song Title</a></div>
      <div class="subhead">{subhead}</div>
      <div class="released">released 2023</div>
      <div class="tags">tags: metal, doom</div>
    </li>"""
    soup = BeautifulSoup(html, "html.parser")
    return soup.find("li", class_="searchresult")


def test_parse_track_normal():
    item = _make_track_item()
    t = BandCamp._parse_track(item)
    assert isinstance(t, BandcampTrack)
    assert t.url == "https://a.bandcamp.com/track/t"
    assert "metal" in t.data.get("tags", [])


def test_parse_track_no_by():
    # subhead without "by" should not crash
    item = _make_track_item(subhead="from Some Album")
    t = BandCamp._parse_track(item)
    assert isinstance(t, BandcampTrack)
    assert t.data.get("artist") == ""


def test_parse_track_multiple_by():
    # "by" appears more than once — should split on first occurrence only
    item = _make_track_item(subhead="from Album by Artist by Other")
    t = BandCamp._parse_track(item)
    assert isinstance(t, BandcampTrack)
    assert "Artist by Other" in t.data.get("artist", "")


def test_parse_album():
    html = """
    <li class="searchresult">
      <div class="itemtype">album</div>
      <div class="art"><img src="http://img/art.jpg"/></div>
      <div class="heading"><a href="https://a.bandcamp.com/album/lp?x=1">Great LP</a></div>
      <div class="subhead">by Cool Artist</div>
      <div class="length">10 tracks, 45 minutes</div>
      <div class="released">released 2020</div>
      <div class="tags">tags: rock, indie</div>
    </li>"""
    item = BeautifulSoup(html, "html.parser").find("li")
    a = BandCamp._parse_album(item)
    assert isinstance(a, BandcampAlbum)
    assert a.url == "https://a.bandcamp.com/album/lp"
    assert a.data.get("artist") == "Cool Artist"
    assert a.data.get("track_number") == "10"


def test_parse_label():
    html = """
    <li class="searchresult">
      <div class="itemtype">label</div>
      <div class="art"><img src="http://img/art.jpg"/></div>
      <div class="heading"><a href="https://label.bandcamp.com?x=1">Good Label</a></div>
      <div class="subhead">New York, NY</div>
      <div class="tags">tags: metal, black-metal</div>
    </li>"""
    item = BeautifulSoup(html, "html.parser").find("li")
    lb = BandCamp._parse_label(item)
    assert isinstance(lb, BandcampLabel)
    assert lb.url == "https://label.bandcamp.com"
    assert "metal" in lb.tags


def test_parse_artist():
    html = """
    <li class="searchresult">
      <div class="itemtype">artist</div>
      <div class="art"><img src="http://img/art.jpg"/></div>
      <div class="heading"><a href="https://artist.bandcamp.com?x=1">My Band</a></div>
      <div class="subhead">Oslo, Norway</div>
      <div class="genre">genre: black metal</div>
      <div class="tags">tags: black-metal, atmospheric</div>
    </li>"""
    item = BeautifulSoup(html, "html.parser").find("li")
    ar = BandCamp._parse_artist(item)
    assert isinstance(ar, BandcampArtist)
    assert ar.url == "https://artist.bandcamp.com"
    assert ar.genre == "black metal"


def test_parse_label_no_tags():
    # missing tags div should not crash
    html = """
    <li class="searchresult">
      <div class="itemtype">label</div>
      <div class="art"></div>
      <div class="heading"><a href="https://label.bandcamp.com">Good Label</a></div>
      <div class="subhead">London</div>
    </li>"""
    item = BeautifulSoup(html, "html.parser").find("li")
    lb = BandCamp._parse_label(item)
    assert lb.tags == []


# ---------------------------------------------------------------------------
# get_stream_url uses get_stream_data result correctly
# ---------------------------------------------------------------------------

def test_get_stream_url_uses_stream_key():
    with patch("py_bandcamp.get_stream_data") as mock_gsd:
        mock_gsd.return_value = {"stream": "http://cdn.example.com/t.mp3",
                                 "title": "T", "artist": "A"}
        url = BandCamp.get_stream_url("https://a.bandcamp.com/track/t")
    assert url == "http://cdn.example.com/t.mp3"


def test_get_stream_url_fallback_to_input_url():
    with patch("py_bandcamp.get_stream_data") as mock_gsd:
        mock_gsd.return_value = {"title": "T"}  # no "stream" key
        url = BandCamp.get_stream_url("https://a.bandcamp.com/track/t")
    assert url == "https://a.bandcamp.com/track/t"


def test_iso_duration_accepts_every_designator_combination():
    from py_bandcamp.utils import _parse_iso_duration
    assert _parse_iso_duration("P00H11M17S") == 677
    assert _parse_iso_duration("PT1H5M") == 3900
    assert _parse_iso_duration("PT45S") == 45
    assert _parse_iso_duration("PT3M") == 180
    assert _parse_iso_duration("PT3M20.5S") == 200
    assert _parse_iso_duration("garbage") == 0
    assert _parse_iso_duration("P1DT1H") == 90000
    assert _parse_iso_duration("PT3Mjunk") == 0


def test_page_attributes_are_fully_entity_decoded():
    from py_bandcamp.utils import _extract_blob_from_text, _extract_tralbum
    assert _extract_tralbum('data-tralbum="{&quot;a&quot;:&quot;&#x27;q&#x27; &lt;b&gt;&quot;}"') == {"a": "'q' <b>"}
    assert _extract_blob_from_text('data-blob="{&quot;a&quot;:&quot;x&#39;y&quot;}"') == {"a": "x'y"}


def test_search_result_without_an_itemtype_is_skipped():
    from py_bandcamp import BandCamp
    typeless = '<li class="searchresult"><div class="other"></div></li>'
    album = ('<li class="searchresult"><div class="itemtype">ALBUM</div><div class="heading">'
             '<a href="https://a.bandcamp.com/album/x?from=s">X</a></div><div class="subhead">by B</div></li>')
    assert BandCamp.parse_search_page(typeless) == []
    found = BandCamp.parse_search_page(typeless + album + typeless)
    assert [a.url for a in found] == ["https://a.bandcamp.com/album/x"]


def test_iso_duration_never_raises_on_huge_digit_runs():
    from py_bandcamp.utils import _parse_iso_duration
    for n in (400, 5000):
        digits = "9" * n
        for iso in (f"PT{digits}S", f"PT{digits}M", f"P{digits}D", f"PT{digits}.5S"):
            assert _parse_iso_duration(iso) == 0


def test_single_quoted_blob_is_decoded_exactly_once():
    from py_bandcamp.utils import _extract_blob_from_text
    assert _extract_blob_from_text("""data-blob='{"a":"x&amp;y &#39;z&#39;"}'""") == {"a": "x&y 'z'"}
    assert _extract_blob_from_text("""data-blob='{"a":"&amp;lt;"}'""") == {"a": "&lt;"}


def test_double_encoded_entities_stay_literal_text():
    from py_bandcamp.utils import _extract_blob_from_text, _extract_tralbum
    assert _extract_blob_from_text('data-blob="{&quot;a&quot;:&quot;&amp;lt;&quot;}"') == {"a": "&lt;"}
    assert _extract_tralbum('data-tralbum="{&quot;a&quot;:&quot;&amp;lt;&quot;}"') == {"a": "&lt;"}
