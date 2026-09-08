"""Load pipeline: seasons.csv - the coarse delineator of snapshots.

A patch tweaks numbers; a season swaps the hero pool and map rotation, so a
snapshot records both. Authored rather than scraped, because the wiki's season
pages are lore articles and its current-era page carries no dates at all -
starts are stable public facts, one new row every nine-ish weeks.

The file is the whole truth, and loading it also RECOMPUTES season_id on
every existing snapshot (latest season started on or before the capture), so
adding a season later corrects history instead of only future captures.

    python -m data.proprietary.load.user.seasons
"""

import csv
import os
import sys
from datetime import date

import psycopg

from data.proprietary import pipeline
from data.proprietary.pipeline import USER

CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "seasons.csv")


class SeasonError(Exception):
    pass


def read_rows(path):
    rows, seen = [], set()
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        expected = ["name", "started", "note"]
        if reader.fieldnames != expected:
            raise SeasonError("%s: header must be %s, found %s"
                             % (path, ",".join(expected), reader.fieldnames))
        for n, row in enumerate(reader, start=2):
            name = row["name"].strip()
            if not name:
                raise SeasonError("line %d: name is required" % n)
            if name.lower() in seen:
                raise SeasonError("line %d: duplicate season %s" % (n, name))
            seen.add(name.lower())
            try:
                started = date.fromisoformat(row["started"].strip())
            except ValueError:
                raise SeasonError("line %d: started must be YYYY-MM-DD" % n)
            rows.append((name, started, row["note"].strip() or None))
    return rows


def main():
    parser = pipeline.build_parser(__doc__)
    args = parser.parse_args()
    rows = read_rows(CSV_PATH)
    cao = pipeline.now()

    with psycopg.connect(pipeline.resolve_dsn(args)) as connection:
        cursor = connection.cursor()
        source_id = pipeline.register_source(cursor, USER, cao)

        cursor.execute("UPDATE meta_snapshots SET season_id = NULL")
        cursor.execute("DELETE FROM seasons")
        for name, started, note in rows:
            cursor.execute(
                "INSERT INTO seasons (name, started, note, source_id)"
                " VALUES (%s, %s, %s, %s)",
                (name, started, note, source_id),
            )
        cursor.execute(
            "UPDATE meta_snapshots ms SET season_id ="
            " (SELECT season_id FROM seasons s"
            "  WHERE s.started <= ms.captured_at::date"
            "  ORDER BY s.started DESC, s.season_id DESC LIMIT 1)"
        )
        stamped = cursor.rowcount
        connection.commit()
        pipeline.export_raw(connection, args, ("seasons", "meta_snapshots"))

    print("seasons: %d loaded; %d snapshots stamped" % (len(rows), stamped))


if __name__ == "__main__":
    try:
        main()
    except (SeasonError, OSError, ValueError, psycopg.Error) as error:
        sys.exit("error: %s" % error)
