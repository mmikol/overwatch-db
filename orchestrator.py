"""The orchestrator: runs every pipeline, across every type of data, into one
model.

Each type is a pipeline of its own - extract, transform, load - and declares
itself in its own `pipeline.py`. This module sits above them, owns the schema
and the CSV export, and runs them in the order their data depends on:

    authoritative   what a source recorded. Cooldowns, health, win rates.
    heuristic       somebody's judgement. Who answers whom, best maps.

The heuristic type links to heroes, maps and regions the authoritative type
loads, so it runs second. Order matters and running out of order does not
error - it quietly produces a partial database - which is why `run` exists
rather than a note in a README.

The verbs, in the order a database lives through them:

    init      apply the migrations to an empty database - schema, no data
    inflate   the first fill: every pipeline into a fresh schema. Refuses a
              database that already holds data - loading again is `update`.
    update    (default) load again into a populated database. Entity tables
              are refreshed in place; each meta run adds a new dated snapshot
              beside the old ones, so repeated updates accumulate a series.
              Never drops anything, so one type can be run alone safely.
    rebuild   create + fill from a clean slate: drop everything, reapply the
              migrations, run every pipeline. The ground truth for structural
              change - a renamed ability, a removed hero - and always runs
              everything, because a partial rebuild is how one type of data
              wipes another.
    export    refresh data/raw/*.csv from whatever is loaded

The db/cluster directory itself is made implicitly: pgserver runs initdb the
first time a verb touches the path.

    python -m orchestrator rebuild               clean slate, everything
    python -m orchestrator                       update, everything
    python -m orchestrator --type heuristic      update one type
    python -m orchestrator --only authoritative.wiki.maps
"""

import argparse
import glob
import os
import subprocess
import sys
from datetime import datetime, timezone

import psycopg


# --- shared plumbing every pipeline uses ------------------------------

ROOT = os.path.dirname(os.path.abspath(__file__))

# db/ pairs the schema with what it builds: db/migrations is the source,
# db/cluster the embedded Postgres built from it. The cluster is a directory,
# not a file, because that is Postgres's on-disk format - there is no single
# database file to point at. It is a build artifact - `rebuild` reproduces it
# from the migrations plus the page caches - so it is gitignored, not
# committed.
DEFAULT_DB_DIR = os.path.join(ROOT, "db", "cluster")


