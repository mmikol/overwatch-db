"""The exported CSVs must be a faithful copy of the database.

They are what anyone checking the data by hand actually opens, so a CSV that
disagrees with its table - or lingers after its table is gone - is worse than
no CSV at all.
"""

import csv
import os

import pytest

from data import orchestrator

pytestmark = pytest.mark.invariant


@pytest.fixture(scope="module")
def exported():
    if not os.path.isdir(orchestrator.RAW_DIR):
        pytest.skip("no data/raw - run the pipeline first")
    return {name[:-4] for name in os.listdir(orchestrator.RAW_DIR)
            if name.endswith(".csv")}


def test_every_table_is_exported(exported, rows):
    tables = {r[0] for r in rows(
        "select tablename from pg_tables where schemaname = 'public'")}
    assert not tables - exported, "tables with no CSV: %s" % sorted(tables - exported)


def test_no_csv_outlives_its_table(exported, rows):
    """A renamed table used to leave its old file behind, looking current."""
    tables = {r[0] for r in rows(
        "select tablename from pg_tables where schemaname = 'public'")}
    assert not exported - tables, "stale CSVs: %s" % sorted(exported - tables)


def test_row_counts_match_the_database(exported, one):
    for table in sorted(exported):
        path = os.path.join(orchestrator.RAW_DIR, table + ".csv")
        with open(path, newline="", encoding="utf-8") as handle:
            # csv.reader, not a newline count: descriptions contain newlines.
            written = sum(1 for _ in csv.reader(handle)) - 1
        assert written == one("select count(*) from " + table), table
