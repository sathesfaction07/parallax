# Architecture

## The shape of the problem

A discrepancy is a **conclusion**. What arrives is two rows. The distance between those two things
is where every wrong answer comes from, so the module layout is that distance, in order:

```
  data/system_a.csv      data/system_b.csv
        │                       │
        └───────────┬───────────┘
                    ▼
              ingest.py          reads rows, and records what each row FAILED to say
                    │            (blank values, missing times, mixed tz, duplicate keys)
                    ▼
             pairing.py          who gets compared with whom, and how many rows there were
                    │            -> Pairing: ONE_TO_ONE | ONE_SIDED | MULTIPLIED
                    ▼
              [ is a comparison even DEFINED for this entity? ]
                    │
                    ▼
             classify_presence   did both sides record anything?
                    │            -> Presence: BOTH | RECORDED_EMPTY | ONE_SILENT | NEITHER
                    ▼
              [ do the two values differ? ]  <- the whole of what a comparator knows
                    │
                    ▼
            ordering.py          can these be sequenced at all?
                    │            -> Order: ORDERED | TIED | INCOMPARABLE | UNTIMED
                    ▼
           influence.py          could the later decider have KNOWN?
                    │            -> Influence: COULD_HAVE_SEEN | COULD_NOT | UNKNOWABLE
                    ▼
            classify.py          name the cause, or admit the evidence cannot
                    │            -> Cause: CONFLICT | TRANSITION | RACE | STALE | UNSEPARABLE
                    ▼
               rules.py          exclusions run LAST, where they can be counted
                    │            -> suppressed, listed, never deducted
                    ▼
            severity.py          an invented number, for ordering a list
                    │
                    ▼
     analyse.py -> render.py / gate.py
```

Every arrow is a place where a naive implementation would have said "these disagree" and moved on.

## Why the rules run last

The brief asks for exception rules *before flagging*. They are here, and they run **after
everything else**, for a reason that is structural rather than stylistic:

A rule inspects a pair. By the time a pair exists, four decisions have already been made — which
rows to compare, whether silence counts as a value, which decision came first, and whether the
later decider knew. Those four are precisely what distinguishes a conflict from a transition. **A
rule cannot see any of them.**

Running the rules last does not fix that. It makes it visible: `rules` prints what each exclusion
removed, so the filtering is auditable rather than invisible.

## The enums are the design

Five enums, none of them a boolean, and that is the point. Each one names a way of *not knowing*
that a bool would have collapsed into a wrong answer:

| enum | the collapse it prevents |
|:--|:--|
| `Pairing` | "we compared them" hides that we *chose* which row, or dropped one |
| `Presence` | "they differ" hides that one side said nothing at all |
| `Order` | "b is later" hides a tie, a timezone mismatch, and a missing timestamp |
| `Influence` | "b reversed a" hides that b could not have known about a |
| `Cause` | a fifth member, `UNSEPARABLE`, because four causes share one appearance |

`UNSEPARABLE` is not an error state and not a clean bill of health. It is the commonest honest
answer, and it is **reportable** — dropping it would be the defect the whole project is about.

## Validators refuse claims the evidence does not support

The models will not construct a verdict that overreaches:

```python
if self.cause is Cause.TRANSITION and self.order is not Order.ORDERED:
    raise ValueError("TRANSITION claims one decision came after another; that needs ORDER")

if self.cause is Cause.RACE and self.influence is not Influence.COULD_NOT_HAVE_SEEN:
    raise ValueError("RACE claims neither side saw the other; that needs INFLUENCE")
```

Same idea in `Decision` (a row that is not present cannot carry a value), in `Pair` (a
`MULTIPLIED` pairing must carry a sibling count), and in `Verdict` (a severity band must carry the
score it came from). The type system holds the argument, so it cannot drift out of the comments.

## Where the answer comes from outside the data

Three things decide the output and are not in the files. All three are settings, deliberately, so
they are arguable rather than buried:

| setting | what it is | if it is wrong |
|:--|:--|:--|
| `propagation_minutes` | how long news takes to travel | races read as reversals, or the reverse |
| `relation` | what the two systems are to each other | `CONFLICT` count goes 3 → 0 → 0 |
| `cached_sources` | which side is a copy rather than a decider | every difference explained away as lag |

`doctor` prints all three under a heading that says **invented, not measured**, next to a table of
what actually was measured. The two look identical in a report otherwise.

`relation` defaults to `UNDECLARED`, which produces *more* `UNSEPARABLE` and *zero* conflicts. That
is the honest default: a tool that guessed would be inventing its own headline.

## The gate's dividing line

`gate.py` asks one question about everything it finds: **can the person who produced these files
fix it in the files?**

```
FAILS (fixable at source)          REPORTS (not a defect in the files)
  duplicate entity keys              UNSEPARABLE causes
  aware and naive tz in one file     an undeclared relation
  no decision time                   suppressions
  unparseable timestamps             genuine simultaneity
  a row present with no value        ties that only appear under truncation
```

Verified in CI both ways: clean files with an unexplained difference **pass**, and a single
duplicate key **fails**. A gate that fires on things nobody can fix gets switched off inside a
week, so it does not fire on them.

## The corpus

`data/generate.py` is hand-authored, not randomised — 16 entities, each named for the outcome it
produces (`e04-tied`, `e05-naive-vs-aware`, `e16-cache-ahead`), so a reader can check the tool's
claim against the input by eye instead of trusting a seed.

The generator **owns** `data/` and prunes any CSV not in its manifest. A stale fixture written to
an older convention is exactly the kind of thing that parses cleanly and silently changes every
count, so CI plants one and asserts it gets removed.

`tests/unit/test_causes_and_reporting.py::TestTheCorpusStillProducesEveryOutcome` asserts that
every `Pairing`, every `Order`, and every `Cause` still appears somewhere. Without it, an
assertion elsewhere could quietly become vacuous.

## What is deliberately absent

- **No model, no network, no credentials.** The accuracy problem here is comparison semantics and
  arithmetic. A model would add a second thing to be wrong about.
- **No pandas.** The two join idioms this project is about are plain Python, which is what people
  actually write. `pd.merge` appears in exactly one file across the whole portfolio, so building
  the finding on it would have been building it on something nobody does here.
- **No `decision tree`,** despite the brief naming one. The branching in `classify` is four
  guards in a fixed order, and the order is the argument. A tree would obscure it.
- **No truncation before comparison.** `tie_risk` reports what truncating *would* cost and is
  never used to compare, because that would be committing the defect it measures.
