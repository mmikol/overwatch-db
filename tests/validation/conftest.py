"""Fixtures for comparing our data against a third party's published figures.

These tests cannot assert equality. Every published source samples a different
population - a different queue, input device, region and time window - so our
numbers will never match theirs exactly, and a test that demanded it would fail
forever and teach nobody anything.

What they check instead:

  shape      the source still publishes what we think it does, and we can
             produce the same rows from our own tables
  agreement  the two broadly agree, with a floor loose enough to survive a
             patch and tight enough to catch our data going wrong

A hard failure here means either the source changed its page, or our pipeline
is producing something badly different from consensus. Both are worth knowing.
"""

import unicodedata

import pytest

requests = pytest.importorskip("requests")

USER_AGENT = "overwatch-db-tests/0.1 (personal project; contact via repo)"


@pytest.fixture(scope="session")
def fetch():
    """GET a page as text, or skip the test if it cannot be reached."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    def get(url, **kwargs):
        try:
            response = session.get(url, timeout=45, **kwargs)
            response.raise_for_status()
        except requests.RequestException as error:
            pytest.skip("%s unreachable: %s" % (url, error))
        return response

    return get


def normalise(name):
    """Fold a hero or map name so two sources' spellings compare equal."""
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return (folded.lower().replace("-", " ").replace(".", "")
            .replace(":", "").replace("'", "").strip())
