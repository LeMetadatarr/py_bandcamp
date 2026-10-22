"""Cassette-backed parser tests for Bandcamp track pages.

These tests replay real captured HTTP responses against the track
parser, exercising :meth:`BandCamp.track_to_release`, lyric scraping,
and free-stream URL extraction.

Re-record cassettes::

    pytest --vcr-record=all test/test_track_vcr.py
"""
from __future__ import annotations

import pytest

from mediavocab import Release, MediaType

from py_bandcamp import BandCamp
from py_bandcamp.models import BandcampTrack


pytestmark = pytest.mark.vcr


# Title track of the 2013 self-titled Run the Jewels album — free,
# permanent, has a public stream and lyrics on Bandcamp.
TRACK_URL = "https://runthejewels.bandcamp.com/track/run-the-jewels"


def test_track_from_url_parses_metadata():
    track = BandcampTrack.from_url(TRACK_URL)
    assert track.title
    assert track.url and track.url.startswith("http")
    # Free Bandcamp previews expose a streamable mp3 URL.
    assert track.stream, "expected a free-stream URL"


def test_track_to_release_returns_typed_release():
    rel = BandCamp.track_to_release(TRACK_URL)
    assert isinstance(rel, Release)
    assert rel.work.title
    assert rel.work.media_type == MediaType.MUSIC
    assert rel.uri.startswith("http")
    # Free preview => mp3 / 128 kbps / stereo per BandCamp convention.
    assert rel.codec == "mp3"
    assert rel.bitrate == "128"


def test_get_track_lyrics_returns_text_or_unavailable_marker():
    lyr = BandCamp.get_track_lyrics(TRACK_URL)
    assert isinstance(lyr, str)
    assert lyr  # never empty; at minimum the unavailable marker


def test_get_stream_url_returns_audio_url():
    url = BandCamp.get_stream_url(TRACK_URL)
    assert isinstance(url, str)
    assert url.startswith("http")


def test_get_streams_handles_list_input():
    urls = BandCamp.get_streams([TRACK_URL])
    assert isinstance(urls, list)
    assert len(urls) == 1
    assert urls[0].startswith("http")
