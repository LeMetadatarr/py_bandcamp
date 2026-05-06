from bs4 import BeautifulSoup

from mediavocab import (
    Entity, EntityRef, EntityKind,
    Credit, CreditSection, RelationRole,
    Release, Work, MediaType, StreamMode,
)

from py_bandcamp.models import BandcampTrack, BandcampAlbum, BandcampArtist, BandcampLabel
from py_bandcamp.session import SESSION as requests, set_session
from py_bandcamp.utils import extract_ldjson_blob, get_props, extract_blob, \
    get_stream_data


def _track_to_release(track: BandcampTrack) -> Release:
    external_ids: dict = {}
    if track.track_id is not None:
        external_ids["bandcamp_track_id"] = str(track.track_id)
    if track.band_id is not None:
        external_ids["bandcamp_band_id"] = str(track.band_id)
    if track.album_id is not None:
        external_ids["bandcamp_album_id"] = str(track.album_id)
    credits: list = []
    artist_name = track.data.get("artist") or ""
    if artist_name:
        artist_ref = EntityRef(name=artist_name, kind=EntityKind.PERSON)
        credits.append(Credit(entity=artist_ref, role="artist",
            relation_role=RelationRole.PERFORMER, section=CreditSection.PRINCIPAL))
    work = Work(title=track.title, media_type=MediaType.MUSIC,
                runtime=float(track.duration) if track.duration else None,
                credits=credits, external_ids=external_ids)
    return Release(work=work, uri=track.url or "", image=track.image or "",
                   stream_mode=StreamMode.ON_DEMAND, external_ids=external_ids)


def _album_to_release(album: BandcampAlbum) -> Release:
    external_ids: dict = {}
    if album.album_id is not None:
        external_ids["bandcamp_album_id"] = str(album.album_id)
    if album.band_id is not None:
        external_ids["bandcamp_band_id"] = str(album.band_id)
    credits: list = []
    artist_name = album.data.get("artist") or ""
    if artist_name:
        artist_ref = EntityRef(name=artist_name, kind=EntityKind.PERSON)
        credits.append(Credit(entity=artist_ref, role="artist",
            relation_role=RelationRole.CREATOR, section=CreditSection.PRINCIPAL))
    work = Work(title=album.title, media_type=MediaType.MUSIC,
                credits=credits, external_ids=external_ids)
    return Release(work=work, uri=album.url or "", image=album.image or "",
                   stream_mode=StreamMode.ON_DEMAND, external_ids=external_ids)


def _artist_to_entity(artist: BandcampArtist) -> Entity:
    external_ids: dict = {}
    if artist.band_id is not None:
        external_ids["bandcamp_band_id"] = str(artist.band_id)
    extra: dict = {"artist_url": artist.url or ""}
    if artist.image:
        extra["image"] = artist.image
    if artist.location:
        extra["location"] = artist.location
    if artist.genre:
        extra["genre"] = artist.genre
    return Entity(name=artist.name or "", kind=EntityKind.PERSON,
                  external_ids=external_ids, extra=extra)


def _label_to_entity(label: BandcampLabel) -> Entity:
    extra: dict = {"artist_url": label.url or ""}
    if label.image:
        extra["image"] = label.image
    if label.location:
        extra["location"] = label.location
    return Entity(name=label.name or "", kind=EntityKind.ORGANISATION,
                  external_ids={}, extra=extra)


class BandCamp:
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

    @classmethod
    def search_tag(cls, tag, albums=True, tracks=True, artists=True, labels=False, max_pages=10):
        tag = tag.strip().replace(" ", "-").lower()
        yield from cls.search(tag, albums=albums, tracks=tracks,
                              artists=artists, labels=labels, max_pages=max_pages)

    @classmethod
    def search_albums(cls, album_name):
        for album in cls.search(album_name, albums=True, tracks=False,
                                artists=False, labels=False):
            yield album

    @classmethod
    def search_tracks(cls, track_name):
        for t in cls.search(track_name, albums=False, tracks=True,
                            artists=False, labels=False):
            yield t

    @classmethod
    def search_artists(cls, artist_name):
        for a in cls.search(artist_name, albums=False, tracks=False,
                            artists=True, labels=False):
            yield a

    @classmethod
    def search_labels(cls, label_name):
        for a in cls.search(label_name, albums=False, tracks=False,
                            artists=False, labels=True):
            yield a

    @classmethod
    def search(cls, name, albums=True, tracks=True, artists=True,
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
        response = requests.get('http://bandcamp.com/search', params=params)
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
        yield from cls.search(name, albums=albums, tracks=tracks,
                              artists=artists, labels=labels,
                              max_pages=max_pages, _page=_page + 1,
                              _seen=_seen)

    @staticmethod
    def get_recommendations(url):
        """Albums recommended for fans of a given album URL."""
        return [_album_to_release(a) for a in BandcampAlbum.get_recommendations(url)]

    @staticmethod
    def get_related_artists(url):
        """Unique artists recommended for fans of a given album URL."""
        album = BandcampAlbum({"url": url}, scrap=False)
        return [_artist_to_entity(a) for a in album.related_artists]

    @staticmethod
    def get_track_lyrics(track_url):
        track_page = requests.get(track_url)
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
