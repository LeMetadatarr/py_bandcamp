"""Cassette-backed parser tests for Bandcamp artist (band root) pages
and the global ``/tags`` taxonomy page.

Re-record cassettes::

    pytest --vcr-record=all test/test_artist_vcr.py
"""
from __future__ import annotations

import pytest

from py_bandcamp import BandCamp
from py_bandcamp.models import BandcampArtist


pytestmark = pytest.mark.vcr


ARTIST_URL = "https://runthejewels.bandcamp.com"


def test_artist_from_url_parses_name_and_albums():
    artist = BandcampArtist.from_url(ARTIST_URL)
    assert artist.name
    # An established artist's discography listing should be non-empty.
    assert artist.albums, "expected at least one album in the discography"


def test_tags_returns_flat_list():
    tags = BandCamp.tags()
    assert isinstance(tags, list)
    assert len(tags) > 50, "expected the full Bandcamp tag taxonomy"
    assert all(isinstance(t, str) and t for t in tags)


def test_tags_returns_structured_when_requested():
    data = BandCamp.tags(tag_list=False)
    assert isinstance(data, dict)
    assert "genres" in data and "subgenres" in data
    assert data["genres"], "expected non-empty genres"
