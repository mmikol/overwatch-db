-- PLAYBOOK: judgements about the game, on top of the measurements.
--
-- Nothing in this file is a count of matches. These tables hold what someone
-- concluded: which playstyle a hero belongs to (the wiki), who answers whom
-- and where a hero is strongest (counterpick.gg), and which heroes work
-- together (hero_synergies - ours, hand-authored in data/proprietary, the
-- one table here a rebuild cannot re-scrape and the repo must therefore
-- carry).
--
-- Depends on heroes (002), maps (003) and meta_snapshots (004).

BEGIN;




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
-- Proprietary, not scraped: no site we accept publishes synergies, so these
-- are hand-authored in data/proprietary/synergies.csv and loaded from there.
-- That provenance shapes the table. There is no snapshot, region or tier,
-- because an authored judgement has no population behind it - it is our read
-- of the game as a whole, like the wiki's playstyles, not a measurement of
-- anyone's matches.
--
-- Ordered pairs, never folded: (a, b) and (b, a) are separate claims, and a
-- deliberate asymmetry ("Ana enables Baptiste more than he enables her") is
-- expressible. score is whatever scale the author keeps consistently;
-- note carries the reasoning, which is the part a model actually wants.
CREATE TABLE hero_synergies (
    hero_id   integer NOT NULL REFERENCES heroes(hero_id) ON DELETE CASCADE,
    other_id  integer NOT NULL REFERENCES heroes(hero_id) ON DELETE CASCADE,
    score     smallint,
    note      text,
    source_id integer NOT NULL REFERENCES sources(source_id),
    cao       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (hero_id, other_id),
    CHECK (hero_id <> other_id)
);


CREATE INDEX ix_hero_counters_other ON hero_counters (other_id);
CREATE INDEX ix_hero_best_maps_map ON hero_best_maps (map_id);
CREATE INDEX ix_hero_synergies_other ON hero_synergies (other_id);

COMMIT;
