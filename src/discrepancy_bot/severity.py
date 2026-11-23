"""Severity scoring -- the second feature the brief asks for.

The weights below are invented. Nothing in this repository observed which discrepancies mattered,
because no outcome was ever recorded, so there is nothing to calibrate against. The number is
useful for putting a list in an order; it is not a measurement of anything, and `doctor` says so.

One thing worth more than the score itself: the ranking by severity and the ranking by
CONFIDENCE-IN-THE-CAUSE are different orders, and a reader takes them for the same one. A HIGH
severity UNSEPARABLE pair means "this looks expensive and we do not know what it is" -- which is
not what "HIGH" reads as.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Cause, Order, Pairing, Presence, Severity, Verdict

# Invented. Every one of these numbers is a guess about relative importance.
CAUSE_WEIGHT: dict[Cause, int] = {
    Cause.CONFLICT: 50,
    Cause.UNSEPARABLE: 30,
    Cause.RACE: 15,
    Cause.TRANSITION: 10,
    Cause.STALE: 5,
}

PAIRING_WEIGHT: dict[Pairing, int] = {
    Pairing.ONE_TO_ONE: 0,
    Pairing.ONE_SIDED: 10,
    Pairing.MULTIPLIED: 20,
}

ORDER_WEIGHT: dict[Order, int] = {
    Order.ORDERED: 0,
    Order.TIED: 10,
    Order.INCOMPARABLE: 15,
    Order.UNTIMED: 15,
}

PRESENCE_WEIGHT: dict[Presence, int] = {
    Presence.BOTH: 0,
    Presence.RECORDED_EMPTY: 10,
    Presence.ONE_SILENT: 10,
    Presence.NEITHER: 5,
}

HIGH_AT = 60
MEDIUM_AT = 30


def score(verdict: Verdict) -> int:
    """Add up the weights. That is all this is."""
    return (
        CAUSE_WEIGHT[verdict.cause]
        + PAIRING_WEIGHT[verdict.pairing]
        + ORDER_WEIGHT[verdict.order]
        + PRESENCE_WEIGHT[verdict.presence]
    )


def band(points: int) -> Severity:
    if points >= HIGH_AT:
        return Severity.HIGH
    if points >= MEDIUM_AT:
        return Severity.MEDIUM
    return Severity.LOW


def apply_severity(verdict: Verdict) -> Verdict:
    points = score(verdict)
    return verdict.model_copy(update={"score": points, "severity": band(points)})


def rank(verdicts: list[Verdict]) -> list[Verdict]:
    """Order by score, descending, then by entity for a stable result.

    The tie-break on entity name is arbitrary and is here so the output does not depend on input
    order -- the same trap this tool reports elsewhere.
    """
    scored = [apply_severity(v) for v in verdicts]
    return sorted(scored, key=lambda v: (-(v.score or 0), v.entity))


@dataclass(frozen=True)
class ScoreCollision:
    """Two verdicts with the same score and nothing else in common."""

    points: int
    entities: tuple[str, ...]
    causes: tuple[Cause, ...]

    def summary(self) -> str:
        return (
            f"{len(self.entities)} entities score exactly {self.points} with "
            f"{len(set(self.causes))} different causes ({', '.join(sorted(set(self.causes)))}). "
            "A weighted sum is not ordinal: equal scores do not mean comparable situations, so "
            "'work down the list' puts unrelated problems next to each other."
        )


def collisions(verdicts: list[Verdict]) -> list[ScoreCollision]:
    """Find scores shared by verdicts with different causes."""
    scored = [apply_severity(v) for v in verdicts]
    buckets: dict[int, list[Verdict]] = {}
    for v in scored:
        buckets.setdefault(v.score or 0, []).append(v)
    out = []
    for points, group in sorted(buckets.items(), reverse=True):
        if len(group) > 1 and len({v.cause for v in group}) > 1:
            out.append(
                ScoreCollision(
                    points=points,
                    entities=tuple(v.entity for v in group),
                    causes=tuple(v.cause for v in group),
                )
            )
    return out


def severity_and_confidence_disagree(verdicts: list[Verdict]) -> tuple[int, str]:
    """Count the pairs a reader is most likely to misread.

    A HIGH-severity UNSEPARABLE is the dangerous shape: it looks like "urgent and understood"
    and it means "expensive-looking and unexplained".
    """
    scored = [apply_severity(v) for v in verdicts]
    confusing = [
        v for v in scored if v.severity in (Severity.HIGH, Severity.MEDIUM)
        and v.cause is Cause.UNSEPARABLE
    ]
    if not confusing:
        return 0, "No high-severity unexplained differences in this batch."
    return len(confusing), (
        f"{len(confusing)} differences are scored MEDIUM or HIGH while their cause is "
        "UNSEPARABLE. Severity ranks how much it would matter IF it is real; it does not rank how "
        "sure we are that it is. Those are two orders and the report shows one."
    )


def weights_are_invented() -> str:
    return (
        f"Severity is a weighted sum of four enums with {len(CAUSE_WEIGHT) + len(PAIRING_WEIGHT) + len(ORDER_WEIGHT) + len(PRESENCE_WEIGHT)} "
        f"hand-chosen weights and two hand-chosen thresholds (MEDIUM at {MEDIUM_AT}, HIGH at "
        f"{HIGH_AT}). No outcome was ever recorded against these, so nothing here is calibrated. "
        "The score orders a list; it does not measure importance, and the units are nothing."
    )
