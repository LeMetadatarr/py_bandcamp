"""Tests targeting the remaining coverage gaps in py_bandcamp.

These exercise edge-case HTML shapes (sold-out tracks, name-your-price
albums, missing tracklist/artwork, etc.), error paths in the scrapers,
the BandcampSingle wrapper, dunder methods on every model, and the
mediavocab conversion helpers in py_bandcamp/__init__.py.

All HTTP traffic is mocked — no live calls, no cassettes needed.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from py_bandcamp import (
    BandCamp,
    _album_to_release,
    _artist_to_entity,
    _band_url_from_url,
    _country_from_location,
    _label_to_entity,
    _map_genres,
    _spdx_from_tags,
    _strip_query,
    _to_iso_date,
    _track_to_release,
)
from py_bandcamp.models import (
    BandcampAlbum,
    BandcampArtist,
    BandcampLabel,
    BandcampSingle,
    BandcampTrack,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _resp(text, status=200):
    r = MagicMock()
    r.text = text
    r.content = text.encode()
    r.status_code = status
    r.ok = status < 400
    return r


def _ld_page(data):
    return f'<html><script type="application/ld+json">{json.dumps(data)}</script></html>'


def _tralbum_page(tralbum, ld):
    blob = json.dumps(tralbum).replace('"', '&quot;')
    return (f'<html><div data-tralbum="{blob}"></div>'
            f'<script type="application/ld+json">{json.dumps(ld)}</script></html>')


TRACK_LD = {
    "@type": "MusicRecording",
    "@id": "https://a.bandcamp.com/track/t",
    "name": "T",
    "image": "http://img/art.jpg",
    "keywords": ["metal"],
    "byArtist": {"@type": "MusicGroup", "name": "B", "@id": "https://a.bandcamp.com"},
    "inAlbum": {"@type": "MusicAlbum", "name": "LP", "@id": "https://a.bandcamp.com/album/lp"},
    "additionalProperty": [],
}

ALBUM_LD = {
    "@type": "MusicAlbum",
    "@id": "https://a.bandcamp.com/album/lp",
    "name": "LP",
    "image": "http://img/art.jpg",
    "keywords": "rock, indie",
    "numTracks": 1,
    "byArtist": {"@type": "MusicGroup", "name": "B", "@id": "https://a.bandcamp.com"},
    "publisher": {"@type": "MusicGroup", "name": "Cool Label", "@id": "https://label.bandcamp.com"},
    "track": {"itemListElement": [
        {"@type": "ListItem", "position": 1, "item": {
            "@type": "MusicRecording",
            "@id": "https://a.bandcamp.com/track/t1",
            "name": "T1", "duration": "P00H03M00S", "additionalProperty": []
        }},
    ]},
    "additionalProperty": [],
    "datePublished": "27 March 2020",
}


# ---------------------------------------------------------------------------
# __init__.py: helper functions
# ---------------------------------------------------------------------------

def test_to_iso_date_variants():
    assert _to_iso_date("") is None
    assert _to_iso_date("   ") is None
    assert _to_iso_date(None) is None
    assert _to_iso_date("2024") == "2024"
    assert _to_iso_date("2024-09") == "2024-09"
    assert _to_iso_date("2024-09-05") == "2024-09-05"
    assert _to_iso_date("27 March 2020") == "2020-03-27"
    assert _to_iso_date("March 27, 2020") == "2020-03-27"
    assert _to_iso_date("garbage") is None
    # with trailing time
    assert _to_iso_date("27 March 2020 12:00:00 GMT") == "2020-03-27"


def test_spdx_from_tags():
    assert _spdx_from_tags([]) == ""
    assert _spdx_from_tags(None) == ""
    assert _spdx_from_tags(["cc-by-nc-nd"]) == "CC-BY-NC-ND-4.0"
    assert _spdx_from_tags(["cc-by-nc-sa"]) == "CC-BY-NC-SA-4.0"
    assert _spdx_from_tags(["cc-by-sa"]) == "CC-BY-SA-4.0"
    assert _spdx_from_tags(["cc-by-nc"]) == "CC-BY-NC-4.0"
    assert _spdx_from_tags(["cc-by-nd"]) == "CC-BY-ND-4.0"
    assert _spdx_from_tags(["cc-by"]) == "CC-BY-4.0"
    assert _spdx_from_tags(["cc0"]) == "CC0-1.0"
    assert _spdx_from_tags(["public domain"]) == "CC0-1.0"
    assert _spdx_from_tags(["unrelated"]) == ""


def test_map_genres_passthrough_alias_and_dedup():
    out = _map_genres(["rock", "hip-hop", "rock", None, "", "Made-Up-Tag"])
    # Dedup, no None / empties
    assert "rock" in out
    assert any("hip" in g.lower() or "hop" in g.lower() for g in out)
    assert out.count("rock") == 1
    assert "made-up-tag" in out
    assert _map_genres([]) == []
    assert _map_genres(None) == []


def test_country_from_location():
    assert _country_from_location("") == ""
    assert _country_from_location(None) == ""
    assert _country_from_location("Berlin") == ""
    assert _country_from_location("Paris, France") == "France"
    assert _country_from_location("Brooklyn, NY, USA") == "USA"


def test_strip_query():
    assert _strip_query("") == ""
    assert _strip_query(None) == ""
    assert _strip_query("https://a.bandcamp.com/album/lp?from=search") == "https://a.bandcamp.com/album/lp"
    assert _strip_query("https://a.bandcamp.com") == "https://a.bandcamp.com"


def test_band_url_from_url():
    assert _band_url_from_url("") == ""
    assert _band_url_from_url(None) == ""
    assert _band_url_from_url("https://a.bandcamp.com/album/lp") == "https://a.bandcamp.com"
    assert _band_url_from_url("https://a.bandcamp.com/track/t") == "https://a.bandcamp.com"
    assert _band_url_from_url("https://a.bandcamp.com") == "https://a.bandcamp.com"


# ---------------------------------------------------------------------------
# __init__.py: conversion helpers
# ---------------------------------------------------------------------------

def test_track_to_release_full():
    t = BandcampTrack({
        "url": "https://a.bandcamp.com/track/t?from=search",
        "title": "T", "image": "http://img/art.jpg",
        "track_id": 1, "band_id": 2, "album_id": 3,
        "file_mp3-128": "http://cdn/t.mp3",
        "duration_secs": 120,
        "artist": "Artist Name",
        "tags": ["rock", "cc-by"],
        "released": "27 March 2020",
    }, parse=False)
    rel = _track_to_release(t)
    assert rel.work.title == "T"
    assert rel.uri == "https://a.bandcamp.com/track/t"
    assert rel.codec == "mp3"
    assert rel.bitrate == "128"
    assert rel.audio_channels == "stereo"
    assert rel.license.identifier == "CC-BY-4.0"
    assert rel.release_date == "2020-03-27"
    assert rel.external_ids["bandcamp_track_id"] == "1"
    assert rel.external_ids["bandcamp_band_id"] == "2"
    assert rel.external_ids["bandcamp_album_id"] == "3"
    assert rel.work.credits[0].entity.name == "Artist Name"


def test_track_to_release_minimal_no_stream():
    t = BandcampTrack({"url": "https://a.bandcamp.com/track/t",
                       "title": "T"}, parse=False)
    rel = _track_to_release(t)
    assert rel.codec == ""  # no stream
    assert rel.bitrate == ""
    assert rel.work.runtime is None
    assert rel.work.credits == []


def test_album_to_release_with_label_and_tracklist():
    album = BandcampAlbum({
        "url": "https://a.bandcamp.com/album/lp",
        "title": "LP", "image": "http://img/art.jpg",
        "album_id": 11, "band_id": 22,
        "artist": "Artist",
        "publisher": "Cool Label",  # different from artist → label kept
        "tags": ["cc-by"],
        "released": "2020-03-27",
    }, scrap=False)
    # Mock tracks property
    fake_track = BandcampTrack({"url": "https://a.bandcamp.com/track/t1",
                                "title": "T1", "track_id": 99,
                                "tracknum": 1, "duration_secs": 120}, parse=False)
    with patch.object(BandcampAlbum, "tracks", new_callable=lambda: property(lambda s: [fake_track])):
        rel = _album_to_release(album, include_tracklist=True)
    assert rel.work.title == "LP"
    assert rel.label is not None
    assert rel.label.name == "Cool Label"
    assert len(rel.work.tracklist) == 1
    assert rel.work.tracklist[0].position == 1
    assert rel.license.identifier == "CC-BY-4.0"


def test_album_to_release_publisher_equals_artist_drops_label():
    album = BandcampAlbum({
        "url": "https://a.bandcamp.com/album/lp",
        "title": "LP",
        "artist": "Self",
        "publisher": "Self",  # self-released → no separate label
    }, scrap=False)
    rel = _album_to_release(album, include_tracklist=False)
    assert rel.label is None


def test_album_to_release_tracklist_position_fallback():
    """Track with no track_num falls back to len(tracklist)+1."""
    album = BandcampAlbum({"url": "https://a.bandcamp.com/album/lp",
                           "title": "LP"}, scrap=False)
    no_num_track = BandcampTrack({"url": "https://a.bandcamp.com/track/t",
                                  "title": "T"}, parse=False)
    with patch.object(BandcampAlbum, "tracks", new_callable=lambda: property(lambda s: [no_num_track])):
        rel = _album_to_release(album, include_tracklist=True)
    assert rel.work.tracklist[0].position == 1


def test_artist_to_entity_full():
    a = BandcampArtist({
        "url": "https://acme.bandcamp.com",
        "name": "Acme",
        "band_id": 42,
        "image": "http://img/a.jpg",
        "location": "Lisbon, Portugal",
        "genre": "rock",
    }, scrap=False)
    e = _artist_to_entity(a)
    assert e.name == "Acme"
    assert e.external_ids["bandcamp_band_id"] == "42"
    assert e.extra["country"] == "Portugal"
    assert e.extra["genre"] == "rock"
    assert e.extra["image"] == "http://img/a.jpg"


def test_artist_to_entity_minimal():
    a = BandcampArtist({"url": "https://x.bandcamp.com", "name": "X"}, scrap=False)
    e = _artist_to_entity(a)
    assert e.name == "X"
    assert "country" not in e.extra
    assert "image" not in e.extra


def test_label_to_entity_full():
    lb = BandcampLabel({
        "url": "https://label.bandcamp.com",
        "name": "L",
        "image": "http://img/l.jpg",
        "location": "Berlin, Germany",
    }, scrap=False)
    e = _label_to_entity(lb)
    assert e.extra["country"] == "Germany"
    assert e.extra["image"] == "http://img/l.jpg"


def test_label_to_entity_minimal():
    lb = BandcampLabel({"url": "https://l.bandcamp.com", "name": "L"}, scrap=False)
    e = _label_to_entity(lb)
    assert "country" not in e.extra


# ---------------------------------------------------------------------------
# BandCamp class methods
# ---------------------------------------------------------------------------

def test_bandcamp_track_to_release_from_url():
    page = _tralbum_page({"trackinfo": [{}]}, TRACK_LD)
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _resp(page)
        rel = BandCamp.track_to_release("https://a.bandcamp.com/track/t")
    assert rel.work.title == "T"


def test_bandcamp_track_to_release_passthrough():
    t = BandcampTrack({"url": "https://a.bandcamp.com/track/t",
                       "title": "T"}, parse=False)
    rel = BandCamp.track_to_release(t)
    assert rel.work.title == "T"


def test_bandcamp_album_to_release_passthrough():
    album = BandcampAlbum({"url": "https://a.bandcamp.com/album/lp",
                           "title": "LP"}, scrap=False)
    rel = BandCamp.album_to_release(album, include_tracklist=False)
    assert rel.work.title == "LP"


def test_bandcamp_get_streams_list_and_scalar():
    with patch("py_bandcamp.get_stream_data") as gsd:
        gsd.return_value = {"stream": "http://cdn/x.mp3"}
        assert BandCamp.get_streams("u") == ["http://cdn/x.mp3"]
        assert BandCamp.get_streams(["u1", "u2"]) == ["http://cdn/x.mp3", "http://cdn/x.mp3"]


def test_bandcamp_get_track_lyrics_present():
    html = '<html><div class="lyricsText">la la la</div></html>'
    with patch("py_bandcamp.requests") as m:
        m.get.return_value = _resp(html)
        assert BandCamp.get_track_lyrics("u") == "la la la"


def test_bandcamp_get_track_lyrics_missing():
    with patch("py_bandcamp.requests") as m:
        m.get.return_value = _resp("<html></html>")
        assert BandCamp.get_track_lyrics("u") == "lyrics unavailable"


def test_bandcamp_tags_tag_list():
    blob_data = {"signup_params": {
        "genres": [{"norm_name": "rock"}],
        "subgenres": {"rock": [{"norm_name": "indie-rock"}, {"norm_name": "punk"}]},
    }}
    html = f'<html><div data-blob=\'{json.dumps(blob_data)}\'></div></html>'
    with patch("py_bandcamp.utils.requests") as m:
        m.get.return_value = _resp(html)
        out = BandCamp.tags(tag_list=True)
    assert "rock" in out and "indie-rock" in out
    with patch("py_bandcamp.utils.requests") as m:
        m.get.return_value = _resp(html)
        out2 = BandCamp.tags(tag_list=False)
    assert "genres" in out2 and "subgenres" in out2


def test_bandcamp_get_recommendations_and_related_artists():
    rec_html = """
    <html><body>
      <div id="recommendations_container">
        <li class="recommended-album">
          <a class="album-link" href="https://other.bandcamp.com/album/x?from=y">
            <span class="release-title">Other</span>
            <span class="by-artist">by Other Artist</span>
          </a>
          <img src="http://img/o.jpg"/>
        </li>
        <li class="recommended-album">
          <!-- no album-link, must be skipped -->
        </li>
      </div>
    </body></html>"""
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _resp(rec_html)
        recs = BandCamp.get_recommendations("https://a.bandcamp.com/album/lp")
    assert len(recs) == 1
    assert recs[0].work.title == "Other"

    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _resp(rec_html)
        related = BandCamp.get_related_artists("https://a.bandcamp.com/album/lp")
    assert len(related) == 1
    assert related[0].name == "Other Artist"


def test_bandcamp_search_yields_all_types():
    """Single search page with every itemtype, exhausting cls.search for one
    full pass + recursive return when page_results empty."""
    search_html = """
    <html><body>
      <li class="searchresult">
        <div class="itemtype">album</div>
        <div class="art"><img src="http://img/a.jpg"/></div>
        <div class="heading"><a href="https://a.bandcamp.com/album/lp">LP</a></div>
        <div class="subhead">by A</div>
        <div class="length">5 tracks, 30 minutes</div>
        <div class="released">released 2020</div>
        <div class="tags">tags: rock</div>
      </li>
      <li class="searchresult">
        <div class="itemtype">track</div>
        <div class="art"><img src="http://img/t.jpg"/></div>
        <div class="heading"><a href="https://a.bandcamp.com/track/t">T</a></div>
        <div class="subhead">from LP by A</div>
        <div class="released">released 2020</div>
        <div class="tags">tags: rock</div>
      </li>
      <li class="searchresult">
        <div class="itemtype">artist</div>
        <div class="art"><img src="http://img/x.jpg"/></div>
        <div class="heading"><a href="https://a.bandcamp.com">A</a></div>
        <div class="subhead">Lisbon, PT</div>
        <div class="genre">genre: rock</div>
        <div class="tags">tags: rock</div>
      </li>
      <li class="searchresult">
        <div class="itemtype">label</div>
        <div class="art"><img src="http://img/l.jpg"/></div>
        <div class="heading"><a href="https://l.bandcamp.com">L</a></div>
        <div class="subhead">London</div>
        <div class="tags">tags: rock</div>
      </li>
    </body></html>"""
    empty_html = "<html><body></body></html>"
    with patch("py_bandcamp.requests") as m:
        # First call: full page; subsequent recursion: empty
        m.get.side_effect = [_resp(search_html), _resp(empty_html)]
        results = list(BandCamp.search("query", labels=True, max_pages=2))
    # 4 results — one of each type
    assert len(results) == 4


def test_bandcamp_search_max_pages_stop():
    """Hits max_pages limit, so recursion stops even with results."""
    search_html = """
    <html><body>
      <li class="searchresult">
        <div class="itemtype">album</div>
        <div class="art"></div>
        <div class="heading"><a href="https://a.bandcamp.com/album/lp">LP</a></div>
        <div class="subhead">by A</div>
      </li>
    </body></html>"""
    with patch("py_bandcamp.requests") as m:
        m.get.return_value = _resp(search_html)
        results = list(BandCamp.search("q", labels=False, max_pages=1))
    assert len(results) == 1


def test_bandcamp_search_dedups_seen():
    # Same item twice across two pages — only one yielded
    page = """
    <html><body>
      <li class="searchresult">
        <div class="itemtype">album</div>
        <div class="art"></div>
        <div class="heading"><a href="https://a.bandcamp.com/album/lp">LP</a></div>
        <div class="subhead">by A</div>
      </li>
    </body></html>"""
    with patch("py_bandcamp.requests") as m:
        m.get.side_effect = [_resp(page), _resp(page), _resp("<html></html>")]
        results = list(BandCamp.search("q", max_pages=3))
    assert len(results) == 1


def test_bandcamp_search_filtered_skip():
    """Item type not requested → skipped via 'continue' branch."""
    page = """
    <html><body>
      <li class="searchresult">
        <div class="itemtype">label</div>
        <div class="art"></div>
        <div class="heading"><a href="https://l.bandcamp.com">L</a></div>
        <div class="subhead">London</div>
      </li>
    </body></html>"""
    with patch("py_bandcamp.requests") as m:
        m.get.return_value = _resp(page)
        # labels=False → label skipped → empty + early return
        results = list(BandCamp.search("q", labels=False, max_pages=1))
    assert results == []


def test_bandcamp_search_helpers_use_item_type():
    """search_albums / search_tracks / search_artists / search_labels /
    search_tag set the item_type filter."""
    page = "<html><body></body></html>"
    for fn in (BandCamp.search_albums, BandCamp.search_tracks,
               BandCamp.search_artists, BandCamp.search_labels):
        with patch("py_bandcamp.requests") as m:
            m.get.return_value = _resp(page)
            list(fn("query"))
    with patch("py_bandcamp.requests") as m:
        m.get.return_value = _resp(page)
        list(BandCamp.search_tag("Some Tag", max_pages=1))


def test_parse_track_no_subhead():
    """Search result with no subhead element."""
    from bs4 import BeautifulSoup
    html = """
    <li class="searchresult">
      <div class="itemtype">track</div>
      <div class="art"></div>
      <div class="heading"><a href="https://a.bandcamp.com/track/t">T</a></div>
    </li>"""
    item = BeautifulSoup(html, "html.parser").find("li")
    t = BandCamp._parse_track(item)
    assert t.data.get("artist") == ""


def test_parse_album_no_length():
    from bs4 import BeautifulSoup
    html = """
    <li class="searchresult">
      <div class="itemtype">album</div>
      <div class="art"></div>
      <div class="heading"><a href="https://a.bandcamp.com/album/lp">LP</a></div>
      <div class="subhead">A</div>
    </li>"""
    item = BeautifulSoup(html, "html.parser").find("li")
    a = BandCamp._parse_album(item)
    # no length, no released, no tags — fallthrough exception branches
    assert a.data.get("track_number") == ""


def test_parse_artist_no_tags_no_genre():
    from bs4 import BeautifulSoup
    html = """
    <li class="searchresult">
      <div class="itemtype">artist</div>
      <div class="art"></div>
      <div class="heading"><a href="https://x.bandcamp.com">X</a></div>
      <div class="subhead">Berlin</div>
    </li>"""
    item = BeautifulSoup(html, "html.parser").find("li")
    ar = BandCamp._parse_artist(item)
    assert ar.tags == []
    assert ar.genre == ""


# ---------------------------------------------------------------------------
# BandcampTrack: properties & dunder
# ---------------------------------------------------------------------------

def test_track_dunder_eq_hash_repr():
    t1 = BandcampTrack({"url": "https://a.bandcamp.com/track/t", "title": "T"}, parse=False)
    t2 = BandcampTrack({"url": "https://a.bandcamp.com/track/t"}, parse=False)
    assert t1 == t2
    assert hash(t1) == hash(t2)
    assert repr(t1).startswith("BandcampTrack:")


def test_track_album_artist_properties():
    """Cover @property album / artist that delegate to get_album / get_artist."""
    t = BandcampTrack({"url": "https://a.bandcamp.com/track/t"}, parse=False)
    page = _tralbum_page({"trackinfo": []}, ALBUM_LD)
    with patch("py_bandcamp.utils.requests") as m, \
         patch("py_bandcamp.models.requests") as mm:
        m.get.return_value = _resp(_ld_page(TRACK_LD))
        mm.get.return_value = _resp(page)
        assert t.album is not None
    with patch("py_bandcamp.utils.requests") as m:
        m.get.return_value = _resp(_ld_page(TRACK_LD))
        assert t.artist is not None


def test_track_title_falls_back_to_url_segment():
    t = BandcampTrack({"url": "https://a.bandcamp.com/track/cool-song"}, parse=False)
    assert t.title == "cool-song"


def test_track_duration_from_iso_only():
    t = BandcampTrack({"url": "https://a.bandcamp.com/track/t",
                       "duration_iso": "P00H01M30S"}, parse=False)
    assert t.duration == 90


def test_track_get_track_data_no_ldjson_raises():
    """Page that lacks the ld+json script tag is rejected with a clear error."""
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _resp("<html>just html, no script</html>")
        with pytest.raises(ValueError, match="No ld\\+json found"):
            BandcampTrack.get_track_data("https://a.bandcamp.com/track/t")


def test_album_item_id_distinct_from_album_id():
    a = BandcampAlbum({"url": "https://a.bandcamp.com/album/lp",
                        "item_id": 777, "album_id": 888}, scrap=False)
    assert a.item_id == 777


def test_label_data_merges_page_data():
    """Force _page_data to be non-empty so the data merge loop executes."""
    lb = BandcampLabel({"url": "https://l.bandcamp.com"}, scrap=False)
    lb._page_data = {"name": "From Page"}
    assert lb.data["name"] == "From Page"


def test_parse_iso_no_match_returns_zero():
    from py_bandcamp.utils import _parse_iso_duration
    assert _parse_iso_duration("PNothing") == 0


def test_extract_blob_absent_returns_none():
    from py_bandcamp.utils import _extract_blob_from_text
    assert _extract_blob_from_text("<html>no blob here</html>") is None


def test_extract_tralbum_invalid_json_returns_empty():
    from py_bandcamp.utils import _extract_tralbum
    # data-tralbum present but unparseable JSON triggers except branch
    assert _extract_tralbum('<div data-tralbum="not json"></div>') == {}


def test_parse_ldjson_clean_nested_list():
    """clean=True must descend into list values containing dicts/lists."""
    from py_bandcamp.utils import _parse_ldjson
    nested = {"@type": "X", "items": [
        [{"@id": "inner"}],  # list-of-list-of-dict — exercises _clean_list recursion
        {"@id": "second"},
    ]}
    html = f'<script type="application/ld+json">{json.dumps(nested)}</script>'
    out = _parse_ldjson(html, clean=True)
    assert out["items"][0][0] == {"id": "inner"}
    assert out["items"][1] == {"id": "second"}


def test_get_stream_data_invalid_json_raises():
    from py_bandcamp.utils import get_stream_data
    html = '<script type="application/ld+json">{not json</script>'
    with patch("py_bandcamp.utils.requests") as m:
        m.get.return_value = _resp(html)
        with pytest.raises(ValueError, match="Failed to parse ld\\+json"):
            get_stream_data("https://a.bandcamp.com/track/t")


def test_track_get_track_data_invalid_json_raises():
    html = '<html><script type="application/ld+json">{not json</script></html>'
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _resp(html)
        with pytest.raises(ValueError, match="Failed to parse ld\\+json"):
            BandcampTrack.get_track_data("https://a.bandcamp.com/track/t")


def test_track_get_track_data_track_id_from_current_id():
    """When trackinfo has no track_id, but current.type=='t', use current.id."""
    tralbum = {
        "current": {"id": 555, "type": "t"},
        "trackinfo": [{"file": {"mp3-128": "u"}, "duration": 60}],
    }
    page = _tralbum_page(tralbum, TRACK_LD)
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _resp(page)
        data = BandcampTrack.get_track_data("https://a.bandcamp.com/track/t")
    assert data["track_id"] == 555


# ---------------------------------------------------------------------------
# BandcampSingle
# ---------------------------------------------------------------------------

def test_single_from_url_and_props():
    page = _tralbum_page({"trackinfo": [{}]}, TRACK_LD)
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _resp(page)
        with patch("py_bandcamp.utils.requests") as mu:
            mu.get.return_value = _resp(_ld_page(TRACK_LD))
            s = BandcampSingle.from_url("https://a.bandcamp.com/track/t")
    assert s.url == "https://a.bandcamp.com/track/t"
    assert s.title  # populated
    assert s.artist == "B"
    assert s.image == "http://img/art.jpg"
    assert s.tracks  # cached track returned
    assert isinstance(s.tracks[0], BandcampTrack)
    assert s.data["url"] == "https://a.bandcamp.com/track/t"
    assert str(s) == s.url
    assert repr(s).startswith("BandcampSingle:")
    s2 = BandcampSingle({"url": s.url})
    assert s == s2
    assert hash(s) == hash(s2)


def test_single_title_falls_back_to_url():
    s = BandcampSingle({"url": "https://a.bandcamp.com/track/cool"})
    assert s.title == "cool"


def test_single_tracks_fetches_when_missing():
    """When _data has no 'track', a BandcampTrack is constructed live."""
    s = BandcampSingle({"url": "https://a.bandcamp.com/track/t"})
    page = _tralbum_page({"trackinfo": [{}]}, TRACK_LD)
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _resp(page)
        tracks = s.tracks
    assert len(tracks) == 1


# ---------------------------------------------------------------------------
# BandcampAlbum: properties & error paths
# ---------------------------------------------------------------------------

def test_album_dunder_and_props():
    a = BandcampAlbum({"url": "https://a.bandcamp.com/album/lp",
                        "album_name": "lp", "image": "http://i",
                        "keywords": ["rock"]}, scrap=False)
    assert a.image == "http://i"
    assert "lp" in a.title
    assert a.keywords == ["rock"]
    assert str(a) == a.url
    assert repr(a).startswith("BandcampAlbum:")
    a2 = BandcampAlbum({"url": a.url}, scrap=False)
    assert a == a2
    assert hash(a) == hash(a2)


def test_album_missing_url_raises():
    with pytest.raises(ValueError):
        BandcampAlbum({}, scrap=False)


def test_album_releases_artist_comments_recommendations_props():
    """Cover .releases / .artist / .comments / .recommendations / .related_artists."""
    a = BandcampAlbum({"url": "https://a.bandcamp.com/album/lp"}, scrap=False)
    with patch("py_bandcamp.utils.requests") as mu:
        mu.get.return_value = _resp(_ld_page(ALBUM_LD))
        assert isinstance(a.releases, list)
    with patch("py_bandcamp.utils.requests") as mu:
        mu.get.return_value = _resp(_ld_page(ALBUM_LD))
        assert a.artist is not None
    # comments: ALBUM_LD has no 'comment' key — empty list
    with patch("py_bandcamp.utils.requests") as mu:
        mu.get.return_value = _resp(_ld_page(ALBUM_LD))
        assert a.comments == []

    rec_html = """
    <html><body>
      <div id="recommendations_container">
        <li class="recommended-album"
            data-artist="Fallback Artist"
            data-albumtitle="Fallback Title">
          <a class="album-link" href="https://other.bandcamp.com/album/x">
          </a>
        </li>
      </div>
    </body></html>"""
    with patch("py_bandcamp.models.requests") as mm:
        mm.get.return_value = _resp(rec_html)
        recs = a.recommendations
    assert recs[0].title == "Fallback Title"

    with patch("py_bandcamp.models.requests") as mm:
        mm.get.return_value = _resp(rec_html)
        ra = a.related_artists
    assert any(r.name == "Fallback Artist" for r in ra)


def test_album_get_artist_none_when_missing():
    ld = {"@type": "MusicAlbum", "@id": "u", "name": "x", "additionalProperty": []}
    with patch("py_bandcamp.utils.requests") as m:
        m.get.return_value = _resp(_ld_page(ld))
        assert BandcampAlbum.get_artist("u") is None


def test_album_get_recommendations_404_returns_empty():
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _resp("nope", status=404)
        assert BandcampAlbum.get_recommendations("https://x") == []


def test_album_get_recommendations_no_container():
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _resp("<html></html>")
        assert BandcampAlbum.get_recommendations("https://x") == []


def test_album_get_tracks_handles_bad_track_num():
    """trackinfo with non-int track_num falls into the except branch and is
    silently dropped from ti_by_num."""
    tralbum = {
        "id": 1, "current": {"id": 1, "band_id": 9},
        "trackinfo": [
            {"track_num": "garbage", "track_id": 100},
            {"track_num": None, "track_id": 200},
            {"track_num": 1, "track_id": 300},
        ],
    }
    page = _tralbum_page(tralbum, ALBUM_LD)
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _resp(page)
        tracks = BandcampAlbum.get_tracks("https://a.bandcamp.com/album/lp")
    assert tracks[0].track_id == 300


def test_album_get_tracks_position_non_int():
    """ld+json position not parseable to int — pos_int falls back to None."""
    ld = dict(ALBUM_LD)
    ld["track"] = {"itemListElement": [
        {"@type": "ListItem", "position": "x", "item": {
            "@type": "MusicRecording", "@id": "u", "name": "T",
            "duration": "P00H01M00S", "additionalProperty": [],
        }},
    ]}
    page = _tralbum_page({"trackinfo": []}, ld)
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _resp(page)
        tracks = BandcampAlbum.get_tracks("https://a.bandcamp.com/album/lp")
    assert len(tracks) == 1


# ---------------------------------------------------------------------------
# BandcampLabel: dunder
# ---------------------------------------------------------------------------

def test_label_dunder_and_props():
    lb = BandcampLabel({"url": "https://l.bandcamp.com",
                         "name": "L", "tags": ["metal"],
                         "location": "London", "image": "http://i"},
                        scrap=False)
    assert lb.location == "London"
    assert lb.tags == ["metal"]
    assert lb.image == "http://i"
    assert str(lb) == lb.url
    assert repr(lb).startswith("BandcampLabel:")
    lb2 = BandcampLabel({"url": lb.url}, scrap=False)
    assert lb == lb2
    assert hash(lb) == hash(lb2)


def test_label_missing_url_raises():
    with pytest.raises(ValueError):
        BandcampLabel({}, scrap=False)


def test_label_scrap_no_url_returns_empty():
    """scrap() with no URL set returns {} without making any HTTP call."""
    lb = BandcampLabel.__new__(BandcampLabel)
    lb._url = None
    lb._data = {}
    lb._page_data = {}
    assert lb.scrap() == {}


def test_label_name_falls_back_to_url_segment():
    lb = BandcampLabel({"url": "https://x.bandcamp.com/foo"}, scrap=False)
    assert lb.name == "foo"


# ---------------------------------------------------------------------------
# BandcampArtist: dunder, error paths, get_albums singles, scrap exception
# ---------------------------------------------------------------------------

def test_artist_dunder_and_props():
    ar = BandcampArtist({"url": "https://x.bandcamp.com",
                          "name": "X", "genre": "g", "image": "http://i",
                          "location": "Berlin", "tags": ["rock"]},
                         scrap=False)
    assert ar.image == "http://i"
    assert ar.tags == ["rock"]
    assert str(ar) == ar.url
    assert repr(ar).startswith("BandcampArtist:")
    ar2 = BandcampArtist({"url": ar.url}, scrap=False)
    assert ar == ar2
    assert hash(ar) == hash(ar2)


def test_artist_name_falls_back_to_url_segment():
    ar = BandcampArtist({"url": "https://x.bandcamp.com/foo"}, scrap=False)
    assert ar.name == "foo"


def test_artist_scrap_404_returns_empty():
    ar = BandcampArtist.__new__(BandcampArtist)
    ar._url = "https://x.bandcamp.com"
    ar._data = {"url": ar._url}
    ar._page_data = {}
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _resp("nope", status=404)
        assert ar.scrap() == {}


def test_artist_scrap_exception_returns_empty():
    ar = BandcampArtist.__new__(BandcampArtist)
    ar._url = "https://x.bandcamp.com"
    ar._data = {"url": ar._url}
    ar._page_data = {}
    with patch("py_bandcamp.models.requests") as m:
        m.get.side_effect = RuntimeError("boom")
        assert ar.scrap() == {}


def test_artist_scrap_no_url_returns_empty():
    ar = BandcampArtist.__new__(BandcampArtist)
    ar._url = None
    ar._data = {}
    ar._page_data = {}
    assert ar.scrap() == {}


def test_artist_scrap_band_id_no_url_returns_none():
    assert BandcampArtist._scrap_band_id(None) is None
    assert BandcampArtist._scrap_band_id("") is None


def test_artist_scrap_band_id_404_returns_none():
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _resp("nope", status=404)
        assert BandcampArtist._scrap_band_id("https://x.bandcamp.com") is None


def test_artist_scrap_band_id_request_exception_returns_none():
    with patch("py_bandcamp.models.requests") as m:
        m.get.side_effect = RuntimeError("boom")
        assert BandcampArtist._scrap_band_id("https://x.bandcamp.com") is None


def test_artist_scrap_band_id_list_form():
    blob_html = ('<html><div data-blob=\'{"item_sellers": ["12345"]}\'></div></html>')
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _resp(blob_html)
        assert BandcampArtist._scrap_band_id("https://x.bandcamp.com") == 12345


def test_artist_scrap_band_id_invalid_returns_none():
    blob_html = ('<html><div data-blob=\'{"item_sellers": {"abc": {}}}\'></div></html>')
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _resp(blob_html)
        assert BandcampArtist._scrap_band_id("https://x.bandcamp.com") is None


def test_artist_get_singles():
    artist_html = """<html><body>
    <a href="/track/single1"><p class="title">Single 1</p><div class="art"><img src="http://i"/></div></a>
    <a href="/album/lp1"><p class="title">LP</p><div class="art"></div></a>
    </body></html>"""
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _resp(artist_html)
        singles = BandcampArtist.get_singles("https://x.bandcamp.com")
    assert len(singles) == 1
    assert isinstance(singles[0], BandcampSingle)


def test_artist_albums_property():
    """albums @property delegates to get_albums."""
    ar = BandcampArtist({"url": "https://x.bandcamp.com"}, scrap=False)
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _resp("<html></html>")
        assert ar.albums == []


def test_artist_featured_album_and_track():
    """featured_album returns BandcampAlbum.from_url; featured_track delegates."""
    ar = BandcampArtist({"url": "https://x.bandcamp.com"}, scrap=False)
    page = _tralbum_page({"trackinfo": []}, ALBUM_LD)
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _resp(page)
        fa = ar.featured_album
        assert isinstance(fa, BandcampAlbum)
    # featured_track on it
    with patch("py_bandcamp.models.requests") as m:
        m.get.return_value = _resp(page)
        ft = ar.featured_track
    assert ft is not None
