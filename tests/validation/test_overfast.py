"""OverFast API - an independent scrape of Blizzard's hero pages.

Useful precisely because it reads the same source we do: where we disagree,
one of the two parsers is wrong. It is never used by the pipeline itself - the
project scrapes rather than consuming a data API - only here, as a second
opinion on what Blizzard published.
"""

import pytest

from tests.validation.conftest import normalise

pytestmark = [pytest.mark.validation, pytest.mark.invariant]

API = "https://overfast-api.tekrop.fr"


@pytest.fixture(scope="module")
def roster(fetch):
    heroes = fetch(API + "/heroes").json()
    if not heroes:
        pytest.skip("OverFast returned an empty roster")
    return {normalise(h["name"]): h for h in heroes}


def test_our_roster_matches_theirs(roster, rows):
    ours = {normalise(r[0]) for r in rows("select name from heroes")}
    theirs = set(roster)
    assert not theirs - ours, "heroes we are missing: %s" % sorted(theirs - ours)
    assert not ours - theirs, "heroes we have that they do not: %s" % sorted(ours - theirs)


def test_roles_agree(roster, rows):
    ours = {normalise(name): role.lower()
            for name, role in rows("""select h.name, r.code from heroes h
                                      join roles r using(role_id)""")}
    disagreements = [
        (name, ours[name], hero["role"])
        for name, hero in roster.items()
        if name in ours and ours[name] != hero["role"].lower()
    ]
    assert not disagreements, "role disagreements: %s" % disagreements


@pytest.mark.parametrize("slug", ["ana", "reinhardt", "mercy"])
def test_ability_names_agree_for_a_sample_hero(fetch, rows, slug):
    """Their ability list should be a subset of ours.

    Ours is a superset by design: Blizzard omits abilities that the wiki
    supplies, and OverFast reads only Blizzard. Anything they list that we
    lack means our parser dropped something.
    """
    detail = fetch("%s/heroes/%s" % (API, slug)).json()
    theirs = {normalise(a["name"]) for a in detail.get("abilities", [])}
    ours = {normalise(r[0]) for r in rows(
        "select a.name from abilities a join heroes h using(hero_id) where h.slug = %s",
        slug)}
    assert theirs <= ours, "%s: they list abilities we lack: %s" % (slug, theirs - ours)
