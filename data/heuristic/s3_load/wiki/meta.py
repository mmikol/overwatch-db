"""Ingest pipeline: overwatch.fandom.com - team composition playstyles.

Loads the playstyles (dive, brawl, poke) and the heroes listed under each. A
hero can appear in several, so the link table is many-to-many.

    python -m data.heuristic.s3_load.wiki.meta --dsn postgresql://...
"""

import sys
from datetime import datetime, timezone

import psycopg
import requests

from data.heuristic import pipeline
from data.ingest.wiki import (
    WIKI,
    USER_AGENT,
    WikiError,
    fetch_wikitext,
)
from data.heuristic.s1_extract.wiki.meta import COMPOSITION_PAGE, parse_playstyles


# "=== Dive heroes ===" opens the hero list for the Dive playstyle.


def main():
    parser = pipeline.build_parser(__doc__, ".cache-wiki")
    args = parser.parse_args()

    pipeline.prepare_cache(args)

    dsn = pipeline.resolve_dsn(args)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    cao = datetime.now(timezone.utc)

    playstyles = parse_playstyles(fetch_wikitext(session, COMPOSITION_PAGE, args.cache))

    with psycopg.connect(dsn) as connection:
        cursor = connection.cursor()
        source_id = pipeline.register_source(cursor, WIKI, cao)
        cursor.execute("DELETE FROM hero_playstyles")
        cursor.execute("DELETE FROM playstyles")

        hero_ids = pipeline.lookup_ids(cursor, "heroes", "name", "hero_id")

        links, unmatched = 0, []
        for code, name, heroes in playstyles:
            cursor.execute(
                "INSERT INTO playstyles (code, name, source_id) VALUES (%s, %s, %s)"
                " RETURNING playstyle_id",
                (code, name, source_id),
            )
            playstyle_id = cursor.fetchone()[0]
            for hero_name in heroes:
                hero_id = hero_ids.get(hero_name.lower())
                if hero_id is None:
                    unmatched.append("%s: %s" % (name, hero_name))
                    continue
                cursor.execute(
                    "INSERT INTO hero_playstyles (hero_id, playstyle_id, source_id)"
                    " VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                    (hero_id, playstyle_id, source_id),
                )
                links += 1
        connection.commit()

        pipeline.export_raw(connection, args, ("playstyles", "hero_playstyles"))

    for code, name, heroes in playstyles:
        print("  %-8s %2d heroes" % (name, len(heroes)))
    print("\nplaystyles: %d   hero links: %d" % (len(playstyles), links))
    if unmatched:
        print("\n%d listed names matched no hero:" % len(unmatched))
        for item in unmatched:
            print("   %s" % item)


if __name__ == "__main__":
    try:
        main()
    except (WikiError, psycopg.Error, requests.RequestException) as error:
        sys.exit("error: %s" % error)
