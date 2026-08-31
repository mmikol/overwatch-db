# Scaling the meta's granularity

Everything here is about the *fact* tables — the ones holding rates and
playbook rows. Hero kits, weapons, maps and modes have no such dimensions: a
cooldown is a cooldown in every region, on every platform, at every rank.

## The one structural fact that makes this cheap

**Every run drops the database and reapplies the migrations from scratch.**
Stage 1 calls `rebuild()` before it loads anything. So adding a dimension is
never a data migration — there is no data to migrate. It is an edit to
`004_meta.sql`, an edit to one loader, and a refetch.

That means the schema is *not* the constraint on any of this. The constraint is
the request count, and it is multiplicative.

## Where each dimension stands

| dimension | column exists? | populated today | to widen it |
| --- | --- | --- | --- |
| tier — `hero_meta_stats` | yes | 9 ranks | already there |
| tier — `map_meta_stats` | yes | all-ranks only | restore the inner loop; ×9 requests |
| region — `hero_meta_stats` | yes | Americas | drop the region pin; ×3 requests |
| region — `hero_counters`, `hero_best_maps`, `hero_synergies` | yes | Americas | widen `REGIONS`; ×4 requests |
| region — `map_meta_stats` | yes | Americas | drop the region pin; ×3 requests |
| platform | as `meta_snapshots.platform` | Console | fetch `input=PC` too; ×2 requests |
| input device | `meta_snapshots.input`, NULL | — | no source publishes it (see below) |
| map stage | `map_meta_stats.stage_id`, NULL | — | no source publishes it (see below) |
| tier — playbook tables | yes | all-ranks | a source that varies by rank; no schema change |

## The two that are not merely unfetched

**Input device is not the same as platform**, and only one of them is
published. Blizzard's filter offers `PC` and `Console` — a platform. It says
nothing about whether that player held a controller or a mouse, and both
platforms support both. A `input` dimension would need a source that actually
separates them; none of the three does. The column is deliberately absent
rather than filled with a guess inferred from platform.

**Map stage has no source at all.** Blizzard's map filter lists 30 whole maps
and stops there — no King's Row first point, no Ilios Well. Adding stages means
a `map_stages` table (parent `map_id`, ordinal, name) and a `stage_id` on
`map_meta_stats`, and then a source that reports per-stage rates. The schema
change is small; the data does not currently exist to put in it.

## Why the request count is the real ceiling

The dimensions compose multiplicatively, and the source refuses long sweeps.
`map_meta_stats` at full granularity:

```
30 maps × 9 ranks × 3 regions × 2 platforms = 1,620 requests
```

The rates endpoint began answering `504 Gateway Time-out` partway through a
**280**-request sweep, and then closed connections outright. 1,620 is not
reachable in one pass at any polite rate.

What makes it tractable is that the page cache is permanent and keyed by the
full query, so granularity can be widened one dimension at a time across many
runs, each resuming from what is already on disk. The order to widen in is
whichever dimension separates the numbers most, and rank is the current
evidence-backed answer: Widowmaker swings about fifteen points between Bronze
and Grandmaster on a single map, which the all-ranks figure averages away.

## Every dimension now has a column

There is no longer a dimension that needs a migration to add — only data to
put in one. Two are empty because nothing publishes them:
`meta_snapshots.input` and `map_meta_stats.stage_id` are both NULL on every
row, and `map_stages` has no rows at all. The rest carry a real value that
used to be implicit: `map_meta_stats.region_id` says Americas rather than
leaving it to be inferred from the database as a whole, and the playbook
tables say all-ranks rather than leaving rank unstated.

`stage_id` is nullable and NULL means the whole map, so `map_meta_stats` uses
`UNIQUE NULLS NOT DISTINCT`. Postgres treats NULLs as distinct by default,
which would let the same hero, map and rank be inserted over and over - every
whole-map row looking unique because its stage is NULL.

## What is already safe to assume

- adding a dimension never invalidates existing rows, because there are none
  that survive a run
- every fact table already carries `snapshot_id`, so a dimension that belongs
  to the whole capture (platform, queue) can be added to `meta_snapshots`
  without touching the fact tables at all
- `map_meta_stats` rows already carry `tier_id`, set to the all-ranks tier, so
  restoring rank granularity there needs no migration whatsoever
