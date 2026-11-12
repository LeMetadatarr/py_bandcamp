"""py_bandcamp as an arrkit indexer and download client, against a fake site on 127.0.0.1.

The pages are synthetic: they carry the structure the parsers read (search result items, a release page's ld+json, data-tralbum and
license section) and placeholder names only. Nothing here reaches the real site. Run with
`python -m pytest tests_arr` after installing the `test-arr` extra; see tests_arr/README.md."""
import html
import http.client
import importlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import unittest
import urllib.error
from unittest import mock

from arrkit import net, plugins
from arrkit.clients import ClientError
from arrkit.indexers import IndexerError
from arrkit.testing import FakeServer

from py_bandcamp import arr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MP3 = b"ID3" + b"\x00" * 2000
CC = "https://creativecommons.org/licenses/by-nc-nd/3.0/"


def result(kind, title, url, by="", released="released 27 March 2020", length="2 tracks, 6 minutes"):
    sub = f"by {by}" if kind == "ALBUM" else f"from Some Album by {by}"
    return (f'<li class="searchresult data-search"><div class="art"><img src="https://f4.bcbits.com/img/{title}.jpg"></div>'
            f'<div class="result-info"><div class="itemtype">{kind}</div><div class="heading"><a href="{url}?from=search">{title}</a></div>'
            f'<div class="subhead">{sub}</div><div class="released">{released}</div><div class="length">{length}</div>'
            f'<div class="tags">tags: ambient, drone</div></div></li>')


def search_page(*items):
    return "<html><ul class='result-items'>" + "".join(items) + "</ul></html>"


def tralbum(tracks, pref=2, minimum=7.0, set_price=None, free_page=None, audio=True, preorder=False, private=None, license_type=1):
    return {"FREE": 1, "PAID": 2, "hasAudio": audio, "freeDownloadPage": free_page, "is_preorder": preorder, "album_is_preorder": preorder,
            "id": 4242, "current": {"download_pref": pref, "minimum_price": minimum, "is_set_price": set_price, "private": private,
                                    "release_date": "27 Mar 2020 00:00:00 GMT"},
            "trackinfo": [{"track_id": 100 + n, "track_num": n, "title": t, "duration": secs, "license_type": license_type,
                           "file": {"mp3-128": s} if s else None} for n, t, secs, s in tracks]}


def album_page(url, tr, title="Placeholder LP", artist="Sample Artist", cc=None, ld_extra=None):
    ld = {"@type": "MusicAlbum", "@id": url, "name": title, "image": "https://f4.bcbits.com/img/a1.jpg", "datePublished": "27 Mar 2020 00:00:00 GMT",
          "keywords": "ambient, drone", "numTracks": len(tr["trackinfo"]), "byArtist": {"@type": "MusicGroup", "name": artist, "@id": "https://sample.bandcamp.com"},
          "additionalProperty": []} | (ld_extra or {})
    lic = f'<div id="license" class="info license"><a href="{cc}">some rights reserved</a></div>' if cc else ""
    return (f'<html><div data-tralbum="{html.escape(json.dumps(tr))}"></div>{lic}'
            f'<script type="application/ld+json">{json.dumps(ld)}</script></html>')


def tracks_for(site, n=2, stream_path="/stream"):
    return [(i, f"Track {i}", 180 + i, f"{site.url}{stream_path}/{i}.mp3") for i in range(1, n + 1)]


CHALLENGE = "<html><title>Just a moment...</title><div>Verify you are human</div></html>"
# the shape of the answer the live site gave to a plain search request: status 200, a JavaScript challenge page
FASTLY_CHALLENGE = ('<!DOCTYPE html><html lang="en"><head><link href="/_fs-ch-1T1wmsGaOgGaSxcX/assets/styles.css" rel="stylesheet" />'
                    '<title>Client Challenge</title></head><body><noscript>JavaScript is disabled in your browser. Please enable JavaScript to proceed.'
                    '</noscript><div id="loading-error" role="alert">A required part of this site couldn\u2019t load.</div></body></html>')


class Base(unittest.TestCase):
    def setUp(self):
        self.site = FakeServer().serve(self)
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        net.space(net.host_of(self.site.url), 0)

    def free_album(self, name="lp", **kw):
        url = f"{self.site.url}/album/{name}"
        self.site.on("GET", f"/album/{name}", album_page(url, tralbum(tracks_for(self.site), pref=1, minimum=None, **kw)))
        return url

    def stream(self, n=2, body=MP3):
        for i in range(1, n + 1):
            self.site.on("GET", f"/stream/{i}.mp3", (200, {"Content-Type": "audio/mpeg"}, body))

    def indexer(self, **settings):
        s = {"url": self.site.url, "delay": "0", "resolve": "1"} | settings
        return arr.Bandcamp({"id": 1, "name": "Bandcamp", "settings": s})


class Plugin(unittest.TestCase):
    """The entry points of pyproject.toml, installed as a distribution in a temporary folder, are what arrkit loads."""

    def setUp(self):
        with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
            eps = tomllib.load(f)["project"]["entry-points"]
        self.site = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.site, True)
        info = os.path.join(self.site, "py_bandcamp_fixture-9.9.dist-info")
        os.makedirs(info)
        with open(os.path.join(info, "METADATA"), "w") as f:
            f.write("Metadata-Version: 2.1\nName: py-bandcamp-fixture\nVersion: 9.9\n")
        with open(os.path.join(info, "entry_points.txt"), "w") as f:
            for group, items in eps.items():
                f.write(f"[{group}]\n" + "".join(f"{k} = {v}\n" for k, v in items.items()))
        sys.path.insert(0, self.site)
        self.addCleanup(sys.path.remove, self.site)
        importlib.invalidate_caches()

    def row(self, kind, enabled=()):
        return next(r for r in plugins.listing(kind, enabled) if r["name"] == "bandcamp")

    def test_installed_is_listed_disabled_and_enabled_only_by_name(self):
        for kind in ("indexer", "client"):
            self.assertEqual(self.row(kind)["status"], "disabled", self.row(kind))
            self.assertEqual(self.row(kind, ["bandcamp"])["status"], "enabled", self.row(kind, ["bandcamp"]))
        self.assertIs(plugins.classes("indexer", ["bandcamp"])["bandcamp"], arr.Bandcamp)
        self.assertIs(plugins.classes("client", ["bandcamp"])["bandcamp"], arr.BandcampClient)
        self.assertEqual(plugins.classes("indexer", []), {})

    def test_the_declared_surface(self):
        self.assertFalse(arr.Bandcamp.adult or arr.BandcampClient.adult)
        self.assertEqual((arr.Bandcamp.API_VERSION, arr.BandcampClient.API_VERSION), (1, 1))
        self.assertEqual((arr.Bandcamp.protocol, arr.BandcampClient.protocols), ("bandcamp", ("bandcamp",)))
        self.assertIn("bandcamp-stream", arr.Bandcamp.protocols)
        self.assertNotIn("bandcamp-stream", arr.BandcampClient.protocols)

    def test_arrkit_is_an_optional_extra_and_never_a_dependency(self):
        with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
            project = tomllib.load(f)["project"]
        self.assertEqual(project["optional-dependencies"]["arr"], ["arrkit>=0.1.0a9"])
        self.assertFalse([d for d in project["dependencies"] if "arrkit" in d])

    def test_the_library_imports_without_arrkit(self):
        code = "import sys; sys.modules['arrkit'] = None; import py_bandcamp; print('py_bandcamp.arr' in sys.modules)"
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual((out.returncode, out.stdout.strip()), (0, "False"), out.stderr)


