"""Unit tests for the transformations - no database, no network.

These are the functions that broke most often while the pipeline was being
built: every case below is one that was actually wrong at some point.
"""

from data.authoritative.s1_extract.wiki import markup
from data.authoritative.s2_transform.wiki.measurements import parse_measurements
from data.authoritative.s2_transform.wiki.modifiers import affected_quantity, applies_to
from data.authoritative.s2_transform.wiki.names import abilities_named_in, match_key
from data.authoritative.s2_transform.wiki.weapons import base_name, group_weapons, head_noun


# --- measurements ------------------------------------------------------

def measure(text, default_unit=None):
    """First measurement as (value, numerator, denominator, denominator_value)."""
    return parse_measurements(text, default_unit)[0][:4]


def test_rate_splits_into_numerator_and_denominator():
    assert measure("125 m/s", "meters") == (125.0, "meters", "seconds", 1)
    assert measure("1.25 shots/s", "shots") == (1.25, "shots", "seconds", 1)


def test_plain_quantity_has_no_denominator():
    assert measure("14 seconds", "seconds") == (14.0, "seconds", None, None)
    assert measure("90", "hp") == (90.0, "hp", None, None)


def test_window_that_is_not_one_second_is_kept():
    # A burst dealing 75 over 0.59s is not 75 per second; the window survives.
    assert measure("75 over 0.59 seconds", "hp") == (75.0, "hp", "seconds", 0.59)


def test_stat_default_unit_applies_to_bare_numbers():
    assert measure("90", "hp")[1] == "hp"
    assert measure("90", None)[1] is None


def test_prose_after_a_number_is_not_treated_as_a_unit():
    # "100 while firing" must not yield a unit of "while".
    assert measure("100 while firing", "hp")[1] == "hp"


def test_range_is_split_and_ordered_by_magnitude():
    # Damage falloff runs high to low; min/max are by value, not position.
    got = {(m[0], m[4]) for m in parse_measurements("105 - 1", "hp")}
    assert got == {(1.0, "min"), (105.0, "max")}


def test_perk_transition_keeps_both_sides():
    got = {(m[0], m[4]) for m in parse_measurements("5 → 7 meters", "meters")}
    assert got == {(5.0, "before perk"), (7.0, "with perk")}


def test_tiered_value_keeps_every_option():
    values = [m[0] for m in parse_measurements("10/20/30 per second", "hp")]
    assert values == [10.0, 20.0, 30.0]


def test_booleans_become_one_and_zero():
    assert measure("✓")[0] == 1
    assert measure("✕")[0] == 0


def test_non_numeric_keeps_the_row_with_a_null_value():
    assert measure("proj") == (None, None, None, None)


def test_broken_template_is_not_read_as_a_number():
    parsed = parse_measurements("Expression error: Unexpected < operator", "meters")
    assert all(m[0] is None for m in parsed)


# --- markup ------------------------------------------------------------

def test_cargo_html_keeps_the_visible_value_not_the_tooltip():
    value = '<span class="tooltip" title="74.4 over 0.592s">75 over 0.59 seconds</span>'
    assert markup.html_to_text(value) == "75 over 0.59 seconds"


def test_file_links_are_dropped():
    value = "[[File:a.png|40x40px|link=Projectile|Projectile ]] <span>Projectile</span>"
    assert markup.html_to_text(value) == "Projectile"


def test_wikitext_tooltip_shows_the_first_argument():
    assert markup.wikitext_to_text("{{tt|1|pierces barriers}}") == "1"


def test_ability_type_splits_into_kind_and_mode():
    assert markup.split_type("Weapon;;Hip Fire") == ("Weapon", "Hip Fire")
    assert markup.split_type("Weapon (ADS)") == ("Weapon", "ADS")
    assert markup.split_type("Ultimate Ability") == ("Ultimate Ability", None)


def test_urls_never_survive_into_a_value():
    assert "http" not in markup.wikitext_to_text("0.27 meters https://example.com/x")


# --- names -------------------------------------------------------------

def test_match_key_reconciles_the_two_sources_spellings():
    assert match_key("Eject! (D.Mon)") == match_key("Eject!")
    assert match_key("Void Accelerator (Omnic Form)") == match_key("Void Accelerator")


def test_abilities_named_in_prefers_the_longest_match():
    named = abilities_named_in(
        "Nano Boost grants a speed boost", ["Nano Boost", "Boost"]
    )
    assert named == ["Nano Boost"]


# --- weapons -----------------------------------------------------------

def entry(name, mode, key=None):
    return {"name": name, "mode": mode, "input_key": key, "display_name": name}


def test_alt_fire_merges_into_one_weapon():
    grouped = group_weapons([
        entry("Particle Cannon", "Primary Fire"),
        entry("Particle Cannon Alt Fire", "Secondary Fire"),
    ])
    assert [name for name, _ in grouped] == ["Particle Cannon"]


def test_hip_fire_and_ads_are_one_weapon_named_for_the_weapon():
    grouped = group_weapons([
        entry("Biotic Rifle", "Hip Fire"),
        entry("Zoom (ADS)", "ADS"),
    ])
    (name, configs), = grouped
    assert name == "Biotic Rifle"
    assert configs[1]["display_name"] == "Biotic Rifle (ADS)"


def test_primary_and_secondary_with_unrelated_names_merge():
    grouped = group_weapons([
        entry("Peacekeeper", "Primary Fire"),
        entry("Fan the Hammer", "Secondary Fire"),
    ])
    assert len(grouped) == 1


def test_two_weapons_of_one_class_stay_separate():
    # Mauga fires his chainguns independently; a shared head noun says so.
    grouped = group_weapons([
        entry("Incendiary Chaingun", "Primary Fire"),
        entry("Volatile Chaingun", "Secondary Fire"),
    ])
    assert len(grouped) == 2


def test_form_based_loadouts_stay_separate():
    grouped = group_weapons([
        entry("Fusion Cannons", "Mech"),
        entry("Light Gun", "Pilot"),
    ])
    assert len(grouped) == 2


def test_base_name_and_head_noun():
    assert base_name("Widow's Kiss (ADS)") == "Widow's Kiss"
    assert head_noun("Incendiary Chaingun") == head_noun("Volatile Chaingun")


# --- modifiers ---------------------------------------------------------

def test_buff_direction_comes_from_the_wording():
    assert affected_quantity("damage_amp", "+50% dealt", "amp outgoing") == "damage_dealt"
    assert affected_quantity("damage_amp", "+30% taken", "amp incoming") == "damage_taken"
    assert affected_quantity("damage_red", "-45% taken", "") == "damage_taken"


def test_target_comes_from_keywords_and_is_none_when_unstated():
    assert applies_to("damage_amp", "+50% dealt", "target ally") == "ally"
    assert applies_to("damage_amp", "+30% taken", "amp incoming") == "enemy"
    assert applies_to("damage_red", "-45% taken", "reduction cap") == "self"
    assert applies_to("mspeed_buff", "+30%", "") is None
