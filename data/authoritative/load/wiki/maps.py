"""Ingest pipeline: overwatch.fandom.com - maps and game modes.

Loads the maps, modes and map/mode combinations playable in Open Queue
Competitive. Only the wiki's "Standard Play" section is read; Former Standard
Play (Assault, Clash), Stadium, Arcade, Custom Games, Training and seasonal
modes are all out of scope and are skipped.

    python -m data.authoritative.load.wiki.maps --dsn postgresql://...
"""

import sys
from datetime import datetime, timezone

import psycopg
import requests

from data.authoritative import pipeline
from data.sources.wiki import (
    WIKI,
    USER_AGENT,
    WikiError,
    fetch_wikitext,
)
from data.authoritative.extract.wiki.maps import parse_modes_and_maps, parse_stages

MAPS_PAGE = "Maps"


def main():
    parser = pipeline.build_parser(__doc__, ".cache-wiki")
    args = parser.parse_args()

    pipeline.prepare_cache(args)

    dsn = pipeline.resolve_dsn(args)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    cao = datetime.now(timezone.utc)

    modes = parse_modes_and_maps(fetch_wikitext(session, MAPS_PAGE, args.cache))

    with psycopg.connect(dsn) as connection:
        cursor = connection.cursor()
        source_id = pipeline.register_source(cursor, WIKI, cao)

        map_ids, combinations = {}, 0
        for code, name, maps in modes:
            cursor.execute(
                # Upserted, never deleted: map_meta snapshots hang off
                # maps, and a DELETE here cascades through every older
                # snapshot's rows. Removals are what `rebuild` is for.
                "INSERT INTO game_modes (code, name, source_id)"
                " VALUES (%s, %s, %s)"
                " ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name,"
                " source_id = EXCLUDED.source_id, cao = now()"
                " RETURNING mode_id",
                (code, name, source_id),
            )
            mode_id = cursor.fetchone()[0]

            for map_name in maps:
                if map_name not in map_ids:
                    cursor.execute(
                        "INSERT INTO maps (name, source_id)"
                        " VALUES (%s, %s)"
                        " ON CONFLICT (name) DO UPDATE SET"
                        " source_id = EXCLUDED.source_id, cao = now()"
                        " RETURNING map_id",
                        (map_name, source_id),
                    )
                    map_ids[map_name] = cursor.fetchone()[0]
                cursor.execute(
                    "INSERT INTO map_modes (map_id, mode_id, source_id)"
                    " VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                    (map_ids[map_name], mode_id, source_id),
                )
                combinations += 1
        # Stages (submaps): Ilios' Well, Busan's MEKA Base. Read from each
        # map's own article - Control and Flashpoint maps list them; Escort,
        # Hybrid and Push maps have none, and load none. Upserted by
        # (map_id, name) rather than delete-reloaded, because map_meta rows
        # may reference a stage and a DELETE here would cascade through them.
        stage_rows = 0
        for map_name, map_id in map_ids.items():
            for position, stage in enumerate(
                parse_stages(fetch_wikitext(
                    session, map_name.replace(" ", "_"), args.cache)),
                start=1,
            ):
                cursor.execute(
                    "INSERT INTO map_stages (map_id, position, name, source_id)"
                    " VALUES (%s, %s, %s, %s)"
                    " ON CONFLICT (map_id, name) DO UPDATE SET"
                    " position = EXCLUDED.position,"
                    " source_id = EXCLUDED.source_id, cao = now()",
                    (map_id, position, stage, source_id),
                )
                stage_rows += 1
        connection.commit()

        pipeline.export_raw(connection, args,
                            ("game_modes", "maps", "map_modes", "map_stages"))

    for code, name, maps in modes:
        print("  %-11s %2d maps" % (name, len(maps)))
    print("\nmodes: %d   maps: %d   playable combinations: %d"
          % (len(modes), len(map_ids), combinations))
    print("stages: %d across the maps that have them" % stage_rows)


if __name__ == "__main__":
    try:
        main()
    except (WikiError, psycopg.Error, requests.RequestException) as error:
        sys.exit("error: %s" % error)
