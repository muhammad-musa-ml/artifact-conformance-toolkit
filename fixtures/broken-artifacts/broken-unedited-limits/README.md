# broken-unedited-limits

A deliberately broken mini-artifact. The defect it carries is a limits
paragraph **nobody edited**, and the check expected to refuse it is **CHECK-03**.

Everything else about this tree is correct on purpose. Its figures record is
well formed and every figure carries its denominator, so CHECK-01 passes over
it. If this fixture failed several checks at once, a test asserting "the checker
refused it" would not say which check did the refusing, and the fixture would
stop discriminating.

## What is wrong with it

The body inside the `artifact:limits` region below is **byte-identical to
`templates/README-SKELETON.md`'s own placeholder**. It hashes to the committed
placeholder constant the skeleton's own plan recorded, and it fails four of
CHECK-03's five conditions simultaneously:

| Condition | How this tree fails it |
|---|---|
| byte-identical to the template placeholder | it is the placeholder, byte for byte |
| under its word floor | the placeholder is twenty-two words against a floor of forty |
| no scope vocabulary | it carries none of the ten declared terms that bound a claim |
| still carries the skeleton's own marker | it opens with the marker an author is meant to delete |

The fifth condition, `absent`, cannot apply here: a region that is present
cannot also be missing. A separate temp-path fixture covers that one, and a
README carrying no region of any kind is a DID-NOT-RUN rather than a finding,
because a check that never read a paragraph has not found a problem with it.

## Why a heading count could not catch this

The inherited acceptance criterion for CHECK-03 was a `grep -c` for the heading
text. This tree **passes that criterion** -- the heading is right there above the
region, untouched, exactly as an unedited copy leaves it. That is the whole
reason the criterion was replaced by a byte comparison against the skeleton.

The check also keys on the **anchor**, never on the heading, because the two
artifacts that shipped before this program existed use two different limitations
headings. A check keyed on either literal passes one of them and fails the other.

## The heading below is deliberately not the skeleton's

`templates/README-SKELETON.md` writes `## What this does not show`. This fixture
writes something else, so that a check which quietly started keying on the
heading again would report this tree CLEAN and the test beside it would go red.
The defect is in the region body; the heading is free prose and is varied here to
prove it.

## Honest limits on this fixture

<!-- artifact:figures:begin -->
The median was {{figures.median_latency_ms}} ms over the replayed corpus.
<!-- artifact:figures:end -->

<!-- artifact:limits:begin -->
TODO(artifact:limits): replace this paragraph before any figure is published.
This placeholder is the skeleton's own text. It is here to be refused.
<!-- artifact:limits:end -->

Dated: 2026-09-15
