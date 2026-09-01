"""Extracting hero data from Blizzard's hero pages.

The roster page carries every hero's role and subrole; each hero page carries
an abilities carousel and a perks section. Blizzard publishes prose only - no
numbers - and omits some abilities outright, which the wiki supplies.
"""

from data.authoritative.s1_extract.blizzard.markup import to_text as html_to_text

PERK_TIERS = {"minor": 1, "major": 2}


class ScrapeError(Exception):
    pass


def parse_subroles(soup):
    """The ten subroles and the passive each one grants."""
    subroles = {}
    for div in soup.select("div.subrole[data-role][data-subrole]"):
        spans = div.find_all("span")
        if len(spans) != 2:
            continue
        code = div["data-subrole"]
        subroles[code] = {
            "code": code,
            "role_code": div["data-role"],
            # The label span reads "Tactician: ".
            "name": spans[0].get_text(strip=True).rstrip(":").strip(),
            "passive_description": html_to_text(spans[1]),
        }
    if not subroles:
        raise ScrapeError("no subroles found on the heroes page")
    return subroles


def parse_roster(soup):
    """Every hero card: slug, name, role, subrole."""
    heroes = []
    for card in soup.select("a.hero-card"):
        heading = card.find("h2", attrs={"slot": "heading"})
        href = card.get("href", "")
        if heading is None or not href:
            raise ScrapeError("hero card missing a name or link: %r" % card.get("id"))
        heroes.append(
            {
                "slug": href.rstrip("/").rsplit("/", 1)[-1],
                "name": heading.get_text(strip=True),
                "role_code": card["data-role"],
                "subrole_code": card["data-subrole"],
            }
        )
    if not heroes:
        raise ScrapeError("no hero cards found on the heroes page")
    return heroes


def parse_abilities(soup, slug):
    """Ordered abilities for one hero.

    The page holds a single carousel and it is the abilities one. position is
    the published order. Nothing here classifies an ability: Blizzard labels
    neither weapons nor ultimates, and the order does not identify them either.
    kind_id is left NULL for the wiki pipeline to fill in.
    """
    carousels = soup.find_all("blz-carousel")
    if len(carousels) != 1:
        raise ScrapeError("%s: expected 1 carousel, found %d" % (slug, len(carousels)))

    slides = carousels[0].find_all("blz-feature", attrs={"slot": "slide"})
    if not slides:
        raise ScrapeError("%s: no abilities found" % slug)

    abilities = []
    for position, slide in enumerate(slides):
        heading = slide.find("h3", class_="heading")
        description = slide.find("p", attrs={"slot": "description"})
        if heading is None or description is None:
            raise ScrapeError("%s: ability slide %d is malformed" % (slug, position))
        abilities.append(
            {
                "name": heading.get_text(strip=True),
                "description": html_to_text(description),
                "position": position,
            }
        )
    return abilities


def parse_perks(soup, slug):
    """The four perks: two minor (level 2) and two major (level 3).

    Stadium Powers live in their own section and are deliberately not read.
    """
    section = soup.find("blz-section", id="perks")
    if section is None:
        raise ScrapeError("%s: no perks section" % slug)

    perks = []
    for category in section.select("div.perk-category"):
        tier_codes = [c for c in category.get("class", []) if c in PERK_TIERS]
        if len(tier_codes) != 1:
            raise ScrapeError("%s: perk category has no tier: %r" % (slug, category.get("class")))
        tier_code = tier_codes[0]

        details = category.select("div.perk-details")
        if len(details) != 2:
            raise ScrapeError(
                "%s: expected 2 %s perks, found %d" % (slug, tier_code, len(details))
            )

        for position, detail in enumerate(details, start=1):
            heading = detail.find("h3", attrs={"slot": "subheading"})
            description = detail.find("div", attrs={"slot": "description"})
            if heading is None or description is None:
                raise ScrapeError("%s: malformed %s perk" % (slug, tier_code))
            perks.append(
                {
                    "tier_id": PERK_TIERS[tier_code],
                    "name": heading.get_text(strip=True),
                    "description": html_to_text(description),
                    "position": position,
                }
            )

    if len(perks) != 4:
        raise ScrapeError("%s: expected 4 perks, found %d" % (slug, len(perks)))
    return perks
