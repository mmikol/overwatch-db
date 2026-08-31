"""AUTHORITATIVE: what a source measured.

Cooldowns, health pools, win rates - facts about the game and about how it is
actually being played. If two sources disagree here, one of them is wrong.

Ingest is not a stage of this type: pages are acquired by data/sources, which
both types share. So the stages here are numbered from extraction:

    s1_extract/    pull structured data out of that markup
    s2_transform/  normalise and derive values
    s3_load/       persist to the database

    pipeline       the type's stage order, and the plumbing every stage shares
"""
