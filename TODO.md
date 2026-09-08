# TODO — py_bandcamp

## Open issues

- [ ] #1 feat request: stream songs!

## Gaps

- [ ] `BandcampLabel.scrap()` is a no-op stub (`py_bandcamp/models.py:543`); label pages are not scraped, so `search_labels` / `10_label_catalog.py` return minimal data.
- [ ] No static type checking configured (only ruff); core source is largely untyped.
- [ ] pyproject `Homepage` points at `OpenJarbas/py_bandcamp` instead of the canonical `TigreGotico/py_bandcamp`.
- [ ] Build artifacts committed to the tree (`build/`, `py_bandcamp.egg-info/`, `.coverage`, `.pytest_cache/`, `.ruff_cache/`) — should be gitignored.

CI coverage is complete: build-tests, coverage, license_check, lint, pip_audit, publish_stable, release_workflow, release-preview, repo-health, conventional-label, plus a custom nightly-live cassette-drift job — all referencing `OpenVoiceOS/gh-automations@dev`.

## Code TODOs

- `py_bandcamp/models.py:543` — `self._page_data = {}  # TODO` (BandcampLabel scrape unimplemented).
