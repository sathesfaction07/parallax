"""Putting two decisions in sequence, when that is possible at all.

"Is this a real discrepancy or an expected state transition?" is a question about ORDER. So the
honest work is here, and most of it is about the ways order fails to exist:

- one timestamp aware, one naive -> Python REFUSES to compare, and forcing it shifts the instant
- equal timestamps -> no sequence, though a stable sort will hand you one anyway
- coarse precision -> manufactures ties that the raw data did not have
- no decision time -> nothing to order, and the read time is not a substitute
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .models import Decision, Order, Pair


def comparable(a: datetime, b: datetime) -> bool:
    """Whether these two timestamps can be compared without raising.

    A timezone-aware datetime and a naive one cannot. This is not a corner case when two
    systems export their own way: one writes an offset, the other writes local wall time.
    """
    return (a.tzinfo is None) == (b.tzinfo is None)


def force_comparable(a: datetime, b: datetime) -> tuple[datetime, datetime, timedelta | None]:
    """Strip the offset so the comparison runs, and report what that cost.

    This is the fix people reach for, and it moves the aware timestamp by its offset. The shift
    is returned so it can be printed rather than absorbed.
    """
    if comparable(a, b):
        return a, b, None
    aware = a if a.tzinfo is not None else b
    offset = aware.utcoffset() or timedelta(0)
    return (
        a.replace(tzinfo=None) if a.tzinfo is not None else a,
        b.replace(tzinfo=None) if b.tzinfo is not None else b,
        offset,
    )


def same_instant(a: datetime, b: datetime) -> bool:
    """Whether these denote the same moment, offsets accounted for."""
    if not comparable(a, b):
        return False
    return a == b


def same_text(a: datetime, b: datetime) -> bool:
    """Whether these two timestamps are the same STRING.

    Kept separate on purpose. `12:00+00:00` and `07:00-05:00` are one instant and two strings,
    so a tool that compares timestamps as text reports a difference that is not there.
    """
    return a.isoformat() == b.isoformat()


def classify_order(pair: Pair) -> tuple[Order, str]:
    """Say whether these two decisions can be sequenced, and how confidently."""
    left, right = pair.left, pair.right
    if left is None or right is None:
        return Order.UNTIMED, "Only one side has a row, so there is no second time to order it against."
    if not left.timed or not right.timed:
        missing = [d.source for d in (left, right) if not d.timed]
        return Order.UNTIMED, (
            f"No decision time from {', '.join(missing)}. A read time will not substitute: it "
            "records when we LOOKED, and looking later does not make a decision newer."
        )

    a, b = left.decided_at, right.decided_at
    assert a is not None and b is not None
    if not comparable(a, b):
        _, _, offset = force_comparable(a, b)
        return Order.INCOMPARABLE, (
            f"One decision time carries a timezone and the other does not, so Python refuses to "
            f"compare them. Dropping the offset to force it moves that instant by {offset}, which "
            "is enough to invert the order."
        )
    if a == b:
        return Order.TIED, (
            "The two decision times are identical, so there is no sequence here. A stable sort "
            "will still put one first -- whichever arrived first in the input."
        )
    first = left if a < b else right
    return Order.ORDERED, (
        f"{first.source} decided first. This establishes SEQUENCE and nothing more; whether the "
        "second decider knew about the first is a separate question."
    )


@dataclass(frozen=True)
class TieRisk:
    """What truncating timestamps to a coarser unit does to orderability."""

    unit: str
    pairs: int
    tied_at_full: int
    tied_after: int

    @property
    def manufactured(self) -> int:
        return self.tied_after - self.tied_at_full

    def summary(self) -> str:
        if not self.pairs:
            return "No timed pairs, so nothing to lose."
        return (
            f"{self.pairs} timed pairs: {self.tied_at_full} tie at full precision, "
            f"{self.tied_after} tie once truncated to the {self.unit}. Truncation turned "
            f"{self.manufactured} orderable pairs into unorderable ones -- the data had the "
            "answer and the format threw it away."
        )


def tie_risk(pairs: list[Pair], unit: str = "day") -> TieRisk:
    """Count the ties that precision loss creates.

    Reports at the granularity people actually store: a date column instead of a timestamp is
    the commonest way a system stops being able to order its own decisions.
    """
    def truncate(d: datetime) -> datetime:
        if unit == "day":
            return d.replace(hour=0, minute=0, second=0, microsecond=0)
        if unit == "hour":
            return d.replace(minute=0, second=0, microsecond=0)
        if unit == "minute":
            return d.replace(second=0, microsecond=0)
        raise ValueError(f"unknown unit: {unit}")

    timed = [
        (p.left.decided_at, p.right.decided_at)
        for p in pairs
        if p.left is not None and p.right is not None and p.left.timed and p.right.timed
        and comparable(p.left.decided_at, p.right.decided_at)  # type: ignore[arg-type]
    ]
    full = sum(1 for a, b in timed if a == b)
    after = sum(1 for a, b in timed if truncate(a) == truncate(b))  # type: ignore[arg-type]
    return TieRisk(unit=unit, pairs=len(timed), tied_at_full=full, tied_after=after)


@dataclass(frozen=True)
class StableSortDemo:
    """The same tied rows, loaded two ways, sorted the same way."""

    as_loaded: str
    reversed_load: str

    @property
    def verdict_flips(self) -> bool:
        return self.as_loaded != self.reversed_load

    def summary(self) -> str:
        if not self.verdict_flips:
            return "No tie here, so input order does not decide anything."
        return (
            f"Loaded one way the latest decision is {self.as_loaded}; loaded the other way it is "
            f"{self.reversed_load}. Identical data, identical sort key, opposite conclusions. "
            "Python's sort is stable, so on a tie it preserves input order -- which means the "
            "answer is decided by the order the rows happened to arrive in."
        )


def stable_sort_demo(rows: list[Decision]) -> StableSortDemo:
    """Show that a tie hands the verdict to whoever loaded the file.

    Given rows with equal decision times, sorting picks a "latest" regardless, and it is
    whichever came last in the input.
    """
    def latest(items: list[Decision]) -> str:
        timed = [r for r in items if r.timed]
        if not timed:
            return "nothing timed"
        chosen = sorted(timed, key=lambda r: r.decided_at)[-1]  # type: ignore[arg-type,return-value]
        return f"{chosen.source}={chosen.value}"

    return StableSortDemo(as_loaded=latest(rows), reversed_load=latest(list(reversed(rows))))


def order_counts(pairs: list[Pair]) -> dict[Order, int]:
    counts = dict.fromkeys(Order, 0)
    for p in pairs:
        counts[classify_order(p)[0]] += 1
    return counts
