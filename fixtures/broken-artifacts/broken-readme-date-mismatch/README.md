# broken-readme-date-mismatch

A deliberately broken mini-artifact. The defect it carries is a **rendered
date that no machine wrote**, and the check expected to refuse it is **CHECK-02**.

Everything else about this tree is correct on purpose. It carries a passing gate
whose `dated_at` precedes every measurement, a complete run record with both
timestamp forms and all three cost fields, and a well-formed figures record whose
every figure carries its denominator. CHECK-01, CHECK-03, CHECK-04 and CHECK-06
all pass over it. If this fixture failed several checks at once, a test asserting
"the checker refused it" would not say which check did the refusing, and the
fixture would stop discriminating.

## What is wrong with it

The `artifact:date` region below renders **the day after** the day the machine
recorded. The run began at half past ten in the evening, local time, on the
fifteenth. Its UTC counterpart, stamped at the same instant, falls on the
sixteenth -- five hours later on a machine whose offset is minus five.

The rendered date is the **sixteenth**. It was read off `started_at_utc` while
`started_at` is the field a reader's intuition matches, and a design rule stores both
precisely so that choice is made deliberately rather than by whichever field came
to hand.

## Why this is the shape worth committing, rather than an arbitrary mismatch

A date typed at random would be caught by any comparison at all. This one is
caught only by a check that knows WHICH of the two stored stamps it compares
against. Both fields are present, both are well formed, both are genuinely
machine-written, and they name different days. A check that quietly compared
against the UTC field would report this tree CLEAN.

That is not a hypothetical. Measured on this machine while CHECK-02 was written:
the local stamp read half past seven in the evening on the fifteenth and its UTC
counterpart read nearly one in the morning on the sixteenth, at the same instant.
For roughly five hours of every day the two disagree about the date here.

So CHECK-02 compares against the LOCAL component, says so out loud, and counts
the divergences in its own summary line. This fixture makes that counter fire:
its record is one in which the two stamps genuinely differ.

## What a reader must not conclude from this tree

Nothing here was measured. The figures are invented and the cost fields are
zeros written deliberately, which is a different claim from a cost field that was
never recorded at all -- the distinction CHECK-06 exists to keep.

<!-- artifact:date:begin -->
Measured 2026-09-16 on the owner's own machine.
<!-- artifact:date:end -->

<!-- artifact:figures:begin -->
The median was {{figures.median_latency_ms}} ms over the replayed corpus.
<!-- artifact:figures:end -->

## Honest limits on this fixture

<!-- artifact:limits:begin -->
This fixture measures nothing real. It does not show throughput, latency under
load, or behaviour on any machine other than the one that wrote its record. The
population is a hermetic test corpus, so the figure here cannot be compared with
a production system and must never be read as a capacity claim. Its cost fields
are recorded zeros and not an absence of recording; that distinction is the only
thing they are here to demonstrate.
<!-- artifact:limits:end -->
