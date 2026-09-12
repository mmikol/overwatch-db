"""Assemble the evidence a recommendation stands on.

Everything the model is shown is a numbered line - E1, E2, ... - each drawn
from one table, so a pick can cite exactly what justified it and the citation
can be stored, joined, and inspected later. Nothing here calls a model; this
is the deterministic half of the inference layer, testable on its own.

The dossier is deliberately selective, not a database dump: the playbook and
strategies go in whole (they are small and all judgement), the meta goes in
as leaders and map slices (the model needs signal, not 4,000 rows).
"""

from data.heuristic.transform.counterpick.names import match_key


class Evidence:
    """The numbered lines, in order, with where each came from."""

    def __init__(self):
        self.lines = []          # [(tag, source_table, text)]

    def add(self, table, text):
        tag = "E%d" % (len(self.lines) + 1)
        self.lines.append((tag, table, text))
        return tag

    def rendered(self):
        return "\n".join("[%s] %s" % (tag, text) for tag, _, text in self.lines)


def _rows(cx, sql, *args):
    return cx.execute(sql, args or None).fetchall()


def build(cx, map_name=None, enemies=()):
    """-> (Evidence, context dict) for one recommendation request.

    map_name and enemies are optional; the dossier simply says less. Unknown
    names raise ValueError - a question about a hero we do not know is a
    question we must not quietly half-answer.
    """
    ev = Evidence()
    ctx = {"map_id": None, "map_name": None, "enemy_ids": []}

    heroes = {match_key(n): (i, n) for n, i in _rows(
        cx, "select name, hero_id from heroes")}
    maps = {match_key(n): (i, n) for n, i in _rows(
        cx, "select name, map_id from maps")}

    unknown = [e for e in enemies if match_key(e) not in heroes]
    if unknown:
        raise ValueError("unknown heroes: %s" % ", ".join(unknown))
    if map_name is not None:
        if match_key(map_name) not in maps:
            raise ValueError("unknown map: %s" % map_name)
        ctx["map_id"], ctx["map_name"] = maps[match_key(map_name)]
    ctx["enemy_ids"] = [heroes[match_key(e)][0] for e in enemies]

    # --- the map, and what it rewards ---------------------------------
    if ctx["map_id"]:
        for mode, in _rows(cx, """select g.name from map_modes mm
                join game_modes g using(mode_id) where mm.map_id=%s""",
                ctx["map_id"]):
            ev.add("map_modes", "%s is a %s map" % (ctx["map_name"], mode))
        stages = [s for s, in _rows(cx, """select name from map_stages
                where map_id=%s order by position""", ctx["map_id"])]
        if stages:
            ev.add("map_stages", "%s stages: %s"
                   % (ctx["map_name"], ", ".join(stages)))
        for style, score, note in _rows(cx, """select style, score, note
                from map_playstyle where map_id=%s""", ctx["map_id"]):
            ev.add("map_playstyle", "%s rewards %s (%s/3): %s"
                   % (ctx["map_name"], style, score, note))
        for hero, win, pick in _rows(cx, """
                select h.name, m.win_rate, m.pick_rate from map_meta m
                join heroes h using(hero_id)
                join competitive_tiers t on t.tier_id=m.tier_id
                where m.map_id=%s and t.code='all' and m.win_rate is not null
                order by m.win_rate desc limit 10""", ctx["map_id"]):
            ev.add("map_meta", "on %s: %s wins %.1f%% (picked %.1f%%)"
                   % (ctx["map_name"], hero, win, pick))
        for hero, pos in _rows(cx, """
                select h.name, ms.position from map_strategy ms
                join heroes h using(hero_id) where ms.map_id=%s
                order by ms.position""", ctx["map_id"]):
            ev.add("map_strategy", "%s is a top-%d map for %s"
                   % (ctx["map_name"], pos, hero))

    # --- the enemy team, and its answers ------------------------------
    for enemy_id in ctx["enemy_ids"]:
        name = _rows(cx, "select name from heroes where hero_id=%s",
                     enemy_id)[0][0]
        styles = [s for s, in _rows(
            cx, "select style from playstyle where hero_id=%s", enemy_id)]
        if styles:
            ev.add("playstyle", "%s plays: %s" % (name, ", ".join(styles)))
        answers = [a for a, in _rows(cx, """
                select cb.name from counters c
                join heroes cb on cb.hero_id=c.countered_by_id
                where c.hero_id=%s order by cb.name""", enemy_id)]
        if answers:
            ev.add("counters", "%s is countered by: %s"
                   % (name, ", ".join(answers)))
        for banned, rate in _rows(cx, """
                select h.name, m.ban_rate from hero_meta m
                join heroes h using(hero_id)
                join competitive_tiers t on t.tier_id=m.tier_id
                where h.hero_id=%s and t.code='all'
                and m.ban_rate is not null limit 1""", enemy_id):
            if rate and rate > 20:
                ev.add("hero_meta", "%s is banned in %.0f%% of lobbies -"
                       " may not be on the enemy team for long" % (banned, rate))

    # --- the playbook, intersected with the map and the enemy -----------
    #
    # The model's question is a join, so the dossier performs the join: not
    # "here are counters" and "here are map rates" side by side, but who
    # answers this enemy AND holds up on this ground, and who fits the style
    # this map rewards. These lines are the COUNTER = MAX[...] intersection
    # made citable.
    if ctx["map_id"]:
        for style, in _rows(cx, """select style from map_playstyle
                where map_id=%s order by score desc nulls last""",
                ctx["map_id"]):
            fits = _rows(cx, """
                select h.name, m.win_rate from playstyle p
                join heroes h using(hero_id)
                join map_meta m on m.hero_id = p.hero_id and m.map_id = %s
                join competitive_tiers t on t.tier_id = m.tier_id
                where p.style = %s and t.code = 'all'
                  and m.win_rate is not null
                order by m.win_rate desc limit 6""", ctx["map_id"], style)
            if fits:
                ev.add("playstyle+map_meta",
                       "%s heroes who hold up on %s: %s" % (
                           style, ctx["map_name"], ", ".join(
                               "%s (%.1f%%)" % f for f in fits)))
        for enemy_id in ctx["enemy_ids"]:
            name = _rows(cx, "select name from heroes where hero_id=%s",
                         enemy_id)[0][0]
            joined = _rows(cx, """
                select h.name, m.win_rate from counters c
                join heroes h on h.hero_id = c.countered_by_id
                join map_meta m on m.hero_id = c.countered_by_id
                    and m.map_id = %s
                join competitive_tiers t on t.tier_id = m.tier_id
                where c.hero_id = %s and t.code = 'all'
                  and m.win_rate is not null
                order by m.win_rate desc limit 6""",
                ctx["map_id"], enemy_id)
            if joined:
                ev.add("counters+map_meta",
                       "answers to %s that also win on %s: %s" % (
                           name, ctx["map_name"], ", ".join(
                               "%s (%.1f%%)" % j for j in joined)))

    # --- who plays which style, roster-wide -----------------------------
    for style, names in _rows(cx, """
            select style, string_agg(h.name, ', ' order by h.name)
            from playstyle p join heroes h using(hero_id)
            group by style order by style"""):
        ev.add("playstyle", "%s heroes: %s" % (style, names))

    # --- the operator's own strategy notes, citable ----------------------
    for title, body in _rows(
            cx, "select title, body from strategies order by title"):
        ev.add("strategies", "operator note '%s': %s"
               % (title, " ".join(body.split())))

    # --- what a composition is ----------------------------------------
    for style, role, slots, note in _rows(cx, """
            select a.style, r.name, a.slots, a.note from comp_archetypes a
            join roles r using(role_id) order by a.style, r.name"""):
        ev.add("comp_archetypes", "a %s comp wants %d %s: %s"
               % (style, slots, role.lower(), note))

    # --- who works with whom (the authored playbook, whole) ------------
    for a, b, score, note in _rows(cx, """
            select h.name, o.name, s.score, s.note from synergies s
            join heroes h on h.hero_id=s.hero_id
            join heroes o on o.hero_id=s.other_id order by s.score desc nulls last"""):
        ev.add("synergies", "%s + %s (%s/3): %s"
               % (a, b, score if score is not None else "?", note or "no note"))

    # --- ban pressure worth knowing ------------------------------------
    for hero, rate in _rows(cx, """
            select h.name, m.ban_rate from hero_meta m
            join heroes h using(hero_id)
            join competitive_tiers t on t.tier_id=m.tier_id
            join meta_snapshots s using(snapshot_id)
            join sources src on src.source_id=s.source_id
            where t.code='all' and src.code='blizzard' and m.ban_rate > 25
            order by m.ban_rate desc limit 6"""):
        ev.add("hero_meta", "%s is banned in %.0f%% of lobbies - do not build"
               " a comp that dies with the ban" % (hero, rate))

    return ev, ctx

