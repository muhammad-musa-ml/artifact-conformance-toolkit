<!--
THE ARTIFACT README SKELETON. Copied into every generated artifact as README.md.

HOW TO READ THIS FILE

Angle-bracket placeholders (<like-this>) are prose an author replaces by hand.
Double-brace key references of the form figures.<key> are rendered from
results/figures.json by render.py and MUST NOT be hand-typed. Those are two
different mechanisms and confusing them is the failure a design rule exists to prevent.

THE REGION MECHANISM (the design rules)

Every generated figure lives inside a PAIRED begin/end HTML-comment region whose
token is `artifact:`. There is no single-marker form. The regions in this file
are: date, claim, figures, env, layout, limits.

The regions are the ADDRESSING MECHANISM; the heading text above them is free.
This is not a style preference, it is a measured requirement. The two artifacts
that shipped before this program existed use two DIFFERENT limitations headings
-- `## What this benchmark is NOT` and `## Honest limits on these numbers` -- so
a checker keyed on either literal passes one artifact and fails the other. The
region token is the same in both, whatever the author called the heading.

Neither of those artifacts contains a single HTML comment, so there is no analog
for this mechanism anywhere. It is designed here, from scratch, on purpose.

UN-RENDERED PROSE MAY NOT CARRY A FIGURE AT ALL

Every figure in this document is a key reference. No literal numeral appears
anywhere in this skeleton, including in an example -- an example numeral in a
template is the first thing a later author copies into a sentence, and a number
typed into a sentence is exactly the back-solving failure this rule closes.
Non-figure numerals (versions, host ports, ISO dates, requirement ids) are
covered by canonkit.classify_numerals' shape allow-list.

MEASURED TRAP, so an author does not rediscover it: a MARKDOWN ORDERED LIST
trips that allow-list. A digit followed by a full stop at the start of a line
is classified UNCLASSIFIED, exactly as a stray figure would be, because the
allow-list has no shape for a list marker. Both skeletons therefore use
bulleted lists throughout. Use a bulleted list, or spell the ordinal ("first",
"second"), until the checker grows a rule for it.

This was found by running the classifier over this file rather than by reading
the allow-list -- and the first draft of THIS PARAGRAPH tripped the check too,
by quoting the offending marker literally while warning about it. That is the
same shape as a ban whose own documentation is a hit for it, and it is why the
warning above is phrased in words instead of in the marker.

THE LIMITS PLACEHOLDER IS DESIGNED TO BE REFUSED

The paragraph inside the artifact:limits region at the foot of this file is the
skeleton's OWN bytes. conformance.py compares the rendered artifact's limits
BODY against these bytes and fails on a match. That is the check -- a `grep -c`
for the heading is explicitly insufficient, because the heading survives every
copy untouched and is present in a completely unedited template. The inherited
acceptance criterion that counted headings is REPLACED by this byte comparison.

An unedited generated artifact therefore does not pass. That is the intended
behaviour, not a defect to be tidied away: generate -> conformance FAILS on
CHECK-03 -> fill in -> conformance PASSES.
-->

# {{artifact.title}}

<!-- artifact:date:begin -->
Measured {{figures.dated_at}} on the owner's own machine.
<!-- artifact:date:end -->

<!-- artifact:claim:begin -->
<one-paragraph claim: what was built, what was measured, and what the headline
number is a function of. Every number in this paragraph is a key reference.>

| | Before | After |
|---|---|---|
| <headline metric, with its unit> | {{figures.headline_before}} | {{figures.headline_after}} |
| Ratio | | {{figures.headline_ratio}} |
| Population | {{figures.headline_population}} | {{figures.headline_population}} |

**What this is.** A from-scratch reproduction, built {{figures.dated_at}}, of the
{{artifact.title}} work done as {{artifact.role}} at {{artifact.organization}}
({{artifact.engagement_dates}}). The original ran on the company's own systems and
is not mine to publish; this rebuilds it from scratch on my own machine so the
numbers can be checked. Every figure below was measured here, on the date it
carries.

