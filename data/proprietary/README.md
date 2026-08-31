# proprietary — the strategy layer

**Nothing is implemented here yet. This file is a description of intent, not
of code that exists.**

## What this tier is for

The other two tiers answer *what is true* about the game:

| tier | claim | example |
| --- | --- | --- |
| `data/authoritative` | what a source measured | Ana's biotic grenade has a 10s cooldown; Widowmaker wins 49.5% on Busan |
| `data/heuristic` | what a source judges | Winston is a dive hero; Zarya is countered by Sombra |

This tier answers *what we should do about it* — and, unlike the other two, its
input is **ours**, not scraped. A user writes strategies in whatever form suits
them: a paragraph of prose, a list of rules, a note about a team's tendencies, a
scribbled preference for brawl over poke. There is no schema to fill in.

A model then reads that alongside everything in the database — the roster and
its abilities, the map pool, the rates, the playbook of counters and best maps
— and infers a team composition.

```
COUNTER = MAX[ HEROES ∩ MAPS ∩ META ]
```

The other tiers supply the three sets. This tier supplies the objective
function: which maximum, for whom, under what constraints.

## Why it is a separate tier

Because its data cannot be re-scraped. Drop the database and rerun the
pipeline, and everything in the authoritative and heuristic tiers comes back
byte for byte. Anything written here does not — it exists only because someone
wrote it. That difference in provenance is the whole reason for the separation:
these are the rows that need backing up, and the ones a rebuild must never
silently discard.

It is also the only tier whose output is an *opinion the database produced*,
rather than an opinion it recorded. A heuristic row says "counterpick.gg thinks
Sombra beats Zarya". A proprietary row would say "given your strategy notes and
this map, play Sombra". Those want to be told apart when reading results back.

## What it will need, when it is built

Sketched here so the shape is not re-derived later. None of it exists:

- somewhere to keep user strategy input in free form, with its own provenance,
  since it is authored rather than read from a source
- a record of what a model was asked, what it was given, and what it answered,
  so a recommendation can be explained and reproduced rather than just trusted
- a link from a recommendation back to the rows that justified it — which
  counters, which rates, which map — so the reasoning is inspectable

## What has to be true first

A recommendation is only as good as the granularity underneath it. See
[docs/scaling.md](../../docs/scaling.md): today the meta is Americas, one
platform, all ranks combined, and whole maps rather than map stages. A team
composition for a specific stage, at a specific rank, on a specific platform is
not answerable from the current data — not because the model could not reason
about it, but because the numbers underneath are not sliced that finely yet.
