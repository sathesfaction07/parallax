# Parallax

Two systems record decisions about the same items, and sometimes they disagree. Some of those
disagreements are real conflicts. Others are a reversal that has not propagated yet, two teams
acting at once, or one side that never recorded anything. Parallax compares the two,
explains every difference it can (pairing, presence, order and timing), and reports the ones it
cannot explain separately instead of calling them conflicts.

```bash
./setup.sh
```

---

## Conflict or Expected Transition Is a Question About Order

The requirements note this project started from described the problem like this:

> **Worst input:** legitimate decision reversals (policy changed), multiple teams working on the
> same entity, timing delays making it look like a conflict when it's just latency.
> **Accuracy concern:** is this a real discrepancy or an expected state transition?
> **Best approach:** decision tree with exception rules (known legitimate reversal patterns)
> before flagging.

The exception rules are built here, because they were asked for. But notice what the accuracy
concern is actually asking. *Conflict or expected transition?* is not a question about comparing
two values. Both readings produce **the same two values.** It is a question about **order**, and
underneath that, about **influence** — and neither is in the values being compared.

So the rules are not wrong. They are downstream of the question.

---

## A discrepancy is a conclusion, not an observation

What arrives is two rows. Getting from two rows to *"these disagree"* means four things have
already been settled, and each one fails in its own way:

| | question | how it fails |
|:--|:--|:--|
| **pairing** | are these two rows about the same thing, one each side? | one join idiom drops a decision, another multiplies rows |
| **presence** | did both sides actually record something? | `None != "APPROVED"` is `True`, so silence reads as dissent |
| **order** | which came first? | ties, timezone mismatches, and precision loss |
| **influence** | did the later decider know about the earlier one? | a timestamp gives sequence, never influence |

An exception rule inspects a pair. By the time a pair exists, all four have happened.

---

## Four causes, one observable pair

```
CONFLICT     both current, genuinely incompatible      <- the only one worth anyone's morning
TRANSITION   the later decision legitimately superseded
RACE         decided independently, neither saw the other
STALE        one row is an old copy; there is one decision
```

All four produce the identical pair `("APPROVED", "REJECTED")`. What separates them is not in it:

- **TRANSITION** needs decision times — not read times, because looking later does not make a
  decision newer
- **RACE** needs the propagation window between the two systems
- **STALE** needs to know whether a row is a decision or a copy of one

Which is why there is a fifth outcome, `UNSEPARABLE`, and why it is **reported rather than
dropped**. An unexplained difference is news. Discarding it because we could not name the cause
would be the whole defect.

On the corpus, with nothing declared: **14 differences, 2 with a named cause, 12 UNSEPARABLE.**

---

## And a fifth precondition, which surfaced while building it

Take a difference that is ordered, six hours apart, where the second decider could easily have
seen the first. Is it a conflict?

**It depends on what the two systems are to each other, and that is nowhere in the data.**

```
                    CONFLICT  TRANSITION  RACE  STALE  UNSEPARABLE
  MIRROR                   3           0     2      0            9
  INDEPENDENT              0           3     2      0            9
  UNDECLARED               0           0     2      0           12
```

The rows never changed. If the right source is supposed to *replicate* the left, a difference that
outlived the propagation window is a conflict — they were meant to converge and did not. If both
are their own authority, the same difference is an ordinary supersession and nothing is broken.

So the relation is declared in configuration, and when nobody declares it the answer stays
`UNSEPARABLE`. Defaulting would be inventing the answer.

---

## The findings

### 1. Silence reads as dissent

```python
None != "APPROVED"   # True
""   != "APPROVED"   # True
```

A naive difference check reports a disagreement about an entity where one system never recorded
anything. **SQL is the mirror image** — `NULL != 'APPROVED'` evaluates to `NULL`, so a `WHERE`
clause *drops* the row. Same intent, written two ways, opposite treatment of exactly the cases
most worth knowing about.

Neither is right. Silence is not dissent, and it is not agreement either.

### 2. Two ordinary join idioms fail in opposite directions

The project brief lists *"multiple teams working on the same entity"* as worst input and proposes to
handle it with exception rules. It is a **pairing** problem, and it happens before a rule can see
anything.

```python
{r.entity: r for r in rows}                        # keeps the LAST row, drops the rest
[(a, b) for a in left for b in right if ...]       # keeps everything, multiplies entities
```

