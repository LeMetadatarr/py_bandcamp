"""py_bandcamp as an arrkit indexer and download client.

Installing py_bandcamp into an app built on arrkit makes both available under the name ``bandcamp`` (entry points in the groups
``arrkit.indexers`` and ``arrkit.clients``). The app lists them as plugins and uses them only once its settings enable them. arrkit is
needed only here: the rest of the library never imports this module.

Indexer. ``search(query)`` reads Bandcamp's album search for ``term``, else for ``artist`` and ``album`` together, else for ``title`` (then
each of ``titles`` in turn until one finds something); with only ``track`` given it reads the track search. ``rss()`` reads the release
grids of the artist and label pages named in ``follow_artists``, in the order the page lists them. The first ``resolve`` releases of an
answer have their page read for the tracklist, the terms of sale and the license; the others are listed with what the search page says.
Requests carry arrkit's User-Agent and are spaced by ``delay`` seconds per host. The library's own HTTP session is not used. Redirects are
followed by hand, at most MAX_HOPS of them, and every hop must be a trusted address and may not leave https. A page is read up to MAX_PAGE
bytes and an audio file up to MAX_AUDIO; a longer answer is an error, and so is one that ends short of its declared length or
takes longer than PAGE_SECONDS (a page) or audio_seconds (an audio file); the headers of all hops together get PAGE_SECONDS, and a page's body
counts in the same budget. A Content-Length that is repeated or is not plain digits is an error. A page that answers with a bot check or a refusal (403, 429, 503) is an error that says Bandcamp is not usable from here; it is
never worked around.

A release adds to arrkit's keys: ``bandcamp_id`` (resolved releases), ``artist``, ``album``, ``year``, ``format`` (MP3), ``bitrate`` (128), ``quality`` (MP3-128), ``tracks``,
``seconds``, ``tracklist`` ([{number, title, seconds}], resolved releases), ``tags``, ``label``, ``thumbnail``, ``license`` (an SPDX id
when the license section names a Creative Commons license), ``license_url``, and ``access``: ``free`` (a free download), ``name_your_price``
(the minimum is nothing), ``licensed`` (a Creative Commons license), ``paid``, ``stream_only``, ``preorder``, ``restricted``,
``no_audio``, or ``unchecked`` (the page was not read). ``downloadable`` is True for the first three only; ``needs_purchase`` is True for ``paid`` and
``preorder``. A downloadable release has protocol ``bandcamp`` and kind ``download``. Any other release has protocol ``bandcamp-stream``
and kind ``stream``, which no download client takes.

Client. ``add(release)`` queues the release page in a job queue in the app's state folder (arrkit's direct client, one job at a time).
The job reads the page again, applies the same rules to what the page says now and refuses a release that is not downloadable. It
saves the 128 kbps MP3 stream of each track, which is the audio the site serves to anyone for listening, as
``<download_dir>/<title>-<job>/<number> - <track>.mp3``. It does not buy anything, fills in no form and cannot fetch the lossless or
higher-rate files that Bandcamp's own download page offers."""
import http.client
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from bs4 import BeautifulSoup
from arrkit import net
from arrkit.bridge.sabnzbd import safe
from arrkit.clients import ClientError
from arrkit.clients.direct import Direct
from arrkit.clients.jobs import JobQueue
from arrkit.indexers import Indexer, IndexerError

from py_bandcamp import BandCamp, _to_iso_date
from py_bandcamp.models import BandcampAlbum, BandcampArtist
from py_bandcamp.utils import _extract_tralbum, _parse_ldjson

API_VERSION = 1
SLUG = "bandcamp"
STREAM_SLUG = "bandcamp-stream"
SITE = "https://bandcamp.com"
MAX_TERMS = 2
NAME_LIMIT = 200
FILE_LIMIT = 255
FREE, PAID = 1, 2
MAX_HOPS = 5
MAX_PAGE = 8 * 1024 * 1024
MAX_AUDIO = 256 * 1024 * 1024
CHUNK = 64 * 1024
PAGE_SECONDS = 120
AUDIO_SECONDS = 60
AUDIO_RATE = 32 * 1024
AUDIO_SECONDS_MAX = 3600
DOWNLOADABLE = ("free", "name_your_price", "licensed")
CHALLENGE = re.compile(r"captcha|client challenge|/_fs-ch-|cf-chl|just a moment|attention required|access denied|verify you are human|checking your browser", re.I)
CC_URL = re.compile(r"creativecommons\.org/(?:licenses/([a-z-]+)/([0-9.]+)|publicdomain/zero/([0-9.]+))", re.I)
SUBDOMAIN = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
UNSAFE = re.compile(r"[\s\x00-\x1f\x7f]")


