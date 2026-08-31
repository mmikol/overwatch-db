-- META: how heroes actually perform, and how they are played.
--
-- Win, pick and ban rates by region, tier and map, plus the team
-- composition playstyles each hero belongs to.
--
-- Depends on heroes (002) and maps (003).

BEGIN;

CREATE TABLE regions (
    region_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code      text NOT NULL UNIQUE,
    name      text NOT NULL UNIQUE,
    source_id integer NOT NULL REFERENCES sources(source_id),
    cao       timestamptz NOT NULL DEFAULT now()
);

-- 'all' is a real member of both dimensions: it is the unfiltered figure the
-- page reports, and keeping it as a row avoids nullable dimension keys.
--
-- Bronze through Champion, plus the "All Tiers" aggregate the source reports
-- alongside them. rank_order follows the source's own ordering.
CREATE TABLE competitive_tiers (
    tier_id    integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code       text NOT NULL UNIQUE,
    name       text NOT NULL UNIQUE,
    rank_order smallint NOT NULL,
    source_id  integer NOT NULL REFERENCES sources(source_id),
    cao        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE meta_snapshots (
    snapshot_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    captured_at timestamptz NOT NULL,
    queue       text NOT NULL,
    input       text NOT NULL,
    source_id   integer NOT NULL REFERENCES sources(source_id),
    cao         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (captured_at, queue, input)
);

-- Rates by region and tier. All rates are percentages as published
-- (47.9 means 47.9%). These rows are across all maps.
CREATE TABLE hero_meta_stats (
    hero_meta_stat_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_id   integer NOT NULL REFERENCES meta_snapshots(snapshot_id) ON DELETE CASCADE,
    hero_id       integer NOT NULL REFERENCES heroes(hero_id) ON DELETE CASCADE,
    region_id     integer NOT NULL REFERENCES regions(region_id),
    tier_id integer NOT NULL REFERENCES competitive_tiers(tier_id),
    win_rate      numeric,
    pick_rate     numeric,
    ban_rate      numeric,
    source_id     integer NOT NULL REFERENCES sources(source_id),
    cao           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (snapshot_id, hero_id, region_id, tier_id)
);

-- Rates per map, across all regions and tiers.
CREATE TABLE map_meta_stats (
    map_meta_stat_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_id integer NOT NULL REFERENCES meta_snapshots(snapshot_id) ON DELETE CASCADE,
    hero_id     integer NOT NULL REFERENCES heroes(hero_id) ON DELETE CASCADE,
    map_id      integer NOT NULL REFERENCES maps(map_id) ON DELETE CASCADE,
    win_rate    numeric,
    pick_rate   numeric,
    ban_rate    numeric,
    source_id   integer NOT NULL REFERENCES sources(source_id),
    cao         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (snapshot_id, hero_id, map_id)
);

CREATE INDEX ix_hero_meta_stats_hero ON hero_meta_stats (hero_id);
CREATE INDEX ix_hero_meta_stats_tier ON hero_meta_stats (tier_id);
CREATE INDEX ix_map_meta_stats_hero ON map_meta_stats (hero_id);
CREATE INDEX ix_map_meta_stats_map ON map_meta_stats (map_id);

CREATE TABLE playstyles (
    playstyle_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code         text NOT NULL UNIQUE,
    name         text NOT NULL UNIQUE,
    source_id    integer NOT NULL REFERENCES sources(source_id),
    cao          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE hero_playstyles (
    hero_id      integer NOT NULL REFERENCES heroes(hero_id) ON DELETE CASCADE,
    playstyle_id integer NOT NULL REFERENCES playstyles(playstyle_id) ON DELETE CASCADE,
    source_id    integer NOT NULL REFERENCES sources(source_id),
    cao          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (hero_id, playstyle_id)
);

CREATE INDEX ix_hero_playstyles_playstyle ON hero_playstyles (playstyle_id);

COMMIT;
