# broken-bare-bullet-id

A deliberately broken mini-artifact. Its claim table names the bullet without its canon prefix, and that bare
id exists in both canons.

<!-- artifact:claim:begin -->
**Claim under test.** This artifact exists to back one published claim,
named here so a reader can check it rather than take it.

| Field | Value |
|---|---|
| Canon | example-beta |
| Project | P2 |
| Bullet id | P2-B1 |
| Bullet text, verbatim | EXAMPLE CLAIM P2-B1. Reduced the median end-to-end latency of the P2 sample pipeline from 900 ms to 540 ms over a fixed 1,000-request replay, and reported the population the figure is a function of. |
| Measured counterpart | the steps-retired figure in the results record |
| Verdict | SUPPORTS-WITH-REVISION |
<!-- artifact:claim:end -->

## What this does not show

<!-- artifact:limits:begin -->
This fixture measures nothing. It is a deliberately broken input to a
checker and shows no throughput, no latency and no behaviour on any
machine. Its population is a hermetic test corpus and none of it may be
read as a capacity claim about anything.
<!-- artifact:limits:end -->