class PageError(ValueError):
    """The page is not a Bandcamp release page."""


def words(value):
    return [w.strip() for w in str(value or "").split(",") if w.strip()]


def is_challenge(text):
    """True for a page that is a bot check and not Bandcamp's."""
    return bool(CHALLENGE.search(text[:20000])) and "searchresult" not in text and "data-tralbum" not in text


def fit(name, suffix="", limit=FILE_LIMIT):
    """`name` and `suffix` as one file name of at most `limit` UTF-8 bytes: the name is cut at a character boundary."""
    room = limit - len(suffix.encode())
    raw = name.encode()
    if len(raw) > room:
        name = raw[:room].decode("utf-8", "ignore").rstrip(" .")
    return name + suffix


def label_of(*parts):
    return " - ".join(p for p in (str(x or "").strip() for x in parts) if p)


def spdx_of(url):
    """The SPDX id of a Creative Commons license address, or ""."""
    m = CC_URL.search(url or "")
    if not m:
        return ""
    if m.group(3):
        return f"CC0-{m.group(3)}"
    return f"CC-{m.group(1).upper()}-{m.group(2)}"


def trusted(url, extra=(), stream=False):
    """True for an https address on bandcamp.com (and on bcbits.com for a stream), or on a host the instance names in extra_hosts."""
    url = str(url or "")
    u = urllib.parse.urlsplit(url)
    if UNSAFE.search(url) or "\\" in u.netloc:
        return False
    host = net.host_of(url) if u.hostname else ""
    if host and host in extra and u.scheme in ("http", "https"):
        return True
    suffixes = (".bandcamp.com", ".bcbits.com") if stream else (".bandcamp.com",)
    name = (u.hostname or "").lower()
    return u.scheme == "https" and bool(name) and (name == "bandcamp.com" or name.endswith(suffixes))


def artist_url(name):
    """The page address of a followed artist: an address as given, or a name turned into its bandcamp.com subdomain."""
    name = str(name or "").strip()
    if name.startswith(("http://", "https://")):
        return name.rstrip("/")
    slug = re.sub(r"[^a-z0-9-]+", "", name.lower().replace(" ", "-"))
    return f"https://{slug}.bandcamp.com" if SUBDOMAIN.fullmatch(slug) else ""


class TooLarge(Exception):
    """An answer is longer than the limit for it."""


class Truncated(Exception):
    """An answer ended before the length it declared: args are the bytes read and the bytes declared."""


class TooSlow(Exception):
    """An answer did not finish within its time budget in seconds, which is args[0]."""


class BadLength(Exception):
    """An answer carries a Content-Length that is not a single run of ASCII digits."""


def page_seconds(declared):
    """The time a page may take to arrive."""
    return PAGE_SECONDS


def audio_seconds(declared):
    """The time an audio file may take to arrive: a base plus the time at AUDIO_RATE bytes a second, up to AUDIO_SECONDS_MAX."""
    return min(AUDIO_SECONDS_MAX, AUDIO_SECONDS + (MAX_AUDIO if declared is None else declared) / AUDIO_RATE)


class Stay(urllib.request.HTTPRedirectHandler):
    """Hands a redirect back to the caller as an HTTPError, so that every hop is checked."""

    def redirect_request(self, *args, **kwargs):
        return None


_local = threading.local()


class Watched:
    """Hands each socket it connects to the watchdog of the fetch that is running in this thread."""

    def connect(self):
        super().connect()
        watch = getattr(_local, "watch", None)
        if watch:
            watch(self.sock)


class WatchedHTTP(Watched, http.client.HTTPConnection):
    pass


class WatchedHTTPS(Watched, http.client.HTTPSConnection):
    pass


class WatchedHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(WatchedHTTP, req)


class WatchedHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(WatchedHTTPS, req, context=self._context)


