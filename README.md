# overwatch-db

A PostgreSQL database of Overwatch gameplay data, scraped and normalized for
analysis. Scope is **Open Queue Competitive**.

The model is three domains that intersect:

```
COUNTER = MAX[ HEROES ∩ MAPS ∩ META ]

HEROES  weapons, abilities, perks, roles
MAPS    modes
META    style, hero W/L, map W/L
```

## Running it

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m orchestrator rebuild
```

That is the whole bootstrap: with no flags the orchestrator builds an embedded
Postgres at `db/cluster` (pgserver runs initdb on first touch), applies the
migrations, and runs every pipeline in dependency order. `--dsn` or
`DATABASE_URL` point it at your own server instead.

The verbs, in the order a database lives through them — each refuses the
state it is not for, and names the verb you wanted:

| command | does |
| --- | --- |
| `-m orchestrator init` | schema into an empty database, no data |
| `-m orchestrator inflate` | first fill: every pipeline (refuses a populated db) |
| `-m orchestrator` | update (default): reload — refreshes entities, appends snapshots |
| `-m orchestrator rebuild` | clean slate: drop, migrate, run everything |
| `-m orchestrator export` | refresh `data/raw/*.csv` |
| `-m orchestrator --type heuristic` | update one type of data (repeatable) |
| `-m orchestrator --only heuristic.wiki.meta` | update one stage (repeatable) |

`update` accumulates: entity tables refresh in place, while each meta run adds
a dated snapshot beside the old ones. `rebuild` is the ground truth for
structural change (a renamed ability, a removed hero) and always runs
everything — a partial rebuild is how one type of data would wipe another.

Pages are cached under `.cache*/`, so re-runs cost no requests. Delete a cache
directory to force a refetch.

## Layout

```
orchestrator.py      the conductor, above db/ and data/: the verbs and the
                     plumbing every pipeline stage shares

data/
  sources/           where scraped data comes from; the scraping types share it
                     blizzard.py  wiki.py  counterpick.py
                     Each module fetches its pages and declares its own
                     `sources` row.

  authoritative/     what a source measured — cooldowns, health, win rates
    pipeline.py      the type: its stage order
    extract/         blizzard/ markup  heroes  meta
                     wiki/     markup  heroes  maps
    transform/       wiki/     measurements  names  weapons  modifiers
    load/            blizzard/ heroes  meta
                     wiki/     heroes  maps

  heuristic/         what a source judges — playstyles, who answers whom
    pipeline.py
    extract/         wiki/        meta      counterpick/ heroes
    transform/       counterpick/ names
    load/            wiki/        meta      counterpick/ heroes

  proprietary/       what WE judge — synergies.csv (authored, committed),
    pipeline.py      loaded by load/user/synergies.py. The one input a
                     rebuild cannot re-scrape, so the repo is its backup.

  raw/               exported CSVs, one per table (gitignored)

db/
  migrations/        001 sources · 002 heroes · 003 maps · 004 meta ·
                     005 playbook — meta holds measurements only; the
                     judgements live in playbook. Within a file, a table is a
                     table: source_id says whose claim each row is.
  cluster/           the built database: an embedded Postgres data directory
                     (Postgres has no single-file format). A build artifact —
                     `rebuild` reproduces it — so gitignored, not committed.

