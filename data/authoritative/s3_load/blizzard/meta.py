"""Ingest pipeline: overwatch.blizzard.com/en-us/rates/ - hero meta statistics.

Loads win, pick and ban rates as a dated snapshot, sliced by skill tier and by
map. The page's filters are server-side query parameters (role, input, rq,
tier, map, region) and it carries its rows as JSON on a blz-data-table
element, so no browser is needed.

Three deliberate restrictions:

  queue   Competitive - Role Queue (rq=1). The page offers no Open Queue; other
          rq values silently fall back to Quick Play. This is the one part of
          the database that is not Open Queue, and the snapshot records it.
  platform  Console (the parameter is spelled input=Console).
  region  Americas, on every request including the baseline. The source offers
          Americas, Asia and Europe and nothing narrower, so this is as close
          to the United States as it can be scoped. Nothing here is a
          multi-region aggregate.

    python -m data.authoritative.s3_load.blizzard.meta --dsn postgresql://...
"""

import sys
from datetime import datetime, timezone

import psycopg
import requests

from data.sources import cache_key, cached_get
from data.authoritative import pipeline
from data.sources.blizzard import BLIZZARD, RATES_URL, USER_AGENT
from data.authoritative.s1_extract.blizzard.meta import (
    parse_filter_options,
    parse_rows,
)

# ~280 sequential pages is more load than the source will take. It answers 504
# first, then stops answering at all and closes the connection. So this stage
# is deliberately slow and stubborn: a jittered gap between requests, and a
# long climbing wait before it gives up on one. Slower here is faster overall,
# because being cut off costs the whole stage.
REQUEST_DELAY = 5.0
REQUEST_TIMEOUT = 90
RETRIES = 6
RETRY_BACKOFF = 5.0

QUEUE_PARAM = "1"                      # Competitive - Role Queue
QUEUE_NAME = "competitive_role_queue"
# The source's query parameter is spelled "input", but it selects a platform:
# its two values are PC and Console. What it is called and what it means differ,
# so the parameter keeps the source's spelling and the column keeps the meaning.
INPUT_PARAM = "Console"
PLATFORM_NAME = "console"
# Derived, not published: console Overwatch supports no input but a
# controller, so the console platform pins the device. A PC snapshot would
# leave this NULL - that population mixes controller and mouse-and-keyboard.
INPUT_DEVICE = "controller"

ALL_TIER = "All"

# Every figure in this database is the Americas. The source offers Americas,
# Asia and Europe and nothing narrower - there is no United States filter - so
# Americas is the closest it can be scoped, and it takes in Canada and Latin
# America as well. There is deliberately no unfiltered "all regions" figure any
# more: mixing three populations into one row made a number nobody plays under.
REGION_PARAM = "Americas"
REGION_CODE = "americas"
REGION_NAME = "Americas"


class RatesError(Exception):
    pass


def fetch(session, params, cache_dir):
    """One rates page for a given filter combination."""
    query = dict(params, rq=QUEUE_PARAM, input=INPUT_PARAM,
                 region=REGION_PARAM)
    return cached_get(
        session,
        RATES_URL,
        cache_dir,
        cache_key("rates", *("%s-%s" % kv for kv in sorted(query.items()))),
        params=query,
        timeout=REQUEST_TIMEOUT,
        retries=RETRIES,
        delay=REQUEST_DELAY,
        backoff=RETRY_BACKOFF,
    )