OPENER = urllib.request.build_opener(Stay, WatchedHTTPHandler, WatchedHTTPSHandler)
CONTENT_LENGTH = re.compile(r"[0-9]+")
_turns, _turn_lock = {}, threading.Lock()


def wait_turn(host, gap):
    """Sleeps until `gap` seconds have passed since the start of the last request to `host`, across threads."""
    if not gap or gap <= 0:
        return
    with _turn_lock:
        now = time.monotonic()
        start = max(now, _turns.get(host, 0) + gap)
        _turns[host] = start
    if start > now:
        time.sleep(start - now)


def declared_length(response):
    """The Content-Length of `response` as an int, or None when it has none. Raises BadLength for one that is repeated or is not ASCII digits."""
    values = response.headers.get_all("Content-Length") or []
    if not values:
        return None
    if len(values) > 1 or not CONTENT_LENGTH.fullmatch(values[0].strip()):
        raise BadLength
    return int(values[0].strip())


def read_capped(response, limit, sink=None, budget=page_seconds, since=None):
    """The body of `response`, or the number of bytes written to `sink` when there is one. Raises TooLarge as soon as the body passes `limit`,
    BadLength for a malformed Content-Length, TooSlow when it is not complete `budget(declared length)` seconds after `since` (the first read
    when not given), and Truncated when it ends short of its declared length."""
    declared = declared_length(response)
    if declared is not None and declared > limit:
        raise TooLarge(limit)
    deadline = (time.monotonic() if since is None else since) + budget(declared)
    chunks, size = [], 0
    while True:
        chunk = response.read1(CHUNK)
        if not chunk:
            break
        size += len(chunk)
        if size > limit:
            raise TooLarge(limit)
        sink.write(chunk) if sink else chunks.append(chunk)
        if time.monotonic() > deadline:
            raise TooSlow(round(budget(declared)))
    if declared is not None and size != declared:
        raise Truncated(size, declared)
    return size if sink else b"".join(chunks)


class Site:
    """The HTTP side shared by the indexer and the client: GET spaced per host, redirects followed by hand, bodies capped, bot checks refused."""

    def __init__(self, delay, extra=(), timeout=30):
        self.delay, self.extra, self.timeout = delay, set(extra), timeout

    def fetch(self, url, read, error, stream=False):
        """`read(response, start)` of the answer to a GET of `url`, or None when it is gone (404); `start` is when the first request began. A
        redirect is followed for at most MAX_HOPS hops, each to a trusted address and never from https to another scheme. The headers of all
        the hops together have page_seconds(None) seconds to arrive."""
        start = None
        for hop in range(MAX_HOPS + 1):
            if not trusted(url, self.extra, stream):
                raise error(f"{net.host_of(url) or url} is not a Bandcamp address; add it to the extra hosts to use it")
            host = net.host_of(url)
            wait_turn(host, self.delay)
            if start is None:
                start = time.monotonic()
            limit = page_seconds(None)
            left = start + limit - time.monotonic()
            socks, fired = [], []

            def expire():
                fired.append(True)
                for sock in socks:
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass

            def watch(sock):
                socks.append(sock)
                if fired:
                    expire()
            watchdog = threading.Timer(left, expire)
            watchdog.daemon = True
            _local.watch = watch
            watchdog.start()
            request = urllib.request.Request(url, headers={"User-Agent": net.USER_AGENT, "Accept": "*/*" if stream else "text/html"})
            try:
                try:
                    response = OPENER.open(request, timeout=self.timeout)
                finally:
                    watchdog.cancel()
                    _local.watch = None
                with response:
                    if fired:
                        raise TooSlow(round(limit))
                    return read(response, start)
            except urllib.error.HTTPError as e:
                with e:
                    status, location = e.code, e.headers.get("Location")
                if status in (301, 302, 303, 307, 308) and location:
                    target = urllib.parse.urljoin(url, location)
                    if urllib.parse.urlsplit(url).scheme == "https" and urllib.parse.urlsplit(target).scheme != "https":
                        raise error(f"{host} redirected from https to {net.host_of(target) or 'another address'} over a weaker scheme; refused") from None
                    url = target
                    continue
                if status == 404:
                    return None
                if status in (403, 429, 503):
                    raise error(f"{host} refused the request (HTTP {status}); bandcamp is not usable from here") from None
                raise error(f"HTTP {status} from {host}") from None
            except TooLarge as e:
                raise error(f"{host} answered with more than {e.args[0]} bytes; refused") from None
            except Truncated as e:
                raise error(f"{host} closed the answer after {e.args[0]} of {e.args[1]} bytes; refused") from None
            except TooSlow as e:
                raise error(f"{host} did not deliver the answer within {e.args[0]} seconds; refused") from None
            except BadLength:
                raise error(f"{host} sent a Content-Length that is not a single number; refused") from None
            except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
                if fired:
                    raise error(f"{host} did not deliver the answer within {round(limit)} seconds; refused") from None
                raise error(f"{host} did not answer: {getattr(e, 'reason', e)}") from None
        raise error(f"{net.host_of(url) or url} redirected more than {MAX_HOPS} times; refused")

    def get(self, url, params=None, error=IndexerError):
        """The text of a page, or None when it is gone (404)."""
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
        body = self.fetch(url, lambda r, start: read_capped(r, MAX_PAGE, budget=page_seconds, since=start), error)
        if body is None:
            return None
        text = body.decode("utf-8", "replace")
        if is_challenge(text):
            raise error(f"{net.host_of(url)} answered with a bot check; bandcamp is not usable from here")
        return text

    def save(self, url, path, error=ClientError):
        """Writes the audio file at `url` to `path` and returns its size, or None when it is gone (404). Stops at MAX_AUDIO bytes."""
        def write(response, start):
            with open(path, "wb") as f:
                return read_capped(response, MAX_AUDIO, f, audio_seconds)
        return self.fetch(url, write, error, stream=True)


