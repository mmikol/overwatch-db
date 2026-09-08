"""Load pipeline: the wiki's Patches cargo table - game versions.

A win rate is true of a patch, and snapshots link to the most recent patch
released at capture time, so the accumulated series stays interpretable. Most
balance patches ship unversioned, so the wiki's page name ("August 14, 2026
Patch") is the identity.

Runs before the meta pipelines so their snapshots have patches to link to.

    python -m data.authoritative.load.wiki.patches
"""

import sys
from datetime import datetime, timezone

import psycopg
import requests

from data.authoritative import pipeline
from data.sources.wiki import USER_AGENT, WIKI, WikiError, cargo_query

CARGO_TABLE = "Patches"
# Cargo refuses bare underscore fields; _pageName must be aliased.
CARGO_FIELDS = ("_pageName=name", "date", "platform", "source")


def main():
    parser = pipeline.build_parser(__doc__, ".cache-wiki")
    args = parser.parse_args()
    pipeline.prepare_cache(args)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    cao = datetime.now(timezone.utc)

    rows = cargo_query(session, CARGO_TABLE, CARGO_FIELDS, args.cache)

    with psycopg.connect(pipeline.resolve_dsn(args)) as connection:
        cursor = connection.cursor()
        source_id = pipeline.register_source(cursor, WIKI, cao)

        loaded, skipped = 0, 0
        for row in rows:
            name, released = row.get("name"), row.get("date")
            if not name or not released:
                skipped += 1          # a page without a date anchors nothing
                continue
            cursor.execute(
                "INSERT INTO patches (name, released, platform, url, source_id)"
                " VALUES (%s, %s, %s, %s, %s)"
                " ON CONFLICT (name) DO UPDATE SET released = EXCLUDED.released,"
                " platform = EXCLUDED.platform, url = EXCLUDED.url,"
                " source_id = EXCLUDED.source_id, cao = now()",
                (name, released, row.get("platform") or None,
                 row.get("source") or None, source_id),
            )
            loaded += 1
        connection.commit()
        pipeline.export_raw(connection, args, ("patches",))

        latest = cursor.execute(
            "SELECT name, released FROM patches ORDER BY released DESC LIMIT 1"
        ).fetchone()

    print("patches: %d loaded, %d skipped (no date)" % (loaded, skipped))
    if latest:
        print("latest: %s (%s)" % latest)


if __name__ == "__main__":
    try:
        main()
    except (WikiError, psycopg.Error, requests.RequestException) as error:
        sys.exit("error: %s" % error)
