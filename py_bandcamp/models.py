from bs4 import BeautifulSoup
from py_bandcamp.session import HTTP as requests
from py_bandcamp.utils import (
    _extract_blob_from_text,
    _extract_tralbum,
    _parse_iso_duration,
    _parse_ldjson,
    extract_ldjson_blob,
    get_props,
)


class BandcampTrack:
    def __init__(self, data, parse=True):
        self._url = data.get("url")
        self._data = data or {}
        self._page_data = {}
        if parse:
            self.parse_page()
        if not self.url:
            raise ValueError("bandcamp url is not set")

    def parse_page(self):
        self._page_data = self.get_track_data(self.url)
        return self._page_data

    @staticmethod
    def from_url(url):
        return BandcampTrack({"url": url})

    @property
    def url(self):
        return self._url or self.data.get("url")

    @property
    def album(self):
        return self.get_album(self.url)

    @property
    def artist(self):
        return self.get_artist(self.url)

    @property
    def data(self):
        for k, v in self._page_data.items():
            self._data[k] = v
        return self._data

    @property
    def title(self):
        return self.data.get("title") or self.data.get("name") or \
               self.url.split("/")[-1]

    @property
    def image(self):
        return self.data.get("image")

    @property
    def track_num(self):
        return self.data.get("tracknum")

    @property
    def duration(self):
        secs = self.data.get("duration_secs")
        if secs:
            return secs
        iso = self.data.get("duration_iso") or ""
        return _parse_iso_duration(iso)

    @property
    def stream(self):
        return self.data.get("file_mp3-128")

    @property
    def item_id(self):
        """Bandcamp internal item id from data-tralbum (stable across slug renames)."""
        return self.data.get("item_id")

    @property
    def track_id(self):
        """Bandcamp internal track id (from data-tralbum trackinfo)."""
        return self.data.get("track_id")

    @property
    def band_id(self):
        """Bandcamp internal band/artist id."""
        return self.data.get("band_id")

    @property
    def album_id(self):
        """Bandcamp internal album id this track belongs to, if any."""
        return self.data.get("album_id")

    @staticmethod
    def get_album(url):
        data = extract_ldjson_blob(url, clean=True)
        if data.get('inAlbum'):
            return BandcampAlbum({
                "title": data['inAlbum'].get('name'),
                "url": data['inAlbum'].get('id', url).split("#")[0],
                'type': data['inAlbum'].get("type"),
            })

    @staticmethod
    def get_artist(url):
        data = extract_ldjson_blob(url, clean=True)
        d = data.get("byArtist")
        if d:
            return BandcampArtist({
                "title": d.get('name'),
                "url": d.get('id', url).split("#")[0],
                'genre': d.get('genre'),
                "artist_type": d.get('type')
            }, scrap=False)
        return None

    @staticmethod
    def get_track_data(url):
        import json

        resp = requests.get(url)
        if not resp.ok:
            raise ValueError(f"HTTP {resp.status_code} fetching {url}")
        text = resp.text

        if '<script type="application/ld+json">' not in text:
            raise ValueError(f"No ld+json found at {url} — may be a 404 or non-track page")

        ld_blob = text.split('<script type="application/ld+json">')[-1].split("</script>")[0]

        def _clean(d):
            if isinstance(d, dict):
                return {k.replace("@", ""): _clean(v) for k, v in d.items()}
            if isinstance(d, list):
                return [_clean(i) for i in d]
            return d

        try:
            data = _clean(json.loads(ld_blob))
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse ld+json from {url}: {e}") from e
        tralbum = _extract_tralbum(text)

        kwords = data.get('keywords', "")
        if isinstance(kwords, str):
            kwords = kwords.split(", ") if kwords else []
        track = {
            'dateModified': data.get('dateModified'),
            'datePublished': data.get('datePublished'),
            "url": data.get('id') or url,
            "title": data.get("name"),
            "type": data.get("type"),
            'image': data.get('image'),
            'keywords': kwords
        }
        for k, v in get_props(data).items():
            track[k] = v

        # Pull stream URL and duration from data-tralbum if not already present
        trackinfo = (tralbum.get("trackinfo") or [{}])[0]
        if not track.get("file_mp3-128"):
            mp3 = trackinfo.get("file", {}).get("mp3-128")
            if mp3:
                track["file_mp3-128"] = mp3
        if not track.get("duration_secs"):
            dur = trackinfo.get("duration")
            if dur:
                track["duration_secs"] = int(dur)

        # Bandcamp's true numeric IDs from data-tralbum
        current = tralbum.get("current") or {}
        item_id = tralbum.get("id") or current.get("id")
        if item_id is not None:
            track["item_id"] = item_id
        band_id = current.get("band_id") or tralbum.get("band_id")
        if band_id is not None:
            track["band_id"] = band_id
        # On a /track/ page, current.type == "t" and current.id is the track id;
        # album_id may be set if the track belongs to an album.
        album_id = tralbum.get("album_id") or current.get("album_id")
        if album_id is not None:
            track["album_id"] = album_id
        track_id = trackinfo.get("track_id") or trackinfo.get("id")
        if track_id is None and current.get("type") == "t":
            track_id = current.get("id")
        if track_id is not None:
            track["track_id"] = track_id

        return track

    def __repr__(self):
        return self.__class__.__name__ + ":" + self.title

    def __str__(self):
        return self.url

    def __eq__(self, other):
        return str(self) == str(other)

    def __hash__(self):
        return hash(self.url)