class Search(Base):
    def two_albums(self):
        a, b = f"{self.site.url}/album/lp", f"{self.site.url}/album/ep"
        self.site.on("GET", "/search", search_page(result("ALBUM", "Placeholder LP", a, "Sample Artist"), result("ALBUM", "Placeholder EP", b, "Sample Artist")))
        self.free_album("lp")

    def test_artist_and_album_search_albums_and_resolve_only_the_first(self):
        self.two_albums()
        rels = self.indexer().search({"artist": "Sample Artist", "album": "Placeholder LP", "year": 2020})
        q = self.site.requests("GET", "/search")
        self.assertEqual((len(q), q[0].query["q"], q[0].query["item_type"]), (1, "Sample Artist Placeholder LP", "a"))
        self.assertEqual(len(self.site.requests("GET", "/album/")), 1, "only `resolve` pages are read")
        one, two = rels
        self.assertEqual((one["title"], one["artist"], one["album"], one["year"], one["published"]),
                         ("Sample Artist - Placeholder LP (2020) [MP3 128]", "Sample Artist", "Placeholder LP", 2020, "2020-03-27"))
        self.assertEqual((one["protocol"], one["kind"], one["access"], one["downloadable"], one["needs_purchase"]), ("bandcamp", "download", "free", True, False))
        self.assertEqual((one["format"], one["bitrate"], one["quality"], one["tracks"], one["seconds"]), ("MP3", 128, "MP3-128", 2, 181 + 182))
        self.assertEqual(one["tracklist"], [{"number": 1, "title": "Track 1", "seconds": 181}, {"number": 2, "title": "Track 2", "seconds": 182}])
        self.assertEqual((one["tags"], one["guid"], one["url"], one["indexer"]), (["ambient", "drone"], "bandcamp:" + self.site.url + "/album/lp", self.site.url + "/album/lp", "Bandcamp"))
        self.assertEqual(one["bandcamp_id"], 4242)
        self.assertEqual((two["access"], two["protocol"], two["kind"], two["downloadable"], two["tracks"], two["seconds"]),
                         ("unchecked", "bandcamp-stream", "stream", False, 2, 360))
        self.assertEqual(two["url"], self.site.url + "/album/ep", "the search tracking query is dropped")

    def test_a_plain_term_is_the_search_text_and_the_titles_are_tried_in_turn(self):
        self.site.on("GET", "q=first", search_page())
        self.site.on("GET", "q=second", search_page(result("ALBUM", "Second LP", self.site.url + "/album/s", "Who")))
        rels = self.indexer(resolve="0").search({"title": "first", "titles": ["second", "third"]})
        self.assertEqual([r["album"] for r in rels], ["Second LP"])
        self.assertEqual([r.query["q"] for r in self.site.requests("GET", "/search")], ["first", "second"])
        self.site.calls.clear()
        self.indexer(resolve="0").search("plain words")
        self.assertEqual([r.query["q"] for r in self.site.requests("GET", "/search")], ["plain words"])

    def test_a_track_query_searches_tracks(self):
        self.site.on("GET", "/search", search_page(result("TRACK", "Placeholder Song", self.site.url + "/track/song", "Sample Artist")))
        rels = self.indexer(resolve="0").search({"artist": "Sample Artist", "track": "Placeholder Song"})
        q = self.site.requests("GET", "/search")[0].query
        self.assertEqual((q["q"], q["item_type"]), ("Sample Artist Placeholder Song", "t"))
        self.assertEqual((rels[0]["title"], rels[0]["url"]), ("Sample Artist - Placeholder Song (2020) [MP3 128]", self.site.url + "/track/song"))

    def test_max_results_caps_the_answer(self):
        self.site.on("GET", "/search", search_page(*[result("ALBUM", f"LP {i}", f"{self.site.url}/album/{i}", "A") for i in range(5)]))
        self.assertEqual(len(self.indexer(resolve="0", max_results="2").search("x")), 2)

    def test_nothing_to_search_for_asks_nothing(self):
        self.assertEqual(self.indexer().search({}), [])
        self.assertEqual(self.site.calls, [])

    def release_with(self, tr, cc=None, name="lp"):
        url = f"{self.site.url}/album/{name}"
        self.site.clear()
        self.site.on("GET", "/search", search_page(result("ALBUM", "Placeholder LP", url, "Sample Artist")))
        self.site.on("GET", f"/album/{name}", album_page(url, tr, cc=cc))
        return self.indexer().search({"artist": "Sample Artist", "album": "Placeholder LP"})[0]

    def test_terms_of_sale_decide_what_is_downloadable(self):
        t = tracks_for(self.site)
        cases = [("free", tralbum(t, pref=1, minimum=None), True), ("free", tralbum(t, pref=2, minimum=7.0, free_page="https://x/download"), True),
                 ("name_your_price", tralbum(t, pref=2, minimum=0.0), True), ("paid", tralbum(t, pref=2, minimum=7.0), False),
                 ("paid", tralbum(t, pref=2, minimum=0.0, set_price=5.0), False), ("stream_only", tralbum(t, pref=None, minimum=None), False),
                 ("preorder", tralbum(t, pref=1, minimum=None, preorder=True), False), ("restricted", tralbum(t, pref=1, minimum=None, private=True), False),
                 ("no_audio", tralbum(t, pref=1, minimum=None, audio=False), False), ("stream_only", tralbum(t, pref=9, minimum=None), False)]
        for access, tr, ok in cases:
            r = self.release_with(tr)
            self.assertEqual((r["access"], r["downloadable"]), (access, ok), tr["current"])
            self.assertEqual((r["protocol"], r["kind"]), ("bandcamp", "download") if ok else ("bandcamp-stream", "stream"))
            self.assertEqual(r["needs_purchase"], access in ("paid", "preorder"))
            self.site.calls.clear()

    def test_a_paid_release_reports_its_minimum_price(self):
        r = self.release_with(tralbum(tracks_for(self.site), pref=2, minimum=7.0))
        self.assertEqual((r["price_min"], r["needs_purchase"]), (7.0, True))

    def test_a_creative_commons_license_makes_a_paid_release_downloadable(self):
        r = self.release_with(tralbum(tracks_for(self.site), pref=2, minimum=7.0, license_type=2), cc=CC)
        self.assertEqual((r["access"], r["downloadable"], r["license"], r["license_url"]), ("licensed", True, "CC-BY-NC-ND-3.0", CC))

    def test_all_rights_reserved_beats_a_license_link(self):
        r = self.release_with(tralbum(tracks_for(self.site), pref=2, minimum=7.0, license_type=1), cc=CC)
        self.assertEqual((r["access"], r["downloadable"], r["license"]), ("paid", False, ""))

    def test_a_license_tag_alone_grants_nothing(self):
        url = f"{self.site.url}/album/lp"
        self.site.on("GET", "/search", search_page(result("ALBUM", "Placeholder LP", url, "A")))
        self.site.on("GET", "/album/lp", album_page(url, tralbum(tracks_for(self.site), pref=2, minimum=7.0), ld_extra={"keywords": "cc-by, ambient"}))
        r = self.indexer().search("x")[0]
        self.assertEqual((r["access"], r["license"]), ("paid", ""))

    def test_license_ids(self):
        self.assertEqual(arr.spdx_of("https://creativecommons.org/licenses/by/4.0/"), "CC-BY-4.0")
        self.assertEqual(arr.spdx_of("http://creativecommons.org/licenses/by-sa/3.0/deed.en"), "CC-BY-SA-3.0")
        self.assertEqual(arr.spdx_of("https://creativecommons.org/publicdomain/zero/1.0/"), "CC0-1.0")
        self.assertEqual(arr.spdx_of("https://example.org/licenses/by/4.0/"), "")

    def test_a_page_that_is_not_a_release_page_leaves_the_release_unchecked(self):
        self.site.on("GET", "/search", search_page(result("ALBUM", "Placeholder LP", self.site.url + "/album/lp", "A")))
        self.site.on("GET", "/album/lp", "<html>nothing here</html>")
        r = self.indexer().search("x")[0]
        self.assertEqual((r["access"], r["protocol"]), ("unchecked", "bandcamp-stream"))

    def test_a_release_page_on_a_foreign_host_is_never_fetched(self):
        self.site.on("GET", "/search", search_page(result("ALBUM", "Placeholder LP", "http://169.254.169.254/album/lp", "A")))
        r = self.indexer().search("x")[0]
        self.assertEqual(r["access"], "unchecked")
        self.assertEqual([c.path.split("?")[0] for c in self.site.calls], ["/search"])
        self.assertTrue(arr.trusted("https://sample.bandcamp.com/album/lp"))
        self.assertFalse(arr.trusted("http://sample.bandcamp.com/album/lp"))
        self.assertFalse(arr.trusted("https://bandcamp.com.evil.example/album/lp"))
        self.assertFalse(arr.trusted("https://evilbandcamp.com/album/lp"))
        self.assertTrue(arr.trusted("https://t4.bcbits.com/stream/1", stream=True))
        self.assertFalse(arr.trusted("https://t4.bcbits.com/stream/1"))

    def test_a_bot_check_is_an_error_and_never_answered(self):
        self.site.on("GET", "/search", CHALLENGE)
        with self.assertRaisesRegex(IndexerError, "bot check.*not usable"):
            self.indexer().search("x")
        self.assertEqual(len(self.site.calls), 1, "the check is reported, not solved and retried")
        ok, msg = self.indexer().test()
        self.assertFalse(ok)
        self.assertIn("bot check", msg)

    def test_the_challenge_page_the_live_site_answers_with_is_a_bot_check(self):
        self.site.on("GET", "/search", FASTLY_CHALLENGE)
        with self.assertRaisesRegex(IndexerError, "bot check.*not usable"):
            self.indexer().search("x")
        self.assertFalse(self.indexer().test()[0])
        self.assertTrue(arr.is_challenge(FASTLY_CHALLENGE))
        self.assertEqual(len(self.site.calls), 2, "one search and one test, no retry and no other route tried")

    def test_a_refusal_is_reported_as_not_usable(self):
        self.site.on("GET", "/search", (403, {}, "Forbidden"))
        with self.assertRaisesRegex(IndexerError, "refused.*not usable"):
            self.indexer().search("x")
        self.assertEqual(len(self.site.calls), 1)

    def test_a_search_page_with_results_is_not_a_bot_check(self):
        page = search_page(result("ALBUM", "Access Denied Captcha", self.site.url + "/album/x", "Verify You Are Human"))
        self.site.on("GET", "/search", page)
        self.assertEqual(len(self.indexer(resolve="0").search("x")), 1)

    def test_requests_are_spaced_by_the_delay_setting_and_carry_arrkits_user_agent(self):
        self.site.on("GET", "/search", search_page(result("ALBUM", "Placeholder LP", self.site.url + "/album/lp", "A")))
        self.free_album("lp")
        self.indexer(delay="0.25").search("x")
        self.assertEqual(len(self.site.calls), 2)
        self.assertTrue(all(c.headers.get("User-Agent") == net.USER_AGENT for c in self.site.calls), [c.headers for c in self.site.calls])

    def test_the_librarys_own_session_is_not_used(self):
        import py_bandcamp
        self.two_albums()
        with mock.patch.object(py_bandcamp.get_session(), "get", side_effect=AssertionError("library transport used")):
            self.indexer().search("x")

    def test_test_counts_the_albums_a_search_answers(self):
        self.site.on("GET", "/search", search_page(result("ALBUM", "Placeholder LP", self.site.url + "/album/lp", "A")))
        self.assertEqual(self.indexer().test(), (True, "search answered with 1 albums"))
        self.site.clear()
        self.site.on("GET", "/search", "<html>changed</html>")
        ok, msg = self.indexer().test()
        self.assertFalse(ok)
        self.assertIn("layout", msg)


