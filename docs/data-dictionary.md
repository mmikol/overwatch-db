# Data dictionary

Generated from the live schema.

Every table carries two columns omitted from the lists below, because they
are on all of them: `source_id` (which source the row came from, see
`sources`) and `cao` — "current as of", when that row was read.

| domain | tables |
| --- | --- |
| **foundation** | `sources` |
| **HEROES** | `abilities` · `ability_kinds` · `ability_modifiers` · `ability_stats` · `heroes` · `perk_ability_effects` · `perk_stats` · `perk_tiers` · `perks` · `roles` · `stat_keys` · `subroles` · `weapon_config_slots` · `weapon_configs` · `weapon_stats` · `weapons` |
| **MAPS** | `game_modes` · `map_modes` · `maps` |
| **META** | `competitive_tiers` · `hero_best_maps` · `hero_counters` · `hero_meta_stats` · `hero_playstyles` · `map_meta_stats` · `meta_snapshots` · `playstyles` · `regions` |


## `abilities`

*HEROES · 307 rows · `002_heroes.sql`*

kind_id is NULL until the wiki pipeline sets it. Blizzard's markup labels neither weapons nor ultimates, and its ordering does not identify them either, so nothing is guessed at scrape time.

| column | type | null | references |
| --- | --- | --- | --- |
| `ability_id` | integer | no |  |
| `hero_id` | integer | no | `heroes.hero_id` |
| `kind_id` | smallint | yes | `ability_kinds.kind_id` |
| `name` | text | no |  |
| `description` | text | no |  |
| `position` | smallint | no |  |

## `ability_kinds`

*HEROES · 4 rows · `002_heroes.sql`*

| column | type | null | references |
| --- | --- | --- | --- |
| `kind_id` | smallint | no |  |
| `code` | text | no |  |

## `ability_modifiers`

*HEROES · 129 rows · `002_heroes.sql`*

affects names the quantity scaled, so a query can find every effect on outgoing damage without knowing which stat it was published under. damage_dealt · damage_taken · healing_received · healing_dealt · movement_speed magnitude is a signed percentage: +50 amplifies, -45 reduces.

| column | type | null | references |
| --- | --- | --- | --- |
| `modifier_id` | integer | no |  |
| `ability_id` | integer | no | `abilities.ability_id` |
| `stat_key_id` | integer | no | `stat_keys.stat_key_id` |
| `affects` | text | no |  |
| `applies_to` | text | yes |  |
| `magnitude` | numeric | no |  |
| `unit` | text | no |  |

## `ability_stats`

*HEROES · 4112 rows · `002_heroes.sql`*

One row per measurement, not per stat. A wiki value like "0.67 shots/s (max charge); 3.33 shots/s (min charge)" becomes two rows sharing a stat_key, separated by `condition`. Units are split into the unit on top and the unit underneath, so nothing has to parse a "/" to know what a number means. denominator_value carries the magnitude underneath - 1 for a plain rate, or the window a burst spans: "125 m/s"              -> 125,  meters  / seconds,  denominator_value 1 "1.25 shots/s"         -> 1.25, shots   / seconds,  denominator_value 1 "75 over 0.59 seconds" -> 75,   hp      / seconds,  denominator_value 0.59 "14 seconds"           -> 14,   seconds / NULL A rate is therefore always value / denominator_value per unit_denominator. value is NULL where the measurement is not numeric (shot types, "partial"). value_text and raw_value always keep the source strings, so anything the parser misreads stays recoverable.

| column | type | null | references |
| --- | --- | --- | --- |
| `ability_stat_id` | integer | no |  |
| `ability_id` | integer | no | `abilities.ability_id` |
| `stat_key_id` | integer | no | `stat_keys.stat_key_id` |
| `value` | numeric | yes |  |
| `unit_numerator` | text | yes |  |
| `unit_denominator` | text | yes |  |
| `denominator_value` | numeric | yes |  |
| `condition` | text | yes |  |
| `value_text` | text | no |  |
| `raw_value` | text | no |  |

## `competitive_tiers`

*META · 9 rows · `004_meta.sql`*

'all' is a real member of both dimensions: it is the unfiltered figure the page reports, and keeping it as a row avoids nullable dimension keys. Bronze through Champion, plus the "All Tiers" aggregate the source reports alongside them. rank_order follows the source's own ordering.

| column | type | null | references |
| --- | --- | --- | --- |
| `tier_id` | integer | no |  |
| `code` | text | no |  |
| `name` | text | no |  |
| `rank_order` | smallint | no |  |

## `game_modes`

*MAPS · 5 rows · `003_maps.sql`*

| column | type | null | references |
| --- | --- | --- | --- |
| `mode_id` | integer | no |  |
| `code` | text | no |  |
| `name` | text | no |  |

## `hero_best_maps`

*META · 636 rows · `004_meta.sql`*

The maps a hero is strongest on, best first. The source ranks them but publishes no per-map figure, so position is the whole of what it says.