That paragraph is MANDATORY and may not be trimmed. This repository's commit
dates are visible to anyone with the link, so a README claiming the engagement's
dates over commits from a different year contradicts itself in one click.
Saying it first turns that from a contradiction a reader finds into a fact the
page already told them.

**Claim under test.** This artifact exists to back one published claim, named here
so a reader can check it rather than take it.

| Field | Value |
|---|---|
| Organization | {{artifact.organization}} |
| Role | {{artifact.role}} |
| Example project | {{artifact.project}} |
| Canon | {{artifact.canon}} |
| Collections entry | {{artifact.collections_entry}} |
| Bullet id | {{artifact.bullet_ids}} |
| Bullet text, verbatim | <paste the bullet verbatim; do not paraphrase it> |
| Measured counterpart | {{figures.headline_ratio}} |
| Verdict | <one of: SUPPORTS, SUPPORTS-WITH-REVISION, DOES-NOT-SUPPORT> |

**EXAMPLE PROJECT, not project.** `P1` / `BP-2` name an example project WITHIN an
engagement. This work is never presented as a personal project, on any surface.
`Canon` is the FROZEN BASELINE -- what the claim said before anything was
measured; `Collections entry` is the LIVE target that this measurement corrects.
Both are named because the comparison needs both sides.

Where the measurement disagrees with the bullet, the measurement wins and **the
collections entry changes** -- its metric, and its description of what was done
and how. A verdict of DOES-NOT-SUPPORT is a legitimate outcome of a build, not a
failure of one.
<!-- artifact:claim:end -->

## Purpose

<what question this artifact answers, in two or three sentences. State the
question the reader would ask an interviewee, and state that this directory is
the answer.>

### Why the "before" side is not a strawman

<the single most important paragraph in this file. Name what the baseline arm
was configured with, why that configuration is a fair one, and what you would
have had to do to make the improvement look bigger. An improvement measured
against a deliberately crippled baseline measures the crippling.>

## Provenance

Every number in this document comes from `results/figures.json`, which is
written by a run and never by a human. Nothing here is estimated. The chain is:

`gate.py` mints a run token from the gate's own inputs -> every run stamps that
token into everything it writes -> `derive.py` computes every figure from the
raw records -> `render.py` writes the figures into the regions of this file ->
`verify.py` fails on a mismatch anywhere along that chain.

A hand edit to a rendered region is therefore not a shortcut, it is a detected
error. Re-run `derive.py` and `render.py --write` instead.

## Data

| Field | Value |
|---|---|
| Source | <name of the corpus or the live system> |
| URL | <the exact URL the data came from> |
| Licence | <the source's licence, named exactly> |
| Fetched | <fetch date, ISO-8601> |
| Extraction script | <the script in this directory that produced the derived set> |

**Derived corpora are never redistributed.** This directory ships the extraction
script and the frozen id lists so the set can be rebuilt, plus the source's own
attribution block. It does not ship the source's material.

## Setup

**Requires the GPU: {{artifact.gpu_required}}.** Stated explicitly either way,
because a reader on a machine without one needs to know before, not after --
and because "it did not say it needed a GPU" is not something a reader should
have to discover by running it.

<the remaining prerequisites, named exactly: the container images this pulls,
the model weights it downloads, and the disk it needs.>

## Usage

Three things a reader can do with this directory, in increasing order of effort:

- **Read the numbers** -- they are in the regions of this file and in
  `results/RESULTS.md`, and every one of them names its population.
- **Re-check them without re-running anything** -- `python verify.py` walks the
  recorded chain and `python conformance.py .` re-runs the contract checks
  against this directory. Both work on a clean checkout with no network.
- **Re-run the measurement** -- see below. This is the expensive one.

## Running it

```
python gate.py --slug {{artifact.slug}}
python run_example.py
python derive.py --specs figure-specs.json
python verify.py
```

`figure-specs.json` is written by the author of this artifact: it declares each
figure, its unit, its population and its population label. `derive.py` refuses
without it rather than inventing a default, because a figure with no declared
population is the thing the whole contract exists to prevent.

Once the renderer is vendored into this directory, `python render.py --check`
goes between `derive.py` and `verify.py`. It is listed separately rather than
above because a command for a file that is not here yet is a dead instruction,
and `.vendor.json` records exactly which declared files were absent when this
artifact was generated -- read it rather than guessing.

