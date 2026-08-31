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
    -- Platform, not input device. The source's query parameter is called
    -- "input" but its values are PC and Console, which say nothing about
    -- whether a controller or a mouse was held - both platforms support both.
    -- Recording it as an input device would assert something no source states.
    platform    text NOT NULL,
    -- The device in the player's hands, which is not the same thing as the
    -- platform - but on console it is derivable: console Overwatch supports
    -- no input except a controller, so platform = console entails
    -- input = controller, and both current sources are console. NULL is for
    -- populations where the device genuinely is not knowable - a PC snapshot
    -- mixes controller and mouse-and-keyboard players, and no source
    -- separates them.
    input       text,
    source_id   integer NOT NULL REFERENCES sources(source_id),
    cao         timestamptz NOT NULL DEFAULT now(),
    UNIQUE NULLS NOT DISTINCT (captured_at, queue, platform, input)
);

-- Rates by region and tier. All rates are percentages as published
-- (47.9 means 47.9%). These rows are across all maps.
CREATE TABLE hero_meta_stats (
    hero_meta_stat_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_id   integer NOT NULL REFERENCES meta_snapshots(snapshot_id) ON DELETE CASCADE,
    hero_id       integer NOT NULL REFERENCES heroes(hero_id) ON DELETE CASCADE,
    region_id     integer NOT NULL REFERENCES regions(region_id),
    tier_id       integer NOT NULL REFERENCES competitive_tiers(tier_id),
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
    region_id   integer NOT NULL REFERENCES regions(region_id),
    -- NULL means the whole map, which is every row today. See map_stages.
    stage_id    integer REFERENCES map_stages(stage_id) ON DELETE CASCADE,
    win_rate    numeric,
    pick_rate   numeric,
    ban_rate    numeric,
    source_id   integer NOT NULL REFERENCES sources(source_id),
    cao         timestamptz NOT NULL DEFAULT now(),
    -- NULLS NOT DISTINCT so two whole-map rows collide as they should:
    -- by default Postgres treats NULL stage_id as always unique, which would
    -- let the same hero/map/tier be inserted twice.
    UNIQUE NULLS NOT DISTINCT
        (snapshot_id, hero_id, map_id, tier_id, region_id, stage_id)
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
    -- The rank these judgements are about. The source does not vary by rank,
    -- so every row is the all-ranks tier; the column is here so one that does
    -- can be loaded without a migration.
    tier_id     integer NOT NULL REFERENCES competitive_tiers(tier_id),
    source_id   integer NOT NULL REFERENCES sources(source_id),
    cao         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_id, region_id, tier_id, hero_id, other_id, relation),
    CHECK (hero_id <> other_id)
);

-- The maps a hero is strongest on, best first. The source ranks them but
-- publishes no per-map figure, so position is the whole of what it says.
CREATE TABLE hero_best_maps (
    snapshot_id integer NOT NULL REFERENCES meta_snapshots(snapshot_id) ON DELETE CASCADE,
    hero_id     integer NOT NULL REFERENCES heroes(hero_id) ON DELETE CASCADE,
    map_id      integer NOT NULL REFERENCES maps(map_id) ON DELETE CASCADE,
    region_id   integer NOT NULL REFERENCES regions(region_id),
    -- The rank these judgements are about. The source does not vary by rank,
    -- so every row is the all-ranks tier; the column is here so one that does
    -- can be loaded without a migration.
    tier_id     integer NOT NULL REFERENCES competitive_tiers(tier_id),
    position    smallint NOT NULL,
    source_id   integer NOT NULL REFERENCES sources(source_id),
    cao         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_id, region_id, tier_id, hero_id, map_id)
);

-- The other half of the playbook: which heroes work WITH which.
--
-- Defined but not yet loaded. counterpick.gg publishes counters and best maps
-- but no synergies, and no second source has been chosen, so nothing writes
-- here and hero_synergies.csv exports with a header and no rows. That is
-- expected, not a broken pipeline.
--
-- Shaped to mirror hero_counters so the two can be read side by side, with
-- two deliberate choices carried over from it:
--
--   Ordered pairs. (a, b) and (b, a) are separate rows, never folded into
--   one. A source that scores "Ana with Baptiste" differently from "Baptiste
--   with Ana" is making two claims, and averaging them invents a third that
--   nobody published.
--
--   score is nullable, because sources disagree about what a synergy even is:
--   some publish a signed number, others only a ranked list. A source that
--   ranks without scoring records the pairing and leaves score NULL rather
--   than inventing a figure.
CREATE TABLE hero_synergies (
    snapshot_id integer NOT NULL REFERENCES meta_snapshots(snapshot_id) ON DELETE CASCADE,
    hero_id     integer NOT NULL REFERENCES heroes(hero_id) ON DELETE CASCADE,
    other_id    integer NOT NULL REFERENCES heroes(hero_id) ON DELETE CASCADE,
    region_id   integer NOT NULL REFERENCES regions(region_id),
    -- The rank these judgements are about. The source does not vary by rank,
    -- so every row is the all-ranks tier; the column is here so one that does
    -- can be loaded without a migration.
    tier_id     integer NOT NULL REFERENCES competitive_tiers(tier_id),
    score       smallint,
    source_id   integer NOT NULL REFERENCES sources(source_id),
    cao         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_id, region_id, tier_id, hero_id, other_id),
    CHECK (hero_id <> other_id)
);


CREATE INDEX ix_hero_counters_other ON hero_counters (other_id);
CREATE INDEX ix_hero_best_maps_map ON hero_best_maps (map_id);
CREATE INDEX ix_hero_synergies_other ON hero_synergies (other_id);

COMMIT;
