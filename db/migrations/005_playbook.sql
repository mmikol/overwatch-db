-- PLAYBOOK: judgements about the game, on top of the measurements.
--
-- Nothing in this file is a count of matches. Four tables, four judgements:
-- which playstyle a hero belongs to (the wiki), who answers whom
-- (counterpick.gg), where a hero is strongest (counterpick.gg), and which
-- heroes work together (synergies - ours, hand-authored in data/proprietary,
-- the one table here a rebuild cannot re-scrape and the repo must carry).
--
-- Depends on heroes (002), maps (003) and meta_snapshots (004).

BEGIN;

-- Which playstyle a hero belongs to, straight from the wiki's team
-- composition page. The style vocabulary (dive, brawl, poke) is whatever the
-- page says, kept as text rather than a three-row lookup table: the page is
-- the vocabulary, and a new style there should load, not break.
CREATE TABLE playstyle (
    hero_id   integer NOT NULL REFERENCES heroes(hero_id) ON DELETE CASCADE,
    style     text NOT NULL,
    source_id integer NOT NULL REFERENCES sources(source_id),
    cao       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (hero_id, style)
);

-- Who answers whom. The two directions are stored separately because the
-- source does not treat them as inverses: of 354 pairings it publishes, 114
-- appear in one direction only, so "X is countered by Y" and "Y counters X"
-- are two judgements rather than one fact seen twice.
--
-- Beware the source's own naming: its field called `counters` is displayed
-- as "Countered by". The direction stored here follows the columns as
-- labelled and explained by their tooltips, not the field names.
CREATE TABLE counters (
    snapshot_id integer NOT NULL REFERENCES meta_snapshots(snapshot_id) ON DELETE CASCADE,
    hero_id     integer NOT NULL REFERENCES heroes(hero_id) ON DELETE CASCADE,
    other_id    integer NOT NULL REFERENCES heroes(hero_id) ON DELETE CASCADE,
    relation    text NOT NULL CHECK (relation IN ('countered_by', 'counters')),
    region_id   integer NOT NULL REFERENCES regions(region_id),
    tier_id     integer NOT NULL REFERENCES competitive_tiers(tier_id),
    source_id   integer NOT NULL REFERENCES sources(source_id),
    cao         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_id, region_id, tier_id, hero_id, other_id, relation),
    CHECK (hero_id <> other_id)
);

-- The maps a hero is strongest on, best first. The source ranks them but
-- publishes no per-map figure, so position is the whole of what it says.
CREATE TABLE map_strategy (
    snapshot_id integer NOT NULL REFERENCES meta_snapshots(snapshot_id) ON DELETE CASCADE,
    hero_id     integer NOT NULL REFERENCES heroes(hero_id) ON DELETE CASCADE,
    map_id      integer NOT NULL REFERENCES maps(map_id) ON DELETE CASCADE,
    region_id   integer NOT NULL REFERENCES regions(region_id),
    tier_id     integer NOT NULL REFERENCES competitive_tiers(tier_id),
    position    smallint NOT NULL,
    source_id   integer NOT NULL REFERENCES sources(source_id),
    cao         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_id, region_id, tier_id, hero_id, map_id)
);

-- Which heroes work WITH which. Proprietary, not scraped: hand-authored in
-- data/proprietary/synergies.csv. No snapshot, region or tier, because an
-- authored judgement has no population behind it. Ordered pairs, never
-- folded: (a, b) and (b, a) are separate claims. score is whatever scale the
-- author keeps consistently; note carries the reasoning, which is the part a
-- model actually wants.
CREATE TABLE synergies (
    hero_id   integer NOT NULL REFERENCES heroes(hero_id) ON DELETE CASCADE,
    other_id  integer NOT NULL REFERENCES heroes(hero_id) ON DELETE CASCADE,
    score     smallint,
    note      text,
    source_id integer NOT NULL REFERENCES sources(source_id),
    cao       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (hero_id, other_id),
    CHECK (hero_id <> other_id)
);


CREATE INDEX ix_counters_other ON counters (other_id);
CREATE INDEX ix_map_strategy_map ON map_strategy (map_id);
CREATE INDEX ix_synergies_other ON synergies (other_id);

COMMIT;