class Recorded(unittest.TestCase):
    """A release page recorded from the live site (the library's test cassette) is read by the same code."""

    def test_a_recorded_paid_album_page_is_paid_with_its_tracklist_and_streams(self):
        import yaml
        path = os.path.join(ROOT, "test", "cassettes", "test_album_vcr", "test_album_from_url_parses_tracklist.yaml")
        with open(path) as f:
            body = next(i["response"]["body"]["string"] for i in yaml.safe_load(f)["interactions"] if "/album/" in i["request"]["uri"])
        page = arr.read_page(body.decode() if isinstance(body, bytes) else body, "https://runthejewels.bandcamp.com/album/run-the-jewels")
        self.assertEqual((page["artist"], page["album"], page["access"], page["downloadable"], page["price_min"], page["license"]),
                         ("Run The Jewels", "Run The Jewels", "paid", False, 7.0, ""))
        self.assertEqual(len(page["tracks"]), 10)
        self.assertEqual((page["tracks"][0]["title"], page["tracks"][0]["number"], page["tracks"][0]["seconds"]), ("Run The Jewels", 1, 210))
        self.assertTrue(page["tracks"][0]["stream"].startswith("https://t4.bcbits.com/stream/"))
        self.assertEqual((page["year"], page["id"]), (2013, 25650332))


