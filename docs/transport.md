# Transport / HTTP session

## Default session: `py_bandcamp/transport.py:52`

On import, `py_bandcamp.session` calls `transport.default_session()` and
stores the result as the module-global `SESSION`. All submodules proxy
requests through `py_bandcamp.session.HTTP`, which resolves to `SESSION` at
call time so `set_session()` takes effect immediately everywhere.

The default session is a `requests.Session` with a Chrome-ish `User-Agent`
replacing the `python-requests/X.Y` default.

## `PYBANDCAMP_TRANSPORT=curl_cffi`

Bandcamp's `/search` endpoint is fronted by a Fastly bot challenge that keys
off the TLS fingerprint of vanilla `requests`. Setting this env var makes
`default_session()` return a `curl_cffi.requests.Session(impersonate="chrome")`
which presents a real browser TLS/JA3 fingerprint.

```bash
pip install "py_bandcamp[stealth]"
export PYBANDCAMP_TRANSPORT=curl_cffi
python your_script.py
```

If `curl_cffi` is not installed the env var is silently ignored and the
plain `requests` session is used. Nothing hard-breaks, but search results
may be empty or contain challenge HTML.

The env var is read on each call to `default_session()`, so tests can flip it
at runtime without restarting the process.

`transport.default_session`: `py_bandcamp/transport.py:52`

## Global session replacement: `py_bandcamp/session.py:13`

```python
from py_bandcamp import set_session, get_session

# Swap in any session-shaped object
import requests
s = requests.Session()
s.headers["User-Agent"] = "my-app/1.0"
set_session(s)

# Read back the current session
current = get_session()
```

The session object must implement `.get(url, **kwargs)` returning a response
with `.text`, `.content`, `.ok`, and `.status_code`.

## Per-instance session: `py_bandcamp/__init__.py:382`

```python
from py_bandcamp import BandCamp
from py_bandcamp.transport import default_session

bc = BandCamp(session=default_session())
for r in bc.search_tracks("doom metal"):
    print(r.work.title)
```

Per-instance sessions leave the global `SESSION` untouched. The `_hybridmethod`
descriptor on `BandCamp` routes `BandCamp.method()` (class-style) through the
global proxy and `bc.method()` (instance-style) through `bc._session`.

## What the bot challenge affects

| Operation | Affected by Fastly? |
|---|---|
| `BandCamp.search(...)` | Yes, keyword search hits `/search` |
| `BandCamp.search_tag(...)` | No, browses tag pages, not `/search` |
| `BandCamp.album_to_release(url)` | No, fetches album page directly |
| `BandCamp.track_to_release(url)` | No, fetches track page directly |
| `BandCamp.get_stream_url(url)` | No, parses `data-tralbum` from track page |
| `BandCamp.get_recommendations(url)` | No, parses `#recommendations_container` |

---
[← mediavocab converters](converters.md) · [Home](index.md)
