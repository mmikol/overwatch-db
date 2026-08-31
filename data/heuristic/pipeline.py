"""The heuristic pipeline: what a source judges.

Where the authoritative tier records what a source measured - a cooldown, a
health pool, a win rate - this tier records what a source *thinks*. Which
playstyle a hero belongs to. Which hero answers which. Which maps a hero is
strongest on. Nobody publishes those as measurements, because they are not
measurements: they move with a community's read of the meta rather than with a
patch, and two sources can disagree without either being wrong.

The split follows the claim, not the source. The wiki appears in both tiers -
its ability numbers are facts, its playstyle assignments are opinions - which
is exactly why ingest is shared at data/ingest rather than owned by a tier.

    wiki          which playstyle each hero belongs to
    counterpick   who counters whom, and where, by region

Stages are numbered in the order they run:

    s1_extract -> s2_transform -> s3_load

This tier links to the heroes, maps and regions the authoritative tier loads,
so it runs after it. The orchestrator already orders them that way; running
this tier alone against an empty database loads nothing and says so.

    python -m data.heuristic.pipeline
"""

from data import orchestrator
from data.orchestrator import (  # the plumbing every stage in this tier uses
    build_parser,
    export_raw,
    lookup_ids,
    now,
    prepare_cache,
    register_source,
    resolve_dsn,
)

TIER = "heuristic"


def main():
    parser = orchestrator.build_parser(__doc__)
    args, passthrough = parser.parse_known_args()
    args.tier, args.only = [TIER], None
    orchestrator.run_pipelines(args, passthrough)


if __name__ == "__main__":
    main()
