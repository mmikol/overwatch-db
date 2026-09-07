"""Load pipeline: synergies.csv - our hand-authored half of the playbook.

Each row is one ordered claim: `hero` works with `other`, scored on whatever
scale the author keeps consistently, with the reasoning in `note` - which is
the part a strategy model actually wants. (a, b) and (b, a) are separate rows,
so a deliberate asymmetry is expressible.

The file is the whole truth: the table is cleared and reloaded from it, so
deleting a row deletes the claim. And because this input is authored rather
than scraped, nothing is fuzzily matched or silently skipped - an unknown hero
name is an error to fix in the file, not a row to drop.

    python -m data.proprietary.load.user.synergies
"""

import csv
import os
import sys

import psycopg

from data.proprietary import pipeline
from data.proprietary.pipeline import USER

CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "synergies.csv")


class SynergyError(Exception):
    pass


def read_rows(path):
    """[(hero, other, score or None, note or None)], validated as authored."""
    rows, seen = [], set()
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        expected = ["hero", "other", "score", "note"]
        if reader.fieldnames != expected:
            raise SynergyError("%s: header must be %s, found %s"
                              % (path, ",".join(expected), reader.fieldnames))
        for n, row in enumerate(reader, start=2):
            hero, other = row["hero"].strip(), row["other"].strip()
            if not hero or not other:
                raise SynergyError("line %d: hero and other are required" % n)
            if hero.lower() == other.lower():
                raise SynergyError("line %d: %s paired with itself" % (n, hero))
            key = (hero.lower(), other.lower())
            if key in seen:
                raise SynergyError("line %d: duplicate pair %s -> %s"
                                  % (n, hero, other))
            seen.add(key)
            score = row["score"].strip()
            rows.append((hero, other, int(score) if score else None,
                         row["note"].strip() or None))
    return rows


def main():
    parser = pipeline.build_parser(__doc__)
    args = parser.parse_args()

    rows = read_rows(CSV_PATH)
    cao = pipeline.now()

    with psycopg.connect(pipeline.resolve_dsn(args)) as connection:
        cursor = connection.cursor()
        source_id = pipeline.register_source(cursor, USER, cao)
        hero_ids = pipeline.lookup_ids(cursor, "heroes", "name", "hero_id")

        unknown = sorted({name for pair in rows for name in pair[:2]
                          if name.lower() not in hero_ids})
        if unknown:
            raise SynergyError(
                "names not in the roster (fix synergies.csv): %s"
                % ", ".join(unknown))

        # The file is the whole truth, so the table mirrors it exactly.
        cursor.execute("DELETE FROM hero_synergies")
        for hero, other, score, note in rows:
            cursor.execute(
                "INSERT INTO hero_synergies (hero_id, other_id, score, note,"
                " source_id) VALUES (%s, %s, %s, %s, %s)",
                (hero_ids[hero.lower()], hero_ids[other.lower()], score, note,
                 source_id),
            )
        connection.commit()
        pipeline.export_raw(connection, args, ("hero_synergies",))

    print("authored synergies: %d claims loaded" % len(rows))
    if not rows:
        print("(synergies.csv is header-only; author rows to fill the"
              " playbook's second half)")


if __name__ == "__main__":
    try:
        main()
    except (SynergyError, OSError, ValueError, psycopg.Error) as error:
        sys.exit("error: %s" % error)
