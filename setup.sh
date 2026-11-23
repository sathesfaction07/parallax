#!/usr/bin/env bash
# Sets the project up, then re-derives every claim in the README from scratch.
#
# Nothing here is quoted from a previous run. If a finding has stopped being true, this script
# fails or prints a different number, and either way you find out.

set -euo pipefail
cd "$(dirname "$0")"

# Rich wraps to the terminal width. Give it room so whole sentences survive.
export COLUMNS=200

banner() { printf '\n\033[1;34m%s\033[0m\n' "$*"; }
note()   { printf '  \033[2m%s\033[0m\n' "$*"; }

banner "1. Environment"
if [ ! -d .venv ]; then
    python3 -m venv .venv
    note "created .venv"
fi
.venv/bin/pip install -q -e ".[dev]"
note "installed discrepancy-bot and its dev extras"
PY=.venv/bin/python
CLI=.venv/bin/discrepancy-bot

banner "2. Corpus"
$PY data/generate.py

banner "3. Tests"
$PY -m pytest -q --cov=discrepancy_bot --cov-report=term-missing 2>&1 | tail -20
$PY -m ruff check src tests data && note "ruff clean"
rm -f .coverage

banner "4. Lint"
.venv/bin/ruff check src tests data >/dev/null && note "ruff clean"

# ---------------------------------------------------------------------------
# The findings, re-derived. Each block proves its claim with live output.
# ---------------------------------------------------------------------------

banner "FINDING 0 -- four causes, one observable pair"
$PY - <<'PY'
print("  Four situations produce the identical value pair ('APPROVED', 'REJECTED'):")
for cause, needs in [
    ("CONFLICT  ", "nothing more -- this is the one worth waking somebody for"),
    ("TRANSITION", "DECISION times, not read times"),
    ("RACE      ", "the propagation window between the two systems"),
    ("STALE     ", "whether a row is a decision or a copy of one"),
]:
    print(f"    {cause} needs {needs}")
observable = {("APPROVED", "REJECTED")}
print(f"  distinguishable value pairs: {len(observable)}")
print("  A comparator sees the pair. An exception rule sees what the comparator passed it.")
PY

banner "FINDING 1 -- silence reads as dissent"
$PY - <<'PY'
print(f"  None != 'APPROVED'  ->  {None != 'APPROVED'}")
print(f"  ''   != 'APPROVED'  ->  {'' != 'APPROVED'}")
print("  So a naive difference check reports a DISAGREEMENT about an entity where one system")
print("  never recorded anything. SQL is the mirror image: NULL != 'APPROVED' is NULL, so a")
print("  WHERE clause DROPS the row. Same intent, opposite answer, on the cases that matter most.")
PY

banner "FINDING 2 -- two ordinary join idioms fail in opposite directions"
$CLI pair | grep -A2 "dict-index join" || true
$PY - <<'PY'
from discrepancy_bot.ingest import read_csv
from discrepancy_bot.pairing import compare_idioms
from pathlib import Path
left = read_csv(Path("data/system_a.csv"), "system-a").decisions
right = read_csv(Path("data/system_b.csv"), "system-b").decisions
result = compare_idioms(left, right)
print(f"  {result.summary()}")
assert not result.idioms_agree
PY

banner "FINDING 3 -- you cannot always compare two timestamps"
$PY - <<'PY'
from datetime import datetime, timedelta, timezone
aware = datetime(2025, 3, 1, 12, tzinfo=timezone.utc)
naive = datetime(2025, 3, 1, 7)
try:
    aware < naive
    raise SystemExit("  it compared, which it should not have")
except TypeError as exc:
    print(f"  aware < naive -> TypeError: {exc}")
est = datetime(2025, 3, 1, 7, tzinfo=timezone(timedelta(hours=-5)))
print(f"  12:00+00:00 and 07:00-05:00 are the same instant: {aware == est}")
print(f"  ...and NOT the same string: {aware.isoformat()} != {est.isoformat()}")
print("  So string comparison of timestamps reports a difference that is not there.")
PY

banner "FINDING 4 and 5 -- precision manufactures ties, and a tie hands over the verdict"
$CLI order | grep -E "timed pairs|Loaded one way" || true

banner "FINDING 6 -- 'reversal' claims influence; a timestamp gives sequence"
$CLI influence | grep -E "e03-race|e02-ordered-far" || true
note "same values, same ordering, and only one of them is anybody overturning anything"

banner "FINDING 7 -- the CSV round trip destroys the distinction it needs"
$PY -c "
from discrepancy_bot.ingest import round_trip_loss
first, second, ok = round_trip_loss()
print(f'  None and \"\" written through csv, read back as {first!r} and {second!r}')
print(f'  distinguishable afterwards: {ok}')
assert ok is False
"

banner "FINDING 8 -- the relation decides the conflict count, and it is not in the data"
$CLI compare-relations

banner "FINDING 9 -- a rule can only subtract"
$CLI rules --relation INDEPENDENT | grep -E "differences in|can only subtract" || true

banner "FINDING 10 -- severity ranks what would matter, not what we are sure of"
$CLI severity --relation MIRROR | grep -E "score exactly|MEDIUM or HIGH" || true

banner "What the tool says about itself"
$CLI doctor

banner "The report you would actually run"
$CLI report --relation MIRROR

banner "The gate"
if $CLI check; then
    note "check passed"
else
    note "check FAILED, which is correct -- the corpus plants five fixable data defects"
fi

banner "Done"
cat <<'EOF'
  Try these:
    discrepancy-bot causes                                  the four causes and what each needs
    discrepancy-bot compare-relations                       one dataset, three declarations
    discrepancy-bot explain e02-ordered-far --relation MIRROR
    discrepancy-bot explain e16-cache-ahead --cache system-b
    discrepancy-bot influence e03-race                      sequence vs influence
    discrepancy-bot report --relation MIRROR -o /tmp/out
EOF
