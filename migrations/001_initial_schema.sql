-- Overwatch DB - initial schema.
--
-- Scope: Open Queue Competitive. Stadium Powers are excluded - they apply only
-- to the Stadium game mode. Gameplay text and numbers only, no lore, no media.
--
-- This migration defines only what every other table depends on. The three
-- domains are created by the migrations that follow, in dependency order:
--
--     002_heroes   heroes, their abilities, weapons, perks and stats
--     003_maps     maps, game modes, and the combinations that are playable
--     004_meta     win/pick/ban rates, playstyles
--
-- Together these four are the baseline. Changes after deployment go in new
-- migrations on top of them rather than editing these.
--
-- Every table carries source_id and cao. source_id says which source the row
-- came from; cao ("current as of") is when it was read. The source URL is held
-- once in `sources` rather than repeated on every row.

BEGIN;

CREATE TABLE sources (
    source_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code      text NOT NULL UNIQUE,
    name      text NOT NULL,
    url       text NOT NULL,
    cao       timestamptz NOT NULL DEFAULT now()
);

-- Seeded here so the vocabulary tables below can reference a source. The
-- pipelines refresh cao whenever they run.
INSERT INTO sources (code, name, url) VALUES
    ('blizzard', 'Blizzard Overwatch site', 'https://overwatch.blizzard.com/en-us/'),
    ('wiki', 'Overwatch Wiki', 'https://overwatch.fandom.com/');

COMMIT;