| column | type | null | references |
| --- | --- | --- | --- |
| `snapshot_id` | integer | no | `meta_snapshots.snapshot_id` |
| `hero_id` | integer | no | `heroes.hero_id` |
| `map_id` | integer | no | `maps.map_id` |
| `region_id` | integer | no | `regions.region_id` |
| `position` | smallint | no |  |

## `hero_counters`

*META · 2760 rows · `004_meta.sql`*

PLAYBOOK: which heroes answer which, and where each hero is strongest. The two directions are stored separately because the source does not treat them as inverses. Of 354 pairings it publishes, 114 appear in one direction only, so "X is countered by Y" and "Y counters X" are two judgements rather than one fact seen twice. Beware the source's own naming: its field called `counters` is displayed as "Countered by". The direction stored here follows the columns as labelled and explained by their tooltips, not the field names.

| column | type | null | references |
| --- | --- | --- | --- |
| `snapshot_id` | integer | no | `meta_snapshots.snapshot_id` |
| `hero_id` | integer | no | `heroes.hero_id` |
| `other_id` | integer | no | `heroes.hero_id` |
| `relation` | text | no |  |
| `region_id` | integer | no | `regions.region_id` |

## `hero_meta_stats`

*META · 848 rows · `004_meta.sql`*

Rates by region and tier. All rates are percentages as published (47.9 means 47.9%). These rows are across all maps.

| column | type | null | references |
| --- | --- | --- | --- |
| `hero_meta_stat_id` | integer | no |  |
| `snapshot_id` | integer | no | `meta_snapshots.snapshot_id` |
| `hero_id` | integer | no | `heroes.hero_id` |
| `region_id` | integer | no | `regions.region_id` |
| `tier_id` | integer | no | `competitive_tiers.tier_id` |
| `win_rate` | numeric | yes |  |
| `pick_rate` | numeric | yes |  |
| `ban_rate` | numeric | yes |  |

## `hero_playstyles`

*META · 89 rows · `004_meta.sql`*

| column | type | null | references |
| --- | --- | --- | --- |
| `hero_id` | integer | no | `heroes.hero_id` |
| `playstyle_id` | integer | no | `playstyles.playstyle_id` |

## `heroes`

*HEROES · 53 rows · `002_heroes.sql`*

The composite foreign key makes it impossible to pair a hero with a subrole belonging to a different role than the hero's own. health, shield and armor are the hero's own pool, all in hp. Blizzard publishes none of them, so the wiki pipeline fills them in; a hero with no shield or armor leaves those NULL rather than storing a zero the source never states.

| column | type | null | references |
| --- | --- | --- | --- |
| `hero_id` | integer | no |  |
| `slug` | text | no |  |
| `name` | text | no |  |
| `role_id` | integer | no | `subroles.subrole_id` |
| `subrole_id` | integer | no | `subroles.subrole_id` |
| `health` | smallint | yes |  |
| `shield` | smallint | yes |  |
| `armor` | smallint | yes |  |

## `map_meta_stats`

*META · 14310 rows · `004_meta.sql`*

Rates per map, and per tier within a map. The source's filters compose, so a hero's rates on King's Row in Bronze are a different figure from the same hero's rates on King's Row overall - and both are published. tier_id 'all' is the unfiltered figure for that map, which keeps the dimension key non-nullable. Region is not broken out here: map x tier is already 240 requests, and map x tier x region would be 720.

| column | type | null | references |
| --- | --- | --- | --- |
| `map_meta_stat_id` | integer | no |  |
| `snapshot_id` | integer | no | `meta_snapshots.snapshot_id` |
| `hero_id` | integer | no | `heroes.hero_id` |
| `map_id` | integer | no | `maps.map_id` |
| `tier_id` | integer | no | `competitive_tiers.tier_id` |
| `win_rate` | numeric | yes |  |
| `pick_rate` | numeric | yes |  |
| `ban_rate` | numeric | yes |  |

## `map_modes`

*MAPS · 30 rows · `003_maps.sql`*

One row per playable combination: this table is the set of matches that can actually be drawn in Open Queue Competitive. Every map currently belongs to exactly one mode, so today this holds one row per map. It is modelled many-to-many anyway because that is what the domain allows - a map can be re-released under a second mode - and because a degenerate join here costs nothing.

| column | type | null | references |
| --- | --- | --- | --- |
| `map_id` | integer | no | `maps.map_id` |
| `mode_id` | integer | no | `game_modes.mode_id` |

## `maps`

*MAPS · 30 rows · `003_maps.sql`*

| column | type | null | references |
| --- | --- | --- | --- |
| `map_id` | integer | no |  |
| `name` | text | no |  |

## `meta_snapshots`

*META · 2 rows · `004_meta.sql`*

| column | type | null | references |
| --- | --- | --- | --- |
| `snapshot_id` | integer | no |  |
| `captured_at` | timestamp with time zone | no |  |
| `queue` | text | no |  |
| `input` | text | no |  |

## `perk_ability_effects`

*HEROES · 194 rows · `002_heroes.sql`*

| column | type | null | references |
| --- | --- | --- | --- |
| `perk_id` | integer | no | `perks.perk_id` |
| `ability_id` | integer | no | `abilities.ability_id` |