class Rss(Base):
    def artist_page(self):
        return ('<html><div id="band-name-location"><span class="title">Sample Artist</span></div><ol id="music-grid">'
                '<li><a href="/album/newer"><div class="art"><img src="https://f4.bcbits.com/img/n.jpg"></div><p class="title">Newer LP</p></a></li>'
                '<li><a href="/album/older"><div class="art"><img src="https://f4.bcbits.com/img/o.jpg"></div><p class="title">Older LP</p></a></li></ol></html>')

    def test_followed_artist_pages_give_their_releases_in_page_order(self):
        self.site.on("GET", "/album/newer", album_page(self.site.url + "/album/newer", tralbum(tracks_for(self.site), pref=1, minimum=None), title="Newer LP"))
        self.site.on("GET", "/album/older", album_page(self.site.url + "/album/older", tralbum(tracks_for(self.site), pref=2, minimum=7.0), title="Older LP"))
        self.site.on("GET", "/", self.artist_page())
        rels = self.indexer(resolve="1", follow_artists=self.site.url).rss()
        self.assertEqual([(r["album"], r["artist"], r["access"]) for r in rels], [("Newer LP", "Sample Artist", "free"), ("Older LP", "Sample Artist", "unchecked")])

    def test_a_name_becomes_its_bandcamp_subdomain_and_junk_is_dropped(self):
        self.assertEqual(arr.artist_url("Some Band"), "https://some-band.bandcamp.com")
        self.assertEqual(arr.artist_url("https://x.bandcamp.com/"), "https://x.bandcamp.com")
        self.assertEqual(arr.artist_url("../../etc"), "https://etc.bandcamp.com")
        self.assertEqual(arr.artist_url("!!!"), "")

    def test_an_instance_that_follows_nothing_returns_nothing_and_asks_nothing(self):
        self.assertEqual(self.indexer().rss(), [])
        self.assertEqual(self.site.calls, [])

    def test_a_followed_address_on_a_foreign_host_is_not_read(self):
        self.assertEqual(self.indexer(follow_artists="http://169.254.169.254").rss(), [])
        self.assertEqual(self.site.calls, [])


class ClientCase(Base):
    def client(self, ident=2, **settings):
        s = {"download_dir": os.path.join(self.tmp, "dl"), "delay": "0", "extra_hosts": net.host_of(self.site.url)} | settings
        os.makedirs(s["download_dir"], exist_ok=True)
        c = arr.BandcampClient({"id": ident, "name": "Bandcamp", "settings": s}, state_dir=os.path.join(self.tmp, "state"))
        self.addCleanup(c.stop)
        return c

    def finish(self, c, jid, timeout=30):
        end = time.time() + timeout
        while time.time() < end:
            row = next(r for r in c.status() if r["client_id"] == jid)
            if row["state"] in ("completed", "failed"):
                return row
            time.sleep(0.05)
        self.fail("the job did not end")

    def leftovers(self):
        return sorted(os.path.join(d, f) for d, _, files in os.walk(os.path.join(self.tmp, "dl")) for f in files)

    def folders(self):
        return os.listdir(os.path.join(self.tmp, "dl"))

    def grab(self, c, url, **extra):
        return c.add({"title": "Sample Artist - Placeholder LP (2020) [MP3 128]", "url": url, "protocol": "bandcamp", **extra})

    def album(self, tr, name="lp", cc=None):
        url = f"{self.site.url}/album/{name}"
        self.site.on("GET", f"/album/{name}", album_page(url, tr, cc=cc))
        return url


