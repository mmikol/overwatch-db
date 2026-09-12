"""The inference layer's two halves, without ever calling a model.

The dossier (deterministic evidence assembly) is tested against the built
database; persistence is tested with a synthetic model answer and rolled
back, which also exercises the citation validation - a model citing evidence
it was never shown must be an error, not a stored row."""

import pytest

from data.proprietary import dossier
from data.proprietary.load.user.strategies import read_files
from data.proprietary.recommend import COMP_TOOL, persist

pytestmark = pytest.mark.invariant


# --- strategy files (pure, needs no db) ----------------------------------

def test_strategy_files_load_whole_and_skip_the_readme(tmp_path):
    (tmp_path / "anti-dive.md").write_text("# Anti dive\nPeel hard.", "utf-8")
    (tmp_path / "README.md").write_text("not a strategy", "utf-8")
    (tmp_path / "empty.md").write_text("   ", "utf-8")
    (tmp_path / "notes.txt").write_text("wrong extension", "utf-8")
    assert read_files(str(tmp_path)) == [("anti dive", "# Anti dive\nPeel hard.")]


def test_comp_tool_schema_is_strict():
    # strict tool use requires additionalProperties: false + required at
    # every level, or the guarantee silently is not one
    def check(schema):
        if schema.get("type") == "object":
            assert schema["additionalProperties"] is False
            assert "required" in schema
            for sub in schema["properties"].values():
                check(sub)
        if schema.get("type") == "array":
            check(schema["items"])
    assert COMP_TOOL["strict"] is True
    check(COMP_TOOL["input_schema"])


# --- the dossier ----------------------------------------------------------

def test_dossier_lines_are_densely_numbered_and_sourced(db):
    ev, ctx = dossier.build(db, "Ilios", ["Zarya"])
    assert [t for t, _, _ in ev.lines] == [
        "E%d" % i for i in range(1, len(ev.lines) + 1)]
    assert all(table and text for _, table, text in ev.lines)
    assert ctx["map_id"] is not None and len(ctx["enemy_ids"]) == 1
    joined = ev.rendered()
    assert "Ilios" in joined and "Zarya is countered by" in joined
    db.rollback()


def test_dossier_refuses_names_it_does_not_know(db):
    with pytest.raises(ValueError, match="unknown map"):
        dossier.build(db, "Atlantis", [])
    with pytest.raises(ValueError, match="unknown heroes"):
        dossier.build(db, None, ["Goku"])
    db.rollback()


def test_dossier_without_map_or_enemies_still_has_a_playbook(db):
    ev, _ = dossier.build(db)
    tables = {t for _, t, _ in ev.lines}
    assert {"comp_archetypes", "synergies"} <= tables
    db.rollback()


# --- persistence of a (synthetic) answer -----------------------------------

def _fake_answer(ev, heroes):
    tags = [t for t, _, _ in ev.lines[:5]]
    return {"playstyle": "brawl",
            "reasoning": "synthetic answer for the persistence test",
            "picks": [{"hero": h, "why": "test", "evidence": [tags[i]]}
                      for i, h in enumerate(heroes)]}


def test_persist_stores_picks_and_citations_then_rolls_back(db, one):
    ev, ctx = dossier.build(db, "Ilios", [])
    heroes = [r[0] for r in db.execute(
        "select name from heroes order by name limit 5")]
    rec_id = persist(db, "test question", _fake_answer(ev, heroes),
                     ev, ctx["map_id"], "PROMPT", "test-model", "{}")
    assert one("select count(*) from recommendation_picks where rec_id=%s",
               rec_id) == 5
    assert one("""select count(*) from recommendation_evidence
                  where rec_id=%s""", rec_id) == 5
    assert one("select playstyle from recommendations where rec_id=%s",
               rec_id) == "brawl"
    db.rollback()          # a test must not leave a recommendation behind


def test_persist_refuses_citations_of_nothing(db):
    ev, ctx = dossier.build(db, None, [])
    heroes = [r[0] for r in db.execute(
        "select name from heroes order by name limit 5")]
    answer = _fake_answer(ev, heroes)
    answer["picks"][0]["evidence"] = ["E9999"]
    with pytest.raises(ValueError, match="never shown"):
        persist(db, "q", answer, ev, None, "P", "m", "{}")
    db.rollback()


def test_persist_refuses_invented_heroes(db):
    ev, ctx = dossier.build(db, None, [])
    answer = _fake_answer(ev, ["Goku", "Ana", "Mei", "Zarya", "Lúcio"])
    with pytest.raises(ValueError, match="invented"):
        persist(db, "q", answer, ev, None, "P", "m", "{}")
    db.rollback()


# --- the playbook intersection, the crucial part ---------------------------

def test_dossier_joins_counters_with_map_meta(db):
    ev, _ = dossier.build(db, "King's Row", ["Zarya"])
    inter = [text for _, table, text in ev.lines if table == "counters+map_meta"]
    assert inter and "answers to Zarya that also win on King's Row" in inter[0]
    db.rollback()


def test_dossier_joins_playstyle_with_map_meta(db):
    ev, _ = dossier.build(db, "King's Row")
    lines = [t for _, table, t in ev.lines if table == "playstyle+map_meta"]
    # King's Row is authored as a brawl map, so the fit line must exist
    assert any(l.startswith("brawl heroes who hold up on King's Row") for l in lines)
    db.rollback()


def test_dossier_lists_roster_styles(db):
    ev, _ = dossier.build(db)
    styles = {t.split(" heroes:")[0] for _, table, t in ev.lines
              if table == "playstyle" and " heroes:" in t}
    assert {"dive", "brawl", "poke"} <= styles
    db.rollback()


def test_strategy_notes_are_citable_evidence(db):
    src = db.execute("select source_id from sources limit 1").fetchone()[0]
    db.execute("insert into strategies (title, body, source_id)"
               " values ('test note', 'never overextend  through\nchokes', %s)",
               (src,))
    ev, _ = dossier.build(db)
    notes = [(tag, t) for tag, table, t in ev.lines if table == "strategies"]
    assert notes and "operator note 'test note': never overextend through chokes" \
        in notes[0][1]
    db.rollback()          # the note was test-only
