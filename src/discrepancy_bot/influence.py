"""Whether the later decider could have known about the earlier decision.

This is the question the word "reversal" actually asks, and it is not the question a timestamp
answers. A timestamp establishes SEQUENCE. "Reversal" claims INFLUENCE -- that the second decider
saw the first decision and overturned it. Two people deciding opposite things four minutes apart,
in systems that take an hour to sync, are ordered and have reversed nothing.

The propagation window is a configured number, not a measurement. It is the honest place to put
the assumption, because it makes the assumption arguable instead of invisible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from .models import Influence, Order, Pair
from .ordering import classify_order


@dataclass(frozen=True)
class InfluenceCall:
    """Whether influence was possible, and what the answer rests on."""

    influence: Influence
    gap: timedelta | None
    window: timedelta
    detail: str

    @property
    def is_a_reversal(self) -> bool:
        """Only COULD_HAVE_SEEN supports calling something a reversal."""
        return self.influence is Influence.COULD_HAVE_SEEN


def assess(pair: Pair, window: timedelta) -> InfluenceCall:
    """Decide whether the second decision could have been informed by the first.

    `window` is how long news takes to travel between the two systems. Inside it, the second
    decider cannot have known, so whatever happened was concurrent rather than corrective.
    """
    order, _ = classify_order(pair)
    if order is not Order.ORDERED:
        return InfluenceCall(
            influence=Influence.UNKNOWABLE,
            gap=None,
            window=window,
            detail=(
                f"Order is {order}, so there is no 'later' decision to ask about. Influence needs "
                "a sequence before it can need anything else."
            ),
        )

    assert pair.left is not None and pair.right is not None
    a, b = pair.left.decided_at, pair.right.decided_at
    assert a is not None and b is not None
    gap = abs(b - a)

    if gap > window:
        return InfluenceCall(
            influence=Influence.COULD_HAVE_SEEN,
            gap=gap,
            window=window,
            detail=(
                f"The decisions are {gap} apart and news takes {window} to travel, so the second "
                "decider COULD have seen the first. That makes 'reversal' a possible reading -- "
                "possible, not established. Being able to see something is not seeing it."
            ),
        )

    return InfluenceCall(
        influence=Influence.COULD_NOT_HAVE_SEEN,
        gap=gap,
        window=window,
        detail=(
            f"Only {gap} separates the two decisions, and news takes {window} to travel. The "
            "second decider CANNOT have known about the first, so nobody overturned anybody. "
            "This is a race, and it is ordered -- which is exactly why ordering is not enough."
        ),
    )


def window_is_a_guess(window: timedelta) -> str:
    """State plainly where the propagation window comes from."""
    return (
        f"The {window} propagation window is CONFIGURED, not measured. Nothing here observed how "
        "long news actually takes to travel between the two systems; if that number is wrong, "
        "races get read as reversals and reversals as races. It is exposed as a setting so the "
        "assumption can be argued with, which is the most that can be done about it here."
    )


def sensitivity(pair: Pair, windows: list[timedelta]) -> list[tuple[timedelta, Influence]]:
    """Re-ask the influence question at several windows.

    A verdict that changes when the guess changes is a verdict about the guess. Worth printing
    next to the answer.
    """
    return [(w, assess(pair, w).influence) for w in windows]


def verdict_depends_on_the_guess(pair: Pair, windows: list[timedelta]) -> bool:
    answers = {influence for _, influence in sensitivity(pair, windows)}
    return len(answers) > 1
