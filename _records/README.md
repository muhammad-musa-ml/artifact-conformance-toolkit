# `_records/` -- append-only fragments, assembled by a tool

Records in this program are written as **fragments** and assembled into one file
by `tools/assemble_records.py`. Nothing in here is edited by hand after it is
written, and no assembled file is ever written by hand at all.

## Layout

```
_records/<kind>/YYYY-MM-DD-HHMMSS--<slug>--<kind>.md     one fragment
_records/<kind>.md                                        the assembled file
```

The assembled file sits **beside** the fragment directory, one level up, never
inside it. An aggregate placed inside the directory it aggregates is either
re-assembled into itself or silently excluded by whatever pattern skips it --
and the second reads as working. One level up makes the two populations
disjoint by construction rather than by a filter someone has to remember.

## Front matter

Every fragment opens with a `---` delimited block:

```
---
id: 2026-09-15-101738--canon-read
plan: an earlier plan
dated_at: 2026-09-15
supersedes: 2026-09-14-090000--canon-read
---

The record's body.
```

| Key          | Required | Meaning                                              |
| ------------ | -------- | ---------------------------------------------------- |
| `id`         | yes      | stable handle; what a `supersedes:` points at        |
| `plan`       | yes      | the plan that wrote it -- a FIELD, not part of the name |
| `dated_at`   | yes      | the local date the record is about                   |
| `supersedes` | no       | the `id` of a fragment this one replaces             |

An unknown key is an error rather than an ignored line. A `supersedes` typo'd
into `superceeds` would otherwise be a retraction that never happens, and the
count would go on looking right.

## Why the name carries a TIMESTAMP and not a plan number

Ordering is by the timestamp prefix, never by plan number.

Five inherited waves hold two or three record-writing plans each, and five of
the eleven example projects are order-free. The plan number therefore stops being
chronological the moment the roadmap reorders -- which it will, because
sequencing is by dependency and there is no fixed deadline. A record set sorted
by plan number would quietly re-order itself under a reader who had already read
it. The plan id lives in the front matter, where re-ordering cannot touch it.

## Assembled files are GENERATED-ONLY

**A plan that appends to an assembled file directly loses another agent's
write, silently.** There is no error, no conflict marker, and no count that
moves.

Parallelization is ON in this program and its granularity is `fine`, so
record-writing plans genuinely do run at the same time. Three things make that
safe, and all three are needed:

1. `build` writes the assembled file **atomically** -- a per-writer `pid+uuid`
   temp file in the same directory, flushed and fsynced, then `os.replace`.
2. The replace happens under a blocking **`tools/mwlock.py`** window, so two
   builds cannot interleave.
3. `lint` re-runs `build` **in memory** and byte-compares. That is what makes a
   direct append *detected* rather than silently winning.

To add a record, add a fragment and re-run `build`. Never open the assembled
file.

## Retraction is exclusion plus a count, never deletion

A fragment carrying `supersedes: <id>` removes that id's **body** from the
assembled output and adds it to the `superseded` count. The superseded file
stays on disk and its id is still named in the assembled header, so a reader can
tell a retracted record from one that was never written.

```
assembled 2, superseded 1, total 3
```

`total` always equals `assembled + superseded`. A `supersedes:` pointing at an
id no fragment carries is a hard failure with the id named -- it means either
the target was deleted (which this rule forbids) or the id was mistyped, and
both make the `superseded` count a lie.

This is the same LIVE-vs-FROZEN classification the later phases apply to
retractions and superseded wording, so the program carries one rule instead of
two. The reason is stated best by the shipped model the shared pattern note quotes:
*discarding the run that disagrees is how a benchmark lies.*

## What the header is for

```
assembled 2, superseded 1, total 3
fragments-sha256: <64 hex characters>
```

A fragment written but never assembled is otherwise **invisible**: nothing
raises, no count moves, and the file a reader trusts is simply missing a record.
The count and the hash are the entire mechanism by which that becomes
detectable. The hash covers both the fragment **names** and their **contents** --
the content half moves when a fragment is edited, the name half when one is
added, removed or renamed, and either alone would miss the other.

## Files that are not fragments

Anything in a fragment directory whose name does not match the pattern is
**ignored, counted and named** in the output:

```
ignored 3: a-census-snapshot--after.json, ... , README.md
```

This is a live case, not a hypothetical: `_records/census/` holds this
repository's committed census snapshots and its own README. A scan that does not
print what it skipped cannot be audited.

## Commands

```
python tools/assemble_records.py build --dir _records/<kind>
python tools/assemble_records.py lint  --dir _records/<kind>
python tools/assemble_records.py lint  --dir _records/<kind> --report out.json
```

Exit codes follow the `canonkit.py` contract:

| Exit | Meaning                                                            |
| ---- | ------------------------------------------------------------------ |
| 0    | ran over a non-empty fragment population and did what it says       |
| 1    | a finding: the assembled file does not match its fragments          |
| 2    | could **not** look: zero fragments. Nothing is written              |

Exit 2 is a refusal, not an empty success. An empty assembled file reported as a
pass would make the next `lint` compare clean, and the missing fragments would
never surface.
