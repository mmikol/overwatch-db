"""The authoritative pipeline: what a source measured.

Blizzard and the wiki publish facts about the game - a roster, an ability's
cooldown, a hero's health, a map's modes, a win rate. Everything this tier
loads is treated as authoritative: if two sources disagree here, one of them is
wrong, and the disagreement is a bug to chase rather than an opinion to keep.

Ingest is shared, at data/sources, because a source is a source whatever a tier
makes of it. So this tier begins at extraction, and its stages are numbered in
the order they run:

    s1_extract -> s2_transform -> s3_load

The plumbing comes from the orchestrator above, so a stage imports its own tier
and gets all of it:

    from data.authoritative import pipeline

    parser = pipeline.build_parser(__doc__, ".cache-wiki")
    source_id = pipeline.register_source(cursor, WIKI, cao)

Run the whole tier on its own, or let the orchestrator run every tier:

    python -m data.authoritative.pipeline
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

# Re-exported so a stage imports its own tier and gets the plumbing with it.
__all__ = [
    "TIER",
    "build_parser",
    "export_raw",
    "lookup_ids",
    "main",
    "now",
    "prepare_cache",
    "register_source",
    "resolve_dsn",
]

TIER = "authoritative"


def main():
    parser = orchestrator.build_parser(__doc__)
    args, passthrough = parser.parse_known_args()
    args.tier, args.only = [TIER], None
    orchestrator.run_pipelines(args, passthrough)


if __name__ == "__main__":
    main()
