# Entity relationship diagram

The model is domains that intersect. A counter-pick question is a join
across them: which hero (HEROES), on which map (MAPS), performing how well
(META), answering whom and alongside whom (PLAYBOOK).

```
COMPOSITION = MAX[ HEROES ∩ MAPS ∩ META ∩ PLAYBOOK]
```

Each section shows every relationship its tables own, including the ones
that reach into another domain - PLAYBOOK's tables are almost entirely
edges like that, judgements attached to heroes and maps defined elsewhere.

Two tables can be joinable with no edge between them: `hero_meta` and
`map_meta` share four dimension keys (hero, snapshot, tier, region) and
join on any of them - an edge here means a foreign key, and neither owns
the other.

Every table also carries `source_id` → `sources` and a `cao` timestamp. Those
edges are left off - they would connect `sources` to all 30 tables and
obscure everything else.

## HEROES

```mermaid
erDiagram
    abilities ||--o{ ability_modifiers : "ability_id"
    abilities ||--o{ ability_stats : "ability_id"
    abilities ||--o{ perk_ability_effects : "ability_id"
    ability_kinds ||--o{ abilities : "kind_id"
    heroes ||--o{ abilities : "hero_id"
    heroes ||--o{ perks : "hero_id"
    heroes ||--o{ weapons : "hero_id"
    perk_tiers ||--o{ perks : "tier_id"
    perks ||--o{ perk_ability_effects : "perk_id"
    perks ||--o{ perk_stats : "perk_id"
    roles ||--o{ heroes : "role_id"
    roles ||--o{ subroles : "role_id"
    stat_keys ||--o{ ability_modifiers : "stat_key_id"
    stat_keys ||--o{ ability_stats : "stat_key_id"
    stat_keys ||--o{ perk_stats : "stat_key_id"
    stat_keys ||--o{ weapon_stats : "stat_key_id"
    subroles ||--o{ heroes : "role_id"
    subroles ||--o{ heroes : "subrole_id"
    weapon_config_slots ||--o{ weapon_configs : "slot_id"
    weapon_configs ||--o{ weapon_stats : "config_id"
    weapons ||--o{ weapon_configs : "weapon_id"
```

## MAPS

```mermaid
erDiagram
    game_modes ||--o{ map_modes : "mode_id"
    maps ||--o{ map_modes : "map_id"
    maps ||--o{ map_stages : "map_id"
```

## META

```mermaid
erDiagram
    competitive_tiers ||--o{ hero_meta : "tier_id"
    competitive_tiers ||--o{ map_meta : "tier_id"
    heroes ||--o{ hero_meta : "hero_id"
    heroes ||--o{ map_meta : "hero_id"
    map_stages ||--o{ map_meta : "stage_id"
    maps ||--o{ map_meta : "map_id"
    meta_snapshots ||--o{ hero_meta : "snapshot_id"
    meta_snapshots ||--o{ map_meta : "snapshot_id"
    regions ||--o{ hero_meta : "region_id"
    regions ||--o{ map_meta : "region_id"
```

## PLAYBOOK

```mermaid
erDiagram
    heroes ||--o{ counters : "hero_id"
    heroes ||--o{ counters : "other_id"
    heroes ||--o{ map_strategy : "hero_id"
    heroes ||--o{ playstyle : "hero_id"
    heroes ||--o{ synergies : "hero_id"
    heroes ||--o{ synergies : "other_id"
    maps ||--o{ map_strategy : "map_id"
```
