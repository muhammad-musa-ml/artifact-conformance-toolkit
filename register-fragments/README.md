# `register-fragments/` -- the one hand-written thing in the register

`backing-artifacts.md` is **generated** by `tools/build_register.py`. Every
figure in it is read out of that artifact's own `results/figures.json` at
generation time.

The inherited register header said, literally:

> Figures here are copied from that artifact's own `results/RESULTS.md`.

That copy is the **last hop in this whole program where a human retypes a
number**, and it is exactly the hop the program exists to remove. two earlier findings overturn
it. Nothing in this directory contains a figure.

## One fragment per artifact

```
register-fragments/<slug>.md
```

A fragment holds the **similarity judgment** and nothing else: whether the
measured number supports the canon bullet it backs, and why. It is prose, it is
the owner's reading, and it is **numeral-free**.

```markdown
# example-cache-benchmark

verdict: CONFIRMS

Measured against BP-5-B2 on 2026-09-15. The measured value sits on the same side
of the bullet's claim, in the same order of magnitude, over the same denominator
the bullet names, so a reader of the bullet would not be misled.
```

## The verdict is the OWNER's reading

The five legal values are declared once, in `canonkit.SIMILARITY_VERDICTS`:

| verdict                    | meaning                                                  |
| -------------------------- | -------------------------------------------------------- |
| `CONFIRMS`                 | the measurement backs the bullet as written               |
| `SUPPORTS`                 | it backs the bullet's claim, less tightly                 |
| `SUPPORTS-WITH-REVISION`   | it backs a revised wording of the bullet                  |
| `DOES-NOT-SUPPORT`         | it does not back the bullet                               |
| `REFRESH`                  | the bullet's figure must be replaced by the measured one  |

**CHECK-09 verifies that a verdict EXISTS and is one of those five. It never
verifies that the verdict is correct.** That is not a gap in the checker, it is
the boundary of what a checker can honestly assert: "similar" is bounded by the
bullet's own `metric_basis`, and deciding whether a reader would be misled is a
judgment, not a computation. A checker claiming to have validated that judgment
would be asserting something it never looked at.

What the tooling *can* enforce, and does, is that the judgment sits beside the
measurement, carries a legal verdict, and contains no retyped number.

## The numeral lint runs BOTH rules

`build_register.py` refuses to generate if a fragment carries a numeral it
cannot account for. Two rules run, and neither is sufficient alone:

1. **Shape allow-list** (the primary rule). Permitted: bullet ids
   (`BP-5-B2`), ISO dates (`2026-09-15`), versions, ports, and
   `{{figures.<id>}}` key references. Anything else bearing a digit is a
   violation, reported with its line and column.
2. **Value check.** Any `value` or `population` from that artifact's
   `figures.json` appearing outside a key reference is a violation, even when
   its shape is allowed.

Rule 1 alone misses a real measured number wearing an allowed shape -- a figure
whose value happens to be `8080`, written as "on port 8080", is classified as a
port and waved through. Rule 2 alone misses a hand-typed number that happens not
to match any figure, which is an earlier finding's recorded back-solving failure: deriving a
numerator from a canon percentage and typing it into a sentence.

The allow-list lives in `canonkit.classify_numerals` and is **shared with
a design rule**, which governs figures in artifact prose. Two implementations of one
allow-list would drift, and the drift would be invisible until the day the two
disagreed about a real fragment.

### If you need to name a figure

Use a key reference. It is the one permitted way to put a figure in prose:

```markdown
The measured {{figures.p95_latency_ms}} sits on the same side of the claim.
```

## What happens if you edit the register instead

`backing-artifacts.md` carries a trailer with two hashes. If its body has been
edited, or anything has been appended after the trailer, the next
`build_register.py` run **refuses, prints the diff, and writes nothing**.

That is deliberate, and the shared pattern note records why it is the cheap option: a
shipped regenerator that tried to reconcile instead -- partial knowledge plus a
carry-forward clause -- silently rewrote a real score to `n/a` on every run, for
an unknown period. Refusing costs one error message. Reconciling cost a real
number that nobody noticed going missing.

If a register entry is wrong, the thing to change is the artifact's
`results/figures.json` or its fragment here -- never the register.

## Where the register lives

| copy    | path                               | anchored to            |
| ------- | ---------------------------------- | ---------------------- |
| tracked | `<this repo>/backing-artifacts.md` | the working checkout   |
| mirror  | `<home>/Research/backing-artifacts.md` | the artifacts root |

The two are byte-identical. The tracked copy is under version control because
the register is tooling output whose trailer is a **tripwire**, not a history --
and a tripwire nobody can diff is not one. The mirror exists for a reader
browsing the artifacts, who should not have to open this repository to find out
what backs what.
