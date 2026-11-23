# ADR 001 — A discrepancy is a conclusion, and four causes share one appearance

**Status:** accepted
**Date:** 2026-09-18

## Context

The brief asks: *is this a real discrepancy or an expected state transition?* and proposes a
decision tree with exception rules for known-legitimate reversal patterns, applied before flagging.

Building that directly means writing a comparator that flags differing values, then a filter that
removes the ones matching a legitimate pattern. Which raised the question of what a rule can
actually see.

Four different situations produce the identical observable pair `("APPROVED", "REJECTED")`:

- **CONFLICT** — both decisions are current and genuinely incompatible
- **TRANSITION** — the later one legitimately superseded the earlier
- **RACE** — both decided independently, inside each other's propagation window
- **STALE** — one row is an old copy, so there is only one decision here

Probed: the number of distinguishable value pairs across all four is **one**. A comparator that
sees only values cannot separate them, and a rule downstream sees only what the comparator passed
it.

What separates them lives outside the pair:

| cause | needs |
|:--|:--|
| TRANSITION | decision times — and the timestamp usually available is the *read* time |
| RACE | the propagation window between the two systems |
| STALE | whether a row is a decision or a copy of one |

## Decision

**Model the preconditions explicitly, in order, and make "cannot tell" a first-class outcome.**

1. `Pairing` before comparison — who gets compared with whom, and how many rows there were
2. `Presence` before difference — did both sides record anything at all
3. `Order` before cause — can these be sequenced
4. `Influence` before "reversal" — could the later decider have known
5. `Cause`, including **`UNSEPARABLE`**

`UNSEPARABLE` is returned when the evidence does not distinguish the four. It is **reported, not
dropped, and never suppressible by a rule.** Model validators refuse a `TRANSITION` without an
established order and a `RACE` without established non-influence, so the type system holds the
argument.

The exception rules are built, and run **last**, after everything they cannot see has been
recorded.

## Consequences

**Good.** The commonest output is honest. On the corpus with nothing declared: 14 differences, 2
with a named cause, 12 `UNSEPARABLE`. A tool reporting "14 discrepancies" would have been wrong in
a way nobody could detect from the output.

**Good.** The brief's "multiple teams working on the same entity" turns out to be a *pairing*
failure, which the rules provably cannot reach — and pairing now reports its cardinality rather
than assuming it.

**Bad.** 12 of 14 unexplained is not a satisfying headline, and a reader who wanted a number of
discrepancies gets a number plus a caveat. That is the correct trade, but it is a trade.

**Bad.** `STALE` requires a source to be *declared* a cache. Nothing in a row says it is a copy, so
this rests entirely on configuration. One guard exists — a cache holding the *newer* value is
reported rather than suppressed, because a copy cannot get ahead of the thing it copies — and it
was only added after the first implementation checked the cache before ordering and swallowed 8 of
13 differences into `STALE`, including the race.

## Alternatives

**Default the ambiguous case to CONFLICT.** Safer-sounding, and it inflates the only number anyone
acts on. A report whose headline is mostly false positives gets ignored, which is worse than a
report that says it does not know.

**Default it to clean.** Silently drops the cases most worth seeing. This is the failure the whole
project is about.

**A confidence score instead of an enum.** A single number would blend "cannot be sequenced" with
"could be a race" with "the relation was never declared" — different problems needing different
fixes. The enum keeps them nameable, and severity is scored separately and labelled invented.