class BandcampSingle:
    """A Bandcamp single — a /track/ release treated as a one-track album."""

    release_type = "single"

    def __init__(self, data):
        self._data = data

    @staticmethod
    def from_url(url):
        t = BandcampTrack({"url": url})
        return BandcampSingle({
            "url": url,
            "title": t.title,
            "artist": getattr(t.artist, "name", None) if t.artist else None,
            "image": t.image,
            "track": t,
        })

    @property
    def url(self):
        return self._data.get("url", "")

    @property
    def title(self):
        return self._data.get("title") or self.url.split("/")[-1]

    @property
    def artist(self):
        return self._data.get("artist")

    @property
    def image(self):
        return self._data.get("image")

    @property
    def tracks(self):
        t = self._data.get("track")
        if t is None:
            t = BandcampTrack({"url": self.url})
        return [t]

    @property
    def data(self):
        return self._data

    def __str__(self):
        return self.url

    def __repr__(self):
        return f"BandcampSingle:{self.title}"

    def __eq__(self, other):
        return str(self) == str(other)

    def __hash__(self):
        return hash(self.url)


class BandcampAlbum:
    def __init__(self, data, scrap=True):
        self._url = data.get("url")
        self._data = data or {}
        self._page_data = {}
        if scrap:
            self.scrap()
        if not self.url:
            raise ValueError("bandcamp url is not set")

    def scrap(self):
        self._page_data = self.get_album_data(self.url)
        return self._page_data

    @staticmethod
    def from_url(url):
        return BandcampAlbum({"url": url})

    @property
    def image(self):
        return self.data.get("image")

    @property
    def url(self):
        return self._url or self.data.get("url")

    @property
    def title(self):
        return self.data.get("title") or self.data.get("name") or \
               self.data.get("album_name") or self.url.split("/")[-1]

    @property
    def releases(self):
        return self.get_releases(self.url)

    @property
    def artist(self):
        return self.get_artist(self.url)

    @property
    def keywords(self):
        return self.data.get("keywords") or []

    @property
    def album_id(self):
        """Bandcamp internal album id from data-tralbum."""
        return self.data.get("album_id")

    @property
    def item_id(self):
        """Bandcamp internal item id (same as album_id for albums)."""
        return self.data.get("item_id") or self.data.get("album_id")

    @property
    def band_id(self):
        """Bandcamp internal band/artist id."""
        return self.data.get("band_id")

    @property
    def tracks(self):
        return self.get_tracks(self.url)

    @property
    def featured_track(self):
        if not len(self.tracks):
            return None
        num = self.data.get('featured_track_num', 1) or 1
        return self.tracks[int(num) - 1]

    @property
    def recommendations(self):
        return self.get_recommendations(self.url)

    @property
    def related_artists(self):
        seen = set()
        artists = []
        for album in self.get_recommendations(self.url):
            artist_name = album.data.get("artist", "")
            if artist_name and artist_name not in seen:
                seen.add(artist_name)
                artists.append(BandcampArtist({"name": artist_name, "url": album.url.split("/album/")[0]}, scrap=False))
        return artists

    @property
    def comments(self):
        return self.get_comments(self.url)

    @property
    def data(self):
        for k, v in self._page_data.items():
            self._data[k] = v
        return self._data

    @staticmethod
    def get_releases(url):
        data = extract_ldjson_blob(url, clean=True)
        releases = []
        for d in data.get("albumRelease", []):
            release = {
                "description": d.get("description"),
                'image': d.get('image'),
                "title": d.get('name'),
                "url": d.get('id', url).split("#")[0],
                'format': d.get('musicReleaseFormat'),
            }
            releases.append(release)
        return releases

    @staticmethod
    def get_artist(url):
        data = extract_ldjson_blob(url, clean=True)
        d = data.get("byArtist")
        if d:
            return BandcampArtist({
                "description": d.get("description"),
                'image': d.get('image'),
                "title": d.get('name'),
                "url": d.get('id', url).split("#")[0],
                'genre': d.get('genre'),
                "artist_type": d.get('type')
            }, scrap=False)
        return None

    @staticmethod
    def get_tracks(url):
        resp = requests.get(url)
        text = resp.text
        data = _parse_ldjson(text, clean=True)
        if not data.get("track"):
            return []

        tralbum = _extract_tralbum(text)
        current = tralbum.get("current") or {}
        album_item_id = tralbum.get("id") or current.get("id")
        band_id = current.get("band_id") or tralbum.get("band_id")
        trackinfos = tralbum.get("trackinfo") or []
        ti_by_num = {}
        for ti in trackinfos:
            try:
                ti_by_num[int(ti["track_num"])] = ti
            except (KeyError, TypeError, ValueError):
                pass

        tracks = []
        for entry in data['track'].get('itemListElement', []):
            d = entry.get('item', {})
            position = entry.get('position')
            try:
                pos_int = int(position)
            except (TypeError, ValueError):
                pos_int = None
            track = {
                "title": d.get('name'),
                "url": d.get('id') or url,
                'type': d.get('type'),
                "tracknum": position,
                "duration_iso": d.get('duration'),
            }
            for k, v in get_props(d).items():
                track[k] = v
            ti = ti_by_num.get(pos_int) or (
                trackinfos[pos_int - 1] if pos_int is not None and 0 < pos_int <= len(trackinfos) else {}
            )
            track_id = ti.get("track_id") or ti.get("id")
            if track_id is not None:
                track["track_id"] = track_id
            if album_item_id is not None:
                track["album_id"] = album_item_id
            if band_id is not None:
                track["band_id"] = band_id
            tracks.append(BandcampTrack(track, parse=False))
        return tracks

    @staticmethod
    def get_recommendations(url):
        """Albums recommended by Bandcamp for fans of this album ('If you like…')."""
        resp = requests.get(url)
        if not resp.ok:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        container = soup.find(id="recommendations_container")
        if not container:
            return []
        albums = []
        for li in container.find_all("li", class_="recommended-album"):
            album_url_tag = li.find("a", class_="album-link")
            if not album_url_tag:
                continue
            href = album_url_tag.get("href", "").split("?")[0]
            title_span = album_url_tag.find(class_="release-title")
            artist_span = album_url_tag.find(class_="by-artist")
            raw_artist = artist_span.text.strip() if artist_span else li.get("data-artist", "")
            artist = raw_artist.removeprefix("by ") if raw_artist else li.get("data-artist")
            albums.append(BandcampAlbum({
                "title": title_span.text.strip() if title_span else li.get("data-albumtitle"),
                "artist": artist,
                "url": href,
                "image": (li.find("img") or {}).get("src"),
            }, scrap=False))
        return albums

    @staticmethod
    def get_comments(url):
        data = extract_ldjson_blob(url, clean=True)
        comments = []
        for d in data.get("comment", []):
            text = d.get("text", "")
            if isinstance(text, list):
                text = " ".join(text)
            comment = {
                "text": text,
                'image': d["author"].get("image"),
                "author": d["author"]["name"]
            }
            comments.append(comment)
        return comments

    @staticmethod
    def get_album_data(url):
        resp = requests.get(url)
        text = resp.text
        data = _parse_ldjson(text, clean=True)
        props = get_props(data)
        kwords = data.get('keywords', "")
        if isinstance(kwords, str):
            kwords = kwords.split(", ")
        artist_data = data.get('byArtist') or {}
        publisher_data = data.get('publisher') or {}
        result = {
            'dateModified': data.get('dateModified'),
            'datePublished': data.get('datePublished'),
            'description': data.get('description'),
            "url": data.get('id') or url,
            "title": data.get("name"),
            "type": data.get("type"),
            "n_tracks": data.get('numTracks'),
            'image': data.get('image'),
            'featured_track_num': props.get('featured_track_num'),
            'keywords': kwords,
            'artist': artist_data.get('name'),
            'artist_url': (artist_data.get('id') or '').split('#')[0] or None,
            'publisher': publisher_data.get('name'),
            'publisher_url': (publisher_data.get('id') or '').split('#')[0] or None,
        }
        tralbum = _extract_tralbum(text)
        current = tralbum.get("current") or {}
        item_id = tralbum.get("id") or current.get("id")
        if item_id is not None:
            result["album_id"] = item_id
            result["item_id"] = item_id
        band_id = current.get("band_id") or tralbum.get("band_id")
        if band_id is not None:
            result["band_id"] = band_id
        return result

    def __repr__(self):
        return self.__class__.__name__ + ":" + self.title

    def __str__(self):
        return self.url

    def __eq__(self, other):
        return str(self) == str(other)

    def __hash__(self):
        return hash(self.url)


