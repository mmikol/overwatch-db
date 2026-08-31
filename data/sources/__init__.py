"""SOURCES: where the data comes from, and how a page is fetched once.

One module per source, and the one part of the pipeline both tiers share. A
source is a source whatever a tier makes of what it says: the wiki is read for
ability numbers by the authoritative tier and for playstyles by the heuristic
one, and there is no reason for two clients. So sources sit above the tiers,
and each tier begins at s1_extract.

    cached_get       one page, from the cache if it is there
    blizzard         the official site
    wiki             the MediaWiki endpoint, which returns JSON and rate-limits
    counterpick      counterpick.gg, fixed to competitive on console

Each module also declares the `sources` row its pages become - code, name and
URL - so provenance lives with the source rather than in a list somewhere else.

Fetching yields raw markup. Pulling data out of it is s1_extract.
"""

import os
import re
import time

import requests

DEFAULT_DELAY = 1.0
DEFAULT_TIMEOUT = 30
DEFAULT_BACKOFF = 1.0
MAX_BACKOFF = 60.0


class FetchError(Exception):
    pass


def cache_key(*parts):
    """A filesystem-safe name for a request."""
    return re.sub(r"[^A-Za-z0-9]+", "_", "_".join(str(p) for p in parts)).strip("_")


def cached_get(session, url, cache_dir, key, params=None, suffix=".html",
               timeout=DEFAULT_TIMEOUT, retries=1, delay=DEFAULT_DELAY,
               backoff=DEFAULT_BACKOFF):
    """Fetch one page as text, reading and writing a local cache.

    retries applies to a source that stalls under load rather than failing
    outright - Blizzard's rates page answers a few hundred sequential requests
    with a 504 - and waits `backoff` seconds, doubling each attempt, before
    trying again. A source that needs hundreds of pages should raise both:
    giving up mid-run loses the whole stage, and the delay is cheap next to
    refetching everything.
    """
    path = os.path.join(cache_dir, key + suffix) if cache_dir else None
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    last_error = None
    for attempt in range(retries):
        try:
            response = session.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            text = response.text
            break
        except requests.RequestException as error:
            last_error = error
            if attempt + 1 < retries:            # no point waiting to give up
                time.sleep(min(MAX_BACKOFF, backoff * (2 ** attempt)))
    else:
        raise FetchError("%s failed after %d attempts: %s" % (url, retries, last_error))

    if path:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    time.sleep(delay)
    return text
