"""What `check` fails on, and what it merely reports.

The line is drawn at one place: **can the person who produced these files fix it in the files?**

A duplicate entity key, a timestamp nobody recorded, an unparseable date, two timezone
conventions in one export -- all fixable at source, all gated.

An UNSEPARABLE cause is not. It needs a relation declaration, or a measured propagation window,
or knowledge of which side is a copy, and none of those live in a CSV. Gating on it would fail
every honest run, and a gate that fails every run gets switched off inside a week.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .analyse import Analysis
from .classify import SourceRelation
from .models import Cause


@dataclass
class Gate:
    """The result of checking one analysis."""

    failures: list[tuple[str, str]] = field(default_factory=list)
    reported: list[tuple[str, str]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    def summary(self) -> str:
        if self.passed:
            return (
                f"PASS. Nothing fixable at source. {len(self.reported)} thing(s) are reported "
                "below and deliberately not failed on -- they are properties of the situation, "
                "not defects in the files."
            )
        return (
            f"FAIL on {len(self.failures)} thing(s) a data producer can fix in their own export. "
            f"{len(self.reported)} further thing(s) are reported and NOT failed on."
        )


def check(analysis: Analysis) -> Gate:
    """Gate on the input files; report on everything else."""
    gate = Gate()

    for side in (analysis.left, analysis.right):
        if side.duplicate_entities:
            names = ", ".join(sorted(side.duplicate_entities)[:3])
            gate.failures.append(
                (
                    f"{side.source}: {len(side.duplicate_entities)} entity key(s) appear more than once",
                    f"({names}) -- so 'the decision in this system' is not a single value, and "
                    "whichever row gets compared was chosen by the join rather than by anyone. "
                    "Fixable: give each decision its own key, or export one row per entity.",
                )
            )
        if side.mixed_timezone_discipline:
            gate.failures.append(
                (
                    f"{side.source}: {len(side.aware_times)} aware and {len(side.naive_times)} "
                    "naive timestamps in ONE file",
                    "Python refuses to compare the two, so some pairs cannot be ordered at all. "
                    "Fixable: pick one convention per export, preferably UTC with an offset.",
                )
            )
        if side.missing_decided_at:
            gate.failures.append(
                (
                    f"{side.source}: {len(side.missing_decided_at)} row(s) carry no decision time",
                    "Without one, nothing can be ordered, so a conflict cannot be told from a "
                    "transition. A read time is not a substitute. Fixable: record when the "
                    "decision was made.",
                )
            )
        if side.unparseable_times:
            gate.failures.append(
                (
                    f"{side.source}: {len(side.unparseable_times)} timestamp(s) could not be parsed",
                    "These were treated as missing, which is the safe reading and also a silent "
                    "downgrade. Fixable: write ISO 8601.",
                )
            )
        if side.blank_values:
            gate.failures.append(
                (
                    f"{side.source}: {len(side.blank_values)} row(s) exist with no decision value",
                    "A row that says nothing is not the same as no row, but a CSV round trip "
                    "cannot tell them apart. Fixable: omit the row, or write an explicit value "
                    "such as PENDING.",
                )
            )

    unseparable = analysis.by_cause[Cause.UNSEPARABLE]
    if unseparable:
        gate.reported.append(
            (
                f"{unseparable} difference(s) are UNSEPARABLE",
                "The evidence present does not distinguish a conflict from a transition, a race "
                "or a stale copy. Not a defect in the files and not fixable by their producer, so "
                "not gated. It is the honest state of the question.",
            )
        )

    if analysis.relation is SourceRelation.UNDECLARED:
        gate.reported.append(
            (
                "the source relation is UNDECLARED",
                "So no difference can be called a CONFLICT, because the same evidence reads as a "
                "transition between independent authorities. Declaring it is an operator's job, "
                "not a data producer's -- and declaring it wrongly is worse than leaving it.",
            )
        )

    if analysis.suppressed:
        gate.reported.append(
            (
                f"{analysis.suppressed} difference(s) were suppressed by rules",
                "Each is now indistinguishable from a discrepancy the tool failed to find. Listed "
                "rather than deducted, and never gated on -- gating on a suppression would be "
                "gating on our own filter.",
            )
        )

    if analysis.ties and analysis.ties.tied_at_full:
        gate.reported.append(
            (
                f"{analysis.ties.tied_at_full} pair(s) tie at FULL precision",
                "Genuine simultaneity, not a formatting problem. Nobody can fix this in an export; "
                "the two decisions really did happen at the same recorded moment.",
            )
        )

    if analysis.ties and analysis.ties.manufactured:
        gate.reported.append(
            (
                f"{analysis.ties.manufactured} pair(s) would tie if truncated to the "
                f"{analysis.ties.unit}",
                "Diagnostic only -- this tool never truncates before comparing. It is here "
                "because a downstream report that groups by date will lose the ordering these "
                "files still have.",
            )
        )

    if analysis.undefined_comparisons:
        gate.reported.append(
            (
                f"{analysis.undefined_comparisons} entity comparison(s) are not even defined",
                "One-sided or multiplied pairings. The one-sided ones may be perfectly correct -- "
                "an entity can legitimately exist in one system only.",
            )
        )

    return gate
