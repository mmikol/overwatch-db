"""Ingest pipeline: overwatch.blizzard.com/en-us/rates/ - hero meta statistics.

Loads win, pick and ban rates as a dated snapshot, sliced by region, by skill
tier and by map. The page's filters are server-side query parameters
(role, input, rq, tier, map, region) and it carries its rows as JSON on a
blz-data-table element, so no browser is needed.

Two deliberate restrictions:

  queue  Competitive - Role Queue (rq=1). The page offers no Open Queue; other
         rq values silently fall back to Quick Play. This is the one part of
         the database that is not Open Queue, and the snapshot records it.
  input  Controller (input=Console).

    python -m data.pipeline.load.blizzard.meta --dsn postgresql://...
"""

import sys
from datetime import datetime, timezone

import psycopg
import requests

from data.pipeline import ingest, orchestrator
from data.pipeline.ingest.blizzard import RATES_URL, USER_AGENT
from data.pipeline.extract.blizzard.meta import (
    parse_filter_options,
    parse_rows,
)

REQUEST_DELAY = 1.0
REQUEST_TIMEOUT = 90
RETRIES = 4

QUEUE_PARAM = "1"                      # Competitive - Role Queue
QUEUE_NAME = "competitive_role_queue"
INPUT_PARAM = "Console"                # Controller
INPUT_NAME = "controller"

ALL_TIER = "All"
ALL_REGION = "all"


class RatesError(Exception):
    pass


def fetch(session, params, cache_dir):
    """One rates page for a given filter combination."""
    query = dict(params, rq=QUEUE_PARAM, input=INPUT_PARAM)
    return ingest.cached_get(
        session,
        RATES_URL,
        cache_dir,
        ingest.cache_key("rates", *("%s-%s" % kv for kv in sorted(query.items()))),
        params=query,
        timeout=REQUEST_TIMEOUT,
        retries=RETRIES,
    )


def main():
    parser = orchestrator.build_parser(__doc__, ".cache-rates")
    args = parser.parse_args()

    orchestrator.prepare_cache(args)

    dsn = orchestrator.resolve_dsn(args)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    cao = datetime.now(timezone.utc)

    # The unfiltered page is both the baseline slice and the source of the
    # filter vocabularies.
    baseline = fetch(session, {}, args.cache)
    tiers = parse_filter_options(baseline, "filter-tier-select")
    regions = parse_filter_options(baseline, "filter-region-select")
    maps = [m for m in parse_filter_options(baseline, "filter-map-select")
            if m[0] != "all-maps"]

    with psycopg.connect(dsn) as connection:
        cursor = connection.cursor()
        source_id = orchestrator.register_source(cursor, orchestrator.BLIZZARD, cao)

        region_ids = {}
        for code, name in [(ALL_REGION, "All Regions")] + regions:
            cursor.execute(
                "INSERT INTO regions (code, name, source_id) VALUES (%s, %s, %s)"
                " ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name"
                " RETURNING region_id",
                (code.lower(), name, source_id),
            )
            region_ids[code] = cursor.fetchone()[0]

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
            "INSERT INTO meta_snapshots (captured_at, queue, input, source_id)"
            " VALUES (%s, %s, %s, %s) RETURNING snapshot_id",
            (cao, QUEUE_NAME, INPUT_NAME, source_id),
        )
        snapshot_id = cursor.fetchone()[0]

        hero_ids = orchestrator.lookup_ids(cursor, "heroes", "name", "hero_id")
        map_ids = orchestrator.lookup_ids(cursor, "maps", "name", "map_id")

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

        rows = load_hero_slice(baseline, ALL_REGION, ALL_TIER)

        for code, _ in regions:
            rows += load_hero_slice(
                fetch(session, {"region": code}, args.cache), code, ALL_TIER
            )

        for code, _ in tiers:
            if code == ALL_TIER:
                continue
            rows += load_hero_slice(
                fetch(session, {"tier": code}, args.cache), ALL_REGION, code
            )

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
                    " win_rate, pick_rate, ban_rate, source_id)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s)"
                    " ON CONFLICT (snapshot_id, hero_id, map_id) DO NOTHING",
                    (snapshot_id, hero_id, map_id, win, pick, ban, source_id),
                )
                map_rows += 1
        connection.commit()

        orchestrator.export_raw(
            connection,
            args,
            ("regions", "competitive_tiers", "meta_snapshots", "hero_meta_stats",
             "map_meta_stats"),
        )
        snapshots = cursor.execute("SELECT count(*) FROM meta_snapshots").fetchone()[0]

    print("queue: %s   input: %s" % (QUEUE_NAME, INPUT_NAME))
    print("regions: %d   tiers: %d   maps: %d"
          % (len(region_ids), len(tier_ids), len(maps) - len(skipped_maps)))
    print("hero/region/tier rows: %d" % rows)
    print("hero/map rows:         %d" % map_rows)
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
