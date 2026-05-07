"""Cassette-backed parser tests for Bandcamp album pages.

These tests replay real captured HTTP responses against the album
parser so upstream HTML/JSON changes surface as test failures rather
than silent empty results.

Re-record cassettes::

    pytest --vcr-record=all test/test_album_vcr.py

The nightly CI workflow runs without cassettes against the live API.
"""
from __future__ import annotations

import pytest

from mediavocab import Release, MediaType

from py_bandcamp import BandCamp
from py_bandcamp.models import BandcampAlbum


pytestmark = pytest.mark.vcr


# ``Run the Jewels`` (the self-titled debut, 2013) is a free, permanent
# Bandcamp release from a well-established act — a stable target.
ALBUM_URL = "https://runthejewels.bandcamp.com/album/run-the-jewels"


def test_album_from_url_parses_tracklist():
    album = BandcampAlbum.from_url(ALBUM_URL)
    assert album.title
    assert album.tracks, "expected at least one track"
    first = album.tracks[0]
    assert first.title
    assert first.url and first.url.startswith("http")


def test_album_to_release_returns_typed_release_with_tracklist():
    rel = BandCamp.album_to_release(ALBUM_URL, include_tracklist=True)
    assert isinstance(rel, Release)
    assert rel.work.title
    assert rel.work.media_type == MediaType.MUSIC
    assert rel.uri.startswith("http")
    assert rel.work.tracklist, "expected populated tracklist"
    # Each appearance should expose a Work with a non-empty title.
    assert all(a.work.title for a in rel.work.tracklist)


def test_album_to_release_skips_tracklist_when_disabled():
    rel = BandCamp.album_to_release(ALBUM_URL, include_tracklist=False)
    assert isinstance(rel, Release)
    assert rel.work.title
    assert rel.work.tracklist == []


def test_get_recommendations_returns_typed_releases():
    recs = BandCamp.get_recommendations(ALBUM_URL)
    assert recs, "expected at least one fan-also-likes recommendation"
    assert all(isinstance(r, Release) for r in recs)
    assert all(r.work.title for r in recs)


def test_get_related_artists_returns_typed_entities():
    related = BandCamp.get_related_artists(ALBUM_URL)
    assert related, "expected at least one related artist"
    assert all(e.name for e in related)