`gate.py` comes first and that ordering is enforced rather than documented: the
gate mints a token from the environment it read, every later step stamps that
token into what it writes, and `verify.py` fails when a measurement carries a
token no gate minted. Running a measurement before the gate produces results
that cannot be verified, which is the point.

`render.py` defaults to `--check`: it reports and exits non-zero rather than
rewriting. Pass `--write` to regenerate the regions of this file.

If the gate REFUSES, it did not look, and nothing was measured. Read the refusal
-- it names the precondition and how to repair it.

## Results

<the narrative version of the headline, one or two paragraphs, with every number
a key reference. The full record with its retractions and its disclosed
instabilities lives in `results/RESULTS.md`.>

### Measurement discipline

<what was held constant, what was varied, how many replicates each arm got, and
what the run-to-run spread was. A single run is a legitimate population for some
facts -- peak memory, free memory at run start, disk free -- and is not a
legitimate population for a throughput claim.>

### The load generator is part of the experiment

<required for any throughput, percentile, or per-call-mean claim, and delete
this section only if this artifact makes none of those.>

<the harness's own ceiling, measured FIRST against a null or echo target, so a
reader can tell a measurement of the system under test from a measurement of the
harness. If the reported number is within a small factor of the harness ceiling,
say so here rather than letting a reader discover it.>

## The guards that make the number mean something

Each guard below ran as part of the measurement and each one names the
population it ran over. A guard that ran over zero inputs is reported as a
FAILURE, never as a pass and never as `skipped`.

<!-- artifact:figures:begin -->
| Guard | Population | Floor | Result |
|---|---|---|---|
| <guard id> | {{figures.guard_population}} | {{figures.guard_minimum_required}} | {{figures.guard_verdict}} |

| Figure | Value | Population | What it is a function of |
|---|---|---|---|
| <figure name> | {{figures.headline_ratio}} | {{figures.headline_population}} | <the denominator, named> |
<!-- artifact:figures:end -->

## Environment

The environment this was measured on, read by the run rather than typed by the
author. Free GPU memory in particular is a per-run population fact, not
housekeeping: it has been observed moving by hundreds of mebibytes between days
on this machine, and a throughput number recorded without it cannot be compared
against a later one.

<!-- artifact:env:begin -->
| Field | Value |
|---|---|
| GPU | {{figures.env_gpu_name}} |
| Free GPU memory at run start | {{figures.env_vram_free_mib}} |
| Host RAM | {{figures.env_host_ram_gib}} |
| Container runtime | {{figures.env_container_runtime}} |
| Wall seconds | {{figures.run_wall_seconds}} |
| Metered spend | {{figures.run_api_spend_usd}} |
| GPU minutes | {{figures.run_gpu_minutes}} |
<!-- artifact:env:end -->

## Layout

<!-- artifact:layout:begin -->
| Path | What it is |
|---|---|
| `gate.py` | The opening gate. Refuses before measuring; mints the run token |
| `run_example.py` | The measurement driver |
| `derive.py` | The single source of truth for every number |
| `render.py` | Writes figures into the regions of this file |
| `verify.py` | Re-derives and fails on a mismatch |
| `provenance.py` | Records sources, image digests and the run record |
| `finalize.py` | The integrity guards |
| `conformance.py` | The vendored contract checker -- re-run it yourself |
| `canonkit.py` | The vendored frozen core. Byte-identical to its source |
| `results/` | Machine-written records. Tracked, never hand-edited |
| `waivers.json` | Owner-authored waivers. Empty unless the owner added one |
| `requirements.txt` | Fully pinned, hash-pinned |
| `docker-compose.yml` | Digest-pinned images only |
<!-- artifact:layout:end -->

A retired script is kept rather than deleted when a guard's story lives in it,
with a note saying why. Deleting the evidence of a correction is how a record
stops being one.

## What this does not show

<!-- artifact:limits:begin -->
TODO(artifact:limits): replace this paragraph before any figure is published.
This placeholder is the skeleton's own text. It is here to be refused.
<!-- artifact:limits:end -->
