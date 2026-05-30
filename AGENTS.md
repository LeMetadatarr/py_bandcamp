# AGENTS.md — py_bandcamp

Bandcamp HTML scraper that returns typed `mediavocab` `Release`/`Entity` objects (no dict fallback) for albums, tracks, artists, labels, search, recommendations, stream URLs, and lyrics.

## Setup

```bash
pip install -e .
# for live keyword search behind Bandcamp's Fastly bot challenge:
pip install -e ".[stealth]"
export PYBANDCAMP_TRANSPORT=curl_cffi
```

## Test

```bash
pip install -e ".[test]"   # pytest, vcrpy, pytest-vcr
pytest test/
```

Tests are VCR-cassette backed (`record_mode="none"` in `test/conftest.py`) — they replay captured Bandcamp responses under `test/cassettes/<module>/<test>.yaml` and make no network calls. Re-record locally with `pytest --vcr-record=all test/test_*_vcr.py`. The `nightly-live.yml` workflow re-runs `_vcr` tests against live endpoints (`--vcr-record=all`, cassettes not committed) to surface upstream markup drift.

## Lint/Typecheck

Ruff via `OpenVoiceOS/gh-automations/.github/workflows/lint.yml@dev` (`lint.yml`). No type checker configured; source is untyped except `transport.py`.

## Layout

- `py_bandcamp/__init__.py` — `BandCamp` facade + mediavocab converters (`album_to_release`, `track_to_release`, `search_*`, `get_stream_url`, `get_recommendations`, genre/SPDX/date mapping).
- `py_bandcamp/models.py` — internal scraper models: `BandcampAlbum`, `BandcampTrack`, `BandcampArtist`, `BandcampSingle`, `BandcampLabel`; each parses page HTML / ld+json. Each has `from_url`.
- `py_bandcamp/session.py` — global session singleton `HTTP`, `set_session`, `get_session`.
- `py_bandcamp/transport.py` — `default_session()`: plain `requests` with Chrome UA, or `curl_cffi` impersonating Chrome when `PYBANDCAMP_TRANSPORT=curl_cffi`.
- `py_bandcamp/utils.py` — ld+json / page-data blob extraction, stream-data parsing.
- `examples/` — 10 runnable example scripts; `docs/` — getting-started, models, search, converters, transport.

## Conventions

- Branch `dev` (work) / `master` (stable); NEVER `main`.
- Never edit `py_bandcamp/version.py` — gh-automations bumps semver from conventional-commit prefixes (`feat:` / `fix:` / `feat!:`).
- New repos private by default.
- Commit identity: JarbasAi <jarbasai@mailfence.com>.
- Reference `OpenVoiceOS/gh-automations` reusable workflows at `@dev`.
- No Neon / `neon-*` references.
- No meta-commentary (no history/dates/"before times"); describe current state only.
- CI is provided by `OpenVoiceOS/gh-automations`.

## Gotchas

- `/search` is fronted by a Fastly JS bot challenge that rejects vanilla `requests` TLS fingerprints — keyword `search_*` needs the `[stealth]` extra + `PYBANDCAMP_TRANSPORT=curl_cffi`. Static fetches (album/track/artist pages, tag browse) work without it.
- Stream URLs from `get_stream_url` are time-limited MP3-128 CDN tokens — do not cache.
- `BandcampLabel.scrap()` is a stub (`self._page_data = {}  # TODO`) — label pages are not actually scraped.
- `Release.license` is best-effort SPDX guessed from CC keyword tags; empty string when no CC hint (does not assume All-Rights-Reserved).
- pyproject `Homepage` URL points at `OpenJarbas/py_bandcamp`, but the canonical remote is `TigreGotico/py_bandcamp`.