docs/                erd.md · data-dictionary.md · scaling.md · model.key
```

## Sources and precedence

Blizzard first; the wiki fills gaps; anything neither publishes stays NULL.

| source | supplies |
| --- | --- |
| `overwatch.blizzard.com` | roster, roles, subroles, ability and perk text |
| `overwatch.blizzard.com/en-us/rates/` | win / pick / ban rates |
| `overwatch.fandom.com` (Cargo) | every number, weapons, maps, playstyles |
| `counterpickgg.com` | hero counters, best maps, rates by region (competitive, console) |
| `data/proprietary/synergies.csv` | hero synergies — hand-authored, the `user` source |

Blizzard's hero pages are marketing content, not a gameplay reference: they
publish **no numbers at all**, and omit abilities outright (Cassidy's
Flashbang, Mauga's and Freja's weapons). The wiki's Cargo tables supply those,
plus an explicit `removed` flag that separates current kit from retired kit.

A few template parameters are never registered as Cargo fields — notably the
`ignores_*` interaction flags, which decide counters. Those are read from
article wikitext in a supplementary pass.

## Things worth knowing

**META is Role Queue.** Blizzard's rates page offers only Quick Play and
Competitive *Role Queue*; there is no Open Queue anywhere, and no other source
publishes it. Every other table is Open Queue. `meta_snapshots.queue` records
this rather than letting it be assumed away. Input is restricted to Controller.

**META is the Americas.** Every rate is the Americas region and nothing is a
multi-region aggregate — there is no "all regions" row, because mixing three
populations produces a number nobody plays under. Americas is the narrowest
scope on offer: the source publishes Americas, Asia and Europe and nothing
smaller, so this is as close to the United States as it can be taken, and it
includes Canada and Latin America. The region is applied to every request,
including the baseline page the map and tier vocabularies are read from.

Every meta row states its own scope: `map_meta` carries `region_id` (and a
`stage_id`, NULL until any source publishes per-stage rates), so nothing is
implied by the database that is not written on the row.

**A snapshot is a population.** `meta_snapshots` is what makes two sources
safely share one table. `hero_meta` holds rows from both Blizzard and
counterpick.gg, and they are not the same measurement:

| source | queue | platform | input |
| --- | --- | --- | --- |
| blizzard | `competitive_role_queue` | `console` | `controller` |
| counterpick | `competitive_unspecified_queue` | `console` | `controller` |

`platform` is not the input device — Blizzard's query parameter is spelled
`input` but its values are PC and Console. On console the device follows
anyway: console Overwatch supports no input except a controller, so
`input = controller` is a derivation, not a guess. A future PC snapshot leaves
`input` NULL, because that population mixes controller and mouse-and-keyboard
and no source separates them. See [docs/scaling.md](docs/scaling.md).

Without the snapshot those rows would be indistinguishable, and a query would
average a role-queue win rate against a figure of unknown queue as though
they were one number. The snapshot keeps them separable.

History is opt-in. `rebuild` drops everything and leaves one snapshot per
source — the current patch, cleanly. Repeated `update` runs add dated
snapshots beside the old ones, so a series accumulates for as long as you
update without rebuilding. Readings never captured remain unrecoverable.


**Every row carries `source_id` and `cao`** ("current as of"). The source URL
lives once in `sources`.

**Stats are one row per measurement, not per stat.** A wiki value like
`0.67 shots/s (max charge); 3.33 shots/s (min charge)` becomes two rows sharing
a `stat_key`, separated by `condition`. Units are split into the unit on top
and the unit underneath, so nothing has to parse a `/`:

```
"125 m/s"              -> 125   meters  / seconds   denominator_value 1
"1.25 shots/s"         -> 1.25  shots   / seconds   denominator_value 1
"75 over 0.59 seconds" -> 75    hp      / seconds   denominator_value 0.59
"14 seconds"           -> 14    seconds / NULL
```

A rate is always `value / denominator_value` per `unit_denominator`.
`denominator_value` exists because 41 measurements span a window that is not
one second - a burst that deals 75 over 0.59s is not 75 per second, and
normalising it away would turn a published total into a derived rate.

`value_text` and `raw_value` keep the source strings, so anything the parser
misreads stays recoverable.

**Weapons have configs.** Ana carries one Biotic Rifle fired two ways, so
firing modes are `weapon_configs`, not separate weapons. `weapon_type` lives on
the config because it varies by mode — her hip fire is a projectile, her ADS is
hitscan.

**Not included:** Stadium Powers and Stadium maps (a different mode), Clash
maps (the wiki files them under *former* standard play), lore, and all media.

## Open

- **`hero_synergies` is authored, and currently empty.** No acceptable site
  publishes synergies, so they are ours: rows written into
  `data/proprietary/synergies.csv` load on the next run, and the file is the
  whole truth — the table mirrors it exactly. Author it to close the playbook.
- **The inference layer** — strategies in, cited team comps out — is
  documented in `data/proprietary/README.md` and not yet built.
- No per-region or per-tier Open Queue data exists to be had.
