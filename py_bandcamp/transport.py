"""Pluggable HTTP transport for py_bandcamp.

By default we use a plain :class:`requests.Session` with a realistic
User-Agent. The Bandcamp search endpoint is currently fronted by a Fastly
bot challenge that rejects vanilla ``requests`` traffic on TLS-fingerprint
grounds — set ``PYBANDCAMP_TRANSPORT=curl_cffi`` (and install the
``[stealth]`` extra) to route through ``curl_cffi`` impersonating Chrome,
which clears the challenge.

Selection rules for :func:`default_session`:

* ``PYBANDCAMP_TRANSPORT=curl_cffi`` AND ``curl_cffi`` is importable
  → ``curl_cffi.requests.Session(impersonate="chrome")``.
* otherwise → ``requests.Session`` with a Chrome-ish ``User-Agent``.

The env var is read on each call so tests can flip it at runtime.
"""
from __future__ import annotations

import os

import requests

# Realistic Chrome desktop UA — the default ``python-requests/X.Y`` UA is
# the easiest single signal a bot wall keys off of.
_DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _make_requests_session():
    s = requests.Session()
    # ``requests.Session`` ships with ``python-requests/X.Y`` as the UA,
    # which is the single easiest signal a bot wall keys off — overwrite
    # rather than ``setdefault``.
    s.headers["User-Agent"] = _DEFAULT_UA
    return s


def _make_curl_cffi_session():
    """Return a ``curl_cffi`` Session impersonating Chrome.

    Raises :class:`ImportError` if ``curl_cffi`` isn't installed — callers
    should catch this and fall back to the plain ``requests`` session.
    """
    from curl_cffi import requests as curl_requests  # type: ignore

    return curl_requests.Session(impersonate="chrome")


def default_session():
    """Build the default HTTP session per the env-var contract.

    Returns a session-shaped object exposing ``get``/``post``/etc.
    """
    if os.environ.get("PYBANDCAMP_TRANSPORT", "").strip().lower() == "curl_cffi":
        try:
            return _make_curl_cffi_session()
        except ImportError:
            # curl_cffi requested but not installed — fall through to
            # plain requests so the user isn't hard-blocked.
            pass
    return _make_requests_session()
