"""Shared fixtures.

Tests come in three kinds:

    unit         pure functions - no database, no network
    invariant    properties the loaded database must hold
    validation   our data against a third party's published figures

Only the first runs anywhere. The other two skip themselves when there is no
database to read or no network, so `pytest` on a fresh clone is still green.
"""

import os

import pytest

MARKERS = {
    "invariant": "needs a loaded database",
    "validation": "needs the network and a loaded database",
}


def pytest_configure(config):
    for name, description in MARKERS.items():
        config.addinivalue_line("markers", "%s: %s" % (name, description))


def _dsn():
    """The same resolution order the pipeline uses."""
    local = os.environ.get("OVERWATCH_DB_LOCAL_SERVER")
    if local:
        import pgserver

        return pgserver.get_server(os.path.abspath(local)).get_uri()
    return os.environ.get("DATABASE_URL") or "postgresql:///overwatch"


@pytest.fixture(scope="session")
def db():
    """A connection to the loaded database, or skip."""
    psycopg = pytest.importorskip("psycopg")
    try:
        connection = psycopg.connect(_dsn())
    except Exception as error:                      # noqa: BLE001 - any failure means skip
        pytest.skip("no database to test against: %s" % error)
    try:
        if connection.execute("select count(*) from heroes").fetchone()[0] == 0:
            pytest.skip("database is empty - run the pipeline first")
    except Exception as error:                      # noqa: BLE001
        pytest.skip("database has no schema: %s" % error)
    yield connection
    connection.close()


@pytest.fixture(scope="session")
def rows(db):
    """query -> list of tuples."""
    def run(sql, *args):
        return db.execute(sql, args or None).fetchall()
    return run


@pytest.fixture(scope="session")
def one(rows):
    """query -> first column of the first row."""
    return lambda sql, *args: rows(sql, *args)[0][0]
