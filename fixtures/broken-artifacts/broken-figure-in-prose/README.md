# broken-figure-in-prose

A deliberately broken mini-artifact. Nothing here was measured. It exists
to carry the one defect a shape allow-list cannot see.

<!-- artifact:limits:begin -->
Run on one laptop with one consumer GPU. No managed-cloud resource of any kind.
<!-- artifact:limits:end -->

<!-- artifact:figures:begin -->
Median latency over the replay was
<!--artifact:key:median_latency_ms-->12.5<!--/artifact:key--> ms, and the
service was reachable at
<!--artifact:key:service_port-->6333<!--/artifact:key-->.
<!-- artifact:figures:end -->

## Why this one is harder than the other fixture

The sentence below sits outside every region, which a design rule already forbids for a
figure. What makes it the interesting case is that its numeral has a PERMITTED
SHAPE: the allow-list classifies a bare integer immediately after the word
`port` as a port and says nothing. A shape rule alone therefore reports this
document clean.

Only the value rule catches it, because only the value rule knows what the
figures record holds. That is the whole reason a design rule and a design rule share one
implementation and run both rules over the same text.

The harness talked to the service on port 6333 for the whole replay.

The sentence above is the defect. It is a figure value, back-solved out of the
record and typed into un-rendered prose, which is the named most-likely
executor failure this fixture is a copy of.

## What this does not show

This is a hermetic fixture, not an artifact. It measures nothing, it has no
gate, and its figures were typed by hand into a record so that a checker would
have something to refuse. Nothing here should be read as evidence about any
example project.

Dated: 2026-09-15