On the corpus: **16 entities. The dict-index join produces 14 pairs and drops a decision for 2 of
them. The nested-loop join produces 16 pairs, multiplying 2 of them.** One undercounts, the other
overcounts, and neither says which it did — so *"we found N discrepancies"* is counting something
other than entities.

This tool emits one row per entity and records the cardinality instead of assuming it.

### 3. You cannot always compare two timestamps

```
aware < naive   ->   TypeError: can't compare offset-naive and offset-aware datetimes
```

Not a corner case when two systems export their own way: one writes an offset, the other writes
local wall time. And the reflex fix makes it worse — stripping the offset to force the comparison
**moves that instant by the offset**, which is enough to invert the order.

From the other side: `12:00+00:00` and `07:00-05:00` are one instant and two strings. Equal as
datetimes, **unequal as text** — so a tool comparing timestamps as strings reports a difference
that is not there.

### 4. Coarse precision manufactures ties

On the corpus: **11 timed pairs. 2 tie at full precision. 10 tie once truncated to the day** — so
truncation turned 8 orderable pairs into unorderable ones. The data had the answer and the format
threw it away.

This tool never truncates before comparing. It reports the number, because a downstream report
that groups by date will lose the ordering these files still have.

### 5. A tie is not an order, and input order decides the verdict

> Loaded one way the latest decision is `system-b=REJECTED`. Loaded the other way it is
> `system-a=APPROVED`.

Identical data, identical sort key, opposite conclusions. Python's `sort` is **stable**, so on a
tie it preserves input order — which means the answer is decided by the order the rows happened to
arrive in. Nothing in the output hints at that.

### 6. "Reversal" is a causal claim; a timestamp only gives sequence

| entity | gap | | |
|:--|:--|:--|:--|
| `e02-ordered-far` | 6:00:00 | `COULD_HAVE_SEEN` | a reversal is possible |
| `e03-race` | 0:04:00 | `COULD_NOT_HAVE_SEEN` | a race — nobody overturned anybody |

Both are ordered. Both differ. Only one of them is anybody overturning anything. With a one-hour
propagation window, two people deciding opposite things four minutes apart cannot have seen each
other — that is a race, and it is *ordered*, which is exactly why ordering is not enough.

And even the six-hour case is a verdict about the window: widen the window to a day and it becomes
a race too. `influence <entity>` re-asks the question at five windows and says when the answer
moves.

Note the ceiling honestly: `COULD_HAVE_SEEN` is the strongest thing available, and **being able to
see something is not seeing it.**

### 7. The CSV round trip destroys the distinction it needs

`csv.writer` writes `None` as an empty field. `csv.DictReader` reads both an empty field and a
missing one back as `""`.

```
None and "" written through csv, read back as '' and ''
distinguishable afterwards: False
```

So *"no decision was made"* and *"a decision was recorded as blank"* arrive identical, and
`"" != "APPROVED"` is `True`, so both get flagged. This is not fixable at read time — the
information left when the file was written. `check` gates on it as a producer-side defect.

### 8. An exclusion rule can only subtract

**14 differences in, 9 out. 5 suppressed by 2 rules.**

A rule cannot add a discrepancy, so its only possible effect is a smaller number. There is no
input on which turning the rules on makes the tool find more.

And after one fires, **a correct suppression and a missed discrepancy are the same thing** — an
entity absent from the report. Each removal is a bet that the pattern really is legitimate, and
the bet cannot be settled: the case has left the report, so nobody looks at it, so nobody finds
out. Rules are how a tool stops learning about the thing it filters.

So suppressions are counted, listed with the rule that removed them, and never deducted from the
clean total. That does not make them safe. It makes them auditable, which is a smaller claim.
`UNSEPARABLE` is never suppressible, and no rule declares it.

### 9. Severity ranks what would matter, not what we are sure of

The weights are invented. Nothing here observed which discrepancies mattered, because no outcome
was ever recorded, so there is nothing to calibrate against.

Two things worth more than the score:

**A weighted sum is not ordinal.** On the corpus, **5 entities score exactly 50 with 2 different
causes (CONFLICT and UNSEPARABLE)** — a real conflict and an unexplained difference at identical
severity. "Work down the list" puts unrelated problems next to each other.

