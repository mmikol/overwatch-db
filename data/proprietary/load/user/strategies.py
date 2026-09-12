"""Load pipeline: strategies/*.md - free-form strategy notes for the model.

No structure is imposed: each markdown file becomes one row, title from the
filename, body verbatim. The model conditions on the prose, so the prose is
the schema. The directory is the whole truth (the table mirrors it), and an
empty directory is a valid state, not an error.

    python -m data.proprietary.load.user.strategies
"""

import os
import sys

import psycopg

from data.proprietary import pipeline
from data.proprietary.pipeline import USER

STRATEGIES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "strategies")


def read_files(directory):
    out = []
    if not os.path.isdir(directory):
        return out
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".md") or name == "README.md":
            continue
        with open(os.path.join(directory, name), encoding="utf-8") as handle:
            body = handle.read().strip()
        if body:
            out.append((name[:-3].replace("_", " ").replace("-", " "), body))
    return out


def main():
    parser = pipeline.build_parser(__doc__)
    args = parser.parse_args()
    rows = read_files(STRATEGIES_DIR)
    cao = pipeline.now()

    with psycopg.connect(pipeline.resolve_dsn(args)) as connection:
        cursor = connection.cursor()
        source_id = pipeline.register_source(cursor, USER, cao)
        cursor.execute("DELETE FROM strategies")
        for title, body in rows:
            cursor.execute(
                "INSERT INTO strategies (title, body, source_id)"
                " VALUES (%s, %s, %s)", (title, body, source_id))
        connection.commit()
        pipeline.export_raw(connection, args, ("strategies",))

    print("strategies: %d loaded" % len(rows))
    if not rows:
        print("(data/proprietary/strategies/ is empty; drop .md files there"
              " and rerun - the inference layer reads them)")


if __name__ == "__main__":
    try:
        main()
    except (OSError, psycopg.Error) as error:
        sys.exit("error: %s" % error)
