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
    assert args[0] == "https://bandcamp.com/search"
    assert kwargs["params"]["q"] == "anything"


def test_injected_session_used_for_lyrics():
    fake = MagicMock()
    fake.get.return_value = _mock_response(
        '<html><div class="lyricsText">la la</div></html>'
    )

    bc = BandCamp(session=fake)
    out = bc.get_track_lyrics("https://x.bandcamp.com/track/y")

    assert out == "la la"
    fake.get.assert_called_once_with("https://x.bandcamp.com/track/y", timeout=30)


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


def test_requests_through_the_global_proxy_carry_a_timeout_the_caller_can_override():
    from py_bandcamp import session as sess
    fake = MagicMock()
    old = sess.get_session()
    sess.set_session(fake)
    try:
        sess.HTTP.get("u")
        fake.get.assert_called_with("u", timeout=sess.DEFAULT_TIMEOUT)
        sess.HTTP.get("u", timeout=5)
        fake.get.assert_called_with("u", timeout=5)
        for method in ("post", "head"):
            getattr(sess.HTTP, method)("u")
            getattr(fake, method).assert_called_with("u", timeout=sess.DEFAULT_TIMEOUT)
        assert sess.HTTP.headers is fake.headers
    finally:
        sess.set_session(old)


def test_injected_session_search_carries_a_timeout():
    fake = MagicMock()
    fake.get.return_value = _mock_response("<html></html>")
    list(BandCamp(session=fake).search_albums("x"))
    assert fake.get.call_args.kwargs["timeout"] > 0


@pytest.mark.parametrize("status", [403, 429, 503])
def test_search_refusal_raises_instead_of_returning_nothing(status):
    from py_bandcamp import BandcampBlocked
    fake = MagicMock()
    fake.get.return_value = _mock_response("<html></html>", status)
    with pytest.raises(BandcampBlocked):
        list(BandCamp(session=fake).search_albums("x"))


def test_search_bot_challenge_raises():
    from py_bandcamp import BandcampBlocked
    fake = MagicMock()
    fake.get.return_value = _mock_response("<html><head><title>Client Challenge</title></head></html>")
    with pytest.raises(BandcampBlocked):
        list(BandCamp(session=fake).search_albums("x"))


_ALBUM_ROW = ('<li class="searchresult"><div class="itemtype">ALBUM</div><div class="heading">'
              '<a href="https://a.bandcamp.com/album/x?from=s">X</a></div><div class="subhead">by B</div></li>')


@pytest.mark.parametrize("title", [
    "<title>client challenge</title>", "<title >Client Challenge</title>", "<TITLE>CLIENT CHALLENGE</TITLE>", "<title>\n  Client   Challenge \n</title >",
])
def test_challenge_detection_ignores_case_and_whitespace(title):
    from py_bandcamp import BandcampBlocked
    fake = MagicMock()
    fake.get.return_value = _mock_response(f"<html><head>{title}</head></html>")
    with pytest.raises(BandcampBlocked):
        list(BandCamp(session=fake).search_albums("x"))


def test_challenge_detection_reads_the_first_8_kib_only():
    from py_bandcamp import BandcampBlocked
    title = "<title>Client Challenge</title>"
    fake = MagicMock()
    fake.get.return_value = _mock_response("<!--" + "x" * 6000 + "-->" + title)
    with pytest.raises(BandcampBlocked):
        list(BandCamp(session=fake).search_albums("x"))
    fake.get.return_value = _mock_response("<!--" + "x" * 9000 + "-->" + title)
    assert list(BandCamp(session=fake).search_albums("x")) == []


def test_block_on_a_later_page_keeps_the_pages_already_yielded():
    fake = MagicMock()
    fake.get.side_effect = [_mock_response(_ALBUM_ROW), _mock_response("", 429)]
    got = list(BandCamp(session=fake).search_albums("x"))
    assert [r.work.title for r in got] == ["X"]
    assert fake.get.call_count == 2


def test_block_on_the_first_page_raises_even_if_nothing_was_yielded():
    from py_bandcamp import BandcampBlocked
    fake = MagicMock()
    fake.get.return_value = _mock_response("", 429)
    with pytest.raises(BandcampBlocked):
        next(BandCamp(session=fake).search_albums("x"))


@pytest.mark.parametrize("method", ["get", "post", "head", "put", "patch", "delete", "options", "request"])
def test_every_http_verb_gets_the_default_timeout(method):
    from py_bandcamp import session as sess
    fake = MagicMock()
    getattr(sess.TimedHTTP(fake), method)("u")
    getattr(fake, method).assert_called_once_with("u", timeout=sess.DEFAULT_TIMEOUT)


def test_session_with_its_own_timeout_keeps_it():
    from py_bandcamp import session as sess
    fake = MagicMock()
    fake.timeout = 5
    sess.TimedHTTP(fake).get("u")
    fake.get.assert_called_once_with("u")
    fake2 = MagicMock()
    fake2.timeout = (1, 2)
    sess.TimedHTTP(fake2).get("u")
    fake2.get.assert_called_once_with("u")


def test_session_without_a_numeric_timeout_gets_the_default():
    from py_bandcamp import session as sess
    for own in (None, "x", True):
        fake = MagicMock()
        fake.timeout = own
        sess.TimedHTTP(fake).get("u")
        fake.get.assert_called_once_with("u", timeout=sess.DEFAULT_TIMEOUT)


def test_positional_timeout_to_request_is_not_duplicated():
    from py_bandcamp import session as sess
    fake = MagicMock()
    http = sess.TimedHTTP(fake)
    http.request("GET", "u", None, None, None, None, None, None, 7)
    fake.request.assert_called_once_with("GET", "u", None, None, None, None, None, None, 7)
    fake.request.reset_mock()
    http.request("GET", "u")
    fake.request.assert_called_once_with("GET", "u", timeout=sess.DEFAULT_TIMEOUT)


def test_proxy_can_be_copied():
    import copy
    from py_bandcamp import session as sess
    assert isinstance(copy.copy(sess.HTTP), sess.TimedHTTP)
    assert isinstance(copy.deepcopy(sess.TimedHTTP(MagicMock())), sess.TimedHTTP)


def test_block_on_a_later_page_is_logged(caplog):
    import logging
    fake = MagicMock()
    fake.get.side_effect = [_mock_response(_ALBUM_ROW), _mock_response("", 503)]
    with caplog.at_level(logging.WARNING, logger="py_bandcamp"):
        got = list(BandCamp(session=fake).search_albums("x"))
    assert len(got) == 1
    assert any("stopped at page 2" in r.getMessage() for r in caplog.records)


def test_title_equal_to_challenge_on_a_page_with_results_is_not_a_block():
    page = f"<html><head><title>Client Challenge</title></head><body>{_ALBUM_ROW}</body></html>"
    fake = MagicMock()
    fake.get.side_effect = [_mock_response(page), _mock_response("<html></html>")]
    assert len(list(BandCamp(session=fake).search_albums("x"))) == 1


def test_half_built_proxy_raises_attribute_error_not_recursion():
    from py_bandcamp import session as sess
    with pytest.raises(AttributeError):
        sess.TimedHTTP.__new__(sess.TimedHTTP).get
