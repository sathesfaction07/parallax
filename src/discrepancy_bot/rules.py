"""Exclusion rules for known-legitimate patterns -- the brief's headline recommendation.

Built, because it was asked for. Two things stated up front, because they are properties of the
mechanism rather than of this implementation:

**A rule can only subtract.** It cannot add a discrepancy, so its only possible effect on the
report is a smaller number. There is no input on which turning rules on makes the tool find more.

**After a rule fires, a correct suppression and a missed discrepancy are the same thing** -- an
entity that does not appear in the report. So suppressions are counted and listed separately and
never folded into the clean total. That does not make the rules safe; it makes them auditable,
which is a smaller claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from .models import Cause, Verdict


@dataclass(frozen=True)
class Rule:
    """One known-legitimate pattern, and what it costs to trust it."""

    name: str
    causes: frozenset[Cause]
    reason: str
    what_it_hides: str

    def matches(self, verdict: Verdict) -> bool:
        return verdict.cause in self.causes


DEFAULT_RULES: tuple[Rule, ...] = (
    Rule(
        name="race-not-reversal",
        causes=frozenset({Cause.RACE}),
        reason=(
            "the two decisions fell inside the propagation window, so neither decider could have "
            "seen the other and nothing was overturned"
        ),
        what_it_hides=(
            "two people genuinely disagreeing who happened to act at the same time -- which is a "
            "real conflict that looks exactly like a race"
        ),
    ),
    Rule(
        name="stale-copy",
        causes=frozenset({Cause.STALE}),
        reason="one side is a declared cache, so there is only one decision here",
        what_it_hides=(
            "a cache that is wrong for a reason other than lag, and a source misdeclared as a "
            "cache when it is actually deciding things"
        ),
    ),
    Rule(
        name="ordered-supersession",
        causes=frozenset({Cause.TRANSITION}),
        reason=(
            "the sources are independent authorities and the later decision supersedes the earlier"
        ),
        what_it_hides=(
            "a later decision made in ignorance of the earlier one by someone who WOULD have "
            "decided differently had they seen it"
        ),
    ),
)


@dataclass(frozen=True)
class RuleOutcome:
    """What the rules did to a set of verdicts."""

    before: int
    kept: tuple[Verdict, ...]
    suppressed: tuple[tuple[Verdict, str], ...]

    @property
    def after(self) -> int:
        return len(self.kept)

    @property
    def removed(self) -> int:
        return len(self.suppressed)

    def by_rule(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for _, rule_name in self.suppressed:
            counts[rule_name] = counts.get(rule_name, 0) + 1
        return counts

    def summary(self) -> str:
        if not self.removed:
            return (
                f"{self.before} differences in, {self.after} out. No rule fired, so the rules "
                "changed nothing -- which is the only case in which they are provably harmless."
            )
        return (
            f"{self.before} differences in, {self.after} out. {self.removed} suppressed by "
            f"{len(self.by_rule())} rule(s). Every one of those is now indistinguishable from a "
            "discrepancy this tool failed to find, so they are listed rather than deducted."
        )


def apply_rules(verdicts: list[Verdict], rules: tuple[Rule, ...] = DEFAULT_RULES) -> RuleOutcome:
    """Filter verdicts through the rules, keeping the removals.

    UNSEPARABLE is never suppressible, and no rule declares it. That is deliberate: a rule that
    suppressed "we could not tell" would convert the tool's most honest output into silence.
    """
    kept: list[Verdict] = []
    suppressed: list[tuple[Verdict, str]] = []
    for verdict in verdicts:
        firing = next((r for r in rules if r.matches(verdict)), None)
        if firing is None or verdict.cause is Cause.UNSEPARABLE:
            kept.append(verdict)
        else:
            suppressed.append(
                (verdict.model_copy(update={"suppressed_by": firing.name}), firing.name)
            )
    return RuleOutcome(before=len(verdicts), kept=tuple(kept), suppressed=tuple(suppressed))


def rules_can_only_subtract(verdicts: list[Verdict], rules: tuple[Rule, ...] = DEFAULT_RULES) -> bool:
    """Verify the claim on real input instead of asserting it in a comment."""
    return apply_rules(verdicts, rules).after <= len(verdicts)


def unseparable_is_never_suppressed(rules: tuple[Rule, ...] = DEFAULT_RULES) -> bool:
    return all(Cause.UNSEPARABLE not in r.causes for r in rules)


def suppression_is_a_wager(outcome: RuleOutcome) -> str:
    """Say what each suppression stakes."""
    if not outcome.removed:
        return "Nothing was suppressed, so nothing was wagered."
    hidden = {name for _, name in outcome.suppressed}
    return (
        f"{outcome.removed} entities were removed from the report by {len(hidden)} rule(s). Each "
        "removal is a bet that the pattern really is legitimate, and the bet cannot be settled: "
        "the report no longer contains the case, so nobody will look at it, so nobody will find "
        "out. Rules are how a tool stops learning about the thing it filters."
    )


def window_sensitivity_note(window: timedelta) -> str:
    """The race rule inherits the propagation window's uncertainty."""
    return (
        f"The race-not-reversal rule fires on a {window} propagation window that was configured "
        "rather than measured. Widen it and more real conflicts get called races; narrow it and "
        "more races get reported as conflicts. The rule is exactly as good as that number."
    )
