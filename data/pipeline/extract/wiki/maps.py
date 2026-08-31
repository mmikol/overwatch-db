"""Extracting maps and game modes from the wiki's Maps article.

Only the "Standard Play" section is read; Former Standard Play (Assault,
Clash), Stadium, Arcade and seasonal modes are out of scope.
"""

import re

from data.pipeline.ingest.wiki import WikiError

# The competitive rotation lives between these two headings.
SECTION_START = "== Standard Play =="
SECTION_END = "== Former Standard Play =="

# <gallery class="maps-gallery maps-gallery--control"> ... </gallery>
GALLERY_RE = re.compile(
    r"<gallery[^>]*maps-gallery--([a-z]+)[^>]*>(.*?)</gallery>", re.S | re.I
)
# File:Busan.jpg|{{flag|kr}} [[Busan]]
MAP_LINE_RE = re.compile(r"^File:[^|]*\|(.*)$", re.M)
LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")

MODE_NAMES = {
    "control": "Control",
    "escort": "Escort",
    "flashpoint": "Flashpoint",
    "hybrid": "Hybrid",
    "push": "Push",
}


def standard_play_section(text):
    """Just the Standard Play part of the article."""
    try:
        start = text.index(SECTION_START)
    except ValueError:
        raise WikiError("Maps: no %r heading" % SECTION_START)
    end = text.find(SECTION_END, start)
    return text[start:end if end != -1 else len(text)]


def parse_modes_and_maps(text):
    """[(mode_code, mode_name, [map_name])] in page order."""
    section = standard_play_section(text)
    modes = []
    for match in GALLERY_RE.finditer(section):
        code = match.group(1).lower()
        if code not in MODE_NAMES:
            continue

        maps = []
        for line in MAP_LINE_RE.findall(match.group(2)):
            link = LINK_RE.search(line)
            if link:
                maps.append(link.group(1).strip())

        modes.append((code, MODE_NAMES[code], maps))

    if not modes:
        raise WikiError("Maps: no mode galleries found in Standard Play")
    return modes
