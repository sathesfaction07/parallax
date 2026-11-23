"""The vocabulary this tool reasons in.

A *discrepancy* is a conclusion, not an observation. What arrives is two rows. Getting from
two rows to "these disagree" means four questions have already been settled -- who to compare
with whom, whether both sides said anything, which came first, and whether the later decider
knew about the earlier one. Each has its own enum here, because collapsing any of them into a
bool is how the answer goes wrong quietly.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class Cause(StrEnum):
    """Why two records of one decision differ.

    All four produce the SAME observable value pair. Separating them needs evidence that is
    not in the pair, which is why UNSEPARABLE is here and is not an error.
    """

    CONFLICT = "CONFLICT"
    TRANSITION = "TRANSITION"
    RACE = "RACE"
    STALE = "STALE"
    UNSEPARABLE = "UNSEPARABLE"


CAUSE_NOTES: dict[Cause, tuple[str, str]] = {
    Cause.CONFLICT: (
        "both decisions are current and genuinely incompatible",
        "This is the only one worth anyone's morning.",
    ),
    Cause.TRANSITION: (
        "the later decision legitimately superseded the earlier one",
        "Needs DECISION times. A read time cannot establish it.",
    ),
    Cause.RACE: (
        "both decided independently, inside each other's propagation window",
        "Nobody overturned anybody. Needs to know how long news takes to travel.",
    ),
    Cause.STALE: (
        "one row is an old copy, so there is only ONE decision here",
        "Needs to know whether a row is a decision or a cache of one.",
    ),
    Cause.UNSEPARABLE: (
        "the evidence present cannot distinguish the four above",
        "NOT an error, and not a clean bill of health. The commonest honest answer.",
    ),
}


class Pairing(StrEnum):
    """What happened when we tried to line up one entity's rows across two sources."""

    ONE_TO_ONE = "ONE_TO_ONE"
    ONE_SIDED = "ONE_SIDED"
    MULTIPLIED = "MULTIPLIED"


PAIRING_NOTES: dict[Pairing, str] = {
    Pairing.ONE_TO_ONE: "exactly one row each side -- the only case a comparison is defined for",
    Pairing.ONE_SIDED: "rows on one side only, so there is nothing to compare it WITH",
    Pairing.MULTIPLIED: (
        "more than one row on a side, so 'the decision in that system' is not a single value"
    ),
}


class Presence(StrEnum):
    """Whether each side actually recorded a decision.

    The distinction that matters: RECORDED_EMPTY is a row that exists and says nothing, which
    a CSV round trip cannot tell apart from a row that says nothing because nothing was typed.
    """

    BOTH = "BOTH"
    RECORDED_EMPTY = "RECORDED_EMPTY"
    ONE_SILENT = "ONE_SILENT"
    NEITHER = "NEITHER"


class Order(StrEnum):
    """Whether the two decisions can be put in sequence at all."""

    ORDERED = "ORDERED"
    TIED = "TIED"
    INCOMPARABLE = "INCOMPARABLE"
    UNTIMED = "UNTIMED"


ORDER_NOTES: dict[Order, str] = {
    Order.ORDERED: "the timestamps differ, so sequence is established (sequence, not influence)",
    Order.TIED: (
        "the timestamps are equal, so there is no sequence -- and a stable sort will hand you "
        "one anyway, decided by the order the rows arrived in"
    ),
    Order.INCOMPARABLE: (
        "one timestamp is timezone-aware and one is not, so Python REFUSES to compare them; "
        "stripping the offset to force it shifts the instant by the offset"
    ),
    Order.UNTIMED: "at least one side carries no decision time, so nothing can be ordered",
}


class Influence(StrEnum):
    """Whether the later decider could have known about the earlier decision.

    This is the question "reversal" actually asks, and no timestamp answers it.
    """

    COULD_HAVE_SEEN = "COULD_HAVE_SEEN"
    COULD_NOT_HAVE_SEEN = "COULD_NOT_HAVE_SEEN"
    UNKNOWABLE = "UNKNOWABLE"


class Severity(StrEnum):
    """How much a reported discrepancy is claimed to matter.

    The thresholds are invented. See `severity.py`; nothing here is calibrated against an
    outcome, because no outcome was ever recorded.
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNSCORED = "UNSCORED"


class Decision(BaseModel):
    """One system's record of one decision about one entity."""

    model_config = {"frozen": True}

    entity: str = Field(min_length=1)
    source: str = Field(min_length=1)
    value: str | None = None
    decided_at: datetime | None = None
    read_at: datetime | None = None
    team: str | None = None
    row_present: bool = True

    @model_validator(mode="after")
    def _absent_rows_say_nothing(self) -> Decision:
        if not self.row_present and (self.value is not None or self.decided_at is not None):
            raise ValueError("a row that is not present cannot carry a value or a decision time")
        return self

    @property
    def said_nothing(self) -> bool:
        """True when this side carries no decision value.

        An empty string counts. That is not fussiness: `csv.DictReader` turns both a missing
        value and an explicitly empty one into `""`, so by the time a row is read the two are
        already the same thing.
        """
        return self.value is None or self.value.strip() == ""

    @property
    def timed(self) -> bool:
        return self.decided_at is not None


class Pair(BaseModel):
    """Two sides lined up for one entity, before any conclusion is drawn."""

    model_config = {"frozen": True}

    entity: str = Field(min_length=1)
    left: Decision | None = None
    right: Decision | None = None
    pairing: Pairing
    siblings: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _pairing_matches_the_sides(self) -> Pair:
        both = self.left is not None and self.right is not None
        if self.pairing is Pairing.ONE_SIDED and both:
            raise ValueError("ONE_SIDED requires exactly one side to be absent")
        if self.pairing is not Pairing.ONE_SIDED and not both:
            raise ValueError(f"{self.pairing} requires both sides")
        if self.pairing is Pairing.MULTIPLIED and self.siblings == 0:
            raise ValueError("MULTIPLIED means other rows exist, so siblings must be > 0")
        return self

    @property
    def values_differ(self) -> bool:
        """Whether the two recorded values are unequal.

        This is the whole of what a value comparison knows, and it is not a discrepancy.
        """
        if self.left is None or self.right is None:
            return False
        return self.left.value != self.right.value


class Verdict(BaseModel):
    """What we concluded, and how much of it the evidence actually supports."""

    model_config = {"frozen": True}

    entity: str = Field(min_length=1)
    cause: Cause
    pairing: Pairing
    presence: Presence
    order: Order
    influence: Influence
    severity: Severity = Severity.UNSCORED
    score: int | None = None
    detail: str = ""
    suppressed_by: str | None = None

    @model_validator(mode="after")
    def _no_claim_beyond_the_evidence(self) -> Verdict:
        if self.cause is Cause.TRANSITION and self.order is not Order.ORDERED:
            raise ValueError("TRANSITION claims one decision came after another; that needs ORDER")
        if self.cause is Cause.RACE and self.influence is not Influence.COULD_NOT_HAVE_SEEN:
            raise ValueError("RACE claims neither side saw the other; that needs INFLUENCE")
        if self.severity is Severity.UNSCORED and self.score is not None:
            raise ValueError("UNSCORED must not carry a score")
        if self.severity is not Severity.UNSCORED and self.score is None:
            raise ValueError(f"{self.severity} was computed from a score, so record it")
        return self

    @property
    def reportable(self) -> bool:
        """Whether this would appear in front of a person.

        UNSEPARABLE is reportable. That is the point of it -- an unexplained difference is
        news, and dropping it because we could not name the cause would be the whole defect.
        """
        return self.suppressed_by is None and self.cause is not Cause.STALE
