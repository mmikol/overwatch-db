"""EXTRACT: pulling structured data out of the markup ingest fetched.

One package per source, because the markup differs:

    blizzard/   their page HTML
    wiki/       Cargo's rendered values and article wikitext

Nothing here touches the network or the database. What comes out is source
data in Python form; normalising it is the transform stage.
"""
