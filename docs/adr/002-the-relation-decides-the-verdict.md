# ADR 002 — The relation between two systems decides the verdict, and it is not in the data

**Status:** accepted
**Date:** 2026-09-18

## Context

This one surfaced while writing `classify.py`, not while planning it.

Having established order and influence, one case remained. Two systems, one entity, different
values. The decisions are six hours apart, news travels between the systems in an hour, so the
second decider could have seen the first. Order: established. Influence: possible. Values: differ.

Is that a conflict?

It turns out the evidence does not answer the question, and the missing piece is not another
column. It is **what the two systems are to each other**:

- If the right source is meant to **replicate** the left, then a difference that outlived the
  propagation window is a genuine conflict — they were supposed to converge and did not.
- If both systems are their **own authority**, the same difference is an ordinary supersession.
  Nothing is broken; a later decision replaced an earlier one, which is what deciding means.

Identical rows, identical timestamps, identical everything — and opposite verdicts. Measured on the
corpus:

```
                    CONFLICT  TRANSITION  RACE  STALE  UNSEPARABLE
  MIRROR                   3           0     2      0            9
  INDEPENDENT              0           3     2      0            9
  UNDECLARED               0           0     2      0           12
```

The count of things worth waking somebody for goes **3 → 0** on a declaration that appears nowhere
in either file.

## Decision

**Make the relation an explicit setting with three values, and refuse to guess.**

```python
class SourceRelation(StrEnum):
    MIRROR = "MIRROR"            # supposed to converge -> an ordered difference is a CONFLICT
    INDEPENDENT = "INDEPENDENT"  # own authorities      -> an ordered difference is a TRANSITION
    UNDECLARED = "UNDECLARED"    # nobody said          -> UNSEPARABLE
```

`UNDECLARED` is the **default**, and it produces zero conflicts and more `UNSEPARABLE`. `doctor`
lists it alongside the propagation window and the cache declaration under a heading that reads
*invented, not measured*. `compare-relations` exists purely to run the same files under all three
and print the table above, because the divergence is the finding.

`check` reports an undeclared relation but does **not** fail on it: declaring it is an operator's
job, not a data producer's, and declaring it wrongly is worse than leaving it alone.

## Consequences

**Good.** The tool cannot manufacture its own headline. A conflict count only exists once somebody
has taken responsibility for saying what these two systems are.

**Good.** It makes an ordinarily invisible assumption arguable. Every reconciliation tool has an
implicit answer to this question baked into whichever branch it took; this one has to say it out
loud.

**Good.** The ordering of guards falls out naturally. `RACE` is checked before the relation, so no
declaration can turn a four-minute gap into a conflict — nobody can overturn a decision they could
not have seen, whatever the systems are to each other.

**Bad.** The default is the least useful setting. Running this tool out of the box gives 12 of 14
differences as `UNSEPARABLE`, which will look like the tool does not work. It is doing the only
honest thing, but the first impression is poor.

**Bad.** A wrong declaration is worse than none, and nothing here can detect one. Declaring two
independent systems a `MIRROR` manufactures conflicts out of ordinary supersessions. The setting
shifts responsibility to a human without giving them a way to check themselves.

**Bad.** Two values is almost certainly too few. Real relationships include "mirror, but only for
these fields", "eventually consistent with a published SLA", and "one is authoritative on Tuesdays".
The enum is a coarse model, and a coarse model that has to be declared is at least visible.

## Alternatives

**Infer it from the data.** Tempting: if the two sources agree on 95% of entities, they are probably
a mirror. But that reasons from the outcome to the premise — a mirror that is badly broken agrees on
very little, and would be classified as independent, which suppresses exactly the conflicts it
should be raising. The inference is most wrong when the answer matters most.

**Assume MIRROR.** The usual implicit default in reconciliation tooling, and it produces the largest
conflict count, which reads as thorough. It also converts every legitimate supersession between
independent teams into an alert.

**Assume INDEPENDENT.** Produces the smallest count, and suppresses real replication failures. A
quiet report from a broken mirror is the worst outcome available.

**Per-entity relations.** More faithful, and it needs a mapping nobody has. Rejected as a bigger
version of the same problem: the answer would still come from a declaration, just a longer one.
