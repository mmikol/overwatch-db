"""HEURISTIC: what a source judges.

Which playstyle a hero belongs to, which hero answers which, where a hero is
strongest. Nobody measures these, so two sources can disagree without either
being wrong.

Ingest is not a stage of this tier: pages are acquired by data/sources, which
both tiers share. So the stages here are numbered from extraction:

    s1_extract/    pull structured data out of that markup
    s2_transform/  normalise and derive values
    s3_load/       persist to the database

    pipeline       the tier's stage order, and the plumbing every stage shares
"""
