# broken-uncorrected-entry -- CHECK-20's known-bad fixture

A slug the expected set marks `built` whose collections entry was never corrected.
This is the exact state CHECK-20 exists to catch: the work is recorded as
finished, the register row is taken, and the entry still says what it said
before anything was measured.

## Why this fixture carries its own inputs

CHECK-20 reads three things, and none of them lives inside an artifact: the
expected set, the two live collections entries, and the correction records. A
fixture that let those resolve to the real ones would have a pinned report that
changed the first time an unrelated slug landed -- a committed expectation that
goes red for reasons having nothing to do with the check.

So all three are supplied HERE and are handed to the check by FLAG:

```
slugs.json      the expected set  ->  --manifest
live/           the live entries  ->  --live-store
corrections/    the records       ->  --records-dir
```

A companion test module declares those flags beside this fixture's name,
with this reason, rather than teaching the check module to look inside the
directory it is judging. That distinction is the point: a checker the thing
being checked can point at its own evidence is not a checker.

## What is wrong here, row by row

| slug | status | obligation | what is wrong |
| ---- | ------ | ---------- | ------------- |
| `measured-path` | built | `example-alpha:P1-B3` | the row still carries its not-yet-measured marker, and no record names it |
| `measured-path` | built | `example-alpha:P1-B4` | the marker is gone, but no record says a measurement ever happened |
| `cited-path` | built | `example-beta:P5-B3` | the entry carries no row with that id at all |
| `not-yet-run` | pending | `example-alpha:P2-B1` | nothing: a pending slug owes no correction yet, and this row proves the check does not reach past `built` |

The second row is the one worth reading twice. Its marker is gone, so a check
that looked only for markers would call it clean -- and "the measurement agreed"
is a RESULT that has to be stated, never inferred from a silent row.

`corrections/` holds no fragment, which is what makes every obligation here
unrecorded. It carries a README so the directory is committed: git tracks files,
not directories, and an absent directory would make the check resolve somewhere
else.