class Client(ClientCase):
    def test_a_free_release_is_downloaded_into_its_own_folder_and_the_files_are_returned(self):
        url = self.free_album()
        self.stream()
        c = self.client()
        row = self.finish(c, self.grab(c, url, access="free"))
        self.assertEqual(row["state"], "completed", row)
        self.assertEqual(row["files"], ["01 - Track 1.mp3", "02 - Track 2.mp3"])
        self.assertEqual(os.path.dirname(row["path"]), os.path.join(self.tmp, "dl"))
        self.assertEqual(sorted(os.listdir(row["path"])), row["files"])
        with open(os.path.join(row["path"], row["files"][0]), "rb") as f:
            self.assertEqual(f.read(), MP3)
        self.assertEqual((row["size"], row["progress"]), (2 * len(MP3), 100))
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "state", "bandcamp-2.json")))

    def test_name_your_price_at_nothing_and_a_creative_commons_license_are_downloaded(self):
        self.stream()
        c = self.client()
        free = self.album(tralbum(tracks_for(self.site), pref=2, minimum=0.0), "nyp")
        licensed = self.album(tralbum(tracks_for(self.site), pref=2, minimum=7.0, license_type=2), "cc", cc=CC)
        self.assertEqual(self.finish(c, self.grab(c, free))["state"], "completed")
        self.assertEqual(self.finish(c, self.grab(c, licensed))["state"], "completed")

    def test_a_release_that_needs_purchase_is_refused_before_anything_is_asked(self):
        c = self.client()
        with self.assertRaisesRegex(ClientError, "needs purchase"):
            self.grab(c, self.site.url + "/album/lp", access="paid")
        with self.assertRaisesRegex(ClientError, "needs purchase"):
            self.grab(c, self.site.url + "/album/lp", access="preorder")
        with self.assertRaisesRegex(ClientError, "not downloadable"):
            self.grab(c, self.site.url + "/album/lp", access="stream_only")
        self.assertEqual((self.site.calls, c.status()), ([], []))

    def test_the_page_is_judged_again_at_download_time(self):
        """A release the indexer called free is refused when the page now asks for money, and no stream is fetched."""
        url = self.album(tralbum(tracks_for(self.site), pref=2, minimum=7.0))
        self.stream()
        c = self.client()
        row = self.finish(c, self.grab(c, url, access="free", downloadable=True))
        self.assertEqual(row["state"], "failed")
        self.assertIn("needs purchase", row["message"])
        self.assertEqual(self.site.requests("GET", "/stream/"), [])
        self.assertEqual((self.leftovers(), self.folders()), ([], []))

    def test_streaming_only_and_private_pages_fail_without_a_download(self):
        self.stream()
        c = self.client()
        for tr in (tralbum(tracks_for(self.site), pref=None, minimum=None), tralbum(tracks_for(self.site), pref=1, minimum=None, private=True)):
            row = self.finish(c, self.grab(c, self.album(tr)))
            self.assertEqual(row["state"], "failed", row)
            self.assertIn("not downloadable", row["message"])
        self.assertEqual(self.site.requests("GET", "/stream/"), [])

    def test_a_release_page_on_another_host_is_refused(self):
        c = self.client(extra_hosts="")
        for url in ("http://169.254.169.254/album/lp", "https://bandcamp.com.evil.example/album/lp", "file:///etc/passwd", self.site.url + "/album/lp", ""):
            with self.assertRaisesRegex(ClientError, "no Bandcamp release page"):
                self.grab(c, url)
        with self.assertRaisesRegex(ClientError, "no Bandcamp release page"):
            self.grab(c, "https://sample.bandcamp.com/")

    def test_a_stream_link_on_another_host_fails_the_job(self):
        t = [(1, "Track 1", 100, "http://169.254.169.254/latest/meta-data"), ]
        url = self.album(tralbum(t, pref=1, minimum=None))
        c = self.client()
        row = self.finish(c, self.grab(c, url))
        self.assertEqual(row["state"], "failed")
        self.assertIn("not a Bandcamp address", row["message"])
        self.assertEqual(self.folders(), [])

    def test_a_track_without_a_stream_fails_before_anything_is_written(self):
        t = tracks_for(self.site)
        t[1] = (2, "Track 2", 100, "")
        url = self.album(tralbum(t, pref=1, minimum=None))
        self.stream()
        c = self.client()
        row = self.finish(c, self.grab(c, url))
        self.assertEqual((row["state"], row["message"]), ("failed", "track 2 has no stream"))
        self.assertEqual((self.folders(), self.site.requests("GET", "/stream/")), ([], []))

    def test_a_download_that_is_not_audio_fails_and_removes_the_files_before_it(self):
        url = self.free_album()
        self.site.on("GET", "/stream/1.mp3", (200, {"Content-Type": "audio/mpeg"}, MP3))
        self.site.on("GET", "/stream/2.mp3", (200, {"Content-Type": "text/html"}, "<html>" + "x" * 3000 + "</html>"))
        c = self.client()
        row = self.finish(c, self.grab(c, url))
        self.assertEqual((row["state"], row["message"]), ("failed", "track 2 did not come as an audio file"))
        self.assertEqual((self.leftovers(), self.folders()), ([], []))

    def test_a_refused_stream_fails_the_job_and_cleans_up(self):
        url = self.free_album()
        self.site.on("GET", "/stream/1.mp3", (200, {}, MP3))
        self.site.on("GET", "/stream/2.mp3", (403, {}, "no"))
        c = self.client()
        row = self.finish(c, self.grab(c, url))
        self.assertEqual(row["state"], "failed")
        self.assertIn("refused", row["message"])
        self.assertEqual((self.leftovers(), self.folders()), ([], []))

    def test_a_bot_check_instead_of_the_release_page_fails_the_job(self):
        self.site.on("GET", "/album/lp", CHALLENGE)
        c = self.client()
        row = self.finish(c, self.grab(c, self.site.url + "/album/lp"))
        self.assertEqual(row["state"], "failed")
        self.assertIn("bot check", row["message"])
        self.assertEqual(len(self.site.calls), 1)

    def test_a_page_gone_from_the_site_fails_the_job(self):
        c = self.client()
        row = self.finish(c, self.grab(c, self.site.url + "/album/none"))
        self.assertEqual((row["state"], row["message"]), ("failed", "the release is gone from the site"))

    def test_cancelling_a_running_job_removes_its_files(self):
        url = self.free_album()
        self.site.on("GET", "/stream/1.mp3", (200, {}, MP3))
        gate, reached = threading.Event(), threading.Event()

        def slow(req):
            reached.set()
            gate.wait(20)
            return MP3
        self.site.on("GET", "/stream/2.mp3", slow)
        c = self.client()
        jid = self.grab(c, url)
        self.assertTrue(reached.wait(20))
        self.assertEqual(len(self.leftovers()), 1, "the first track is on disk while the second is awaited")
        c.remove(jid)
        gate.set()
        end = time.time() + 20
        while time.time() < end and (self.leftovers() or self.folders()):
            time.sleep(0.05)
        self.assertEqual((self.leftovers(), self.folders()), ([], []))
        self.assertEqual(c.status(), [])

    def test_names_stay_within_255_bytes_for_the_file_and_the_folder(self):
        long = "é" * 400
        t = [(1, long, 100, f"{self.site.url}/stream/1.mp3"), (2, "日本語" * 100, 100, f"{self.site.url}/stream/2.mp3")]
        url = self.album(tralbum(t, pref=1, minimum=None))
        self.stream()
        c = self.client()
        row = self.finish(c, c.add({"title": "ü" * 300, "url": url}))
        self.assertEqual(row["state"], "completed", row)
        parts = os.path.relpath(row["path"], os.path.join(self.tmp, "dl")).split(os.sep) + row["files"]
        self.assertTrue(all(0 < len(p.encode()) + (5 if p.endswith(".mp3") else 0) <= 255 for p in parts), [len(p.encode()) for p in parts])
        self.assertTrue(all(f.endswith(".mp3") and f.startswith(("01 - ", "02 - ")) for f in row["files"]), row["files"])
        self.assertEqual(len(os.listdir(row["path"])), 2)
        self.assertEqual(arr.fit("é" * 200, ".mp3", 255).encode().decode(), "é" * 125 + ".mp3")

    def test_two_tracks_with_one_title_get_two_files(self):
        t = [(1, "Same", 100, f"{self.site.url}/stream/1.mp3"), (1, "Same", 100, f"{self.site.url}/stream/2.mp3")]
        url = self.album(tralbum(t, pref=1, minimum=None))
        self.stream()
        c = self.client()
        row = self.finish(c, self.grab(c, url))
        self.assertEqual((row["state"], len(set(row["files"]))), ("completed", 2), row)

    def test_stream_requests_are_spaced_and_carry_arrkits_user_agent(self):
        url = self.free_album()
        self.stream()
        c = self.client(delay="0.2")
        self.finish(c, self.grab(c, url))
        self.assertEqual(len(self.site.calls), 3)
        self.assertTrue(all(x.headers.get("User-Agent") == net.USER_AGENT for x in self.site.calls))

    def test_remove_with_delete_files_removes_the_folder_and_nothing_else(self):
        url = self.free_album()
        self.stream()
        c = self.client()
        other = os.path.join(self.tmp, "dl", "keep.txt")
        with open(other, "w") as f:
            f.write("x")
        jid = self.grab(c, url)
        row = self.finish(c, jid)
        c.remove(jid, delete_files=True)
        self.assertFalse(os.path.exists(row["path"]))
        self.assertTrue(os.path.exists(other))

    def test_a_missing_download_folder_is_refused_and_test_says_so(self):
        c = arr.BandcampClient({"id": 3, "settings": {"download_dir": "", "extra_hosts": net.host_of(self.site.url)}}, state_dir=os.path.join(self.tmp, "state"))
        with self.assertRaisesRegex(ClientError, "no download folder"):
            self.grab(c, self.site.url + "/album/lp")
        ok, msg = self.client().test()
        self.assertTrue(ok, msg)


