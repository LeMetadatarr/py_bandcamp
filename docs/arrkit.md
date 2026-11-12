# Use from an arrkit app

py_bandcamp registers itself with apps built on arrkit (Musicarr and the other *arr-style apps) as an indexer and a download client, both named `bandcamp`. Install it with its `arr` extra into the app's environment and restart the app:

    uv pip install "py_bandcamp[arr]"

The app then lists `bandcamp` among its plugins, disabled. Add `bandcamp` to the app's enabled plugins, then create one indexer and one download client of implementation `bandcamp` in its settings. Nothing is called on a disabled plugin.

## Indexer

A search reads Bandcamp's album search. The text is the query's `term`; else its `artist` and `album` together; else its `title`, then each of `titles` in turn until one finds something. A query with a `track` and no album reads the track search instead. RSS reads the release grids of the artist and label pages the instance follows, in the order the page lists them; an instance that follows nothing returns nothing. Bandcamp has no feed of new releases by tag, so tags are not followed.

| Setting | Meaning |
|---|---|
| `url` | site address |
| `delay` | seconds between two requests to one host (default 3) |
| `resolve` | releases per answer whose page is read (default 5) |
| `max_results` | releases per answer (default 20) |
| `follow_artists` | RSS: artist and label pages, as addresses or `bandcamp.com` names, comma separated |
| `extra_hosts` | hosts of artists who use their own domain; release pages there are read only when listed |

The first `resolve` releases have their release page read once. The others are listed with what the search page says and cost no request. A release has the usual keys and these: `artist`, `album`, `track`, `year`, `published`, `format` (MP3), `bitrate` (128), `quality` (MP3-128), `tracks`, `seconds`, `tracklist`, `tags`, `label`, `thumbnail`, `license`, `license_url`, `price_min`, `bandcamp_id`, `access`, `downloadable` and `needs_purchase`. The title reads `Artist - Album (Year) [MP3 128]`, so a decision engine that reads quality from titles sees the rate.

`access` says what the page offers:

| `access` | Meaning | Downloadable |
|---|---|---|
| `free` | the page offers a free download | yes |
| `name_your_price` | the price is open and the minimum is nothing | yes |
| `licensed` | the license section names a Creative Commons license and no track is marked all rights reserved | yes |
| `paid` | there is a price | no, needs purchase |
| `preorder` | the release is a pre-order | no, needs purchase |
| `stream_only` | the page offers listening and no purchase | no |
| `restricted` | the release is private or for subscribers | no |
| `no_audio` | the page has no audio | no |
| `unchecked` | the page was not read, or was not a release page | no |

A downloadable release has protocol `bandcamp` and kind `download`. Every other release has protocol `bandcamp-stream` and kind `stream`, which no download client takes, so a decision engine rejects it for want of a client. Anything the page does not state plainly counts as not downloadable.

The `license` field holds an SPDX id such as `CC-BY-NC-ND-3.0` or `CC0-1.0`, read from the Creative Commons link in the page's license section. A license tag in the release's keywords is the artist's label and grants nothing.

## Download client

The client takes releases of protocol `bandcamp`. A grab is queued in the app's state folder and worked one at a time. The job reads the release page again and judges what the page says now, whatever the release said, so a release that has become a paid one is refused. It then saves the 128 kbps MP3 stream of every track into `<download_dir>/<title>-<job>/<number> - <track>.mp3`. The status of a job lists the file names.

It saves the stream that Bandcamp serves to anyone for listening, so it is what a free download offers at a lower rate. It does not fetch the lossless or higher-rate files behind Bandcamp's own download page, which asks for an email address, and it does not buy, log in or fill in any form. It writes no tags and no cover art.

A job fails, and its files and folder are removed, when the page asks for money or is not a release page, when a track has no stream, when a stream is not an audio file, when a host is not Bandcamp's, or when it is cancelled. Release pages must be `https` addresses on `bandcamp.com` or hosts listed in `extra_hosts`; stream links must be on `bandcamp.com` or `bcbits.com` or in `extra_hosts`. A file name stays within 255 bytes with its `.part` suffix, and so does the folder name.

| Setting | Meaning |
|---|---|
| `download_dir` | where the folders go |
| `delay` | seconds between two requests to one host (default 3) |
| `timeout` | seconds without data before a request fails (default 60) |
| `extra_hosts` | as for the indexer |

## Limits

Bandcamp's search page may answer a plain HTTP client with a JavaScript client challenge (status 200, title "Client Challenge"). The indexer reports that as a bot check and returns no releases; its test fails with the same message. RSS does not use the search page: it reads artist and label pages and the release pages of the first `resolve` releases, which answer a plain client.

Requests carry arrkit's User-Agent and are spaced per host by `delay`. Redirects are followed by hand, at most five, and every hop must be a trusted address and may not leave https. A page is read up to 8 MiB and an audio file up to 256 MiB; a longer answer is an error. An answer that ends before the length it declares, whole or chunked, is an error too, and a job that meets one fails and keeps nothing. A page must arrive within 120 seconds. An audio file must arrive within 60 seconds plus the time its size takes at 32 KiB a second, at most an hour, so a body that trickles in is cut off however slowly it comes; the `timeout` setting bounds only the wait for the next bytes. The library's own HTTP session, including the `curl_cffi` transport, is not used. A page that answers with a bot check, or a refusal (403, 429, 503), is an error that says Bandcamp is not usable from here. The plugin never tries again to get past it.

The pages are read for the structure the library parses: the search result list, the `data-tralbum` data and the `ld+json` block of a release page, and the license section. When Bandcamp changes them, a release shows up as `unchecked` or not at all, and the indexer's test says the layout may have changed.
