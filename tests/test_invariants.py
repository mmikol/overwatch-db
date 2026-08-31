"""Properties the loaded database must hold.

Each of these encodes something that was actually broken at some point, or a
guarantee the pipeline claims to make. They read the database and assert on
shape and completeness, never on exact figures - those move with every patch.
"""

import pytest

pytestmark = pytest.mark.invariant


# --- completeness ------------------------------------------------------

def test_every_hero_has_a_role_and_subrole(one):
    assert one("select count(*) from heroes where role_id is null or subrole_id is null") == 0


def test_every_hero_has_health(one):
    # Blizzard publishes none of it; the wiki pipeline must fill it in.
    assert one("select count(*) from heroes where health is null") == 0


def test_every_hero_has_a_weapon(one):
    assert one("""select count(*) from heroes h
                  where not exists (select 1 from weapons w where w.hero_id = h.hero_id)""") == 0


def test_every_hero_has_an_ultimate(one):
    assert one("""select count(*) from heroes h
                  where not exists (select 1 from abilities a
                                    where a.hero_id = h.hero_id and a.kind_id = 3)""") == 0


def test_every_ability_is_classified(one):
    # kind_id is NULL until the wiki pipeline types it; none may be left.
    assert one("select count(*) from abilities where kind_id is null") == 0


def test_every_map_has_a_mode(one):
    assert one("""select count(*) from maps m
                  where not exists (select 1 from map_modes x where x.map_id = m.map_id)""") == 0


def test_every_hero_has_meta_and_a_playstyle(one):
    assert one("""select count(*) from heroes h
                  where not exists (select 1 from hero_meta_stats x where x.hero_id = h.hero_id)""") == 0
    assert one("""select count(*) from heroes h
                  where not exists (select 1 from hero_playstyles x where x.hero_id = h.hero_id)""") == 0


# --- provenance --------------------------------------------------------

def test_every_table_records_its_source_and_when_it_was_read(rows):
    missing = rows("""
        select table_name from information_schema.columns
        where table_schema = 'public' and table_name <> 'sources'
        group by table_name
        having count(*) filter (where column_name in ('source_id','cao')) < 2""")
    assert missing == []


def test_no_row_is_missing_its_source(rows, one):
    for (table,) in rows("""select table_name from information_schema.columns
                            where table_schema='public' and column_name='source_id'"""):
        assert one("select count(*) from %s where source_id is null" % table) == 0


# --- units -------------------------------------------------------------

CANONICAL = {"charges", "degrees", "hp", "meters", "multiplier", "pellets",
             "percent", "points", "rounds", "seconds", "shots", "swings", "volleys"}

STAT_TABLES = ("ability_stats", "weapon_stats", "perk_stats")


def test_units_are_canonical_base_quantities(rows):
    for table in STAT_TABLES:
        used = {r[0] for r in rows(
            "select distinct unit_numerator from %s where unit_numerator is not null" % table)}
        assert used <= CANONICAL, "%s has unrecognised units: %s" % (table, used - CANONICAL)


def test_no_unit_is_written_as_a_rate(rows):
    for table in STAT_TABLES:
        assert rows("select 1 from %s where unit_numerator like '%%/%%' limit 1" % table) == []


def test_a_denominator_always_has_a_numerator_and_a_magnitude(one):
    for table in STAT_TABLES:
        assert one("""select count(*) from %s where unit_denominator is not null
                      and (unit_numerator is null or denominator_value is null)""" % table) == 0
        assert one("""select count(*) from %s where denominator_value is not null
                      and unit_denominator is null""" % table) == 0


def test_source_text_is_always_kept(one):
    for table in STAT_TABLES:
        assert one("select count(*) from %s where value_text is null "
                   "or raw_value is null" % table) == 0


# --- scope -------------------------------------------------------------

def test_no_media_or_links_leak_into_stored_text(one):
    assert one("select count(*) from abilities where description like '%http%'") == 0
    for table in STAT_TABLES:
        assert one("select count(*) from %s where value_text like '%%http%%'" % table) == 0


def test_meta_records_the_queue_it_came_from(rows):
    # The model is Open Queue Competitive, but neither rate source is that.
    # Blizzard publishes Role Queue only; counterpick.gg never states a queue.
    # Both must say so, so that neither is read as Open Queue by accident.
    by_source = {(code, queue) for code, queue in rows(
        "select s.code, m.queue from meta_snapshots m join sources s using(source_id)")}
    assert by_source
    assert all(queue.startswith("competitive_") for _, queue in by_source)
    assert {q for c, q in by_source if c == "blizzard"} <= {"competitive_role_queue"}
    assert {q for c, q in by_source if c == "counterpick"} <= {
        "competitive_unspecified_queue"}


def test_map_pool_is_standard_play_only(one, rows):
    modes = {r[0] for r in rows("select code from game_modes")}
    assert modes == {"control", "escort", "flashpoint", "hybrid", "push"}
    assert one("select count(*) from maps") == one(
        "select count(distinct map_id) from map_modes")


# --- weapons -----------------------------------------------------------

def test_each_hero_weapon_has_at_least_one_config(one):
    assert one("""select count(*) from weapons w
                  where not exists (select 1 from weapon_configs c
                                    where c.weapon_id = w.weapon_id)""") == 0


def test_ads_configs_are_named_for_their_weapon(rows):
    for weapon, config in rows("""
            select w.name, c.name from weapon_configs c
            join weapons w using(weapon_id)
            join weapon_config_slots s using(slot_id) where s.code = 'ads'"""):
        assert config == "%s (ADS)" % weapon
