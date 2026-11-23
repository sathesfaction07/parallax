"""Terminal output.

Excluded from coverage: it prints. The claims live in the modules it prints from.

One rule followed throughout: no number appears without the thing that qualifies it. A count of
discrepancies next to nothing else is the misleading artefact this whole project is about.
"""

from __future__ import annotations

from datetime import timedelta

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .analyse import Analysis
from .classify import (
    RELATION_NOTES,
    SourceRelation,
    separability,
    why_rules_are_too_late,
)
from .config import provenance
from .influence import InfluenceCall, window_is_a_guess
from .ingest import round_trip_loss
from .models import (
    CAUSE_NOTES,
    ORDER_NOTES,
    PAIRING_NOTES,
    Cause,
    Order,
    Pairing,
    Severity,
    Verdict,
)
from .ordering import StableSortDemo, TieRisk
from .pairing import IdiomComparison
from .rules import (
    DEFAULT_RULES,
    RuleOutcome,
    suppression_is_a_wager,
    window_sensitivity_note,
)
from .severity import (
    HIGH_AT,
    MEDIUM_AT,
    ScoreCollision,
    severity_and_confidence_disagree,
    weights_are_invented,
)

console = Console()

CAUSE_COLOUR = {
    Cause.CONFLICT: "red",
    Cause.UNSEPARABLE: "yellow",
    Cause.RACE: "cyan",
    Cause.TRANSITION: "green",
    Cause.STALE: "dim",
}

SEVERITY_COLOUR = {
    Severity.HIGH: "red",
    Severity.MEDIUM: "yellow",
    Severity.LOW: "green",
    Severity.UNSCORED: "dim",
}


def show_causes() -> None:
    console.print()
    console.print(
        Panel(
            "FOUR causes, ONE observable pair.\n\n"
            "A difference between two systems shows up as two values. Those same two values are\n"
            "produced by four different situations, and only one of them is worth waking anybody\n"
            "for. What separates them is not in the pair.",
            title="why a difference is not a discrepancy",
            border_style="blue",
        )
    )
    table = Table(show_header=True, header_style="bold blue")
    table.add_column("cause", style="bold")
    table.add_column("what it is")
    table.add_column("what it needs")
    for cause in Cause:
        what, needs = CAUSE_NOTES[cause]
        table.add_row(f"[{CAUSE_COLOUR[cause]}]{cause.value}[/]", what, needs)
    console.print(table)
    console.print()
    console.print(f"[dim]{why_rules_are_too_late()}[/dim]")
    console.print()


def show_relations() -> None:
    table = Table(title="and a fifth thing, which is not in the data at all",
                  show_header=True, header_style="bold blue")
    table.add_column("declared relation", style="bold")
    table.add_column("what the SAME ordered difference becomes")
    for relation in SourceRelation:
        table.add_row(relation.value, RELATION_NOTES[relation])
    console.print(table)
    console.print()
    console.print(
        "[yellow]The identical evidence supports opposite verdicts depending on a relationship "
        "between the two systems that appears nowhere in the rows.[/yellow]"
    )
    console.print()


def show_pairing(idioms: IdiomComparison, counts: dict[Pairing, int]) -> None:
    console.print()
    console.print("[bold]Lining the rows up, before anything is compared[/bold]")
    console.print()
    table = Table(show_header=True, header_style="bold blue")
    table.add_column("pairing")
    table.add_column("n", justify="right")
    table.add_column("what it means")
    for pairing in Pairing:
        table.add_row(pairing.value, str(counts[pairing]), PAIRING_NOTES[pairing])
    console.print(table)
    console.print()
    console.print(
        f"[dim]{idioms.left_rows} rows on the left, {idioms.right_rows} on the right, "
        f"{idioms.entities} distinct entities.[/dim]"
    )
    console.print()
    idiom_table = Table(title="two ordinary join idioms on this exact input",
                        show_header=True, header_style="bold blue")
    idiom_table.add_column("idiom")
    idiom_table.add_column("pairs", justify="right")
    idiom_table.add_column("failure mode")
    idiom_table.add_row(
        "{r.entity: r for r in rows}", str(idioms.dict_pairs),
        "keeps the LAST row per entity and drops the rest, silently",
    )
    idiom_table.add_row(
        "[(a, b) for a in L for b in R ...]", str(idioms.nested_pairs),
        "keeps everything, so one entity becomes several rows",
    )
    console.print(idiom_table)
    console.print()
    console.print(f"[yellow]{idioms.summary()}[/yellow]")
    console.print()