class BandcampLabel:
    def __init__(self, data, scrap=True):
        self._url = data.get("url")
        self._data = data or {}
        self._page_data = {}
        if scrap:
            self.scrap()
        if not self.url:
            raise ValueError("bandcamp url is not set")

    def scrap(self):
        if not self._url:
            return {}
        try:
            import json as _json
            resp = requests.get(self._url)
            if not resp.ok:
                return {}
            soup = BeautifulSoup(resp.text, "html.parser")

            band_data: dict = {}
            band_tag = soup.find(attrs={"data-band": True})
            if band_tag:
                try:
                    band_data = _json.loads(band_tag["data-band"])
                except Exception:
                    pass

            band_id = band_data.get("id")
            name, location = None, None
            loc_tag = soup.find(id="band-name-location")
            if loc_tag:
                name_span = loc_tag.find(class_="title")
                loc_span = loc_tag.find(class_="location")
                name = name_span.text.strip() if name_span else None
                location = loc_span.text.strip() if loc_span else None
            name = name or band_data.get("name")

            img_tag = soup.find("div", id="bio-container")
            image = None
            if img_tag:
                img = img_tag.find("img")
                image = img["src"] if img else None

            self._page_data = {k: v for k, v in {
                "name": name, "location": location,
                "image": image, "band_id": band_id,
                "is_label": True,
            }.items() if v is not None}
        except Exception:
            self._page_data = {}
        return self._page_data

    @staticmethod
    def from_url(url):
        return BandcampLabel({"url": url}, scrap=False)

    @property
    def url(self):
        return self._url or self.data.get("url")

    @property
    def data(self):
        for k, v in self._page_data.items():
            self._data[k] = v
        return self._data

    @property
    def name(self):
        return self.data.get("title") or self.data.get("name") or \
               self.url.split("/")[-1]

    @property
    def location(self):
        return self.data.get("location")

    @property
    def tags(self):
        return self.data.get("tags") or []

    @property
    def image(self):
        return self.data.get("image")

    def __repr__(self):
        return self.__class__.__name__ + ":" + self.name

    def __str__(self):
        return self.url

    def __eq__(self, other):
        return str(self) == str(other)

    def __hash__(self):
        return hash(self.url)


