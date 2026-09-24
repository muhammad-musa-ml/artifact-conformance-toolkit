# broken-gate-after-measurement

A deliberately broken mini-artifact. It carries **two** defects, both
belonging to **CHECK-04**, and the check is expected to name them separately.

Everything else about this tree is correct on purpose: its rendered date matches
the local date of every machine stamp, its limits paragraph is written, its
figure carries its denominator, and every run record carries both timestamp
forms and all three cost fields. CHECK-01, CHECK-02, CHECK-03 and CHECK-06 all
pass over it.

## The two defects

**One: the gate was recorded AFTER the measurement it supposedly governs.**
`results/gate.json` is dated at eight in the evening. `results/figures.json`
records a run that began at seven. A gate that was decided an hour after the
measurement started did not authorise it; at best it was written up afterwards,
which is the thing gate-before-measurement exists to make impossible.

**Two: a run record carries no gate token at all.**
The SECOND run record under `results/raw/` is complete and well formed -- both
timestamp forms, all three cost fields -- and nothing ties it to any gate. A run
with no token cannot be tested against anything, which is why
`runmeta.start_run` refuses to open one. This record is what that refusal
prevents, committed so the check that catches it can be tested.

The FIRST run record in that directory is correct in both respects: it began
after the gate and carries the gate's token. It is there so "the checker refused
this tree" cannot be satisfied by a rule that refuses every record.

Filenames are described rather than typed here on purpose. CHECK-01 lints every
numeral in un-rendered prose, and a record name carrying a run number is a
numeral it cannot classify -- so spelling those names out would make this tree
fail a check that has nothing to do with its defect. That is not a workaround:
it is the same one-defect discipline the rest of this document follows, applied
to the document itself.

## Why the ordering is proven from the RECORDS and never from the files

The obvious way to ask which came first is to compare the two files'
modification times. That answer is wrong here for reasons that are measured
rather than stylistic, and the reasoning lives beside the code in the check
module under `tools/checks/`.

The short version: an ordinary copy PRESERVES a file's modification time, so a
results tree carried forward from an earlier session arrives with entirely
plausible times on every file. The ordering above is therefore recorded INSIDE
each record, in ISO-8601 with a real offset, and the check reads only that. The
test module beside it sets a deliberately misleading modification time on a
measurement and asserts the verdict does not move.

## What a reader must not conclude from this tree

Nothing here was measured. The figure is invented and the cost fields are zeros
written deliberately, which is a different claim from a cost field that was
never recorded at all.

<!-- artifact:date:begin -->
Measured 2026-09-15 on the owner's own machine.
<!-- artifact:date:end -->

<!-- artifact:figures:begin -->
The median was {{figures.median_latency_ms}} ms over the replayed corpus.
<!-- artifact:figures:end -->

## Honest limits on this fixture

<!-- artifact:limits:begin -->
This fixture measures nothing real. It does not show throughput, latency under
load, or behaviour on any machine other than the one that wrote its record. The
population is a hermetic test corpus, so the figure here cannot be compared with
a production system and must never be read as a capacity claim. Its gate is
deliberately mis-ordered and one of its runs is deliberately unauthorised; no
conclusion about a real measurement may be drawn from either.
<!-- artifact:limits:end -->
