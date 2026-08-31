# Entity relationship diagram

The model is three domains that intersect. A counter-pick question is a join
across all three: which hero (HEROES), on which map (MAPS), performing how
well (META).

```
COUNTER = MAX[ HEROES ∩ MAPS ∩ META ]
```

Every table also carries `source_id` → `sources` and a `cao` timestamp. Those
edges are left off the diagram below - they would connect `sources` to all 27
tables and obscure everything else.

## HEROES

```mermaid
erDiagram
    ability_kinds ||--o{ abilities : "kind_id"
    heroes ||--o{ abilities : "hero_id"
    abilities ||--o{ ability_modifiers : "ability_id"
    stat_keys ||--o{ ability_modifiers : "stat_key_id"
    abilities ||--o{ ability_stats : "ability_id"
    stat_keys ||--o{ ability_stats : "stat_key_id"
    roles ||--o{ heroes : "role_id"
    subroles ||--o{ heroes : "subrole_id"
    subroles ||--o{ heroes : "role_id"
    abilities ||--o{ perk_ability_effects : "ability_id"
    perks ||--o{ perk_ability_effects : "perk_id"
    perks ||--o{ perk_stats : "perk_id"
    stat_keys ||--o{ perk_stats : "stat_key_id"
    heroes ||--o{ perks : "hero_id"
    perk_tiers ||--o{ perks : "tier_id"
    roles ||--o{ subroles : "role_id"
    weapon_config_slots ||--o{ weapon_configs : "slot_id"
    weapons ||--o{ weapon_configs : "weapon_id"
    stat_keys ||--o{ weapon_stats : "stat_key_id"
    weapon_configs ||--o{ weapon_stats : "config_id"
    heroes ||--o{ weapons : "hero_id"
```

## MAPS

```mermaid
erDiagram
    game_modes ||--o{ map_modes : "mode_id"
    maps ||--o{ map_modes : "map_id"
```

## META

```mermaid
erDiagram
    competitive_tiers ||--o{ hero_meta_stats : "tier_id"
    meta_snapshots ||--o{ hero_meta_stats : "snapshot_id"
    regions ||--o{ hero_meta_stats : "region_id"
    playstyles ||--o{ hero_playstyles : "playstyle_id"
    meta_snapshots ||--o{ map_meta_stats : "snapshot_id"
```

## Where the domains join

META and MAPS both hang off HEROES, and `map_meta_stats` is the one table
that reaches all three - a hero's rates on a specific map.

```mermaid
erDiagram
    heroes ||--o{ hero_meta_stats : "hero_id"
    heroes ||--o{ hero_playstyles : "hero_id"
    heroes ||--o{ map_meta_stats : "hero_id"
    maps ||--o{ map_meta_stats : "map_id"
```
