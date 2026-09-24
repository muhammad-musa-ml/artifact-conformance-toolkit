# broken-retracted-figure-live

A deliberately broken mini-artifact. The defect it carries is a figure
this tree's own declaration says was **withdrawn**, still asserted as a current
result in `NOTES.md`, and the check expected to refuse it is **CHECK-16**.

Everything else about this tree is correct on purpose. Its figures record is
well formed, its retraction declaration is complete and dated, and its
withdrawal record quotes what it withdrew. If this fixture failed several checks
at once, a test asserting "the checker refused it" would not say which check did
the refusing, and the fixture would stop discriminating.

## Every figure in this tree is invented

Nothing here is a number any artifact in this programme ever published. A
fixture that quoted a REAL withdrawn figure would become a carrier for the very
scan it exists to test, and this repository has been bitten several times by a
guard matching its own documentation.

## Why the live assertion lives in its own file

`NOTES.md` carries the defect and NOTHING ELSE, and that is not tidiness. This
README has to use the word "withdrawn" in order to explain the fixture, and a
withdrawal marker anywhere within the adjudication radius is exactly what makes
an appearance FROZEN. A live assertion written a few lines under a paragraph
explaining that it was withdrawn would classify as a record of the withdrawal --
correctly, by the check's own rule -- and this fixture would then discriminate
nothing while looking like it did.

So this file quotes NO withdrawn figure at all -- not one digit of either
needle -- and contributes zero hits to the scan. That is the safe version of the
same argument: a fixture's own explanation cannot be allowed to change the
verdict it is explaining.

## The four arms, and where each one is exercised

| Arm | Where | Why it classifies that way |
|---|---|---|
| **LIVE** | `NOTES.md` | a withdrawn ratio stated as a current measurement, with no withdrawal marker anywhere near it. **The finding.** |
| FROZEN | `results/RETRACTED.md` | the withdrawal quotes the figure it withdrew, marker on the same line -- a record doing its job |
| FROZEN | `results/retractions.json` | the declaration carries every needle by construction, each beside its own `withdrawn_on`. It is scanned like every other file rather than excluded by name, so this is the classifier getting it right rather than an exemption |
| FROZEN | `results/figures.json` | the withdrawn ratio is still the machine record's value, and the record says so beside it |
| FALSE-POSITIVE | `results/throughput.json` | a throughput reading whose digits END with the second needle's digits, which is the tail of a longer number and not the figure |

The false positive is the one worth having committed. The one-off sweep that
preceded this check found exactly that shape in a real results file, and the
conclusion it drew is this check's needle rule: a bare-numeric needle whose
match is adjacent to another digit is not the figure at all.

UNCLASSIFIED has no committed example, because a hit nobody can place is by
definition one nobody anticipated. It is reserved and it is never silent.

## What this does not show

<!--artifact:limits:begin-->
This tree is a fixture, not a measurement. Nothing in it was run, nothing in it
was timed, and no conclusion about any system may be drawn from any number in
it. It exists so one check can be proven to discriminate a live assertion of a
withdrawn figure from a record quoting one, and it does not exercise every arm.
<!--artifact:limits:end-->