def main():
    parser = pipeline.build_parser(__doc__, ".cache-blizzard")
    args = parser.parse_args()

    pipeline.prepare_cache(args)

    dsn = pipeline.resolve_dsn(args)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    cao = datetime.now(timezone.utc)

    # The region-filtered page with no other filter is both the baseline slice
    # and the source of the tier and map vocabularies.
    baseline = fetch(session, {}, args.cache)
    tiers = parse_filter_options(baseline, "filter-tier-select")
    maps = [m for m in parse_filter_options(baseline, "filter-map-select")
            if m[0] != "all-maps"]

    with psycopg.connect(dsn) as connection:
        cursor = connection.cursor()
        source_id = pipeline.register_source(cursor, BLIZZARD, cao)

        cursor.execute(
            "INSERT INTO regions (code, name, source_id) VALUES (%s, %s, %s)"
            " ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name"
            " RETURNING region_id",
            (REGION_CODE, REGION_NAME, source_id),
        )
        region_ids = {REGION_CODE: cursor.fetchone()[0]}

        tier_ids = {}
        for order, (code, name) in enumerate(tiers):
            cursor.execute(
                "INSERT INTO competitive_tiers (code, name, rank_order, source_id)"
                " VALUES (%s, %s, %s, %s)"
                " ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name,"
                " rank_order = EXCLUDED.rank_order RETURNING tier_id",
                (code.lower(), name, order, source_id),
            )
            tier_ids[code] = cursor.fetchone()[0]

        cursor.execute(
            "INSERT INTO meta_snapshots (captured_at, queue, platform, input, source_id)"
            " VALUES (%s, %s, %s, %s, %s) RETURNING snapshot_id",
            (cao, QUEUE_NAME, PLATFORM_NAME, INPUT_DEVICE, source_id),
        )
        snapshot_id = cursor.fetchone()[0]

        hero_ids = pipeline.lookup_ids(cursor, "heroes", "name", "hero_id")
        map_ids = pipeline.lookup_ids(cursor, "maps", "name", "map_id")

        unmatched = set()

        def load_hero_slice(html, region_code, tier_code):
            written = 0
            for name, win, pick, ban in parse_rows(html):
                hero_id = hero_ids.get(name.lower())
                if hero_id is None:
                    unmatched.add(name)
                    continue
                cursor.execute(
                    "INSERT INTO hero_meta_stats (snapshot_id, hero_id, region_id,"
                    " tier_id, win_rate, pick_rate, ban_rate, source_id)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
                    " ON CONFLICT (snapshot_id, hero_id, region_id, tier_id)"
                    " DO NOTHING",
                    (snapshot_id, hero_id, region_ids[region_code],
                     tier_ids[tier_code], win, pick, ban, source_id),
                )
                written += 1
            return written

        # The baseline page is already the Americas, so it is this region's
        # figure across all tiers rather than a global one.
        rows = load_hero_slice(baseline, REGION_CODE, ALL_TIER)

        for code, _ in tiers:
            if code == ALL_TIER:
                continue
            rows += load_hero_slice(
                fetch(session, {"tier": code}, args.cache), REGION_CODE, code
            )

        # Per map, across all ranks. The source's filters compose, so map and
        # tier could be crossed to get a hero's rates on one map in Bronze -
        # and that is real signal, not noise: Widowmaker swings some fifteen
        # points between Bronze and Grandmaster on a single map, which the
        # all-ranks figure averages into an unremarkable middle.
        #
        # It is not fetched, because it costs 30 maps x 9 tiers = 270 requests
        # against 30, and the source starts refusing connections well before
        # the end of a sweep that size. Rows still carry tier_id, set to the
        # all-ranks tier, so crossing them later needs no migration - only the
        # inner loop back.
        map_rows, skipped_maps = 0, []
        for slug, label in maps:
            map_id = map_ids.get(label.lower())
            if map_id is None:
                skipped_maps.append(label)
                continue
            for name, win, pick, ban in parse_rows(
                fetch(session, {"map": slug}, args.cache)
            ):
                hero_id = hero_ids.get(name.lower())
                if hero_id is None:
                    unmatched.add(name)
                    continue
                cursor.execute(
                    "INSERT INTO map_meta_stats (snapshot_id, hero_id, map_id,"
                    " tier_id, region_id, stage_id, win_rate, pick_rate,"
                    " ban_rate, source_id)"
                    " VALUES (%s, %s, %s, %s, %s, NULL, %s, %s, %s, %s)"
                    " ON CONFLICT (snapshot_id, hero_id, map_id, tier_id,"
                    " region_id, stage_id) DO NOTHING",
                    (snapshot_id, hero_id, map_id, tier_ids[ALL_TIER],
                     region_ids[REGION_CODE], win, pick, ban, source_id),
                )
                map_rows += 1
        connection.commit()

        pipeline.export_raw(
            connection,
            args,
            ("regions", "competitive_tiers", "meta_snapshots", "hero_meta_stats",
             "map_meta_stats"),
        )
        snapshots = cursor.execute("SELECT count(*) FROM meta_snapshots").fetchone()[0]

    print("queue: %s   platform: %s" % (QUEUE_NAME, PLATFORM_NAME))
    print("regions: %d   tiers: %d   maps: %d"
          % (len(region_ids), len(tier_ids), len(maps) - len(skipped_maps)))
    print("hero/region/tier rows: %d" % rows)
    print("hero/map/tier rows:    %d" % map_rows)
    print("snapshots held:        %d" % snapshots)
    if unmatched:
        print("\n%d names matched no hero: %s" % (len(unmatched), ", ".join(sorted(unmatched))))
    if skipped_maps:
        print("\n%d maps outside Open Queue Competitive scope: %s"
              % (len(skipped_maps), ", ".join(skipped_maps)))


if __name__ == "__main__":
    try:
        main()
    except (RatesError, psycopg.Error, requests.RequestException) as error:
        sys.exit("error: %s" % error)