class BandcampArtist:
    def __init__(self, data, scrap=True):
        self._url = data.get("url")
        self._data = data or {}
        self._page_data = {}
        if scrap:
            self.scrap()

    @staticmethod
    def _scrap_band_id(artist_url):
        """Hit ``<artist_url>/releases`` and pull the band id out of the
        embedded ``item_sellers`` dict. Returns ``None`` on any failure
        — callers must tolerate it, since Bandcamp's HTML is not stable.
        """
        if not artist_url:
            return None
        try:
            resp = requests.get(artist_url.rstrip("/") + "/releases")
            if not resp.ok:
                return None
            blob = _extract_blob_from_text(resp.text) or {}
        except Exception:
            return None
        sellers = blob.get("item_sellers") or {}
        try:
            if isinstance(sellers, dict) and sellers:
                return int(next(iter(sellers)))
            if isinstance(sellers, list) and sellers:
                return int(sellers[0])
        except (TypeError, ValueError):
            return None
        return None

    def scrap(self):
        if not self._url:
            return {}
        try:
            resp = requests.get(self._url)
            if not resp.ok:
                return {}
            import json as _json
            soup = BeautifulSoup(resp.text, "html.parser")

            # Prefer data-band JSON — has the numeric id, name, subdomain,
            # is_label flag and genre_id without a second HTTP call.
            band_data: dict = {}
            band_tag = soup.find(attrs={"data-band": True})
            if band_tag:
                try:
                    band_data = _json.loads(band_tag["data-band"])
                except Exception:
                    pass

            # Numeric band id: from data-band first, /releases fallback
            band_id = band_data.get("id") or self._scrap_band_id(self._url)
            is_label = bool(band_data.get("is_label"))

            loc_tag = soup.find(id="band-name-location")
            name, location = None, None
            if loc_tag:
                name_span = loc_tag.find(class_="title")
                loc_span = loc_tag.find(class_="location")
                name = name_span.text.strip() if name_span else None
                location = loc_span.text.strip() if loc_span else None
            # data-band name as fallback (already present)
            name = name or band_data.get("name")

            genre_tag = soup.find("dd", class_="genre") or soup.find("span", class_="genre")
            genre = genre_tag.text.strip() if genre_tag else None
            img_tag = soup.find("div", id="bio-container")
            image = None
            if img_tag:
                img = img_tag.find("img")
                image = img["src"] if img else None

            # External/social links — Bandcamp artist pages embed links in
            # a <div class="social-links"> or as data-url on icon anchors.
            social: dict = {}
            for a in soup.find_all("a", href=True):
                href = a["href"]
                for platform in ("twitter", "instagram", "facebook",
                                 "youtube", "spotify", "tiktok", "linktree"):
                    if platform in href and href not in social.values():
                        social[platform] = href
                        break

            self._page_data = {k: v for k, v in {
                "name": name, "location": location,
                "genre": genre, "image": image, "band_id": band_id,
                "is_label": is_label or None,
                "social": social or None,
            }.items() if v is not None}
        except Exception:
            self._page_data = {}
        return self._page_data

    @property
    def band_id(self):
        """Numeric Bandcamp band/artist id — the canonical cross-platform
        identifier for an artist. Same value other ``Bandcamp*`` models
        expose under ``.band_id`` for tracks and albums."""
        return self.data.get("band_id")

    @property
    def item_id(self):
        """Alias for :attr:`band_id` — matches the property name used on
        :class:`BandcampTrack` and :class:`BandcampAlbum` for symmetry."""
        return self.band_id

    @property
    def featured_album(self):
        return BandcampAlbum.from_url(self.url + "/releases")

    @property
    def featured_track(self):
        if not self.featured_album:
            return None
        return self.featured_album.featured_track

    @staticmethod
    def get_albums(url, scrap=False, include_singles=False):
        albums = []
        singles = []
        soup = BeautifulSoup(requests.get(url).text, "html.parser")
        for item in soup.find_all("a"):
            title_tag = item.find("p", {"class": "title"})
            if not title_tag:
                continue
            title = title_tag.text.strip()
            art_div = item.find("div", {"class": "art"})
            art_img = art_div.find("img") if art_div else None
            art = art_img["src"] if art_img else None
            href = item.get("href", "")
            item_url = url.rstrip("/") + href
            if "/track/" in href:
                singles.append(BandcampSingle({"url": item_url, "title": title, "image": art}))
            elif "/album/" in href:
                albums.append(BandcampAlbum({"album_name": title, "image": art, "url": item_url}, scrap=scrap))
        if include_singles:
            return albums, singles
        return albums

    @staticmethod
    def get_singles(url):
        _, singles = BandcampArtist.get_albums(url, include_singles=True)
        return singles

    @property
    def albums(self):
        return self.get_albums(self.url)

    @staticmethod
    def from_url(url):
        return BandcampArtist({"url": url})

    @property
    def url(self):
        return self._url or self.data.get("url")

    @property
    def data(self):
        for k, v in self._page_data.items():
            self._data[k] = v
        return self._data

    @property
    def name(self):
        return self.data.get("title") or self.data.get("name") or \
               self.url.split("/")[-1]

    @property
    def location(self):
        return self.data.get("location")

    @property
    def genre(self):
        return self.data.get("genre")

    @property
    def tags(self):
        return self.data.get("tags") or []

    @property
    def image(self):
        return self.data.get("image")

    def __repr__(self):
        return self.__class__.__name__ + ":" + self.name

    def __str__(self):
        return self.url

    def __eq__(self, other):
        return str(self) == str(other)

    def __hash__(self):
        return hash(self.url)
