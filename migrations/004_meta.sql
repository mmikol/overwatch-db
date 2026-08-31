-- META: how heroes actually perform, and what that is taken to mean.
--
-- Two kinds of claim live here. The rates are measurements - win, pick and
-- ban by region, tier and map. The playstyles and the playbook are
-- judgements: which playstyle a hero suits, which hero answers which, where a
-- hero is strongest. Nobody measures those; they move with a community's read
-- of the meta rather than with a patch, and two sources can disagree without
-- either being wrong.
--
-- Every table carries source_id, so a query that cares about the difference
-- can filter on where the row came from.
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

-- 'all' is a real member of the tier dimension: it is the unfiltered figure
-- the page reports, and keeping it as a row avoids a nullable dimension key.
-- Region has no such member. Everything here is the Americas, so an "all
-- regions" row would be a second population mixed in beside it.
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

-- Rates per map, and per tier within a map. The source's filters compose, so
-- a hero's rates on King's Row in Bronze are a different figure from the same
-- hero's rates on King's Row overall - and both are published.
--
-- tier_id 'all' is the unfiltered figure for that map, which keeps the
-- dimension key non-nullable. Region is not broken out here: map x tier is
-- already 240 requests, and map x tier x region would be 720.
CREATE TABLE map_meta_stats (
    map_meta_stat_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_id integer NOT NULL REFERENCES meta_snapshots(snapshot_id) ON DELETE CASCADE,
    hero_id     integer NOT NULL REFERENCES heroes(hero_id) ON DELETE CASCADE,
    map_id      integer NOT NULL REFERENCES maps(map_id) ON DELETE CASCADE,
    tier_id     integer NOT NULL REFERENCES competitive_tiers(tier_id),
    win_rate    numeric,
    pick_rate   numeric,
    ban_rate    numeric,
    source_id   integer NOT NULL REFERENCES sources(source_id),
    cao         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (snapshot_id, hero_id, map_id, tier_id)
);

CREATE INDEX ix_hero_meta_stats_hero ON hero_meta_stats (hero_id);
CREATE INDEX ix_hero_meta_stats_tier ON hero_meta_stats (tier_id);
CREATE INDEX ix_map_meta_stats_hero ON map_meta_stats (hero_id);
CREATE INDEX ix_map_meta_stats_map ON map_meta_stats (map_id);
CREATE INDEX ix_map_meta_stats_tier ON map_meta_stats (tier_id);



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


-- PLAYBOOK: which heroes answer which, and where each hero is strongest.
--
-- The two directions are stored separately because the source does not treat
-- them as inverses. Of 354 pairings it publishes, 114 appear in one direction
-- only, so "X is countered by Y" and "Y counters X" are two judgements rather
-- than one fact seen twice.
--
-- Beware the source's own naming: its field called `counters` is displayed as
-- "Countered by". The direction stored here follows the columns as labelled
-- and explained by their tooltips, not the field names.
CREATE TABLE hero_counters (
    snapshot_id integer NOT NULL REFERENCES meta_snapshots(snapshot_id) ON DELETE CASCADE,
    hero_id     integer NOT NULL REFERENCES heroes(hero_id) ON DELETE CASCADE,
    other_id    integer NOT NULL REFERENCES heroes(hero_id) ON DELETE CASCADE,
    relation    text NOT NULL CHECK (relation IN ('countered_by', 'counters')),
    region_id   integer NOT NULL REFERENCES regions(region_id),
    source_id   integer NOT NULL REFERENCES sources(source_id),
    cao         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_id, region_id, hero_id, other_id, relation),
    CHECK (hero_id <> other_id)
);

-- The maps a hero is strongest on, best first. The source ranks them but
-- publishes no per-map figure, so position is the whole of what it says.
CREATE TABLE hero_best_maps (
    snapshot_id integer NOT NULL REFERENCES meta_snapshots(snapshot_id) ON DELETE CASCADE,
    hero_id     integer NOT NULL REFERENCES heroes(hero_id) ON DELETE CASCADE,
    map_id      integer NOT NULL REFERENCES maps(map_id) ON DELETE CASCADE,
    region_id   integer NOT NULL REFERENCES regions(region_id),
    position    smallint NOT NULL,
    source_id   integer NOT NULL REFERENCES sources(source_id),
    cao         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_id, region_id, hero_id, map_id)
);


CREATE INDEX ix_hero_counters_other ON hero_counters (other_id);
CREATE INDEX ix_hero_best_maps_map ON hero_best_maps (map_id);

COMMIT;