def build_parser(description, cache_dir=None):
    """A parser carrying the options every pipeline accepts."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--dsn", help="Postgres DSN (default: $DATABASE_URL)")
    parser.add_argument(
        "--local-server",
        nargs="?",
        const="pgdata",
        help="run against an embedded Postgres in this directory (needs pgserver)",
    )
    parser.add_argument(
        "--no-export", action="store_true", help="skip refreshing data/raw/*.csv"
    )
    if cache_dir:
        parser.add_argument(
            "--cache",
            default=os.path.join(ROOT, cache_dir),
            help="page cache directory ('' to disable)",
        )
    return parser


def resolve_dsn(args):
    """Where to write: --local-server, --dsn, $DATABASE_URL, or db/ at the root."""
    explicit = args.dsn or os.environ.get("DATABASE_URL")
    if not getattr(args, "local_server", None) and explicit:
        return explicit
    import pgserver

    return pgserver.get_server(
        os.path.abspath(getattr(args, "local_server", None) or DEFAULT_DB_DIR)
    ).get_uri()


def prepare_cache(args):
    """Create the page cache directory if this pipeline uses one."""
    cache = getattr(args, "cache", None)
    if cache and not os.path.isdir(cache):
        os.makedirs(cache)
    return cache


def lookup_ids(cursor, table, name_column, id_column):
    """{lowercased name: id} for matching scraped names against loaded rows."""
    return {
        row[0].lower(): row[1]
        for row in cursor.execute(
            "SELECT %s, %s FROM %s" % (name_column, id_column, table)
        ).fetchall()
    }


def export_raw(connection, args, tables=()):
    """Refresh data/raw/*.csv unless asked not to, reporting the named tables."""
    if args.no_export:
        return
    counts = dict(export(connection))
    print("\nrefreshed data/raw: %d tables" % len(counts))
    for table in tables:
        if table in counts:
            print("  %-22s %d rows" % (table + ".csv", counts[table]))


# --- where rows came from ----------------------------------------------
#
# One row per source rather than a URL and a timestamp repeated on every
# entity row. `cao` ("current as of") is refreshed each time a pipeline runs.
# The sources themselves are declared by the type that scrapes them, in its
# own pipeline.py, so each carries its own provenance.


def now():
    """One timestamp for a pipeline run."""
    return datetime.now(timezone.utc)


def register_source(cursor, source, cao):
    """Upsert one source and return its source_id."""
    code, name, url = source
    cursor.execute(
        "INSERT INTO sources (code, name, url, cao) VALUES (%s, %s, %s, %s)"
        " ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name,"
        " url = EXCLUDED.url, cao = EXCLUDED.cao RETURNING source_id",
        (code, name, url, cao),
    )
    return cursor.fetchone()[0]


# --- the schema, from migrations/ -------------------------------------

MIGRATIONS_DIR = os.path.join(ROOT, "db", "migrations")


class SchemaError(Exception):
    pass


def read_migrations():
    """Every migration, in filename order."""
    migrations = []
    for path in sorted(glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql"))):
        with open(path, encoding="utf-8") as handle:
            migrations.append((path, handle.read()))
    if not migrations:
        raise SchemaError("no migrations found in %s/" % MIGRATIONS_DIR)
    return migrations


def apply(connection, migrations, quiet=False):
    for path, sql in migrations:
        with connection.cursor() as cursor:
            cursor.execute(sql)
        connection.commit()
        if not quiet:
            print("  applied %s" % os.path.basename(path))


def drop_all(connection):
    """Drop every table in the public schema.

    Read from the catalog rather than from the migration text. Deriving the
    list from the migrations leaves orphans behind: a table whose migration is
    later deleted is never dropped, and goes on holding stale rows that nothing
    references. This database is a full rebuild of one project's schema, so the
    catalog is the honest source of truth for what to clear.
    """
    with connection.cursor() as cursor:
        tables = [
            row[0]
            for row in cursor.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            ).fetchall()
        ]
        if tables:
            cursor.execute(
                "DROP TABLE IF EXISTS %s CASCADE"
                % ", ".join(
                    psycopg.sql.Identifier(t).as_string(connection) for t in tables
                )
            )
    connection.commit()
    return tables


def rebuild(connection, quiet=False):
    """Drop everything and reapply every migration."""
    dropped = drop_all(connection)
    if dropped and not quiet:
        print("  dropped %d existing tables" % len(dropped))
    apply(connection, read_migrations(), quiet)


# --- exporting every table to data/raw --------------------------------

RAW_DIR = os.path.join(ROOT, "data", "raw")

def table_names(connection):
    """Every table in the database, from the catalog.

    Read rather than listed: a hand-maintained list drifts silently, and the
    table it forgets is exactly the one nobody notices is stale.
    """
    return [
        row[0]
        for row in connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            " ORDER BY tablename"
        ).fetchall()
    ]


def export(connection, raw_dir=RAW_DIR):
    """Write one CSV per table. Returns [(table, row_count)]."""
    if not os.path.isdir(raw_dir):
        os.makedirs(raw_dir)

    counts = []
    for table in table_names(connection):
        path = os.path.join(raw_dir, table + ".csv")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            with connection.cursor().copy(
                "COPY (SELECT * FROM %s) TO STDOUT WITH (FORMAT csv, HEADER true)" % table
            ) as copy:
                for chunk in copy:
                    handle.write(bytes(chunk).decode("utf-8"))
        # Counted from the database, not by counting newlines in the file:
        # descriptions contain embedded newlines, which inflates the latter.
        counts.append(
            (table, connection.execute("SELECT count(*) FROM " + table).fetchone()[0])
        )

    # A table that is renamed or dropped leaves its old CSV behind, and a stale
    # file is indistinguishable from a current one. Remove what no longer maps
    # to a table.
    current = {table + ".csv" for table, _ in counts}
    for stale in sorted(set(os.listdir(raw_dir)) - current):
        if stale.endswith(".csv"):
            os.remove(os.path.join(raw_dir, stale))
            print("  removed stale %s" % stale)
    return counts


# --- running the stages in order --------------------------------------

# Each type's stages as source.domain, in the order they must run, and the
# types themselves in the order they must run. Held here as plain strings and
# dispatched as subprocesses: a type's pipeline.py imports this module for its
# shared plumbing, so importing them back would be a cycle.
PIPELINES = {
    "authoritative": (
        "blizzard.heroes",
        "wiki.heroes",
        "wiki.maps",
        "blizzard.meta",
    ),
    "heuristic": (
        "wiki.meta",
        "counterpick.heroes",
    ),
}


def qualified():
    """Every pipeline as type.source.domain, in the order they must run."""
    return [
        "%s.%s" % (dtype, stage)
        for dtype, stages in PIPELINES.items()
        for stage in stages
    ]


# --- command line ------------------------------------------------------


def main():
    parser = build_parser(__doc__)
    parser.add_argument(
        "command", nargs="?", default="update",
        choices=("init", "inflate", "update", "rebuild", "export"),
        help="init creates the schema; inflate is the first fill; update"
             " (default) loads again; rebuild starts clean and does all of"
             " it; export refreshes data/raw",
    )
    parser.add_argument(
        "--type", action="append", choices=tuple(PIPELINES),
        help="run just this type of data (repeatable)",
    )
    parser.add_argument(
        "--only", action="append",
        help="run just this pipeline, as type.source.domain (repeatable)",
    )
    args, passthrough = parser.parse_known_args()

    if args.command == "export":
        with psycopg.connect(resolve_dsn(args)) as connection:
            for table, rows in export(connection):
                print("  data/raw/%s.csv  %d rows" % (table, rows))
        return

    def table_count(connection):
        return connection.execute(
            "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"
        ).fetchone()[0]

    if args.command == "init":
        with psycopg.connect(resolve_dsn(args)) as connection:
            if table_count(connection):
                sys.exit("error: the database already has tables; `rebuild`"
                         " is the verb that starts over")
            apply(connection, read_migrations())
            print("\n%d tables, no data; `inflate` fills them" %
                  table_count(connection))
        return

    if args.command in ("rebuild", "inflate"):
        # Always the whole thing. Filling or rebuilding a slice would leave
        # the exact half-loaded database the verb split exists to prevent.
        if args.type or args.only:
            sys.exit("error: %s always runs every pipeline; use update with"
                     " --type/--only for partial runs" % args.command)

    if args.command == "rebuild":
        with psycopg.connect(resolve_dsn(args)) as connection:
            rebuild(connection)
    else:
        # inflate and update need the schema to exist already, and inflate
        # additionally means FIRST fill - a populated database is update's.
        with psycopg.connect(resolve_dsn(args)) as connection:
            if table_count(connection) == 0:
                sys.exit("error: the database is empty; run"
                         " `python -m orchestrator init` (or rebuild) first")
            if args.command == "inflate" and connection.execute(
                "SELECT count(*) FROM heroes"
            ).fetchone()[0]:
                sys.exit("error: the database already holds data; `update`"
                         " is the verb for loading again")

    run_pipelines(args, passthrough)


def run_pipelines(args, passthrough):
    """Every selected pipeline, in dependency order, stopping at the first
    failure.

    A later stage run against a half-loaded database does not fail loudly - it
    silently drops the rows it cannot link - so a failure stops the run.
    """
    every = qualified()
    selected = set(every)
    if args.type:
        selected = {name for name in every if name.split(".")[0] in args.type}
    if args.only:
        unknown = [name for name in args.only if name not in every]
        if unknown:
            sys.exit("error: unknown pipeline(s): %s\nknown: %s"
                     % (", ".join(unknown), ", ".join(every)))
        selected &= set(args.only)
    selected = [name for name in every if name in selected]
    if not selected:
        sys.exit("error: no pipelines selected")

    forwarded = list(passthrough)
    for flag, value in (("--dsn", args.dsn), ("--local-server", args.local_server)):
        if value:
            forwarded += [flag, value]
    if args.no_export:
        forwarded.append("--no-export")

    shown = None
    for index, name in enumerate(selected, start=1):
        dtype, stage = name.split(".", 1)
        if dtype != shown:
            print("\n--- %s ---" % dtype)
            shown = dtype
        print("\n=== [%d/%d] %s ===" % (index, len(selected), name))
        result = subprocess.run(
            [sys.executable, "-m", "data.%s.s3_load.%s" % (dtype, stage)] + forwarded,
            cwd=ROOT,
        )
        if result.returncode != 0:
            sys.exit("\n%s failed (exit %d); stopping so later stages do not run"
                     " against a partial database." % (name, result.returncode))
    print("\nall %d pipelines completed" % len(selected))


if __name__ == "__main__":
    try:
        main()
    except (SchemaError, psycopg.Error) as error:
        sys.exit("error: %s" % error)