class Redirects(ClientCase):
    """Every hop of a redirect is checked like the first address, and a redirect never leaves https."""

    def setUp(self):
        super().setUp()
        self.other = FakeServer().serve(self)
        self.hosts = [net.host_of(self.site.url)]

    def get(self, url, hosts=None):
        return arr.Site(0, self.hosts if hosts is None else hosts).get(url)

    def test_a_redirect_to_an_untrusted_host_is_refused_and_never_requested(self):
        self.other.on("GET", "/page", "<html>the other server's body</html>")
        self.site.on("GET", "/go", (302, {"Location": self.other.url + "/page"}, ""))
        with self.assertRaisesRegex(IndexerError, "not a Bandcamp address"):
            self.get(self.site.url + "/go")
        self.assertEqual(self.other.calls, [])

    def test_a_search_whose_answer_redirects_to_an_untrusted_host_is_an_error(self):
        self.other.on("GET", "/search", search_page(result("ALBUM", "Placeholder LP", self.site.url + "/album/lp", "A")))
        self.site.on("GET", "/search", (301, {"Location": self.other.url + "/search"}, ""))
        with self.assertRaisesRegex(IndexerError, "not a Bandcamp address"):
            self.indexer().search("x")
        self.assertEqual(self.other.calls, [])

    def test_a_redirect_to_a_trusted_host_is_followed_and_a_relative_one_too(self):
        self.hosts.append(net.host_of(self.other.url))
        self.other.on("GET", "/page", "<html>body</html>")
        self.site.on("GET", "/go", (302, {"Location": self.other.url + "/page"}, ""))
        self.site.on("GET", "/rel", (307, {"Location": "/page2"}, ""))
        self.site.on("GET", "/page2", "<html>relative</html>")
        self.assertEqual(self.get(self.site.url + "/go"), "<html>body</html>")
        self.assertEqual(self.get(self.site.url + "/rel"), "<html>relative</html>")

    def test_a_redirect_loop_ends(self):
        self.site.on("GET", "/a", (302, {"Location": "/b"}, ""))
        self.site.on("GET", "/b", (302, {"Location": "/a"}, ""))
        with self.assertRaisesRegex(IndexerError, "redirected more than"):
            self.get(self.site.url + "/a")
        self.assertEqual(len(self.site.calls), arr.MAX_HOPS + 1)

    def chain(self, hops):
        for i in range(hops):
            self.site.on("GET", f"/c{i}x", (302, {"Location": f"/c{i + 1}x"}, ""))
        self.site.on("GET", f"/c{hops}x", "<html>arrived</html>")
        return self.get(self.site.url + "/c0x")

    def test_the_hop_limit_is_exact(self):
        self.assertEqual(self.chain(arr.MAX_HOPS), "<html>arrived</html>")
        self.site.clear()
        with self.assertRaisesRegex(IndexerError, "redirected more than"):
            self.chain(arr.MAX_HOPS + 1)

    def test_a_redirect_from_https_to_http_is_refused(self):
        class Page:
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self, n):
                return b""
        hop = urllib.error.HTTPError("https://art.example/album/x", 302, "Found", {"Location": "http://art.example/album/x"}, None)
        with mock.patch.object(arr.OPENER, "open", side_effect=[hop, Page()]) as opener:
            with self.assertRaisesRegex(IndexerError, "weaker scheme"):
                arr.Site(0, ["art.example"]).get("https://art.example/album/x")
        self.assertEqual(opener.call_count, 1)

    def test_the_client_refuses_a_stream_that_redirects_to_an_untrusted_host(self):
        c = self.client()
        url = self.free_album()
        self.site.on("GET", "/stream/1.mp3", (302, {"Location": self.other.url + "/loot.mp3"}, ""))
        self.stream()
        self.other.on("GET", "/loot.mp3", (200, {}, MP3))
        row = self.finish(c, self.grab(c, url))
        self.assertEqual(row["state"], "failed", row)
        self.assertIn("not a Bandcamp address", row["message"])
        self.assertEqual(self.other.calls, [])


def message(**headers):
    msg = http.client.HTTPMessage()
    for name, value in headers.items():
        msg[name.replace("_", "-")] = value
    return msg


class Caps(ClientCase):
    """A page and an audio file are read up to a limit; a longer answer is an error and is not kept in memory or on disk."""

    def test_the_limits(self):
        self.assertEqual((arr.MAX_PAGE, arr.MAX_AUDIO, arr.MAX_HOPS), (8 * 1024 * 1024, 256 * 1024 * 1024, 5))

    def test_a_page_over_the_limit_is_an_error(self):
        self.site.on("GET", "/big", "<html>" + "x" * 5000 + "</html>")
        with mock.patch.object(arr, "MAX_PAGE", 4000):
            with self.assertRaisesRegex(IndexerError, "more than 4000 bytes"):
                arr.Site(0, [net.host_of(self.site.url)]).get(self.site.url + "/big")
        self.assertEqual(arr.Site(0, [net.host_of(self.site.url)]).get(self.site.url + "/big")[:6], "<html>")

    def test_a_body_without_a_declared_length_is_cut_off_as_it_arrives(self):
        class Body:
            headers = message()
            reads = 0

            def read1(self, n):
                self.reads += 1
                if self.reads > 50:
                    raise AssertionError("read on past the limit")
                return b"x" * n
        body = Body()
        with mock.patch.object(arr, "CHUNK", 100):
            with self.assertRaises(arr.TooLarge):
                arr.read_capped(body, 1000)
        self.assertEqual(body.reads, 11)

    def test_the_declared_length_refuses_before_reading(self):
        class Body:
            headers = message(Content_Length="5000")

            def read1(self, n):
                raise AssertionError("read")
        with self.assertRaises(arr.TooLarge):
            arr.read_capped(Body(), 4000)

    def test_a_stream_over_the_limit_fails_the_job_and_leaves_nothing(self):
        url = self.free_album()
        self.stream(body=MP3 + b"\x00" * 5000)
        c = self.client()
        with mock.patch.object(arr, "MAX_AUDIO", 4000):
            row = self.finish(c, self.grab(c, url))
        self.assertEqual(row["state"], "failed", row)
        self.assertIn("more than 4000 bytes", row["message"])
        self.assertEqual((self.leftovers(), self.folders()), ([], []))

    def test_a_stream_at_the_limit_is_kept(self):
        url = self.free_album()
        self.stream(body=MP3)
        c = self.client()
        with mock.patch.object(arr, "MAX_AUDIO", len(MP3)):
            row = self.finish(c, self.grab(c, url))
        self.assertEqual(row["state"], "completed", row)


class RawServer:
    """A server on 127.0.0.1 that answers every request with bytes of the test's choosing, then closes. `script(conn)` runs after the request headers are read."""

    def __init__(self, script):
        self.script = script
        self.sock = socket.create_server(("127.0.0.1", 0))
        self.url = f"http://127.0.0.1:{self.sock.getsockname()[1]}"
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self.serve, args=(conn,), daemon=True).start()

    def serve(self, conn):
        with conn:
            data = b""
            while b"\r\n\r\n" not in data:
                more = conn.recv(4096)
                if not more:
                    return
                data += more
            try:
                self.script(conn)
            except OSError:
                pass

    def close(self):
        self.sock.close()


