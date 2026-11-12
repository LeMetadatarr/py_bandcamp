# Tests for the arrkit plugin

These tests cover `py_bandcamp/arr.py` against a fake Bandcamp on loopback. They need arrkit, which is not on PyPI, so the repository's CI (`test_path: test`) does not run them. Run them before every change to the plugin.

From a checkout, with an arrkit wheel or checkout at hand:

    uv venv && uv pip install ./arrkit-wheel.whl -e '.[test,test-arr]'
    python -m pytest test tests_arr -q

The `test-arr` extra holds what the suite imports beyond the library: arrkit, pytest and PyYAML (one test reads a recorded page from the library's cassette). The suite runs without network access.