**And it is the wrong order.** **9 differences score MEDIUM or HIGH while their cause is
UNSEPARABLE**, and the two highest-scoring items in the whole run are both unexplained. Severity
ranks how much something would matter *if it is real*; it does not rank how sure we are that it is.
Those are two orders and the report shows one.

---

## Commands

| | |
|:--|:--|
| `causes` | the four causes, what each needs, and the relation that flips the verdict |
| `pair` | line the rows up; both join idioms side by side |
| `order` | which pairs can be sequenced, and what precision loss would cost |
| `influence [entity]` | sequence versus influence, with a window sensitivity table |
| `report` | the run you would actually do; `-o DIR` also writes `report.json` |
| `compare-relations` | one dataset, three declarations |
| `rules` | apply the exclusions and list what they removed |
| `severity` | score and rank, and say what the score is worth |
| `explain <entity>` | walk one entity through all four steps in order |
| `doctor` | what was measured, what was invented |
| `check` | fail on what a data producer can fix; report everything else |

### `check` gates only on what an author can fix

**Fails on** a duplicate entity key, a naive timestamp mixed with aware ones in one file, a row
with no decision time, an unparseable timestamp, a row that exists with no decision value. All
five are fixable in the export.

**Reports and does not fail on** `UNSEPARABLE` causes, an undeclared relation, suppressions,
genuine simultaneity, and ties that only appear under truncation. None of those is a defect in the
files, and a gate that fires on things nobody can fix gets switched off inside a week.

Verified: clean files with an unexplained difference **pass**, and still report the difference.

---

## Honest limits

- **The propagation window is configured, never measured.** Nothing observed how long news
  actually takes to travel between the two systems. Widen it and real conflicts become races;
  narrow it and races become conflicts. It is a setting so the assumption can be argued with,
  which is the most that can be done here.
- **The source relation is declared, never discovered.** The conflict count rests on it entirely.
- **A cache is declared, never detected.** Nothing in a row says it is a copy. A real
  decision-maker mislabelled a cache has every difference explained away as lag. Only one guard
  exists: a cache holding the *newer* value is reported rather than suppressed, because a copy
  cannot get ahead of the thing it copies.
- **`COULD_HAVE_SEEN` is the ceiling.** Nothing here establishes that anyone actually read
  anything.
- **Severity is invented.** The units are nothing.
- **Rules cannot be evaluated.** Their effect on precision is unmeasurable, because measuring it
  would need the outcomes the suppression prevents anyone from collecting.
- **Nothing here fixes anything.** Record decision times, pick one timezone convention per export,
  give each decision its own key, and say what your two systems are to each other.

---

## Tests

**252 tests, 100% coverage** (`render.py` excluded — it prints; the claims live in the modules it
prints from).

The suite includes a class asserting the corpus still produces every outcome the other tests
assert about, so no assertion can quietly become vacuous. `data/generate.py` owns `data/` and
prunes anything not in its manifest.

```
tests/unit/test_preconditions.py         88   pairing, order, influence, the models
tests/unit/test_causes_and_reporting.py  99   causes, rules, severity, ingest, gate, corpus
tests/integration/test_cli.py            65   every command and the sentences it must say
```

---

## Five defects found while building this

**1. The cache check ran before ordering, and swallowed everything.** Declaring `system-b` a cache
turned **8 of 13** differences into `STALE`, including the race, the ties, and the untimed pairs.
"Stale" means *behind*, which requires a sequence — so the check now runs after ordering and
requires the cache to be the side holding the older decision.

**2. And a cache holding the newer value is not lag at all.** Falling out of that fix: a copy
cannot get ahead of the thing it copies, so that case is now reported rather than suppressed —
the declaration is wrong, or the copy is being written to directly, and both are worse than the
difference itself.

**3. `pair_up` shipped with an `if True else` artefact** — dead ternary left from an edit, which
worked by accident.

**4. `show_influence` called a helper with inverted logic** (`if not windows else []`), so the
sensitivity table would have been empty in every real call and populated only when there was
nothing to show.

**5. A test asserted the wrong thing about my own tool.** I expected the six-hour gap to hold
`COULD_HAVE_SEEN` across every window; it flips to a race at 24 hours. The code was right and the
expectation was wrong, which is the more interesting finding — the "obvious reversal" is also a
verdict about the window.
