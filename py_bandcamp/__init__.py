import re
from datetime import datetime

from bs4 import BeautifulSoup

from mediavocab import (
    Entity, EntityRef, EntityKind,
    Credit, CreditSection, RelationRole,
    Release, Work, MediaType, StreamMode,
    Appearance,
)
from mediavocab.taxonomy import genre as _genre_tax

from py_bandcamp.models import BandcampTrack, BandcampAlbum, BandcampArtist, BandcampLabel
from py_bandcamp.session import HTTP as requests, set_session as set_session, get_session as get_session
from py_bandcamp.utils import (
    extract_ldjson_blob as extract_ldjson_blob,
    get_props as get_props,
    extract_blob,
    get_stream_data,
)


_BC_DATE_FORMATS = ("%d %B %Y", "%B %d, %Y", "%d %b %Y", "%b %d, %Y")
_ISO_DATE_RE = re.compile(r"^\d{4}(?:-\d{2}(?:-\d{2})?)?$")

# Map Bandcamp tag/genre strings to mediavocab GENRE_* constants. Anything
# not in this map passes through as a raw string in ``Work.content_genres``.
_GENRE_MAP = {
    v: getattr(_genre_tax, n) for n, v in vars(_genre_tax).items()
    if n.startswith("GENRE_") and isinstance(v, str)
}
# Common Bandcamp aliases that don't match the canonical mediavocab tokens.
_GENRE_ALIASES = {
    "hip-hop": _genre_tax.GENRE_HIP_HOP,
    "hiphop": _genre_tax.GENRE_HIP_HOP,
    "rap": _genre_tax.GENRE_HIP_HOP,
    "r-n-b": _genre_tax.GENRE_RNB,
    "r&b": _genre_tax.GENRE_RNB,
    "rnb": _genre_tax.GENRE_RNB,
    "drum-and-bass": _genre_tax.GENRE_DRUM_AND_BASS,
    "dnb": _genre_tax.GENRE_DRUM_AND_BASS,
    "drum-n-bass": _genre_tax.GENRE_DRUM_AND_BASS,
    "edm": _genre_tax.GENRE_ELECTRONIC,
    "electro": _genre_tax.GENRE_ELECTRONIC,
}


