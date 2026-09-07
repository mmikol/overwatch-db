"""The proprietary pipeline: what WE judge.

The other two types read the outside world. This one loads what was authored
here - starting with hero_synergies, our half of the playbook, written by hand
in synergies.csv because no source we accept publishes synergies at all.

That provenance is the whole character of this type: nothing in it can be
re-scraped, so its inputs are committed to the repo rather than cached, and a
rebuild recreates its tables from those files the same way it recreates
everything else from the page caches.

There is no ingest and no extract - the input is already ours, already
structured. The one stage is load:

    s3_load/user/synergies.py    synergies.csv -> hero_synergies

Runs last: it links to heroes the authoritative type loads.

    python -m data.proprietary.pipeline
"""

import orchestrator
from orchestrator import (  # the plumbing every stage in this type uses
    build_parser,
    export_raw,
    lookup_ids,
    now,
    prepare_cache,
    register_source,
    resolve_dsn,
)

# Re-exported so a stage imports its own type and gets the plumbing with it.
__all__ = [
    "TYPE",
    "build_parser",
    "export_raw",
    "lookup_ids",
    "main",
    "now",
    "prepare_cache",
    "register_source",
    "resolve_dsn",
]

TYPE = "proprietary"

# The sources row for hand-authored data. Declared here rather than in
# data/sources because there is nothing to fetch - the "url" is the file.
USER = ("user", "Hand-authored playbook", "data/proprietary/synergies.csv")


def main():
    parser = orchestrator.build_parser(__doc__)
    args, passthrough = parser.parse_known_args()
    args.type, args.only = [TYPE], None
    orchestrator.run_pipelines(args, passthrough)


if __name__ == "__main__":
    main()
