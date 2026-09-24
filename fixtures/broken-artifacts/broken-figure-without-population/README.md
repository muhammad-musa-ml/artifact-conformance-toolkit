# broken-figure-without-population

A deliberately broken mini-artifact. Nothing here was measured and no
number below was produced by running anything; the record and the document exist
only so CHECK-01 has a real defect to refuse.

<!-- artifact:limits:begin -->
Run on one laptop with one consumer GPU. No managed-cloud resource of any kind.
<!-- artifact:limits:end -->

<!-- artifact:figures:begin -->
The replay issued <!--artifact:key:replayed_requests-->500<!--/artifact:key-->
requests against the warm cache, and the hit ratio over that window was
<!--artifact:key:cache_hit_ratio-->0.62<!--/artifact:key-->.
<!-- artifact:figures:end -->

## The defect, and how to read it

1. Both figures above sit inside a paired region and neither is hand-typed, so
   the numeral rule has nothing to say about this document.
2. One of the two records carries no denominator of its own: the `figures`
   entry has a `population_label` and no `population` beside it.
3. CHECK-01 must name that key, and must leave the other one alone. A check that
   simply refused the whole record would pass this fixture while discriminating
   nothing.

The ordered list you have just read is part of the fixture. A numeral rule that
counted its markers would raise a finding against every author who writes a
numbered list, and a checker people learn to ignore is the failure a design rule exists
to prevent.

## What this does not show

This is a hermetic fixture, not an artifact. It measures nothing, it has no
gate, and its figures were typed by hand into a record so that a checker would
have something to refuse. Nothing here should be read as evidence about any
example project.

Dated: 2026-09-15
