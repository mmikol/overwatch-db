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
DATABASE_URL=postgresql://user@localhost/overwatch .venv/bin/python -m data.pipeline.orchestrator
```

`orchestrator` runs the five pipelines in dependency order. The order matters and
running them out of order does not error — it quietly produces a partial
database — so prefer it over invoking pipelines by hand.

No PostgreSQL to hand? `pip install pgserver` and pass `--local-server pgdata`
to run against an embedded server.

| command | does |
| --- | --- |
| `-m data.pipeline.orchestrator` | every stage, correct order |
| `-m data.pipeline.orchestrator --only wiki.maps` | one stage (repeatable) |
| `-m data.pipeline.orchestrator schema --reset` | rebuild the schema, load nothing |
| `-m data.pipeline.orchestrator export` | refresh `data/raw/*.csv` |

Pages are cached under `.cache*/`, so re-runs cost no requests. Delete a cache
directory to force a refetch.

## Layout

```
migrations/          001 initial · 002 heroes · 003 maps · 004 meta
data/pipeline/
  orchestrator.py    runs the stages, owns schema + export + shared CLI
  ingest/            blizzard.py  wiki.py       acquire pages, cache them
  extract/           blizzard/ markup  heroes  meta
                     wiki/     markup  heroes  maps  meta
  transform/         wiki/     measurements  names  weapons  modifiers
  load/              blizzard/ heroes  meta
                     wiki/     heroes  maps  meta
data/raw/            exported CSVs, one per table (gitignored)
docs/                erd.md · data-dictionary.md · model.key
```

## Sources and precedence

Blizzard first; the wiki fills gaps; anything neither publishes stays NULL.

| source | supplies |
| --- | --- |
| `overwatch.blizzard.com` | roster, roles, subroles, ability and perk text |
| `overwatch.blizzard.com/en-us/rates/` | win / pick / ban rates |
| `overwatch.fandom.com` (Cargo) | every number, weapons, maps, playstyles |

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

**META is a time series.** A win rate is true of a patch, not of a hero. Each
run writes a dated snapshot; readings not captured as they happen cannot be
recovered.


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

- **PLAYBOOK** in the model has no identified source.
- No per-region or per-tier Open Queue data exists to be had.
