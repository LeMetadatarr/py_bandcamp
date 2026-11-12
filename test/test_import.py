def test_import():
    from py_bandcamp import BandCamp, BandcampTrack, BandcampAlbum, BandcampArtist, BandcampLabel


def test_version():
    from py_bandcamp.version import __version__
    assert __version__


def test_readme_names_the_mediavocab_floor_the_package_declares():
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parent.parent
    declared = re.search(r'"(mediavocab>=[^"]+)"', (root / "pyproject.toml").read_text()).group(1)
    assert f"`{declared}`" in (root / "README.md").read_text()


def _root():
    import pathlib
    return pathlib.Path(__file__).resolve().parent.parent


def _floor(text):
    import re
    major, minor = re.search(r'requires-python = ">=(\d+)\.(\d+)', text).groups()
    return int(major), int(minor)


def test_every_module_parses_under_the_declared_python_floor():
    import ast
    floor = _floor((_root() / "pyproject.toml").read_text())
    files = sorted((_root() / "py_bandcamp").glob("*.py"))
    assert files
    for path in files:
        ast.parse(path.read_text(), filename=str(path), feature_version=floor)


def test_declared_floor_is_the_oldest_python_in_the_ci_matrix():
    import json
    import re
    ci = (_root() / ".github" / "workflows" / "build-tests.yml").read_text()
    versions = json.loads(re.search(r"python_versions: '(\[.*?\])'", ci).group(1))
    oldest = min(tuple(int(x) for x in v.split(".")) for v in versions)
    assert _floor((_root() / "pyproject.toml").read_text()) == oldest