def read_page(text, url):
    """What a release page says, as a dict: url, id, artist, album, title, year, published, tags, label, image, tracks
    ([{number, title, seconds, stream, licensed}]), license, license_url, access, downloadable, needs_purchase, price_min and reason.
    Raises PageError for a page that is not a release page. The terms of sale are read from the page's tralbum data; anything the page
    does not state plainly leaves the release not downloadable."""
    try:
        meta = BandcampAlbum.data_from_page(text, url)
        ld = _parse_ldjson(text, clean=True)
    except (ValueError, IndexError, KeyError, TypeError, AttributeError) as e:
        raise PageError(f"{net.host_of(url)} did not answer a release page: {type(e).__name__}") from None
    tralbum = _extract_tralbum(text)
    current = tralbum.get("current") or {}
    infos = [t for t in tralbum.get("trackinfo") or [] if isinstance(t, dict)]
    tracks = []
    for i, t in enumerate(infos, 1):
        file = t.get("file") if isinstance(t.get("file"), dict) else {}
        n = t.get("track_num")
        secs = t.get("duration")
        tracks.append({"number": n if isinstance(n, int) and not isinstance(n, bool) and n > 0 else i, "title": str(t.get("title") or ""),
                       "seconds": int(secs) if isinstance(secs, (int, float)) and not isinstance(secs, bool) and secs > 0 else None,
                       "stream": file.get("mp3-128") or "", "license_type": t.get("license_type")})
    license_url = next((a["href"] for a in BeautifulSoup(text, "html.parser").select("#license a[href], .license a[href]")
                        if CC_URL.search(a["href"])), "")
    # a license section naming Creative Commons counts only when no track says "all rights reserved" (license type 1)
    reserved = any(t["license_type"] == 1 for t in tracks)
    license_id = "" if reserved else spdx_of(license_url)
    terms = sale_terms(tralbum, current, bool(license_id))
    artist = meta.get("artist") or ""
    album = (ld.get("inAlbum") or {}).get("name") if str(url).find("/track/") >= 0 else meta.get("title")
    published = _to_iso_date(meta.get("datePublished") or current.get("release_date")) or ""
    out = {"url": str(url).split("?")[0], "id": meta.get("item_id") or tralbum.get("id") or "", "artist": artist, "album": album or "",
           "title": meta.get("title") or "", "year": int(published[:4]) if published[:4].isdigit() else None, "published": published,
           "tags": [str(k).strip().lower() for k in meta.get("keywords") or [] if str(k).strip()],
           "label": meta.get("publisher") if meta.get("publisher") and meta.get("publisher") != artist else "", "image": meta.get("image") or "",
           "tracks": tracks, "license": license_id, "license_url": license_url if license_id else ""}
    return out | terms