def show_order(counts: dict[Order, int], ties: TieRisk, demo: StableSortDemo) -> None:
    console.print()
    console.print("[bold]Putting two decisions in sequence, where that is possible[/bold]")
    console.print()
    table = Table(show_header=True, header_style="bold blue")
    table.add_column("order")
    table.add_column("n", justify="right")
    for order in Order:
        table.add_row(order.value, str(counts[order]))
    console.print(table)
    console.print()
    for order in Order:
        console.print(f"[dim]{order.value}:[/dim] {ORDER_NOTES[order]}")
    console.print()
    console.print(f"[yellow]{ties.summary()}[/yellow]")
    console.print()
    console.print("[bold]A tie is not an order, and something still has to give[/bold]")
    console.print(f"[yellow]{demo.summary()}[/yellow]")
    console.print()


def show_influence(
    entity: str, call: InfluenceCall, answers: list[tuple[timedelta, str]], flips: bool
) -> None:
    console.print()
    console.print(f"[bold]{entity}[/bold]")
    console.print(f"  influence: [bold]{call.influence.value}[/bold]")
    if call.gap is not None:
        console.print(f"  gap {call.gap}, propagation window {call.window}")
    console.print(f"  {call.detail}")
    console.print()
    table = Table(title="the same question, asked at other windows", show_header=True,
                  header_style="bold blue")
    table.add_column("window")
    table.add_column("answer")
    for window, answer in answers:
        table.add_row(str(window), answer)
    console.print(table)
    console.print()
    if flips:
        console.print(
            "[bold yellow]The answer changes with the window, so this verdict is a verdict about "
            "the guess.[/bold yellow]"
        )
    else:
        console.print("[dim]The answer holds across every window tried.[/dim]")
    console.print()
    console.print(f"[dim]{window_is_a_guess(call.window)}[/dim]")
    console.print()


def show_influence_table(rows: list[tuple[str, str, str, str]]) -> None:
    console.print()
    table = Table(title="sequence is not influence", show_header=True, header_style="bold blue")
    table.add_column("entity")
    table.add_column("gap")
    table.add_column("influence")
    table.add_column("reading")
    for entity, gap, influence, reading in rows:
        table.add_row(entity, gap, influence, reading)
    console.print(table)
    console.print()
    console.print(
        "[yellow]Ordering establishes SEQUENCE. The word 'reversal' claims INFLUENCE -- that the "
        "second decider saw the first decision and overturned it. Being able to see something is "
        "not seeing it, and a timestamp cannot tell you either way.[/yellow]"
    )
    console.print()


def show_verdicts(verdicts: list[Verdict], title: str) -> None:
    console.print()
    table = Table(title=title, show_header=True, header_style="bold blue")
    table.add_column("entity")
    table.add_column("cause")
    table.add_column("sev")
    table.add_column("score", justify="right")
    table.add_column("pairing")
    table.add_column("order")
    for v in verdicts:
        table.add_row(
            v.entity,
            f"[{CAUSE_COLOUR[v.cause]}]{v.cause.value}[/]",
            f"[{SEVERITY_COLOUR[v.severity]}]{v.severity.value}[/]",
            "-" if v.score is None else str(v.score),
            v.pairing.value,
            v.order.value,
        )
    console.print(table)
    console.print()


def show_rules(outcome: RuleOutcome, window: timedelta) -> None:
    console.print()
    table = Table(title="exclusion rules -- what each one buys and what it costs",
                  show_header=True, header_style="bold blue")
    table.add_column("rule")
    table.add_column("fires because")
    table.add_column("and hides")
    for rule in DEFAULT_RULES:
        table.add_row(rule.name, rule.reason, rule.what_it_hides)
    console.print(table)
    console.print()
    console.print(f"[yellow]{outcome.summary()}[/yellow]")
    console.print()
    if outcome.removed:
        removed = Table(title="removed from the report", show_header=True,
                        header_style="bold blue")
        removed.add_column("entity")
        removed.add_column("by rule")
        removed.add_column("cause")
        for verdict, rule_name in outcome.suppressed:
            removed.add_row(verdict.entity, rule_name, verdict.cause.value)
        console.print(removed)
        console.print()
    console.print(f"[dim]{suppression_is_a_wager(outcome)}[/dim]")
    console.print()
    console.print(f"[dim]{window_sensitivity_note(window)}[/dim]")
    console.print()
    console.print(
        "[bold yellow]A rule can only subtract.[/bold yellow] There is no input on which turning "
        "these on makes the tool find more."
    )
    console.print()