def declared(length, body):
    def script(conn):
        conn.sendall(f"HTTP/1.1 200 OK\r\nContent-Length: {length}\r\nConnection: close\r\n\r\n".encode("latin-1") + body)
    return script


def chunked(*parts, end=False):
    """A chunked answer made of whole chunks and then cut, or ended properly when `end`; a part given as (size, bytes) declares `size` and sends `bytes`."""
    def script(conn):
        out = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n"
        for part in parts:
            size, data = part if isinstance(part, tuple) else (len(part), part)
            out += f"{size:x}\r\n".encode() + data + (b"\r\n" if len(data) == size else b"")
        conn.sendall(out + (b"0\r\n\r\n" if end else b""))
    return script


def drip(length=None, seconds=10, gap=0.2, first=b"x"):
    """Sends one byte every `gap` seconds for `seconds`, with Content-Length `length` when given."""
    def script(conn):
        head = "HTTP/1.1 200 OK\r\nConnection: close\r\n" + (f"Content-Length: {length}\r\n" if length else "") + "\r\n"
        conn.sendall(head.encode() + first)
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            time.sleep(gap)
            conn.sendall(b"y")
    return script


PAGE = "<html>" + "x" * 3000 + "</html>"


class RawCase(ClientCase):
    def raw(self, script):
        server = RawServer(script)
        self.addCleanup(server.close)
        return server

    def hosts(self, *servers):
        return ",".join(net.host_of(x.url) for x in (self.site, *servers))

    def album_streaming_from(self, server):
        return self.album(tralbum([(1, "Track 1", 181, server.url + "/a.mp3")], pref=1, minimum=None))

    def job_against(self, server, **settings):
        url = self.album_streaming_from(server)
        c = self.client(extra_hosts=self.hosts(server), **settings)
        return self.finish(c, self.grab(c, url))


class Truncation(RawCase):
    """An answer that ends before the length it declared is an error: the job fails, the page is not parsed, and nothing is kept."""

    def check_failed(self, row, pattern="closed the answer|did not answer"):
        self.assertEqual(row["state"], "failed", row)
        self.assertRegex(row["message"], pattern)
        self.assertEqual((self.leftovers(), self.folders()), ([], []))

    def test_audio_shorter_than_its_content_length_fails_the_job(self):
        row = self.job_against(self.raw(declared(90000, MP3)))
        self.check_failed(row, f"closed the answer after {len(MP3)} of 90000 bytes")

    def test_an_audio_file_of_its_declared_length_is_kept(self):
        self.assertEqual(self.job_against(self.raw(declared(len(MP3), MP3)))["state"], "completed")
        self.assertEqual(len(self.leftovers()), 1)

    def test_a_chunked_audio_cut_inside_a_chunk_fails_the_job(self):
        self.check_failed(self.job_against(self.raw(chunked((4000, MP3)))))

    def test_a_chunked_audio_cut_between_chunks_fails_the_job(self):
        self.check_failed(self.job_against(self.raw(chunked(MP3))))

    def test_a_chunked_audio_that_ends_properly_is_kept(self):
        self.assertEqual(self.job_against(self.raw(chunked(MP3, end=True)))["state"], "completed")

    def test_a_page_shorter_than_its_content_length_is_an_error(self):
        server = self.raw(declared(90000, PAGE.encode()))
        with self.assertRaisesRegex(IndexerError, f"closed the answer after {len(PAGE)} of 90000 bytes"):
            arr.Site(0, [net.host_of(server.url)]).get(server.url + "/p")

    def test_a_body_one_byte_short_of_its_content_length_is_refused(self):
        body = b"ID3" + b"\x00" * 89996
        self.assertEqual(len(body), 89999)
        self.check_failed(self.job_against(self.raw(declared(90000, body))), "closed the answer after 89999 of 90000 bytes")
        server = self.raw(declared(90000, body))
        with self.assertRaisesRegex(IndexerError, "closed the answer after 89999 of 90000 bytes"):
            arr.Site(0, [net.host_of(server.url)]).get(server.url + "/p")

    def malformed_audio(self, value):
        self.check_failed(self.job_against(self.raw(declared(value, MP3))), "Content-Length")

    def test_a_plus_sign_in_the_content_length_fails_the_job(self):
        self.malformed_audio("+90000")

    def test_an_underscore_in_the_content_length_fails_the_job(self):
        self.malformed_audio("9_0000")

    def test_a_repeated_value_in_the_content_length_fails_the_job(self):
        self.malformed_audio("90000, 90000")

    def test_a_negative_content_length_fails_the_job(self):
        self.malformed_audio("-1")

    def test_a_hex_content_length_fails_the_job(self):
        self.malformed_audio("0x15f90")

    def test_a_latin1_digit_in_the_content_length_fails_the_job(self):
        self.malformed_audio("\xb2")

    def test_a_malformed_content_length_on_a_page_is_an_indexer_error(self):
        for value in ("+90000", "9_0000", "90000, 90000", "90000,90000", "-1", "0x15f90", "\xb2"):
            with self.subTest(value=value):
                server = self.raw(declared(value, PAGE.encode()))
                with self.assertRaisesRegex(IndexerError, "Content-Length"):
                    arr.Site(0, [net.host_of(server.url)]).get(server.url + "/p")

    def test_a_repeated_content_length_line_is_refused(self):
        def script(conn):
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 3003\r\nContent-Length: 3003\r\nConnection: close\r\n\r\n" + PAGE.encode())
        server = self.raw(script)
        with self.assertRaisesRegex(IndexerError, "Content-Length"):
            arr.Site(0, [net.host_of(server.url)]).get(server.url + "/p")

    def test_a_chunked_page_cut_inside_or_between_chunks_is_an_error(self):
        for script in (chunked((4000, PAGE.encode())), chunked(PAGE.encode())):
            server = self.raw(script)
            with self.assertRaisesRegex(IndexerError, "closed the answer|did not answer"):
                arr.Site(0, [net.host_of(server.url)]).get(server.url + "/p")

    def test_a_complete_page_is_read(self):
        for script in (declared(len(PAGE), PAGE.encode()), chunked(PAGE.encode(), end=True)):
            server = self.raw(script)
            self.assertEqual(arr.Site(0, [net.host_of(server.url)]).get(server.url + "/p"), PAGE)

    def test_a_release_page_cut_short_fails_the_job(self):
        server = self.raw(declared(90000, album_page(self.site.url + "/album/x", tralbum(tracks_for(self.site), pref=1, minimum=None)).encode()[:200]))
        c = self.client(extra_hosts=self.hosts(server))
        row = self.finish(c, self.grab(c, server.url + "/album/x"))
        self.check_failed(row, "closed the answer after 200 of 90000 bytes")


