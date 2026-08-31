"""INGEST: acquiring pages from a source, and not acquiring them twice.

Every pipeline needs the same thing: fetch a URL, keep a copy on disk, and
serve later runs from that copy so a rerun costs no requests. That was written
out three times before this module existed.

    cached_get   one page, from the cache if it is there
    wiki         the MediaWiki endpoint, which returns JSON and rate-limits

This stage yields raw markup. Pulling data out of it is the extract stage.
"""

import os
import re
import time

import requests

DEFAULT_DELAY = 1.0
DEFAULT_TIMEOUT = 30


class FetchError(Exception):
    pass


def cache_key(*parts):
    """A filesystem-safe name for a request."""
    return re.sub(r"[^A-Za-z0-9]+", "_", "_".join(str(p) for p in parts)).strip("_")


def cached_get(session, url, cache_dir, key, params=None, suffix=".html",
               timeout=DEFAULT_TIMEOUT, retries=1, delay=DEFAULT_DELAY):
    """Fetch one page as text, reading and writing a local cache.

    retries applies to a source that stalls under load rather than failing
    outright - Blizzard's rates page does - and backs off between attempts.
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
            time.sleep(2 ** attempt)
    else:
        raise FetchError("%s failed after %d attempts: %s" % (url, retries, last_error))

    if path:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    time.sleep(delay)
    return text