def _to_iso_date(raw):
    """Normalise Bandcamp date forms to an IsoDate-validatable string.

    Accepts already-ISO inputs ("2024", "2024-09", "2024-09-05") plus
    Bandcamp's free text ("27 March 2020", "March 27, 2020"). Returns
    ``None`` for empty / unparseable values — IsoDate treats absence
    as "unknown" rather than invalid.
    """
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if _ISO_DATE_RE.match(s):
        return s
    s_clean = re.sub(r"\s+\d{2}:\d{2}(:\d{2})?(\s+\w+)?\s*$", "", s).strip()
    for fmt in _BC_DATE_FORMATS:
        try:
            return datetime.strptime(s_clean, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _spdx_from_tags(tags):
    """Best-effort SPDX guess from Bandcamp keyword tags. Returns ``""``
    when no Creative Commons hint is present — Release.license stays
    empty rather than guessing All-Rights-Reserved (the default in many
    SPDX vocabularies but not what Bandcamp asserts)."""
    if not tags:
        return ""
    norm = {str(t).lower().replace("_", "-").replace(" ", "-") for t in tags}
    for spdx, needles in (
        ("CC-BY-NC-ND-4.0", {"cc-by-nc-nd", "by-nc-nd"}),
        ("CC-BY-NC-SA-4.0", {"cc-by-nc-sa", "by-nc-sa"}),
        ("CC-BY-SA-4.0",    {"cc-by-sa", "by-sa"}),
        ("CC-BY-NC-4.0",    {"cc-by-nc", "by-nc"}),
        ("CC-BY-ND-4.0",    {"cc-by-nd", "by-nd"}),
        ("CC-BY-4.0",       {"cc-by"}),
        ("CC0-1.0",         {"cc0", "public-domain"}),
    ):
        if norm & needles:
            return spdx
    return ""


def _map_genres(tags):
    """Translate a list of Bandcamp tags into ``Work.content_genres``.

    Known tags map to the canonical ``GENRE_*`` token from
    ``mediavocab.taxonomy.genre``; unknown tags pass through verbatim
    so callers don't lose information. Order is preserved and the
    result is deduplicated.
    """
    if not tags:
        return []
    out = []
    seen = set()
    for raw in tags:
        if not raw:
            continue
        norm = str(raw).strip().lower().replace("_", "-").replace(" ", "-")
        token = _GENRE_ALIASES.get(norm) or _GENRE_MAP.get(norm.replace("-", "_")) or norm
        if token and token not in seen:
            seen.add(token)
            out.append(token)
    return out


def _country_from_location(loc):
    """Extract the country name from a Bandcamp ``location`` field.

    Bandcamp formats locations as ``"City, Country"`` or ``"City, State,
    Country"``. We take the trailing component as a best-effort country
    label. Returns ``""`` when no comma is present (single-token
    locations like ``"Berlin"`` are too ambiguous to risk).
    """
    if not loc or "," not in loc:
        return ""
    return loc.rsplit(",", 1)[-1].strip()


def _strip_query(url):
    """Drop the ``?...`` query string from a Bandcamp permalink. Bandcamp
    appends search-tracking params (``?from=search&search_item_id=...``)
    that aren't part of the canonical URL — ``Release.uri`` should be
    the bare permalink so equality checks work across sources."""
    if not url:
        return ""
    return url.split("?")[0]


def _band_url_from_url(url):
    """Derive the canonical artist/band root URL from any Bandcamp page
    URL. ``https://acme.bandcamp.com/album/foo`` →
    ``https://acme.bandcamp.com``; custom-domain releases stay as-is.
    """
    if not url:
        return ""
    bare = _strip_query(url)
    for segment in ("/album/", "/track/"):
        if segment in bare:
            return bare.split(segment, 1)[0]
    return bare


def _track_to_release(track: BandcampTrack) -> Release:
    """Convert a :class:`BandcampTrack` to a mediavocab :class:`Release`.

    Populates artist credits, runtime, license (CC tags only), release
    date, image, all known Bandcamp numeric ids and URLs, free-stream
    audio params (mp3 / 128 kbps / stereo — Bandcamp's free preview),
    and the parent album when a track was loaded from one.
    """
    track_url = _strip_query(track.url or "")
    band_url = _band_url_from_url(track_url)
    external_ids: dict = {}
    if track.track_id is not None:
        external_ids["bandcamp_track_id"] = str(track.track_id)
    if track.band_id is not None:
        external_ids["bandcamp_band_id"] = str(track.band_id)
    if track.album_id is not None:
        external_ids["bandcamp_album_id"] = str(track.album_id)
    if track_url:
        external_ids["bandcamp_track_url"] = track_url
    if band_url:
        external_ids["bandcamp_band_url"] = band_url

    credits: list = []
    artist_name = track.data.get("artist") or ""
    if artist_name:
        artist_ref = EntityRef(name=artist_name, kind=EntityKind.GROUP)
        credits.append(Credit(entity=artist_ref, role="artist",
            relation_role=RelationRole.PERFORMER, section=CreditSection.PRINCIPAL))

    tags = track.data.get("tags") or track.data.get("keywords") or []
    work = Work(
        title=track.title, media_type=MediaType.MUSIC,
        runtime=float(track.duration) if track.duration else None,
        credits=credits,
        content_genres=_map_genres(tags),
        external_ids=external_ids,
    )
    release_date = _to_iso_date(
        track.data.get("released") or track.data.get("datePublished")
    )
    has_stream = bool(track.stream)
    return Release(
        work=work, uri=track_url, image=track.image or "",
        stream_mode=StreamMode.ON_DEMAND, external_ids=external_ids,
        release_date=release_date,
        license=_spdx_from_tags(tags),
        # Bandcamp's free streaming preview is mp3 / 128 kbps / stereo.
        codec="mp3" if has_stream else "",
        bitrate="128" if has_stream else "",
        audio_channels="stereo" if has_stream else "",
    )


def _album_to_release(album: BandcampAlbum, include_tracklist: bool = False) -> Release:
    """Convert a :class:`BandcampAlbum` to a mediavocab :class:`Release`.

    Populates album credits, license, release date, content_genres,
    Bandcamp ids/URLs, and optionally a full ordered ``tracklist`` of
    :class:`mediavocab.Appearance` entries.

    ``include_tracklist=True`` will trigger an HTTP fetch (per track
    iteration) when the album was constructed with ``scrap=False`` and
    its tracks haven't been loaded yet — callers that don't need the
    tracklist (search, recommendations) should leave it ``False``.
    """
    album_url = _strip_query(album.url or "")
    band_url = _band_url_from_url(album_url)
    external_ids: dict = {}
    if album.album_id is not None:
        external_ids["bandcamp_album_id"] = str(album.album_id)
    if album.band_id is not None:
        external_ids["bandcamp_band_id"] = str(album.band_id)
    if album_url:
        external_ids["bandcamp_album_url"] = album_url
    if band_url:
        external_ids["bandcamp_band_url"] = band_url

    credits: list = []
    artist_name = album.data.get("artist") or ""
    if artist_name:
        artist_ref = EntityRef(name=artist_name, kind=EntityKind.GROUP)
        credits.append(Credit(entity=artist_ref, role="artist",
            relation_role=RelationRole.CREATOR, section=CreditSection.PRINCIPAL))

    tags = album.data.get("tags") or album.data.get("keywords") or []

    tracklist: list = []
    if include_tracklist:
        for t in album.tracks:
            tracklist.append(Appearance(
                work=Work(
                    title=t.title, media_type=MediaType.MUSIC,
                    runtime=float(t.duration) if t.duration else None,
                    external_ids={
                        k: v for k, v in {
                            "bandcamp_track_id": str(t.track_id) if t.track_id is not None else None,
                            "bandcamp_track_url": _strip_query(t.url or "") or None,
                        }.items() if v is not None
                    },
                ),
                position=int(t.track_num) if t.track_num else len(tracklist) + 1,
                disc=1,
            ))

    work = Work(
        title=album.title, media_type=MediaType.MUSIC,
        credits=credits,
        content_genres=_map_genres(tags),
        tracklist=tracklist,
        external_ids=external_ids,
    )
    release_date = _to_iso_date(
        album.data.get("released") or album.data.get("datePublished")
    )

    # Bandcamp's ld+json ``publisher`` is the imprint/label that issued the
    # release. When the publisher equals the artist (the common self-released
    # case) we drop it to avoid noise — ``Release.label`` should mean a
    # distinct label entity.
    label = None
    publisher = album.data.get("publisher") or ""
    if publisher and publisher != artist_name:
        label = EntityRef(name=publisher, kind=EntityKind.ORGANISATION)

    return Release(
        work=work, uri=album_url, image=album.image or "",
        stream_mode=StreamMode.ON_DEMAND, external_ids=external_ids,
        release_date=release_date,
        license=_spdx_from_tags(tags),
        codec="mp3", bitrate="128", audio_channels="stereo",
        label=label,
    )


def _artist_to_entity(artist: BandcampArtist) -> Entity:
    external_ids: dict = {}
    if artist.band_id is not None:
        external_ids["bandcamp_band_id"] = str(artist.band_id)
    artist_url = _strip_query(artist.url or "")
    if artist_url:
        external_ids["bandcamp_band_url"] = artist_url
    extra: dict = {"artist_url": artist_url}
    if artist.image:
        extra["image"] = artist.image
    if artist.location:
        extra["location"] = artist.location
        country = _country_from_location(artist.location)
        if country:
            extra["country"] = country
    if artist.genre:
        extra["genre"] = artist.genre
    return Entity(name=artist.name or "", kind=EntityKind.GROUP,
                  external_ids=external_ids, extra=extra)


def _label_to_entity(label: BandcampLabel) -> Entity:
    label_url = _strip_query(label.url or "")
    external_ids: dict = {}
    if label_url:
        external_ids["bandcamp_band_url"] = label_url
    extra: dict = {"artist_url": label_url}
    if label.image:
        extra["image"] = label.image
    if label.location:
        extra["location"] = label.location
        country = _country_from_location(label.location)
        if country:
            extra["country"] = country
    return Entity(name=label.name or "", kind=EntityKind.ORGANISATION,
                  external_ids=external_ids, extra=extra)


class _hybridmethod:
    """Descriptor that exposes one function as both a classmethod and an
    instance method.

    The wrapped function receives ``(owner_cls, session, *args, **kwargs)``.
    When accessed via the class, ``session`` is ``None``; when accessed
    via an instance, ``session`` is ``instance._session`` (which may
    itself be ``None`` if the user didn't inject one).

    This lets ``BandCamp.search(...)`` keep working unchanged (using the
    module-level :data:`requests` proxy that existing tests patch) while
    ``BandCamp(session=s).search(...)`` routes through the injected
    session.
    """

    def __init__(self, func):
        self.func = func
        self.__doc__ = func.__doc__

    def __get__(self, obj, cls):
        session = obj._session if obj is not None else None

        def bound(*args, **kwargs):
            return self.func(cls, session, *args, **kwargs)

        bound.__name__ = self.func.__name__
        bound.__doc__ = self.func.__doc__
        return bound


def _http(session):
    """Return the HTTP-callable to use for this call site.

    ``session`` is the per-instance override (or ``None``). When
    ``None`` we return the module-level :data:`requests` proxy so test
    patches against ``py_bandcamp.requests`` keep intercepting traffic.
    """
    return session if session is not None else requests


class BandCamp:
    """Bandcamp scraper facade.

    Usage as a classmethod-style helper (default global session)::

        BandCamp.search("foo")

    Or with an injected session — useful for routing through curl_cffi
    to bypass the search-page Fastly bot challenge::

        from py_bandcamp.transport import default_session
        bc = BandCamp(session=default_session())
        bc.search("foo")
    """

    def __init__(self, session=None):
        self._session = session

    @staticmethod
    def tags(tag_list=True):
        data = extract_blob("https://bandcamp.com/tags")
        tags = {"genres": data["signup_params"]["genres"],
                "subgenres": data["signup_params"]["subgenres"]}
        if not tag_list:
            return tags
        tag_list = []
        for genre in tags["subgenres"]:
            tag_list.append(genre)
            tag_list += [sub["norm_name"] for sub in tags["subgenres"][genre]]
        return tag_list

    @_hybridmethod
    def search_tag(cls, _session, tag, albums=True, tracks=True, artists=True, labels=False, max_pages=10):
        tag = tag.strip().replace(" ", "-").lower()
        yield from cls.__dict__['search'].func(
            cls, _session, tag, albums=albums, tracks=tracks,
            artists=artists, labels=labels, max_pages=max_pages)

    @_hybridmethod
    def search_albums(cls, _session, album_name):
        yield from cls.__dict__['search'].func(
            cls, _session, album_name, albums=True, tracks=False,
            artists=False, labels=False)

    @_hybridmethod
    def search_tracks(cls, _session, track_name):
        yield from cls.__dict__['search'].func(
            cls, _session, track_name, albums=False, tracks=True,
            artists=False, labels=False)

    @_hybridmethod
    def search_artists(cls, _session, artist_name):
        yield from cls.__dict__['search'].func(
            cls, _session, artist_name, albums=False, tracks=False,
            artists=True, labels=False)

    @_hybridmethod
    def search_labels(cls, _session, label_name):
        yield from cls.__dict__['search'].func(
            cls, _session, label_name, albums=False, tracks=False,
            artists=False, labels=True)

    @_hybridmethod
    def search(cls, _session, name, albums=True, tracks=True, artists=True,
               labels=False, max_pages=10, _page=1, _seen=None):
        _seen = _seen or set()

        # Use Bandcamp's item_type filter when only one type is requested
        if tracks and not albums and not artists and not labels:
            item_type = "t"
        elif albums and not tracks and not artists and not labels:
            item_type = "a"
        elif artists and not albums and not tracks and not labels:
            item_type = "b"
        else:
            item_type = None

        params = {"page": _page, "q": name}
        if item_type:
            params["item_type"] = item_type
        response = _http(_session).get('http://bandcamp.com/search', params=params)
        soup = BeautifulSoup(response.content, 'html.parser')

        page_results = []
        for item in soup.find_all("li", class_="searchresult"):
            item_type_text = item.find('div', class_='itemtype').text.strip().lower()
            if item_type_text == "album" and albums:
                data = cls._parse_album(item)
            elif item_type_text == "track" and tracks:
                data = cls._parse_track(item)
            elif item_type_text == "artist" and artists:
                data = cls._parse_artist(item)
            elif item_type_text == "label" and labels:
                data = cls._parse_label(item)
            else:
                continue
            if data is None or str(data) in _seen:
                continue
            _seen.add(str(data))
            page_results.append(data)
            if isinstance(data, BandcampTrack):
                yield _track_to_release(data)
            elif isinstance(data, BandcampAlbum):
                yield _album_to_release(data)
            elif isinstance(data, BandcampArtist):
                yield _artist_to_entity(data)
            elif isinstance(data, BandcampLabel):
                yield _label_to_entity(data)

        if not page_results or _page >= max_pages:
            return
        # Recurse through the underlying function so the injected session
        # (if any) propagates across page fetches without round-tripping
        # through the descriptor.
        yield from cls.__dict__['search'].func(
            cls, _session, name, albums=albums, tracks=tracks,
            artists=artists, labels=labels, max_pages=max_pages,
            _page=_page + 1, _seen=_seen)

    @staticmethod
    def album_to_release(album_or_url, include_tracklist: bool = True) -> Release:
        """Convert a :class:`BandcampAlbum` (or album URL) into a fully
        populated :class:`mediavocab.Release` — including the ordered
        tracklist by default. Use this when you need the rich record;
        ``BandCamp.search_*`` skips the tracklist to avoid extra fetches.
        """
        album = (album_or_url if isinstance(album_or_url, BandcampAlbum)
                 else BandcampAlbum.from_url(album_or_url))
        return _album_to_release(album, include_tracklist=include_tracklist)

    @staticmethod
    def track_to_release(track_or_url) -> Release:
        """Convert a :class:`BandcampTrack` (or track URL) into a populated
        :class:`mediavocab.Release`."""
        track = (track_or_url if isinstance(track_or_url, BandcampTrack)
                 else BandcampTrack.from_url(track_or_url))
        return _track_to_release(track)

    @staticmethod
    def get_recommendations(url):
        """Albums recommended for fans of a given album URL."""
        return [_album_to_release(a) for a in BandcampAlbum.get_recommendations(url)]

    @staticmethod
    def get_related_artists(url):
        """Unique artists recommended for fans of a given album URL."""
        album = BandcampAlbum({"url": url}, scrap=False)
        return [_artist_to_entity(a) for a in album.related_artists]

    @_hybridmethod
    def get_track_lyrics(cls, _session, track_url):
        track_page = _http(_session).get(track_url)
        track_soup = BeautifulSoup(track_page.text, 'html.parser')
        track_lyrics = track_soup.find("div", {"class": "lyricsText"})
        if track_lyrics:
            return track_lyrics.text
        return "lyrics unavailable"

    @classmethod
    def get_streams(cls, urls):
        if not isinstance(urls, list):
            urls = [urls]
        return [cls.get_stream_url(url) for url in urls]

    @classmethod
    def get_stream_url(cls, url):
        data = get_stream_data(url)
        return data.get("stream") or url

    @staticmethod
    def _parse_label(item):
        art_tag = item.find("div", {"class": "art"})
        art_img = art_tag.find("img") if art_tag else None
        art = art_img["src"] if art_img else None
        name = item.find('div', class_='heading').text.strip()
        url = item.find('div', class_='heading').find('a')['href'].split("?")[0]
        subhead = item.find('div', class_='subhead')
        location = subhead.text.strip() if subhead else ""
        try:
            tags = item.find('div', class_='tags').text.replace("tags:", "").split(",")
            tags = [t.strip().lower() for t in tags]
        except (AttributeError, KeyError):
            tags = []
        return BandcampLabel({"name": name, "location": location,
                              "tags": tags, "url": url, "image": art})

    @staticmethod
    def _parse_artist(item):
        name = item.find('div', class_='heading').text.strip()
        url = item.find('div', class_='heading').find('a')['href'].split("?")[0]
        genre_tag = item.find('div', class_='genre')
        genre = genre_tag.text.strip().replace("genre: ", "") if genre_tag else ""
        subhead = item.find('div', class_='subhead')
        location = subhead.text.strip() if subhead else ""
        try:
            tags = item.find('div', class_='tags').text.replace("tags:", "").split(",")
            tags = [t.strip().lower() for t in tags]
        except (AttributeError, KeyError):
            tags = []
        art_tag = item.find("div", {"class": "art"})
        art_img = art_tag.find("img") if art_tag else None
        art = art_img["src"] if art_img else None
        return BandcampArtist({"name": name, "genre": genre, "location": location,
                               "tags": tags, "url": url, "image": art, "albums": []},
                              scrap=False)

    @staticmethod
    def _parse_track(item):
        track_name = item.find('div', class_='heading').text.strip()
        url = item.find('div', class_='heading').find('a')['href'].split("?")[0]
        subhead = item.find('div', class_='subhead')
        subhead_text = subhead.text.strip() if subhead else ""
        if "by" in subhead_text:
            parts = subhead_text.split("by", 1)
            album_name = parts[0].strip().replace("from ", "")
            artist = parts[1].strip()
        else:
            album_name = subhead_text.replace("from ", "").strip()
            artist = ""
        released_tag = item.find('div', class_='released')
        released = released_tag.text.strip().replace("released ", "") if released_tag else ""
        try:
            tags = item.find('div', class_='tags').text.replace("tags:", "").split(",")
            tags = [t.strip().lower() for t in tags]
        except (AttributeError, KeyError):
            tags = []
        art_tag = item.find("div", {"class": "art"})
        art_img = art_tag.find("img") if art_tag else None
        art = art_img["src"] if art_img else None
        return BandcampTrack({"track_name": track_name, "released": released,
                              "url": url, "tags": tags, "album_name": album_name,
                              "artist": artist, "image": art}, parse=False)

    @staticmethod
    def _parse_album(item):
        art_tag = item.find("div", {"class": "art"})
        art_img = art_tag.find("img") if art_tag else None
        art = art_img["src"] if art_img else None
        album_name = item.find('div', class_='heading').text.strip()
        url = item.find('div', class_='heading').find('a')['href'].split("?")[0]
        length_tag = item.find('div', class_='length')
        tracks, minutes = "", ""
        if length_tag:
            length = length_tag.text.strip()
            parts = length.split(",")
            if len(parts) == 2:
                tracks = parts[0].replace(" tracks", "").replace(" track", "").strip()
                minutes = parts[1].replace(" minutes", "").strip()
        released_tag = item.find('div', class_='released')
        released = released_tag.text.strip().replace("released ", "") if released_tag else ""
        try:
            tags = item.find('div', class_='tags').text.replace("tags:", "").split(",")
            tags = [t.strip().lower() for t in tags]
        except (AttributeError, KeyError):
            tags = []
        artist = item.find("div", {"class": "subhead"}).text.strip()
        if artist.startswith("by "):
            artist = artist[3:]
        return BandcampAlbum({"album_name": album_name, "minutes": minutes,
                              "url": url, "image": art, "artist": artist,
                              "track_number": tracks, "released": released,
                              "tags": tags}, scrap=False)
