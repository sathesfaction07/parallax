"""Command line.

Each command answers one question and shows its reasoning. `report` is the one you would run; the
rest exist because the reasoning is the product.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import render
from .analyse import analyse, payload
from .classify import SourceRelation, classify, why_rules_are_too_late
from .config import Settings
from .gate import check as run_check
from .influence import assess, sensitivity, verdict_depends_on_the_guess
from .models import Cause, Order
from .ordering import classify_order, order_counts, stable_sort_demo, tie_risk
from .pairing import cardinality_counts, compare_idioms, comparison_is_defined, pair_up
from .rules import DEFAULT_RULES, apply_rules
from .severity import apply_severity, collisions

app = typer.Typer(
    add_completion=False,
    help="Compares decisions recorded in two systems, and reports which differences it cannot explain.",
)
console = Console()

WINDOWS = [timedelta(minutes=m) for m in (1, 5, 60, 240, 1440)]


def _settings(relation: str | None = None, cache: str | None = None) -> Settings:
    kwargs: dict = {}
    if relation is not None:
        kwargs["relation"] = SourceRelation(relation.upper())
    if cache is not None:
        kwargs["cached_sources"] = cache
    return Settings(**kwargs)


@app.command()
def doctor(
    relation: str = typer.Option(None, help="MIRROR, INDEPENDENT or UNDECLARED"),
    cache: str = typer.Option(None, help="comma-separated source names that are copies"),
) -> None:
    """Say what was measured and what was invented."""
    render.show_doctor(analyse(_settings(relation, cache)))


@app.command()
def causes() -> None:
    """The four causes of a difference, and what each one needs to be told apart."""
    render.show_causes()
    render.show_relations()


@app.command()
def pair(
    relation: str = typer.Option(None),
    cache: str = typer.Option(None),
) -> None:
    """Line the rows up, and show what two ordinary join idioms do to them."""
    settings = _settings(relation, cache)
    result = analyse(settings)
    pairs = pair_up(result.left.decisions, result.right.decisions)
    render.show_pairing(
        compare_idioms(result.left.decisions, result.right.decisions),
        cardinality_counts(pairs),
    )
    undefined = [(p.entity, comparison_is_defined(p)[1]) for p in pairs if not comparison_is_defined(p)[0]]
    if undefined:
        table = Table(title="entities where the comparison is not defined", show_header=True,
                      header_style="bold blue")
        table.add_column("entity")
        table.add_column("why")
        for entity, why in undefined:
            table.add_row(entity, why)
        console.print(table)
        console.print()


@app.command()
def order(
    relation: str = typer.Option(None),
    cache: str = typer.Option(None),
) -> None:
    """Show which pairs can be sequenced, and what precision loss would cost."""
    settings = _settings(relation, cache)
    result = analyse(settings)
    pairs = pair_up(result.left.decisions, result.right.decisions)
    tied = [
        p for p in pairs
        if classify_order(p)[0] is Order.TIED and p.left is not None and p.right is not None
    ]
    demo_rows = [tied[0].left, tied[0].right] if tied else []
    render.show_order(
        order_counts(pairs),
        tie_risk(pairs, settings.truncate_unit),
        stable_sort_demo([d for d in demo_rows if d is not None]),
    )


@app.command()
def influence(
    entity: str = typer.Argument(None, help="one entity, or omit for all ordered pairs"),
    relation: str = typer.Option(None),
    cache: str = typer.Option(None),
) -> None:
    """Ask whether the later decider could have known -- which is what "reversal" claims."""
    settings = _settings(relation, cache)
    result = analyse(settings)
    pairs = pair_up(result.left.decisions, result.right.decisions)

    if entity:
        match = next((p for p in pairs if p.entity == entity), None)
        if match is None:
            console.print(f"[red]no entity {entity}[/red]")
            raise typer.Exit(1)
        call = assess(match, settings.window)
        render.show_influence(
            entity,
            call,
            [(w, i.value) for w, i in sensitivity(match, WINDOWS)],
            verdict_depends_on_the_guess(match, WINDOWS),
        )
        return

    rows = []
    for p in pairs:
        call = assess(p, settings.window)
        if call.gap is None:
            continue
        rows.append((
            p.entity,
            str(call.gap),
            call.influence.value,
            "a reversal is possible" if call.is_a_reversal else "a race -- nobody overturned anybody",
        ))
    render.show_influence_table(rows)


@app.command()
def rules(
    relation: str = typer.Option(None),
    cache: str = typer.Option(None),
) -> None:
    """Apply the exclusion rules, and list what they removed."""
    settings = _settings(relation, cache)
    result = analyse(settings)
    render.show_rules(apply_rules(result.verdicts, DEFAULT_RULES), settings.window)


@app.command()
def severity(
    relation: str = typer.Option(None),
    cache: str = typer.Option(None),
) -> None:
    """Score and rank, and say what the score is worth."""
    result = analyse(_settings(relation, cache))
    render.show_severity(result.verdicts, collisions(result.verdicts))
    render.show_verdicts(
        sorted((apply_severity(v) for v in result.verdicts),
               key=lambda v: (-(v.score or 0), v.entity)),
        "every difference, ranked by an invented number",
    )


@app.command()
def report(
    relation: str = typer.Option(None),
    cache: str = typer.Option(None),
    out: Path = typer.Option(None, "--out", "-o", help="also write report.json here"),
) -> None:
    """The run you would actually do."""
    settings = _settings(relation, cache)
    result = analyse(settings)
    render.show_report(result)
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(json.dumps(payload(result), indent=2, sort_keys=True), encoding="utf-8")
        console.print(f"[dim]wrote {out / 'report.json'}[/dim]")


@app.command()
def compare_relations() -> None:
    """Run the same data under every relation, because that is the finding."""
    console.print()
    table = Table(
        title="one set of files, three declarations",
        show_header=True,
        header_style="bold blue",
    )
    table.add_column("declared relation")
    for cause in Cause:
        table.add_column(cause.value, justify="right")
    for relation in SourceRelation:
        result = analyse(_settings(relation.value, None))
        table.add_row(relation.value, *[str(result.by_cause[c]) for c in Cause])
    console.print(table)
    console.print()
    console.print(
        "[bold yellow]The rows never changed. The count of real conflicts is decided by a "
        "declaration about what these two systems are to each other, and that declaration is not "
        "in the data.[/bold yellow]"
    )
    console.print()


@app.command()
def check(
    relation: str = typer.Option(None),
    cache: str = typer.Option(None),
) -> None:
    """Fail on what a data producer can fix; report everything else."""
    result = analyse(_settings(relation, cache))
    gate = run_check(result)

    console.print()
    if gate.failures:
        console.print("[bold red]Fixable in the source files[/bold red]")
        for headline, detail in gate.failures:
            console.print(f"  [red]x[/red] {headline}")
            console.print(f"    [dim]{detail}[/dim]")
        console.print()
    if gate.reported:
        console.print("[bold]Reported and NOT failed on[/bold]")
        for headline, detail in gate.reported:
            console.print(f"  [yellow]-[/yellow] {headline}")
            console.print(f"    [dim]{detail}[/dim]")
        console.print()
    console.print(
        f"[bold red]{gate.summary()}[/bold red]" if gate.failures
        else f"[bold green]{gate.summary()}[/bold green]"
    )
    console.print()
    if gate.failures:
        raise typer.Exit(1)


@app.command()
def explain(
    entity: str,
    relation: str = typer.Option(None),
    cache: str = typer.Option(None),
) -> None:
    """Walk one entity through every step, in order."""
    settings = _settings(relation, cache)
    result = analyse(settings)
    pairs = pair_up(result.left.decisions, result.right.decisions)
    match = next((p for p in pairs if p.entity == entity), None)
    if match is None:
        console.print(f"[red]no entity {entity}[/red]")
        raise typer.Exit(1)

    console.print()
    console.print(f"[bold]{entity}[/bold]")
    console.print()
    for label, decision in (("left", match.left), ("right", match.right)):
        if decision is None:
            console.print(f"  {label:<6} [dim]no row at all[/dim]")
        else:
            console.print(
                f"  {label:<6} {decision.source} value={decision.value!r} "
                f"decided_at={decision.decided_at} team={decision.team}"
            )
    console.print()

    defined, why = comparison_is_defined(match)
    console.print(f"  1. pairing    [bold]{match.pairing.value}[/bold] -- {why}")
    order_kind, order_detail = classify_order(match)
    console.print(f"  2. order      [bold]{order_kind.value}[/bold] -- {order_detail}")
    call = assess(match, settings.window)
    console.print(f"  3. influence  [bold]{call.influence.value}[/bold] -- {call.detail}")
    verdict = classify(match, settings.window, settings.relation, settings.caches)
    console.print()
    if verdict is None:
        console.print(
            "  [green]The two recorded values match, so there is nothing to explain.[/green] That "
            "is a statement about two strings, not a clean bill of health."
        )
    else:
        scored = apply_severity(verdict)
        console.print(
            f"  [bold]{scored.cause.value}[/bold] "
            f"(severity {scored.severity.value}, score {scored.score})"
        )
        console.print(f"  {scored.detail}")
        firing = next((r for r in DEFAULT_RULES if r.matches(scored)), None)
        if firing and scored.cause is not Cause.UNSEPARABLE:
            console.print()
            console.print(
                f"  [dim]Rule {firing.name} would remove this from the report. It hides: "
                f"{firing.what_it_hides}.[/dim]"
            )
    console.print()
    console.print(f"[dim]{why_rules_are_too_late()}[/dim]")
    console.print()


if __name__ == "__main__":  # pragma: no cover
    app()
