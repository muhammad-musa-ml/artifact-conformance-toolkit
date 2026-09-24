<!--
THE RESULTS SKELETON. Copied into every generated artifact as results/RESULTS.md.

This is the FULL record. README.md carries the headline and the claim; this file
carries everything the headline was distilled from, including the parts that did
not survive.

WHAT MAKES THIS DOCUMENT WORTH HAVING

Not the tables. The tables are regenerated from results/figures.json and could be
rebuilt from it at any time. What cannot be rebuilt is the history: which numbers
moved, why they moved, and which claims were withdrawn. Two structures below
carry that, and both are copied from the strongest honesty model this program has
-- the shipped example-cache-benchmark RESULTS document, written by this
program's owner before this repository existed:

  A RETRACTION KEPT IN PLACE, WITH ITS REASONING. A claim that turned out to be
  wrong is struck through and explained where it stood. It is never deleted and
  never quietly replaced by the corrected version, because a reader cannot
  distinguish a document that was always right from one that was edited to look
  that way.

  A DISAGREEING RUN DISCLOSED RATHER THAN DISCARDED. When replicates disagree,
  every observation is reported and the disagreement becomes the result --
  "unstable across runs" is a finding, and a single clean-looking point chosen
  from a bimodal population is not.

THE SAME RULE APPLIES TO SUPERSEDED FRAGMENTS. Superseded content is
EXCLUDED from the assembled body and COUNTED separately, so a reader sees
`assembled N, superseded M`. Counting is what stops exclusion from being
deletion.

REGIONS AND FIGURES. Same contract as README.md: paired begin/end regions with
the `artifact:` token, every figure a key reference of the form figures.<key>,
and no literal numeral anywhere in this skeleton.
-->

# Measured results

<!-- artifact:date:begin -->
Measured {{figures.dated_at}}.
<!-- artifact:date:end -->

Every number here comes from `results/figures.json`, which is written by a run
and never by a human. Nothing is estimated.

<!-- artifact:claim:begin -->
**<one-sentence statement of what this measured and what the headline is.>**

| | Before | After |
|---|---|---|
| <headline metric, with its unit> | {{figures.headline_before}} | {{figures.headline_after}} |
| Ratio | | {{figures.headline_ratio}} |
| Population | {{figures.headline_population}} | {{figures.headline_population}} |
<!-- artifact:claim:end -->

<state here whether this document reports a result BEFORE or AFTER adversarial
review. If a review moved the headline, say so in this position, at the top,
and keep the pre-review numbers below rather than replacing them.>

## Environment

<!-- artifact:env:begin -->
| Field | Value |
|---|---|
| GPU | {{figures.env_gpu_name}} |
| Free GPU memory at run start | {{figures.env_vram_free_mib}} |
| Host RAM | {{figures.env_host_ram_gib}} |
| Container runtime | {{figures.env_container_runtime}} |
| Started | {{figures.run_started_at}} |
| Finished | {{figures.run_finished_at}} |
| Wall seconds | {{figures.run_wall_seconds}} |
| Metered spend | {{figures.run_api_spend_usd}} |
| GPU minutes | {{figures.run_gpu_minutes}} |
<!-- artifact:env:end -->

Free GPU memory is a per-run population fact and is recorded per run for that
reason. A throughput number recorded without it cannot be compared against a
later one on the same card.

## Headline

<!-- artifact:figures:begin -->
| Figure | Value | Population | Population label | What it is a function of |
|---|---|---|---|---|
| <figure name> | {{figures.headline_ratio}} | {{figures.headline_population}} | <what was counted> | <the denominator, named> |

<the paragraph a reader should take away. Name the denominator in words. A ratio
whose denominator is unstated is not a result.>

## Integrity guards

Every guard names the population it ran over and the floor it required. A guard
that ran over zero inputs is a FAILURE, never a pass and never `skipped` -- a
verdict with no count is an unrun check.

| Guard | Population | Population label | Floor | Result |
|---|---|---|---|---|
| <guard id> | {{figures.guard_population}} | <what was counted> | {{figures.guard_minimum_required}} | {{figures.guard_verdict}} |
<!-- artifact:figures:end -->

## Everything the reviews found, and what happened to it

<one subsection per finding. Keep the categories separate -- collapsing them
loses the distinction between a defect that was fixed and a claim that was
withdrawn, and that distinction is the whole value of this section.>

### Fixed

<defects found and corrected, each with what was wrong and what the number was
before and after.>

### Verified and overstated

<claims that were true but said more than the evidence supported, with the
narrowed wording.>

### Still open, honestly

<known defects that were NOT fixed, each naming who or what will close it. An
item with no named owner is not a limitation, it is an unowned defect -- say so
in those words rather than filing it as accepted.>

### The instability, disclosed rather than hidden

<if replicates disagreed, every observation goes here, including the one that
disagrees with the conclusion. Report the spread, say which mode the reported
figure came from, and say what you did not control.>

That earlier observation is kept, not discarded --

> "discarding the run that disagrees is how a benchmark lies."
>
> -- `example-cache-benchmark/results/RESULTS.md`, under the heading
> "The instability, disclosed rather than hidden", written by this program's
> owner before this repository existed.

-- which is why a disagreement is reported as an instability rather than as a
point.

### Retracted

<claims withdrawn, struck through in place with the reason. The withdrawn text
stays visible. Deleting it would make this document unable to show that it was
ever wrong, which is the only thing that makes it evidence rather than an
advertisement.>

## Does this support the published claim?

| Field | Value |
|---|---|
| Organization | {{artifact.organization}} |
| Role | {{artifact.role}} |
| Example project | {{artifact.project}} |
| Canon | {{artifact.canon}} |
| Collections entry | {{artifact.collections_entry}} |
| Bullet id | {{artifact.bullet_ids}} |
| Bullet text, verbatim | <paste the bullet verbatim; do not paraphrase it> |
| Measured counterpart | the headline ratio rendered in the claim block at the top of this file |
| Verdict | <one of: SUPPORTS, SUPPORTS-WITH-REVISION, DOES-NOT-SUPPORT> |

**EXAMPLE PROJECT, not project.** `P1` / `BP-2` name an example project WITHIN an engagement,
and this work is never presented as a personal project. `Canon` is the frozen
baseline; `Collections entry` is the live target the measurement corrects.

<the argument for that verdict, in the reader's terms. "Similar" is bounded by
the bullet: same direction, same order of magnitude, same denominator. Anything
else is a refresh of the bullet, not a footnote to it. If the measurement
disagrees, say what the bullet should now say.>

## What this does not show

<!-- artifact:limits:begin -->
TODO(artifact:limits): replace this paragraph before any figure is published.
This placeholder is the skeleton's own text. It is here to be refused.
<!-- artifact:limits:end -->
