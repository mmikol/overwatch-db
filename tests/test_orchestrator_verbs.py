"""The verb ladder and its guardrails, against real throwaway clusters.

Each verb refuses the state it is not for and names the verb you wanted -
these tests are those promises, order-independent: the shared cluster comes
pre-initialised, and tests that need emptiness make their own. run_pipelines
is stubbed, so nothing here touches the network; pgserver's initdb is the
only real work, which keeps this CI-safe.
"""

import sys

import pytest

import orchestrator

psycopg = pytest.importorskip("psycopg")
pgserver = pytest.importorskip("pgserver")


def connect(path):
    return psycopg.connect(pgserver.get_server(path).get_uri())


@pytest.fixture(scope="module")
def cluster(tmp_path_factory):
    """A cluster with the schema applied and no data - post-`init` state."""
    path = str(tmp_path_factory.mktemp("verbs") / "cluster")
    with connect(path) as cx:
        orchestrator.apply(cx, orchestrator.read_migrations(), quiet=True)
    return path


@pytest.fixture()
def fresh(tmp_path):
    """A cluster with nothing in it at all - pre-`init` state."""
    return str(tmp_path / "cluster")


@pytest.fixture()
def run(monkeypatch):
    def make(path):
        calls = []
        monkeypatch.setattr(orchestrator, "run_pipelines",
                            lambda args, passthrough: calls.append(args.command))

        def invoke(*argv):
            del calls[:]
            monkeypatch.setattr(sys, "argv",
                                ["orchestrator", *argv, "--local-server", path])
            orchestrator.main()
            return calls
        return invoke
    return make


def test_init_builds_the_schema_and_only_the_schema(run, fresh, capsys):
    run(fresh)("init")
    assert "no data" in capsys.readouterr().out
    with connect(fresh) as cx:
        assert cx.execute(
            "select count(*) from pg_tables where schemaname='public'"
        ).fetchone()[0] >= 30
        assert cx.execute("select count(*) from heroes").fetchone()[0] == 0
    with pytest.raises(SystemExit, match="rebuild.*starts over"):
        run(fresh)("init")


def test_inflate_and_update_dispatch_on_an_empty_schema(run, cluster):
    invoke = run(cluster)
    assert invoke("inflate") == ["inflate"]
    assert invoke("update") == ["update"]
    assert invoke() == ["update"]          # update is the default verb


def test_inflate_refuses_a_populated_database(run, cluster):
    with connect(cluster) as cx:
        cx.execute("insert into roles (code,name,source_id) values"
                   " ('tank','Tank',1) on conflict (code) do nothing")
        cx.execute("insert into subroles (role_id,code,name,passive_description,source_id)"
                   " select role_id,'x','X','',1 from roles where code='tank'"
                   " on conflict (code) do nothing")
        cx.execute("insert into heroes (slug,name,role_id,subrole_id,source_id)"
                   " select 'mei','Mei',role_id,subrole_id,1"
                   " from subroles where code='x'"
                   " on conflict (slug) do nothing")
        cx.commit()
    with pytest.raises(SystemExit, match="`update` is the verb"):
        run(cluster)("inflate")
    assert run(cluster)("update") == ["update"]   # update still welcome


def test_rebuild_refuses_a_partial_selection(run, cluster):
    with pytest.raises(SystemExit, match="always runs every pipeline"):
        run(cluster)("rebuild", "--type", "heuristic")


def test_update_on_a_truly_empty_database_points_at_a_builder(run, fresh):
    pgserver.get_server(fresh)            # cluster exists, zero tables
    with pytest.raises(SystemExit, match="rebuild"):
        run(fresh)("update")
