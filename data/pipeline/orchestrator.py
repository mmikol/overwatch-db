"""Orchestration: everything around the four pipeline stages.

The stages themselves are packages - ingest, extract, transform, load. This
module is the machinery that runs them and the shared plumbing they lean on,
kept in one place rather than scattered across four root modules.

    python -m data.pipeline.orchestrator                  every stage, in order
    python -m data.pipeline.orchestrator --only wiki.maps one pipeline
    python -m data.pipeline.orchestrator schema --reset   rebuild the schema
    python -m data.pipeline.orchestrator export           refresh data/raw

Order matters and running out of order does not error - it quietly produces a
partial database - which is why `run` exists rather than a note in a README.
"""

import argparse
import csv
import glob
import hashlib
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

import psycopg


# --- shared plumbing every pipeline uses ------------------------------

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DSN = "postgresql:///overwatch"


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
    """Where to write: an embedded server, --dsn, $DATABASE_URL, or the default."""
    if getattr(args, "local_server", None):
        import pgserver

        return pgserver.get_server(os.path.abspath(args.local_server)).get_uri()
    return args.dsn or os.environ.get("DATABASE_URL") or DEFAULT_DSN


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

BLIZZARD = ("blizzard", "Blizzard Overwatch site", "https://overwatch.blizzard.com/en-us/")
WIKI = ("wiki", "Overwatch Wiki", "https://overwatch.fandom.com/")


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

MIGRATIONS_DIR = os.path.join(ROOT, "migrations")


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

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW_DIR = os.path.join(ROOT, "data", "raw")
HISTORICAL_DIR = os.path.join(ROOT, "data", "historical")

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


# --- keeping what each run produced ------------------------------------


def _fingerprint(raw_dir):
    """A hash of the exported data, ignoring when it was read.

    Every row carries `cao`, and snapshot ids move each run, so comparing files
    byte-for-byte would call every run a change. Those columns are dropped
    before hashing so the fingerprint tracks the data itself.
    """
    volatile = {"cao", "captured_at", "snapshot_id"}
    digest = hashlib.sha256()
    for name in sorted(os.listdir(raw_dir)):
        if not name.endswith(".csv"):
            continue
        digest.update(name.encode())
        with open(os.path.join(raw_dir, name), newline="", encoding="utf-8") as handle:
            rows = csv.reader(handle)
            header = next(rows, [])
            keep = [i for i, column in enumerate(header) if column not in volatile]
            digest.update(",".join(header[i] for i in keep).encode())
            for row in rows:
                digest.update(",".join(row[i] for i in keep if i < len(row)).encode())
    return digest.hexdigest()


def archive(raw_dir=RAW_DIR, historical_dir=HISTORICAL_DIR):
    """Keep a dated copy of this run, unless the data is unchanged.

    A full run drops and rebuilds every table, so the database only ever holds
    the present. This is where earlier runs survive - diff two folders to see
    what a patch changed. Runs that read the same data twice do not accumulate
    a second identical copy.
    """
    if not os.path.isdir(raw_dir):
        return None
    if not os.path.isdir(historical_dir):
        os.makedirs(historical_dir)

    fingerprint = _fingerprint(raw_dir)
    previous = sorted(
        name for name in os.listdir(historical_dir)
        if os.path.isdir(os.path.join(historical_dir, name))
    )
    if previous:
        marker = os.path.join(historical_dir, previous[-1], ".fingerprint")
        if os.path.exists(marker):
            with open(marker, encoding="utf-8") as handle:
                if handle.read().strip() == fingerprint:
                    print("\nhistorical: unchanged since %s, nothing archived"
                          % previous[-1])
                    return None

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    target = os.path.join(historical_dir, stamp)
    shutil.copytree(raw_dir, target, dirs_exist_ok=True)
    with open(os.path.join(target, ".fingerprint"), "w", encoding="utf-8") as handle:
        handle.write(fingerprint + "\n")
    print("\nhistorical: archived %d tables to data/historical/%s"
          % (len([f for f in os.listdir(target) if f.endswith(".csv")]), stamp))
    return target


# --- running the stages in order --------------------------------------

# source.domain, in the order they must run.
PIPELINES = (
    "blizzard.heroes",
    "wiki.heroes",
    "wiki.maps",
    "wiki.meta",
    "blizzard.meta",
)


# --- command line ------------------------------------------------------


def main():
    parser = build_parser(__doc__)
    parser.add_argument(
        "command", nargs="?", default="run", choices=("run", "schema", "export"),
        help="run every stage (default), rebuild the schema, or refresh data/raw",
    )
    parser.add_argument(
        "--only", action="append",
        help="run just this pipeline, as source.domain (repeatable)",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="schema: drop everything before applying",
    )
    parser.add_argument(
        "--no-archive", action="store_true",
        help="do not keep a dated copy of this run under data/historical/",
    )
    args, passthrough = parser.parse_known_args()

    if args.command == "schema":
        with psycopg.connect(resolve_dsn(args)) as connection:
            if args.reset:
                rebuild(connection)
            else:
                apply(connection, read_migrations())
            tables = connection.execute(
                "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"
            ).fetchone()[0]
        print("\n%d tables in the database" % tables)
        return

    if args.command == "export":
        with psycopg.connect(resolve_dsn(args)) as connection:
            for table, rows in export(connection):
                print("  data/raw/%s.csv  %d rows" % (table, rows))
        return

    run_pipelines(args, passthrough)


def run_pipelines(args, passthrough):
    """Every pipeline, in dependency order, stopping at the first failure."""
    selected = args.only or list(PIPELINES)
    unknown = [name for name in selected if name not in PIPELINES]
    if unknown:
        sys.exit("error: unknown pipeline(s): %s" % ", ".join(unknown))
    selected = [name for name in PIPELINES if name in selected]

    forwarded = list(passthrough)
    for flag, value in (("--dsn", args.dsn), ("--local-server", args.local_server)):
        if value:
            forwarded += [flag, value]
    if args.no_export:
        forwarded.append("--no-export")

    for index, name in enumerate(selected, start=1):
        print("\n=== [%d/%d] %s ===" % (index, len(selected), name))
        result = subprocess.run(
            [sys.executable, "-m", "data.pipeline.load." + name] + forwarded, cwd=ROOT
        )
        if result.returncode != 0:
            sys.exit("\n%s failed (exit %d); stopping so later stages do not run"
                     " against a partial database." % (name, result.returncode))
    print("\nall %d pipelines completed" % len(selected))
    if not args.no_export and not args.no_archive:
        archive()


if __name__ == "__main__":
    try:
        main()
    except (SchemaError, psycopg.Error) as error:
        sys.exit("error: %s" % error)
