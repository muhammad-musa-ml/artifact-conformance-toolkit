# `_records/pre-fix/` -- the one-shot failing state, committed on purpose

This directory is a deliberate exception to the conventions document §3, which says a
report is never read out of git history because it can be re-produced by
re-running the checker.

**That is true of every other report in this programme and false of these two.**
an earlier round exists to FIX the defects `example-cache-benchmark` and
`example-search-benchmark` carry. The moment a range of project requirements land,
re-running `conformance.py` answers a different question, and the failing state
these files record cannot be re-observed at any sha -- the artifacts are not git
work trees yet, so there is no earlier revision of them to check out. a success criterion asks
for the pre-fix failure list; the only way that list survives the fix is if it
is a committed file rather than a claim.

## What is here

| File | What it is |
|---|---|
| `<slug>--pre-fix.txt` | The full run output, with a header carrying the toolkit `HEAD=`, the capture time, the exit code and the measured non-passing count |
| `<slug>--pre-fix.json` | The machine report the same run wrote via `--report` (`schema_version: canonkit/1`) |

## How they were produced

```
python tools/conformance.py <artifact> --report _records/pre-fix/<slug>--pre-fix.json
```

stdout and stderr redirected to the `.txt`, the exit code captured explicitly and
the file READ BACK before it was believed -- this console renders correct UTF-8
as replacement characters, so console output is never the evidence.

The header's `HEAD=` is the full forty-character sha printed by
`git rev-parse HEAD`, pasted from that command rather than expanded from a short
form.

## What they record

Both artifacts return **EXIT=1** with an identical shape: **1 pass, 4 findings,
7 did-not-run -- 11 non-passing checks each.** The eleven are counted, not
compared against a success criterion's floor of five; the floor is the requirement, the eleven
is the measurement.

Two of the four findings are worth naming here because they are not properties
of the artifact at all:

- **CHECK-05** reports `expected 12, found 1 | built 2 of 14, pending 12` on
  **both** artifacts -- a programme-level fact about eleven paths nobody has
  built yet, which no per-artifact fix can move.
- **CHECK-20** reports `built slugs 2, of which 1 under obligation | 1 built
  slug(s) map to no claim: example-search-benchmark` on **both** artifacts,
  byte-identically, including when it is pointed at a directory that is not
  either of them. Its verdict does not depend on the artifact it is given.

That identity is the evidence, not an aside: a check whose output is the same
whatever it is handed has not examined what it was handed. an earlier plan owns
the per-artifact scoping for both, and this capture is its "before" side.