def show_severity(verdicts: list[Verdict], collisions_found: list[ScoreCollision]) -> None:
    console.print()
    console.print(f"[dim]{weights_are_invented()}[/dim]")
    console.print()
    table = Table(title="bands", show_header=True, header_style="bold blue")
    table.add_column("band")
    table.add_column("from")
    table.add_row("HIGH", f">= {HIGH_AT}")
    table.add_row("MEDIUM", f">= {MEDIUM_AT}")
    table.add_row("LOW", "below that")
    console.print(table)
    console.print()
    for collision in collisions_found:
        console.print(f"[yellow]{collision.summary()}[/yellow]")
        console.print()
    count, note = severity_and_confidence_disagree(verdicts)
    console.print(f"[bold yellow]{note}[/bold yellow]" if count else f"[dim]{note}[/dim]")
    console.print()


def show_report(analysis: Analysis) -> None:
    console.print()
    console.print(Panel(analysis.headline(), title="what this run found", border_style="blue"))
    console.print()
    table = Table(show_header=True, header_style="bold blue")
    table.add_column("cause")
    table.add_column("n", justify="right")
    for cause, n in analysis.by_cause.items():
        table.add_row(f"[{CAUSE_COLOUR[cause]}]{cause.value}[/]", str(n))
    console.print(table)
    console.print()
    _, _, sentence = separability(analysis.verdicts)
    console.print(f"[yellow]{sentence}[/yellow]")
    console.print()
    if analysis.rule_outcome and analysis.rule_outcome.removed:
        console.print(
            f"[dim]{analysis.rule_outcome.removed} entities were suppressed by rules and are "
            "listed under `rules`, not deducted from the totals.[/dim]"
        )
        console.print()
    show_verdicts(analysis.reported, "reported, ranked by an invented score")


def show_doctor(analysis: Analysis) -> None:
    console.print()
    console.print(
        Panel(
            "Everything below is either measured from the input files or invented. This screen\n"
            "says which, because the two look identical in a report.",
            title="what this tool knows, and how",
            border_style="blue",
        )
    )
    console.print()

    table = Table(title="measured from the files", show_header=True, header_style="bold blue")
    table.add_column("fact")
    table.add_column("value")
    table.add_row("entities", str(analysis.entities))
    table.add_row("values matched", str(analysis.matched))
    table.add_row("values differ", str(analysis.differences))
    table.add_row("comparisons not even defined", str(analysis.undefined_comparisons))
    if analysis.ties:
        table.add_row("ties at full precision", str(analysis.ties.tied_at_full))
        table.add_row(f"ties truncated to the {analysis.ties.unit}", str(analysis.ties.tied_after))
    console.print(table)
    console.print()

    guesses = Table(title="invented, not measured", show_header=True, header_style="bold blue")
    guesses.add_column("setting")
    guesses.add_column("where the value comes from")
    guesses.add_column("what goes wrong if it is off")
    for name, source, risk in provenance():
        guesses.add_row(name, source, risk)
    console.print(guesses)
    console.print()

    console.print("[bold]Four things this tool cannot do[/bold]")
    for line in (
        "It cannot tell silence from dissent in the input, because a CSV round trip already "
        "merged them before the file arrived.",
        "It cannot measure the propagation window, so RACE and CONFLICT are separated by a "
        "number somebody typed.",
        "It cannot discover the source relation, so the count of real conflicts rests on a "
        "declaration.",
        "It cannot learn from its own suppressions, because a suppressed case leaves the report "
        "and nobody looks at it again.",
    ):
        console.print(f"  [yellow]-[/yellow] {line}")
    console.print()

    first, second, distinguishable = round_trip_loss()
    console.print(
        f"[dim]Demonstrated, not asserted: None and \"\" written through csv and read back give "
        f"{first!r} and {second!r}; distinguishable afterwards = {distinguishable}.[/dim]"
    )
    console.print()