## `perk_stats`

*HEROES · 678 rows · `002_heroes.sql`*

| column | type | null | references |
| --- | --- | --- | --- |
| `perk_stat_id` | integer | no |  |
| `perk_id` | integer | no | `perks.perk_id` |
| `stat_key_id` | integer | no | `stat_keys.stat_key_id` |
| `value` | numeric | yes |  |
| `unit_numerator` | text | yes |  |
| `unit_denominator` | text | yes |  |
| `denominator_value` | numeric | yes |  |
| `condition` | text | yes |  |
| `value_text` | text | no |  |
| `raw_value` | text | no |  |

## `perk_tiers`

*HEROES · 2 rows · `002_heroes.sql`*

| column | type | null | references |
| --- | --- | --- | --- |
| `tier_id` | smallint | no |  |
| `code` | text | no |  |
| `name` | text | no |  |
| `unlock_level` | smallint | no |  |

## `perks`

*HEROES · 212 rows · `002_heroes.sql`*

| column | type | null | references |
| --- | --- | --- | --- |
| `perk_id` | integer | no |  |
| `hero_id` | integer | no | `heroes.hero_id` |
| `tier_id` | smallint | no | `perk_tiers.tier_id` |
| `name` | text | no |  |
| `description` | text | no |  |
| `position` | smallint | no |  |

## `playstyles`

*META · 3 rows · `004_meta.sql`*

| column | type | null | references |
| --- | --- | --- | --- |
| `playstyle_id` | integer | no |  |
| `code` | text | no |  |
| `name` | text | no |  |

## `regions`

*META · 4 rows · `004_meta.sql`*

| column | type | null | references |
| --- | --- | --- | --- |
| `region_id` | integer | no |  |
| `code` | text | no |  |
| `name` | text | no |  |

## `roles`

*HEROES · 3 rows · `002_heroes.sql`*

| column | type | null | references |
| --- | --- | --- | --- |
| `role_id` | integer | no |  |
| `code` | text | no |  |
| `name` | text | no |  |

## `sources`

*foundation · 3 rows · `001_initial_schema.sql`*

| column | type | null | references |
| --- | --- | --- | --- |
| `code` | text | no |  |
| `name` | text | no |  |
| `url` | text | no |  |

## `stat_keys`

*HEROES · 48 rows · `002_heroes.sql`*

The stat vocabulary. `unit` is the canonical unit for the stat, used when a value carries no unit of its own ("damage = 90" is 90 hp).

| column | type | null | references |
| --- | --- | --- | --- |
| `stat_key_id` | integer | no |  |
| `code` | text | no |  |
| `label` | text | no |  |
| `unit` | text | yes |  |

## `subroles`

*HEROES · 10 rows · `002_heroes.sql`*

The ten subroles, each belonging to exactly one role, each carrying the passive it grants (e.g. "Tactician: Store excess ultimate charge.").

| column | type | null | references |
| --- | --- | --- | --- |
| `subrole_id` | integer | no |  |
| `role_id` | integer | no | `roles.role_id` |
| `code` | text | no |  |
| `name` | text | no |  |
| `passive_description` | text | no |  |

## `weapon_config_slots`

*HEROES · 5 rows · `002_heroes.sql`*

| column | type | null | references |
| --- | --- | --- | --- |
| `slot_id` | smallint | no |  |
| `code` | text | no |  |

## `weapon_configs`

*HEROES · 82 rows · `002_heroes.sql`*

weapon_type lives here rather than on the weapon because it varies by config: Ana's Biotic Rifle is a projectile from the hip and hitscan in ADS.

| column | type | null | references |
| --- | --- | --- | --- |
| `config_id` | integer | no |  |
| `weapon_id` | integer | no | `weapons.weapon_id` |
| `slot_id` | smallint | no | `weapon_config_slots.slot_id` |
| `name` | text | no |  |
| `weapon_type` | text | yes |  |
| `position` | smallint | no |  |

## `weapon_stats`

*HEROES · 1304 rows · `002_heroes.sql`*

| column | type | null | references |
| --- | --- | --- | --- |
| `weapon_stat_id` | integer | no |  |
| `config_id` | integer | no | `weapon_configs.config_id` |
| `stat_key_id` | integer | no | `stat_keys.stat_key_id` |
| `value` | numeric | yes |  |
| `unit_numerator` | text | yes |  |
| `unit_denominator` | text | yes |  |
| `denominator_value` | numeric | yes |  |
| `condition` | text | yes |  |
| `value_text` | text | no |  |
| `raw_value` | text | no |  |

## `weapons`

*HEROES · 60 rows · `002_heroes.sql`*

One row per weapon. A weapon's firing modes are configs, not weapons: Ana carries one Biotic Rifle, fired from the hip or down the sights.

| column | type | null | references |
| --- | --- | --- | --- |
| `weapon_id` | integer | no |  |
| `hero_id` | integer | no | `heroes.hero_id` |
| `name` | text | no |  |
| `position` | smallint | no |  |
