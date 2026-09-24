# broken-claim-block

A deliberately broken mini-artifact. Its claim table names no measured counterpart and carries a verdict
outside the three legal values.

<!-- artifact:claim:begin -->
**Claim under test.** This artifact exists to back one published claim,
named here so a reader can check it rather than take it.

| Field | Value |
|---|---|
| Canon | example-alpha |
| Project | P2 |
| Bullet id | example-alpha:P2-B3 |
| Bullet text, verbatim | EXAMPLE CLAIM P2-B3. Reduced the median end-to-end latency of the P2 sample pipeline from 900 ms to 540 ms over a fixed 1,000-request replay, and reported the population the figure is a function of. |
| Verdict | PARTIALLY-SUPPORTS |
<!-- artifact:claim:end -->

## What this does not show

<!-- artifact:limits:begin -->
This fixture measures nothing. It is a deliberately broken input to a
checker and shows no throughput, no latency and no behaviour on any
machine. Its population is a hermetic test corpus and none of it may be
read as a capacity claim about anything.
<!-- artifact:limits:end -->