class Budget(RawCase):
    """A body that trickles in is cut off at a time budget, however slowly it trickles and however far under the byte cap it stays."""

    def test_the_budgets(self):
        self.assertEqual((arr.PAGE_SECONDS, arr.AUDIO_SECONDS, arr.AUDIO_RATE, arr.AUDIO_SECONDS_MAX), (120, 60, 32 * 1024, 3600))
        self.assertEqual(arr.page_seconds(None), 120)
        self.assertEqual(arr.audio_seconds(0), 60)
        self.assertEqual(arr.audio_seconds(32 * 1024 * 100), 160)
        self.assertEqual(arr.audio_seconds(arr.MAX_AUDIO), 3600)
        self.assertEqual(arr.audio_seconds(None), 3600)

    def test_a_page_that_trickles_is_cut_off_at_the_budget(self):
        server = self.raw(drip(length=1000))
        started = time.monotonic()
        with mock.patch.object(arr, "PAGE_SECONDS", 1):
            with self.assertRaisesRegex(IndexerError, "within 1 seconds"):
                arr.Site(0, [net.host_of(server.url)], timeout=1).get(server.url + "/p")
        self.assertLess(time.monotonic() - started, 4)

    def test_a_page_without_a_length_that_trickles_is_cut_off_at_the_budget(self):
        server = self.raw(drip())
        started = time.monotonic()
        with mock.patch.object(arr, "PAGE_SECONDS", 1):
            with self.assertRaisesRegex(IndexerError, "within 1 seconds"):
                arr.Site(0, [net.host_of(server.url)], timeout=1).get(server.url + "/p")
        self.assertLess(time.monotonic() - started, 4)

    def trickle(self, length):
        server = self.raw(drip(length=length, first=MP3[:1]))
        started = time.monotonic()
        with mock.patch.object(arr, "AUDIO_SECONDS", 1), mock.patch.object(arr, "AUDIO_RATE", 10 ** 15):
            row = self.job_against(server, timeout="1")
        self.assertEqual(row["state"], "failed", row)
        self.assertIn("within 1 seconds", row["message"])
        self.assertEqual((self.leftovers(), self.folders()), ([], []))
        self.assertLess(time.monotonic() - started, 5)

    def test_an_audio_file_that_trickles_fails_the_job_and_leaves_nothing(self):
        self.trickle(1000)

    def test_an_audio_file_without_a_length_that_trickles_fails_the_job_and_leaves_nothing(self):
        self.trickle(None)

    def test_headers_that_trickle_are_cut_off_at_the_budget(self):
        head = b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\nX-Pad: " + b"a" * 40

        def script(conn):
            for byte in head:
                time.sleep(0.4)
                conn.sendall(bytes([byte]))
            conn.sendall(b"\r\n\r\nhello")
        server = self.raw(script)
        started = time.monotonic()
        with mock.patch.object(arr, "PAGE_SECONDS", 1):
            with self.assertRaisesRegex(IndexerError, "within 1 seconds"):
                arr.Site(0, [net.host_of(server.url)], timeout=2).get(server.url + "/p")
        self.assertLess(time.monotonic() - started, 3)

    def test_headers_cut_off_by_the_budget_are_not_an_empty_answer(self):
        def script(conn):
            conn.sendall(b"HTTP/1.1 200 OK\r\n")
            time.sleep(3)
        server = self.raw(script)
        with mock.patch.object(arr, "PAGE_SECONDS", 1):
            with self.assertRaisesRegex(IndexerError, "within 1 seconds"):
                arr.Site(0, [net.host_of(server.url)], timeout=2).get(server.url + "/p")

    def test_a_page_has_one_budget_for_its_headers_and_its_body(self):
        def script(conn):
            time.sleep(0.7)
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 1000\r\nConnection: close\r\n\r\n")
            for _ in range(30):
                time.sleep(0.1)
                conn.sendall(b"y")
        server = self.raw(script)
        started = time.monotonic()
        with mock.patch.object(arr, "PAGE_SECONDS", 1):
            with self.assertRaisesRegex(IndexerError, "within 1 seconds"):
                arr.Site(0, [net.host_of(server.url)], timeout=2).get(server.url + "/p")
        self.assertLess(time.monotonic() - started, 1.4)

    def test_redirect_hops_share_one_budget(self):
        hops = []

        def script(conn):
            n = len(hops)
            hops.append(n)
            time.sleep(0.6)
            if n < 4:
                conn.sendall(f"HTTP/1.1 302 Found\r\nLocation: /h{n + 1}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode())
            else:
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\nConnection: close\r\n\r\nhello")
        server = self.raw(script)
        started = time.monotonic()
        with mock.patch.object(arr, "PAGE_SECONDS", 2):
            with self.assertRaisesRegex(IndexerError, "within 2 seconds"):
                arr.Site(0, [net.host_of(server.url)], timeout=2).get(server.url + "/h0")
        self.assertLess(time.monotonic() - started, 3.5)
        self.assertLess(len(hops), 5)

    def test_a_fast_body_inside_the_budget_is_kept(self):
        self.assertEqual(self.job_against(self.raw(declared(len(MP3), MP3)))["state"], "completed")


class Trusted(unittest.TestCase):
    def test_lookalike_authorities_are_refused(self):
        for url in ("https://evil.com\\@x.bandcamp.com/", "https://x.bandcamp.com\\.evil.com/", "https://evil.com\\@bandcamp.com/",
                    "https://evil.com @x.bandcamp.com/", "https://evil.com\t@x.bandcamp.com/", "https://evil.com\n@x.bandcamp.com/",
                    "https://evil.com\x00@x.bandcamp.com/", "https://evil.com\x7f@x.bandcamp.com/", "https://x.bandcamp.com/a b"):
            self.assertFalse(arr.trusted(url), url)
            self.assertFalse(arr.trusted(url, stream=True), url)
            self.assertFalse(arr.trusted(url, extra=["evil.com"]), url)

    def test_ordinary_addresses_are_trusted(self):
        self.assertTrue(arr.trusted("https://x.bandcamp.com/album/y"))
        self.assertTrue(arr.trusted("https://bandcamp.com/"))
        self.assertTrue(arr.trusted("https://t4.bcbits.com/stream/a?x=1", stream=True))
        self.assertTrue(arr.trusted("http://127.0.0.1:5000/a", extra=["127.0.0.1:5000"]))


class Spacing(Base):
    def test_requests_to_one_host_start_at_least_delay_seconds_apart(self):
        starts = []
        self.site.on("GET", "/p", lambda req: starts.append(time.monotonic()) or "<html>p</html>")
        site = arr.Site(0.3, [net.host_of(self.site.url)])
        for _ in range(3):
            site.get(self.site.url + "/p")
        gaps = [b - a for a, b in zip(starts, starts[1:])]
        self.assertEqual(len(gaps), 2)
        self.assertTrue(all(g >= 0.25 for g in gaps), gaps)