def sale_terms(tralbum, current, licensed):
    """{access, downloadable, needs_purchase, price_min, reason} from a page's tralbum data and whether its license is Creative Commons.
    Free: the page offers a free download. Name your price: the price is not fixed and the minimum is nothing. Licensed: a Creative
    Commons license. Paid: a price. Anything unreadable is not downloadable."""
    free_code, paid_code = tralbum.get("FREE", FREE), tralbum.get("PAID", PAID)
    pref, minimum = current.get("download_pref"), current.get("minimum_price")
    minimum = float(minimum) if isinstance(minimum, (int, float)) and not isinstance(minimum, bool) else None

    def terms(access, reason=""):
        return {"access": access, "downloadable": access in DOWNLOADABLE, "needs_purchase": access in ("paid", "preorder"),
                "price_min": minimum, "reason": reason}
    if not tralbum:
        return terms("unchecked", "the page carries no sale data")
    if not tralbum.get("hasAudio"):
        return terms("no_audio", "the page offers no audio")
    if current.get("private") or current.get("killed") or tralbum.get("is_private_stream") or tralbum.get("tralbum_subscriber_only"):
        return terms("restricted", "the release is private or for subscribers")
    if tralbum.get("is_preorder") or tralbum.get("album_is_preorder"):
        return terms("preorder", "the release is a pre-order and needs purchase")
    if (pref is not None and pref == free_code) or tralbum.get("freeDownloadPage"):
        return terms("free")
    if pref == paid_code and not current.get("is_set_price") and minimum == 0:
        return terms("name_your_price")
    if licensed:
        return terms("licensed")
    if pref == paid_code and minimum is not None:
        return terms("paid", f"needs purchase (from {minimum:g})")
    return terms("stream_only", "the page offers streaming only")


