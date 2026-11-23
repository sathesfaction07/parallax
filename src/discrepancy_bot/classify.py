"""Naming the cause of a difference, or admitting the evidence cannot.

Four causes produce one observable value pair. Separating them takes evidence that lives outside
the pair, and this module is explicit about which piece each one needs:

    TRANSITION  needs order       -- which decision came second
    RACE        needs influence   -- whether the second decider could have known
    STALE       needs provenance  -- whether a row is a decision or a copy of one
    CONFLICT    needs a RELATION  -- whether these two systems were supposed to agree

That last one surfaced while writing this file and is worth stating plainly. Given two systems
that legitimately hold their own views, an ordered difference is just a transition. Given a mirror
that is supposed to replicate, the same ordered difference is a conflict. **The identical evidence
supports opposite verdicts depending on a relationship between the systems that appears nowhere in
the data.** So the relation is declared in configuration, and when it is not declared the answer
is UNSEPARABLE rather than a default.
"""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum

from .influence import assess
from .models import Cause, Influence, Order, Pair, Presence, Verdict
from .ordering import classify_order
from .pairing import comparison_is_defined


class SourceRelation(StrEnum):
    """What the two systems are to each other."""

    MIRROR = "MIRROR"
    INDEPENDENT = "INDEPENDENT"
    UNDECLARED = "UNDECLARED"


RELATION_NOTES: dict[SourceRelation, str] = {
    SourceRelation.MIRROR: (
        "the right source is supposed to replicate the left, so a difference that outlived the "
        "propagation window is a CONFLICT -- they were meant to converge and did not"
    ),
    SourceRelation.INDEPENDENT: (
        "both systems are their own authority, so an ordered difference is a TRANSITION -- the "
        "second decision superseded the first and nothing is broken"
    ),
    SourceRelation.UNDECLARED: (
        "nobody said what these systems are to each other, so the SAME evidence supports either "
        "reading. Defaulting would be inventing the answer, so this stays UNSEPARABLE"
    ),
}


def classify_presence(pair: Pair) -> Presence:
    """Whether both sides recorded a decision at all."""
    left, right = pair.left, pair.right
    if left is None or right is None:
        return Presence.ONE_SILENT
    silent = [d for d in (left, right) if d.said_nothing]
    if len(silent) == 2:
        return Presence.NEITHER
    if len(silent) == 1:
        return Presence.RECORDED_EMPTY if silent[0].row_present else Presence.ONE_SILENT
    return Presence.BOTH


def classify(
    pair: Pair,
    window: timedelta,
    relation: SourceRelation = SourceRelation.UNDECLARED,
    cached_sources: frozenset[str] = frozenset(),
) -> Verdict | None:
    """Explain one pair, or return None when there is nothing to explain.

    None means the two recorded values match. It is not a guarantee that all is well -- it is a
    statement about two strings.
    """
    presence = classify_presence(pair)
    order, order_detail = classify_order(pair)
    call = assess(pair, window)

    def verdict(cause: Cause, detail: str) -> Verdict:
        return Verdict(
            entity=pair.entity,
            cause=cause,
            pairing=pair.pairing,
            presence=presence,
            order=order,
            influence=call.influence,
            detail=detail,
        )

    defined, why = comparison_is_defined(pair)
    if not defined:
        return verdict(Cause.UNSEPARABLE, why)

    if presence is not Presence.BOTH:
        return verdict(
            Cause.UNSEPARABLE,
            f"Presence is {presence}: at least one side recorded nothing. An inequality test says "
            "these differ, because `None != 'APPROVED'` is True -- but silence is not dissent, and "
            "reporting it as a disagreement would be a category error.",
        )

    if not pair.values_differ:
        return None

    if order is not Order.ORDERED:
        return verdict(
            Cause.UNSEPARABLE,
            f"Order is {order}, so the difference cannot be sequenced. {order_detail} Without a "
            "sequence, a transition and a conflict look identical -- and a stale copy cannot be "
            "identified either, because 'stale' means BEHIND and that needs a sequence.",
        )

    # A declared cache is not a decision-maker, so it cannot supersede and it cannot race.
    # But the claim "this is just lag" only holds if the cache is the side holding the OLDER
    # decision. A cache carrying a NEWER value than its source is not lag; it is a cache that
    # is not a copy of the thing it claims to copy, and suppressing that would hide the worse bug.
    assert pair.left is not None and pair.right is not None
    cached = [d for d in (pair.left, pair.right) if d.source in cached_sources]
    if cached:
        copy = cached[0]
        authority = pair.right if copy is pair.left else pair.left
        assert copy.decided_at is not None and authority.decided_at is not None
        if copy.decided_at < authority.decided_at:
            return verdict(
                Cause.STALE,
                f"{copy.source} is declared a cache rather than a decision-maker, and it holds the "
                f"OLDER decision, so this is lag: there is only ONE decision here. Note the claim "
                "rests entirely on the DECLARATION -- nothing in the row says it is a copy.",
            )
        return verdict(
            Cause.UNSEPARABLE,
            f"{copy.source} is declared a cache, but it holds the NEWER value. Lag cannot explain "
            "that: a copy cannot get ahead of the thing it copies. Either the declaration is "
            "wrong or the copy is being written to directly, and both are worse than the "
            "difference itself -- so this is not suppressed.",
        )

    if call.influence is Influence.COULD_NOT_HAVE_SEEN:
        return verdict(Cause.RACE, call.detail)

    if relation is SourceRelation.MIRROR:
        return verdict(
            Cause.CONFLICT,
            f"These sources are declared a MIRROR, so they were supposed to converge. {call.detail} "
            "They did not converge, which makes this a real conflict.",
        )

    if relation is SourceRelation.INDEPENDENT:
        return verdict(
            Cause.TRANSITION,
            f"These sources are declared INDEPENDENT authorities, so the later decision "
            f"legitimately supersedes the earlier one. {call.detail}",
        )

    return verdict(
        Cause.UNSEPARABLE,
        "The difference is ordered and the second decider could have seen the first, which is "
        "exactly where CONFLICT and TRANSITION become indistinguishable. "
        f"{RELATION_NOTES[SourceRelation.UNDECLARED]}.",
    )


def cause_counts(verdicts: list[Verdict]) -> dict[Cause, int]:
    counts = dict.fromkeys(Cause, 0)
    for v in verdicts:
        counts[v.cause] += 1
    return counts


def separability(verdicts: list[Verdict]) -> tuple[int, int, str]:
    """How much of the output actually names a cause.

    Returns (named, unseparable, sentence). The ratio is the honest headline: a tool that
    explains a third of what it finds should say which third.
    """
    unseparable = sum(1 for v in verdicts if v.cause is Cause.UNSEPARABLE)
    named = len(verdicts) - unseparable
    if not verdicts:
        return 0, 0, "No differences to explain."
    return (
        named,
        unseparable,
        f"{named} of {len(verdicts)} differences have a named cause; {unseparable} are "
        "UNSEPARABLE -- the evidence present does not distinguish a conflict from a transition, "
        "a race or a stale copy. Those are reported, not dropped.",
    )


def why_rules_are_too_late() -> str:
    """The brief's recommendation, and where it lands."""
    return (
        "The brief proposes exception rules for known-legitimate patterns BEFORE flagging. A rule "
        "inspects a pair -- so by the time it runs, the pairing has already been chosen, silence "
        "has already been folded in with dissent, and the order has already been decided (or "
        "invented by a stable sort). Those four things are what separate a conflict from a "
        "transition, and none of them is visible to a rule. The rules are not wrong; they are "
        "downstream of the question."
    )
