"""Tests for the pluggable HTTP transport.

Covers:

* Per-instance session injection — ``BandCamp(session=...)`` routes
  every HTTP call through the given session and never touches the
  module-level proxy.
* ``PYBANDCAMP_TRANSPORT=curl_cffi`` falls back gracefully to the
  plain ``requests`` session when ``curl_cffi`` isn't importable.
* ``PYBANDCAMP_TRANSPORT=curl_cffi`` uses the ``curl_cffi`` factory
  when it is importable (mocked).
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from py_bandcamp import BandCamp
from py_bandcamp import transport as transport_mod


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _mock_response(text="<html></html>", status=200):
    r = MagicMock()
    r.text = text
    r.content = text.encode()
    r.status_code = status
    r.ok = status < 400
    return r


# ---------------------------------------------------------------------------
# session injection
# ---------------------------------------------------------------------------

def test_injected_session_captures_search_calls():
    """``BandCamp(session=s).search(...)`` must drive the injected session,
    not the module-level proxy. We verify by giving the injected mock an
    empty page (so the search terminates after one HTTP round-trip) and
    asserting it was the one that received ``.get``."""
    fake = MagicMock()
    fake.get.return_value = _mock_response("<html></html>")

    bc = BandCamp(session=fake)
    list(bc.search("anything"))

    assert fake.get.call_count == 1
    args, kwargs = fake.get.call_args
    assert args[0] == "http://bandcamp.com/search"
    assert kwargs["params"]["q"] == "anything"


def test_injected_session_used_for_lyrics():
    fake = MagicMock()
    fake.get.return_value = _mock_response(
        '<html><div class="lyricsText">la la</div></html>'
    )

    bc = BandCamp(session=fake)
    out = bc.get_track_lyrics("https://x.bandcamp.com/track/y")

    assert out == "la la"
    fake.get.assert_called_once_with("https://x.bandcamp.com/track/y")


def test_classmethod_path_uses_module_proxy():
    """When called as a classmethod, ``BandCamp.search`` should still go
    through the module-level ``requests`` proxy — existing tests rely on
    being able to ``patch("py_bandcamp.requests")``."""
    with patch("py_bandcamp.requests") as mock_proxy:
        mock_proxy.get.return_value = _mock_response("<html></html>")
        list(BandCamp.search("x"))
    assert mock_proxy.get.called


def test_search_tracks_propagates_injected_session():
    fake = MagicMock()
    fake.get.return_value = _mock_response("<html></html>")
    bc = BandCamp(session=fake)
    list(bc.search_tracks("x"))
    assert fake.get.called


# ---------------------------------------------------------------------------
# default_session() / env-var contract
# ---------------------------------------------------------------------------

def test_default_session_is_plain_requests_when_env_unset(monkeypatch):
    monkeypatch.delenv("PYBANDCAMP_TRANSPORT", raising=False)
    s = transport_mod.default_session()
    import requests as _r
    assert isinstance(s, _r.Session)
    # realistic UA — not the stock python-requests one
    assert "python-requests" not in s.headers.get("User-Agent", "")


def test_curl_cffi_env_falls_back_when_missing(monkeypatch):
    """``PYBANDCAMP_TRANSPORT=curl_cffi`` without curl_cffi installed must
    fall back to the plain ``requests`` session — never crash the import
    or the first HTTP call."""
    monkeypatch.setenv("PYBANDCAMP_TRANSPORT", "curl_cffi")

    # Force the import inside _make_curl_cffi_session to fail.
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "curl_cffi" or name.startswith("curl_cffi."):
            raise ImportError("curl_cffi not installed")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        s = transport_mod.default_session()

    import requests as _r
    assert isinstance(s, _r.Session)


def test_curl_cffi_env_uses_curl_cffi_when_present(monkeypatch):
    """``PYBANDCAMP_TRANSPORT=curl_cffi`` must call into curl_cffi when
    it's importable. We inject a fake ``curl_cffi.requests`` module and
    assert ``Session(impersonate="chrome")`` is invoked."""
    monkeypatch.setenv("PYBANDCAMP_TRANSPORT", "curl_cffi")

    fake_session_instance = MagicMock(name="curl_cffi_session")
    fake_session_cls = MagicMock(return_value=fake_session_instance)

    fake_curl_cffi = types.ModuleType("curl_cffi")
    fake_curl_cffi_requests = types.ModuleType("curl_cffi.requests")
    fake_curl_cffi_requests.Session = fake_session_cls
    fake_curl_cffi.requests = fake_curl_cffi_requests

    monkeypatch.setitem(sys.modules, "curl_cffi", fake_curl_cffi)
    monkeypatch.setitem(sys.modules, "curl_cffi.requests", fake_curl_cffi_requests)

    s = transport_mod.default_session()

    fake_session_cls.assert_called_once_with(impersonate="chrome")
    assert s is fake_session_instance


def test_curl_cffi_env_value_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("PYBANDCAMP_TRANSPORT", "CURL_CFFI")
    fake_session_instance = MagicMock()
    fake_session_cls = MagicMock(return_value=fake_session_instance)
    fake_curl_cffi = types.ModuleType("curl_cffi")
    fake_curl_cffi_requests = types.ModuleType("curl_cffi.requests")
    fake_curl_cffi_requests.Session = fake_session_cls
    fake_curl_cffi.requests = fake_curl_cffi_requests
    monkeypatch.setitem(sys.modules, "curl_cffi", fake_curl_cffi)
    monkeypatch.setitem(sys.modules, "curl_cffi.requests", fake_curl_cffi_requests)
    assert transport_mod.default_session() is fake_session_instance


# ---------------------------------------------------------------------------
# session.set_session propagates through the HTTP proxy
# ---------------------------------------------------------------------------

def test_set_session_is_seen_by_submodules():
    """Re-binding the global session via ``set_session`` must affect the
    proxy used by ``utils``/``models``/``__init__`` — the previous
    ``from session import SESSION as requests`` pattern silently kept
    using the original session object."""
    from py_bandcamp import session as session_mod
    from py_bandcamp.utils import requests as utils_proxy

    fake = MagicMock()
    fake.get.return_value = _mock_response("not-a-real-blob")

    original = session_mod.SESSION
    try:
        session_mod.set_session(fake)
        # Going through utils' bound proxy must hit the new session.
        utils_proxy.get("http://example.invalid")
        assert fake.get.called
    finally:
        session_mod.set_session(original)
