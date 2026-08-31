"""Load pipeline: counterpick.gg - counters, best maps and rates by region.

This is the PLAYBOOK half of the model: who answers whom. The rates it also
publishes go into hero_meta_stats under their own snapshot, because they are a
different population from Blizzard's - competitive on console, and the site's
own sample rather than Blizzard's.

Scope is fixed to competitive on console; region is the axis that varies, and
every row records which region it came from.

Run after wiki.maps and blizzard.meta, whose maps and regions it links to:

    python -m data.heuristic.s3_load.counterpick.heroes --dsn postgresql://...
"""

import sys

import psycopg
import requests

from data.sources import FetchError, cache_key, cached_get
from data.heuristic import pipeline
from data.heuristic.s1_extract.counterpick.heroes import CounterpickError, parse_table
from data.heuristic.s2_transform.counterpick.names import index, match_key
from data.sources.counterpick import (
    COUNTERPICK,
    BASE_URL,
    GAMEMODE,
    PLATFORM,
    REGIONS,
    USER_AGENT,
)

# The site filters on gamemode=competitive and never says which queue those
# games were: it offers no role/open switch and states nothing either way.
# "competitive" alone would be a game mode sitting in a column that everywhere
# else names a queue, and would read as though the queue were known. This model
# is about Open Queue, so an unlabelled snapshot must not be mistaken for one.
QUEUE = "competitive_unspecified_queue"
INPUT = "console"


def main():
    parser = pipeline.build_parser(__doc__, ".cache-counterpick")
    args = parser.parse_args()
    pipeline.prepare_cache(args)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    cao = pipeline.now()

    pages = {}
    for their_region, our_region in REGIONS.items():
        pages[our_region] = parse_table(cached_get(
            session, BASE_URL, args.cache,
            cache_key("heroes", GAMEMODE, PLATFORM, their_region),
            params={"platform": PLATFORM, "gamemode": GAMEMODE,
                    "region": their_region},
        ))
        print("  %-14s %d heroes" % (their_region, len(pages[our_region])))

    with psycopg.connect(pipeline.resolve_dsn(args)) as connection:
        cursor = connection.cursor()
        source_id = pipeline.register_source(
            cursor, COUNTERPICK, cao)

        cursor.execute("INSERT INTO meta_snapshots (captured_at, queue, input,"
                       " source_id) VALUES (%s, %s, %s, %s) RETURNING snapshot_id",
                       (cao, QUEUE, INPUT, source_id))
        snapshot_id = cursor.fetchone()[0]

        hero_ids = index(pipeline.lookup_ids(cursor, "heroes", "name", "hero_id"))
        map_ids = index(pipeline.lookup_ids(cursor, "maps", "name", "map_id"))
        region_ids = pipeline.lookup_ids(cursor, "regions", "code", "region_id")
        all_tier = cursor.execute(
            "SELECT tier_id FROM competitive_tiers WHERE code = 'all'").fetchone()

        rates = counters = best_maps = 0
        unknown_heroes, unknown_maps, missing_regions = set(), set(), set()

        for region_code, heroes in pages.items():
            region_id = region_ids.get(region_code)
            if region_id is None:
                missing_regions.add(region_code)
                continue

            for entry in heroes:
                hero_id = hero_ids.get(match_key(entry["hero"]))
                if hero_id is None:
                    unknown_heroes.add(entry["hero"])
                    continue

                if all_tier:
                    cursor.execute(
                        "INSERT INTO hero_meta_stats (snapshot_id, hero_id,"
                        " region_id, tier_id, win_rate, pick_rate, source_id)"
                        " VALUES (%s, %s, %s, %s, %s, %s, %s)"
                        " ON CONFLICT (snapshot_id, hero_id, region_id, tier_id)"
                        " DO NOTHING",
                        (snapshot_id, hero_id, region_id, all_tier[0],
                         entry["win_rate"], entry["pick_rate"], source_id),
                    )
                    rates += cursor.rowcount

                for relation in ("countered_by", "counters"):
                    for name in entry[relation]:
                        other_id = hero_ids.get(match_key(name))
                        if other_id is None:
                            unknown_heroes.add(name)
                            continue
                        if other_id == hero_id:
                            continue
                        cursor.execute(
                            "INSERT INTO hero_counters (snapshot_id, hero_id,"
                            " other_id, relation, region_id, source_id)"
                            " VALUES (%s, %s, %s, %s, %s, %s)"
                            " ON CONFLICT DO NOTHING",
                            (snapshot_id, hero_id, other_id, relation,
                             region_id, source_id),
                        )
                        counters += cursor.rowcount

                for position, name in enumerate(entry["best_maps"], start=1):
                    map_id = map_ids.get(match_key(name))
                    if map_id is None:
                        unknown_maps.add(name)
                        continue
                    cursor.execute(
                        "INSERT INTO hero_best_maps (snapshot_id, hero_id, map_id,"
                        " region_id, position, source_id)"
                        " VALUES (%s, %s, %s, %s, %s, %s)"
                        " ON CONFLICT DO NOTHING",
                        (snapshot_id, hero_id, map_id, region_id, position,
                         source_id),
                    )
                    best_maps += cursor.rowcount
        connection.commit()

        pipeline.export_raw(
            connection, args,
            ("hero_meta_stats", "hero_counters", "hero_best_maps"),
        )

    print("\nqueue: %s   input: %s   regions: %d" % (QUEUE, INPUT, len(pages)))
    print("hero rate rows:    %d" % rates)
    print("counter pairings:  %d" % counters)
    print("best map rows:     %d" % best_maps)
    if unknown_heroes:
        print("\n%d names matched no hero: %s"
              % (len(unknown_heroes), ", ".join(sorted(unknown_heroes))))
    if unknown_maps:
        print("\n%d maps outside Open Queue Competitive: %s"
              % (len(unknown_maps), ", ".join(sorted(unknown_maps))))
    if missing_regions:
        print("\nregions not in the database: %s" % ", ".join(sorted(missing_regions)))


if __name__ == "__main__":
    try:
        main()
    except (CounterpickError, FetchError, psycopg.Error,
            requests.RequestException) as error:
        sys.exit("error: %s" % error)
