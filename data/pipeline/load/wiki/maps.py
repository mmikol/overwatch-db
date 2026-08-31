"""Ingest pipeline: overwatch.fandom.com - maps and game modes.

Loads the maps, modes and map/mode combinations playable in Open Queue
Competitive. Only the wiki's "Standard Play" section is read; Former Standard
Play (Assault, Clash), Stadium, Arcade, Custom Games, Training and seasonal
modes are all out of scope and are skipped.

    python -m data.pipeline.load.wiki.maps --dsn postgresql://...
"""

import sys
from datetime import datetime, timezone

import psycopg
import requests

from data.pipeline import orchestrator
from data.pipeline.ingest.wiki import (
    USER_AGENT,
    WikiError,
    fetch_wikitext,
)
from data.pipeline.extract.wiki.maps import parse_modes_and_maps

MAPS_PAGE = "Maps"


def main():
    parser = orchestrator.build_parser(__doc__, ".cache-wiki")
    args = parser.parse_args()

    orchestrator.prepare_cache(args)

    dsn = orchestrator.resolve_dsn(args)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    cao = datetime.now(timezone.utc)

    modes = parse_modes_and_maps(fetch_wikitext(session, MAPS_PAGE, args.cache))

    with psycopg.connect(dsn) as connection:
        cursor = connection.cursor()
        source_id = orchestrator.register_source(cursor, orchestrator.WIKI, cao)
        cursor.execute("DELETE FROM map_modes")
        cursor.execute("DELETE FROM maps")
        cursor.execute("DELETE FROM game_modes")

        map_ids, combinations = {}, 0
        for code, name, maps in modes:
            cursor.execute(
                "INSERT INTO game_modes (code, name, source_id)"
                " VALUES (%s, %s, %s) RETURNING mode_id",
                (code, name, source_id),
            )
            mode_id = cursor.fetchone()[0]

            for map_name in maps:
                if map_name not in map_ids:
                    cursor.execute(
                        "INSERT INTO maps (name, source_id)"
                        " VALUES (%s, %s) RETURNING map_id",
                        (map_name, source_id),
                    )
                    map_ids[map_name] = cursor.fetchone()[0]
                cursor.execute(
                    "INSERT INTO map_modes (map_id, mode_id, source_id)"
                    " VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                    (map_ids[map_name], mode_id, source_id),
                )
                combinations += 1
        connection.commit()

        orchestrator.export_raw(connection, args, ("game_modes", "maps", "map_modes"))

    for code, name, maps in modes:
        print("  %-11s %2d maps" % (name, len(maps)))
    print("\nmodes: %d   maps: %d   playable combinations: %d"
          % (len(modes), len(map_ids), combinations))


if __name__ == "__main__":
    try:
        main()
    except (WikiError, psycopg.Error, requests.RequestException) as error:
        sys.exit("error: %s" % error)
