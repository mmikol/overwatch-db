"""The data pipeline: ingest, extract, transform, load.

    ingest/     acquire pages from a source, and cache them
    extract/    pull structured data out of that markup
    transform/  normalise and derive values
    load/       persist to the database

    orchestrator   runs the stages in order, owns the schema and the CSV
                   export, and holds the CLI plumbing every stage shares
"""