class Bandcamp(Indexer):
    implementation = SLUG
    name = "Bandcamp"
    protocol = SLUG
    protocols = (SLUG, STREAM_SLUG)
    caps = {"search": True, "rss": True}
    adult = False
    API_VERSION = API_VERSION
    fields = [("url", "Site address", SITE),
              ("delay", "Seconds between requests to the site", "3", {"address": False}),
              ("resolve", "Releases per answer whose page is read (one request each)", "5", {"address": False}),
              ("max_results", "Releases per answer at most", "20", {"address": False}),
              ("follow_artists", "RSS: artist and label pages followed (addresses or bandcamp.com names), comma separated", "", {"address": False}),
              ("extra_hosts", "Other hosts whose release pages are read (artists on their own domain), comma separated", "", {"address": False})]

    def base(self):
        return (self.settings["url"] or SITE).rstrip("/")

    def site(self):
        return Site(self.num("delay", 3), [*words(self.settings["extra_hosts"]), net.host_of(self.base())])

    def search_texts(self, query):
        titles = [str(t).strip() for t in [query.get("title"), *(query.get("titles") or ())] if t and str(t).strip()]
        if query.get("term"):
            return [str(query["term"]).strip()]
        both = label_of(query.get("artist"), query.get("album")).replace(" - ", " ")
        return ([both] if both else []) + [t for t in titles if t != both][:MAX_TERMS]

    def found(self, site, text, kind):
        """The search page's results for `text` as library objects: albums, or tracks."""
        html = site.get(self.base() + "/search", {"q": text, "item_type": "t" if kind == "track" else "a"})
        flags = {"albums": kind != "track", "tracks": kind == "track", "artists": False, "labels": False}
        return BandCamp.parse_search_page(html or "", **flags)

    def cards(self, site, query):
        kind = "track" if query.get("track") and not (query.get("album") or query.get("term")) else "album"
        texts = self.search_texts(query)
        if kind == "track":
            texts = [label_of(query.get("artist"), query["track"]).replace(" - ", " ")]
        for text in texts[:MAX_TERMS] if kind == "album" else texts:
            items = self.found(site, text, kind)
            if items:
                return items
        return []

    def page(self, site, url):
        """read_page of a release's page, or None when it cannot be read or is not on a trusted host."""
        if not trusted(url, site.extra):
            return None
        try:
            text = site.get(url)
            return read_page(text, url) if text is not None else None
        except (IndexerError, PageError):
            return None

    def release_of(self, card, page):
        """One release from a search or grid card and, when its page was read, the page."""
        data = card.data
        card_url = str(card.url).split("?")[0]
        artist = data.get("artist") or ""
        album = data.get("album_name") or data.get("title") or card.title
        track_name = data.get("track_name") or ""
        published = _to_iso_date(data.get("released")) or ""
        n = str(data.get("track_number") or "")
        minutes = str(data.get("minutes") or "")
        track = track_name if "/track/" in card_url else ""
        base = dict(artist=artist, album=album, track=track, bandcamp_id=None, year=int(published[:4]) if published[:4].isdigit() else None,
                    tracks=int(n) if n.isdigit() else None, seconds=int(minutes) * 60 if minutes.isdigit() else None, tracklist=[],
                    tags=[t for t in (data.get("tags") or []) if t], label="", thumbnail=data.get("image") or "", license="", license_url="",
                    access="unchecked", downloadable=False, needs_purchase=False, price_min=None, published=published)
        if page:
            base.update(bandcamp_id=page["id"] or None, artist=page["artist"] or artist, album=page["album"] or album, year=page["year"] or base["year"],
                        published=page["published"] or published, tags=page["tags"] or base["tags"], label=page["label"],
                        thumbnail=page["image"] or base["thumbnail"], license=page["license"], license_url=page["license_url"],
                        access=page["access"], downloadable=page["downloadable"], needs_purchase=page["needs_purchase"], price_min=page["price_min"],
                        tracklist=[{"number": t["number"], "title": t["title"], "seconds": t["seconds"]} for t in page["tracks"]],
                        tracks=len(page["tracks"]) or base["tracks"])
            durations = [t["seconds"] for t in page["tracks"]]
            if durations and all(durations):
                base["seconds"] = sum(durations)
        title = label_of(base["artist"], base["track"] or base["album"])
        if base["year"]:
            title += f" ({base['year']})"
        ok = base["downloadable"]
        return self.release(title=f"{title} [MP3 128]", guid=f"{SLUG}:{card_url}", url=card_url,
                            info_url=card_url, size=None, quality="MP3-128", format="MP3", bitrate=128,
                            protocol=SLUG if ok else STREAM_SLUG, kind="download" if ok else "stream", **base)

    def releases(self, site, cards):
        cards = [c for c in cards if c.url][:int(self.num("max_results", 20)) or 20]
        resolve = int(self.num("resolve", 5))
        return [self.release_of(c, self.page(site, str(c.url).split("?")[0]) if i < resolve else None) for i, c in enumerate(cards)]

    def search(self, query):
        query = {"term": query} if isinstance(query, str) else dict(query or {})
        site = self.site()
        return self.releases(site, self.cards(site, query))

    def rss(self):
        site = self.site()
        cards, seen = [], set()
        for name in words(self.settings["follow_artists"]):
            url = artist_url(name)
            if not url or not trusted(url, site.extra):
                continue
            html = site.get(url)
            for album in BandcampArtist.albums_from_page(html or "", url):
                if album.url not in seen:
                    seen.add(album.url)
                    album.data.setdefault("artist", artist_name(html, url))
                    cards.append(album)
        return self.releases(site, cards)

    def test(self):
        try:
            n = len(self.found(self.site(), "test", "album"))
        except IndexerError as e:
            return False, str(e)
        return (n > 0, f"search answered with {n} albums" if n else "search answered with no albums; the page layout may have changed")


def artist_name(html, url):
    """The name an artist or label page gives itself, else the first part of its host name."""
    tag = BeautifulSoup(html or "", "html.parser").find(id="band-name-location")
    title = tag.find(class_="title") if tag else None
    return title.text.strip() if title and title.text.strip() else (urllib.parse.urlsplit(url).hostname or "").split(".")[0]


def source_of(release, extra=()):
    """The release page a release names: its url, which must be a trusted address of a release page."""
    url = str(release.get("url") or release.get("info_url") or "").split("?")[0]
    if not trusted(url, extra) or not re.search(r"/(?:album|track)/[^/]+$", urllib.parse.urlsplit(url).path):
        raise ClientError("the release names no Bandcamp release page")
    return url


