# broken-no-run-record

A deliberately broken mini-artifact. It carries **two** defects, both
belonging to **CHECK-06**, and the check is expected to name them separately
because their repairs are different.

Everything else about this tree is correct on purpose: its rendered date matches
the local date of the machine stamp, its limits paragraph is written, its figure
carries its denominator, and its gate precedes the run and is stamped on it.
CHECK-01, CHECK-02, CHECK-03 and CHECK-04 all pass over it.

## The two defects

**One: a results file carrying numbers that NO run stands behind.**
The figures record holds a figure, a denominator and a gate token, and there is
no run record anywhere in this tree that the token matches -- the raw directory
does not exist. Nothing machine-written says when that figure was produced, how
long it took, or what it cost. The number is not wrong; it is unbacked, which is
a different and worse thing, because an unbacked number cannot be argued with.

**Two: a record that is PARTIAL, and partial in the one way that reads as a
zero.**
The provenance record carries a complete run block except for the metered-spend
field, which is simply absent. Read with the ordinary defaulting idiom, an
absent key and a recorded zero are indistinguishable: both come back as nothing
spent. One of them means "this run cost nothing" and the other means "nobody
recorded what this run cost", and a project requirement re-derives each path's metered spend
from exactly this record before the owner is asked to approve it.

That is why the check counts a present key with a zero value as a PASS and the
same key omitted as a finding, and why the two are separate tests rather than
one.

## Why the two defects are named separately

A single verdict covering both would tell an author that the run metadata is
wrong without saying which repair applies. "Run the measurement through the
emitter" and "record what the run spent" are different jobs, and a check that
merges them makes the second invisible behind the first.

## What a reader must not conclude from this tree

Nothing here was measured. The figure is invented, and the cost fields that ARE
present are zeros written deliberately so that the contrast with the absent one
is the only thing this fixture demonstrates.

<!-- artifact:date:begin -->
Measured 2026-09-15 on the owner's own machine.
<!-- artifact:date:end -->

<!-- artifact:figures:begin -->
The median was {{figures.median_latency_ms}} ms over the replayed corpus.
<!-- artifact:figures:end -->

## Honest limits on this fixture

<!-- artifact:limits:begin -->
This fixture measures nothing real. It does not show throughput, latency under
load, or behaviour on any machine other than the one whose name appears in its
records. The population is a hermetic test corpus, so the figure here cannot be
compared with a production system and must never be read as a capacity claim.
Its run metadata is deliberately incomplete; no conclusion about a real
measurement may be drawn from any part of it.
<!-- artifact:limits:end -->
