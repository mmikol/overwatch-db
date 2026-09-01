"""Ingest pipeline: overwatch.blizzard.com - heroes.

Scrapes hero, role, subrole, ability and perk data. Blizzard publishes no
numbers and no map data, so weapons, stats and maps come from the wiki.

Loads the PostgreSQL schema defined by migrations/001_ddl_schema.sql.
Scope is Open Queue Competitive: gameplay text only. Stadium Powers are
skipped; perks are included. No lore, no media URLs.

    python -m data.authoritative.s3_load.blizzard.heroes --dsn postgresql://user@localhost/overwatch
    DATABASE_URL=... python -m data.authoritative.s3_load.blizzard.heroes
"""

import re
import sys
from datetime import datetime, timezone

import psycopg
import requests
from bs4 import BeautifulSoup

from data.sources import cache_key, cached_get
from data.authoritative import pipeline
from data.sources.blizzard import BASE_URL, BLIZZARD, HEROES_URL, USER_AGENT
from data.authoritative.s1_extract.blizzard.heroes import (
    parse_abilities,
    parse_perks,
    parse_roster,
    parse_subroles,
)

REQUEST_DELAY = 1.0

ROLE_NAMES = {"tank": "Tank", "damage": "Damage", "support": "Support"}


class ScrapeError(Exception):
    pass


def load(connection, subroles, heroes, abilities_by_slug, perks_by_slug, cao):
    cursor = connection.cursor()
    source_id = pipeline.register_source(cursor, BLIZZARD, cao)

    role_ids = {}
    for code in ("tank", "damage", "support"):
        cursor.execute(
            "INSERT INTO roles (code, name, source_id) VALUES (%s, %s, %s)"
            " ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name,"
            " source_id = EXCLUDED.source_id, cao = now()"
            " RETURNING role_id",
            (code, ROLE_NAMES[code], source_id),
        )
        role_ids[code] = cursor.fetchone()[0]

    subrole_ids = {}
    for subrole in sorted(subroles.values(), key=lambda s: (s["role_code"], s["code"])):
        cursor.execute(
            "INSERT INTO subroles (role_id, code, name, passive_description,"
            " source_id) VALUES (%s, %s, %s, %s, %s)"
            " ON CONFLICT (code) DO UPDATE SET role_id = EXCLUDED.role_id,"
            " name = EXCLUDED.name,"
            " passive_description = EXCLUDED.passive_description,"
            " source_id = EXCLUDED.source_id, cao = now()"
            " RETURNING subrole_id",
            (
                role_ids[subrole["role_code"]],
                subrole["code"],
                subrole["name"],
                subrole["passive_description"],
                source_id,
            ),
        )
        subrole_ids[subrole["code"]] = cursor.fetchone()[0]

    for hero in heroes:
        cursor.execute(
            "INSERT INTO heroes (slug, name, role_id, subrole_id, source_id)"
            " VALUES (%s, %s, %s, %s, %s)"
            " ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name,"
            " role_id = EXCLUDED.role_id, subrole_id = EXCLUDED.subrole_id,"
            " source_id = EXCLUDED.source_id, cao = now()"
            " RETURNING hero_id",
            (
                hero["slug"],
                hero["name"],
                role_ids[hero["role_code"]],
                subrole_ids[hero["subrole_code"]],
                source_id,
            ),
        )
        hero_id = cursor.fetchone()[0]

        for ability in abilities_by_slug[hero["slug"]]:
            cursor.execute(
                # Upserting by name means a RENAMED ability collides with its
                # own old row on (hero_id, position) and fails the stage. That
                # is deliberate: an update refreshes values, and a structural
                # change to a kit is what `rebuild` is for.
                "INSERT INTO abilities (hero_id, name, description, position,"
                " source_id) VALUES (%s, %s, %s, %s, %s)"
                " ON CONFLICT (hero_id, name) DO UPDATE SET"
                " description = EXCLUDED.description,"
                " position = EXCLUDED.position,"
                " source_id = EXCLUDED.source_id, cao = now()",
                (
                    hero_id,
                    ability["name"],
                    ability["description"],
                    ability["position"],
                    source_id,
                ),
            )
        for perk in perks_by_slug[hero["slug"]]:
            cursor.execute(
                "INSERT INTO perks (hero_id, tier_id, name, description, position,"
                " source_id) VALUES (%s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (hero_id, name) DO UPDATE SET"
                " tier_id = EXCLUDED.tier_id,"
                " description = EXCLUDED.description,"
                " position = EXCLUDED.position,"
                " source_id = EXCLUDED.source_id, cao = now()",
                (
                    hero_id,
                    perk["tier_id"],
                    perk["name"],
                    perk["description"],
                    perk["position"],
                    source_id,
                ),
            )

    connection.commit()


def main():
    parser = pipeline.build_parser(__doc__, ".cache-blizzard")
    args = parser.parse_args()

    pipeline.prepare_cache(args)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    roster_soup = BeautifulSoup(cached_get(session, HEROES_URL, args.cache,
                            cache_key(HEROES_URL)), "html.parser")
    subroles = parse_subroles(roster_soup)
    heroes = parse_roster(roster_soup)
    print("roster: %d heroes, %d subroles" % (len(heroes), len(subroles)))

    abilities_by_slug = {}
    perks_by_slug = {}
    for index, hero in enumerate(heroes, start=1):
        slug = hero["slug"]
        url = "%s/heroes/%s/" % (BASE_URL, slug)
        page = cached_get(
            session, url, args.cache, cache_key(slug)
        )
        soup = BeautifulSoup(page, "html.parser")
        abilities_by_slug[slug] = parse_abilities(soup, slug)
        perks_by_slug[slug] = parse_perks(soup, slug)
        print(
            "  [%2d/%d] %-18s %d abilities, %d perks"
            % (index, len(heroes), hero["name"],
               len(abilities_by_slug[slug]), len(perks_by_slug[slug]))
        )

    cao = datetime.now(timezone.utc)
    dsn = pipeline.resolve_dsn(args)
    with psycopg.connect(dsn) as connection:
        load(connection, subroles, heroes, abilities_by_slug, perks_by_slug, cao)
        pipeline.export_raw(
            connection, args, ("roles", "subroles", "heroes", "abilities", "perks")
        )

    print("loaded into %s" % re.sub(r"//[^@/]*@", "//", dsn))
    print("\nRun wiki.heroes next: it classifies these abilities and adds"
          "\nthe ones Blizzard does not publish.")


if __name__ == "__main__":
    try:
        main()
    except (ScrapeError, psycopg.Error, requests.RequestException) as error:
        sys.exit("error: %s" % error)