class BandcampClient(Direct):
    implementation = SLUG
    name = "Bandcamp"
    protocols = (SLUG,)
    category = ""
    adult = False
    API_VERSION = API_VERSION
    fields = [("download_dir", "Download folder", ""),
              ("delay", "Seconds between requests to the site", "3", {"address": False}),
              ("timeout", "Seconds without data before a download fails", "60", {"address": False}),
              ("extra_hosts", "Other hosts whose release pages are read (artists on their own domain), comma separated", "", {"address": False})]

    def __init__(self, inst=None, state_dir=None):
        super().__init__(inst, state_dir)
        self.queue = JobQueue(state_dir, f"{SLUG}-{self.inst.get('id') or 0}.json", prefix=f"{SLUG}_")

    def extra(self):
        return words(self.settings["extra_hosts"])

    def add(self, release):
        url = source_of(release, self.extra())
        if release.get("access") in ("paid", "preorder"):
            raise ClientError(f"needs purchase: {release.get('title') or url} is sold on Bandcamp and is not downloaded here")
        if release.get("access") in ("stream_only", "restricted", "no_audio"):
            raise ClientError(f"not downloadable: {release.get('title') or url} is {release['access']}")
        self.folder()
        title = fit(safe(release.get("title") or "") or "bandcamp", limit=NAME_LIMIT)
        jid = self.queue.add(url, title, self.category or "*", 0, own_folder=True)
        self.start()
        return jid

    def run(self, job, ctl):
        site = Site(self.num("delay", 3), self.extra(), self.num("timeout", 60))
        try:
            text = site.get(job["ref"], error=ClientError)
            if text is None:
                return "the release is gone from the site"
            page = read_page(text, job["ref"])
        except (ClientError, PageError) as e:
            return str(e)
        if not page["downloadable"]:
            return f"{'needs purchase' if page['needs_purchase'] else 'not downloadable'}: {page['reason'] or page['access']}"
        if not page["tracks"]:
            return "the page lists no tracks"
        missing = [t["number"] for t in page["tracks"] if not t["stream"]]
        if missing:
            return "track " + ", ".join(str(n) for n in missing) + " has no stream"
        target = os.path.join(self.folder(), job.get("folder") or job["title"])
        os.makedirs(target, exist_ok=True)
        written, done, total = [], False, 0
        try:
            for i, t in enumerate(page["tracks"]):
                if ctl.cancelled:
                    return "cancelled"
                name = fit(safe(f"{t['number']:02d} - {t['title'] or 'track'}") or f"{t['number']:02d}", ".mp3", FILE_LIMIT - len(".part"))
                if name in written:
                    name = fit(name[:-4], f" ({i + 1}).mp3", FILE_LIMIT - len(".part"))
                part = os.path.join(target, name + ".part")
                size = site.save(t["stream"], part)
                if ctl.cancelled:
                    return "cancelled"
                if not size:
                    return f"track {t['number']} did not come as an audio file"
                with open(part, "rb") as f:
                    head = f.read(1024)
                if not is_mp3(head):
                    return f"track {t['number']} did not come as an audio file"
                os.replace(part, os.path.join(target, name))
                written.append(name)
                total += size
                ctl.progress(100 * (i + 1) // len(page["tracks"]))
            done = True
        except ClientError as e:
            return str(e)
        except OSError as e:
            return f"cannot write to {target}: {e.strerror or e}"
        finally:
            if not done:
                for name in written:
                    os.unlink(os.path.join(target, name))
                for name in os.listdir(target):
                    if name.endswith(".part"):
                        os.unlink(os.path.join(target, name))
                if not os.listdir(target):
                    os.rmdir(target)
        ctl.set(bytes=total, path=target, files=written, file=written[0], access=page["access"])
        return "done"

    def status(self):
        files = {j["id"]: j.get("files") or [] for j in self.queue.load()}
        return [dict(row, files=files.get(row["client_id"], [])) for row in super().status()]


def is_mp3(body):
    """True for bytes that start like an MP3 file: an ID3 tag or an MPEG audio frame header."""
    return len(body) >= 1024 and (body[:3] == b"ID3" or (body[0] == 0xFF and body[1] & 0xE0 == 0xE0))


IMPLEMENTATION = Bandcamp
