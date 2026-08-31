"""owherostats.com - best heroes per map.

Their /maps/best page ranks heroes per role per map with win, pick and ban
rates. Every element of it is derivable from map_meta_stats joined to heroes,
roles, maps and game_modes, which is what these tests check.
"""

import json
import re

import pytest

from tests.validation.conftest import normalise

pytestmark = [pytest.mark.validation, pytest.mark.invariant]

URL = "https://owherostats.com/maps/best"
PER_ROLE = 3


@pytest.fixture(scope="module")
def published(fetch):
    """{map name: [hero names, best first]} from their JSON-LD."""
    html = fetch(URL).text
    lists = {}
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>',
                            html, re.S):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        name = data.get("name", "")
        if data.get("@type") == "ItemList" and name.startswith("Best heroes on"):
            lists[normalise(name.replace("Best heroes on ", ""))] = [
                item["name"] for item in data["itemListElement"]
            ]
    if not lists:
        pytest.skip("owherostats no longer publishes ItemList data on this page")
    return lists


@pytest.fixture(scope="module")
def ours(rows):
    """{map name: {role: [hero names, best first]}} - the same shape, from us."""
    # Scoped to the unfiltered tier. map_meta_stats holds every map against
    # every tier, so ranking without this mixes nine populations and the top
    # three become whichever heroes had a freak win rate in a small tier
    # sample. Their page ranks the unfiltered figure, so ours must too.
    ranked = rows("""
        select mp.name, r.name, h.name,
               row_number() over (partition by mp.map_id, r.role_id
                                  order by m.win_rate desc)
        from map_meta_stats m
        join heroes h using(hero_id)
        join roles r using(role_id)
        join maps mp on mp.map_id = m.map_id
        join competitive_tiers t on t.tier_id = m.tier_id
        where t.code = 'all'""")
    out = {}
    for map_name, role, hero, rank in ranked:
        if rank <= PER_ROLE:
            out.setdefault(normalise(map_name), {}).setdefault(role, []).append(hero)
    return out


def test_we_cover_every_map_they_publish(published, ours):
    # "Antartic Peninsula" is their typo; fold it so the test tracks coverage
    # rather than spelling.
    missing = [m for m in published if m.replace("antartic", "antarctic") not in ours]
    assert not missing, "no map_meta_stats for: %s" % missing


def test_we_can_produce_a_full_list_for_each_map(ours, published):
    for map_name in ours:
        roles = ours[map_name]
        assert set(roles) == {"Tank", "Damage", "Support"}, map_name
        for role, heroes in roles.items():
            assert len(heroes) == PER_ROLE, "%s / %s" % (map_name, role)


def test_our_rankings_broadly_agree_with_theirs(published, ours):
    """Overlap of the two top-9 sets, averaged over every map.

    Not equality: ours is Blizzard's Competitive Role Queue on controller,
    theirs is a different population entirely. The floor catches our data
    going wrong, not a patch moving the meta.
    """
    matched = total = 0
    for map_name, heroes in published.items():
        mine = ours.get(map_name.replace("antartic", "antarctic"))
        if not mine:
            continue
        ours_flat = {normalise(h) for role in mine.values() for h in role}
        theirs = {normalise(h) for h in heroes}
        matched += len(theirs & ours_flat)
        total += len(theirs)

    assert total, "nothing comparable was published"
    agreement = matched / total
    print("\nowherostats agreement: %d/%d heroes (%.0f%%)" % (matched, total, agreement * 100))
    assert agreement >= 0.40, (
        "only %.0f%% of their picks appear in ours - our map stats may be wrong"
        % (agreement * 100)
    )


def test_the_metrics_they_show_all_exist_in_our_schema(rows):
    """Their page shows WR, PR and BR per hero per map. We must hold all three."""
    sample = rows("""select win_rate, pick_rate, ban_rate from map_meta_stats
                     where win_rate is not null limit 1""")
    assert sample, "map_meta_stats is empty"
    assert all(value is not None for value in sample[0])
