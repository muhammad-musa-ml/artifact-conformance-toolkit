# `fixtures/broken-artifacts/` -- the committed known-bad tree

Every subdirectory here is a **deliberately broken mini-artifact**. Each one is a
one-known-bad fixture: an input a checker is expected to REFUSE, committed so the
defect shape is a reviewable artifact rather than a string built inside a test.

a design rule departs from the research deliberately. Research Section 4 item 10 specifies
temp-path construction **only**; a design rule adopts **both** -- temp paths for the
hermetic zero-input / one-known-bad pair (`conftest.tmp_artifact`), **plus** this
committed tree for the defect shapes drawn from the real artifacts. The reason is
that "made to fail on a real defect" is a stronger claim when the defect is
committed and a reviewer can open it.

## Naming

Every subdirectory name is prefixed **`broken-`**. The prefix is not decoration:
it is the mechanically locatable marker that lets a tool enumerate this tree
without a hand-maintained list, and a design rule requires the tree to be named
unmistakably.

Nothing that is not a deliberate defect belongs in a `broken-*` directory. A
fixture that accidentally became valid is worse than no fixture, because the test
that consumes it keeps passing while asserting nothing.

## This tree MUST stay outside anything `conformance.py` enumerates (a design rule -> a design rule)

If `conformance.py` scanned its own fixtures it would report a permanent wall of
findings against files that are broken on purpose -- and a checker nobody reads
is the exact failure a design rule exists to prevent, arriving through the other door.

**The constant that pins this is `conftest.SCAN_ROOT`**, declared in
`tools/tests/conftest.py` and asserted by
`tools/tests/test_repo_hygiene.py::test_broken_fixture_tree_is_outside_the_scan_root`.
an earlier plan writes the same value into `tools/manifest.json`'s declared scan root
 and asserts the two resolve equal, so the two cannot drift. If they
ever disagree, that disagreement is the finding -- never a value to pick between.

**Read the predicate before changing either constant.** This repository lives
INSIDE the scan root, at `<home>/Research/artifact-conformance-toolkit`, so this tree IS
a descendant of `SCAN_ROOT` by naive path containment. The property that actually
holds, and the one the test asserts, is that no part of this tree is ever
ENUMERATED as an artifact: `conformance.py` enumerates the immediate children of
`SCAN_ROOT` (depth 1) and this tree sits at depth 3. A test written as
`assert not tree.is_relative_to(SCAN_ROOT)` can never pass here, and making it
pass by shrinking `SCAN_ROOT` would break the manifest reconciliation and invent
a constraint nobody asked for.

## Access from a test

Never hand-build a path into this tree. Use the loader, which raises with the
list of available names on a miss so a typo is a findable error rather than a
silent skip:

```python
from tools.tests import conftest

tree = conftest.broken_fixture("broken-unpinned-dependency")
```

## Current fixtures

| Directory | Defect | Which check should refuse it | Provenance |
|-----------|--------|------------------------------|------------|
| `broken-unpinned-dependency/` | `requirements.txt` carries the unpinned specifier `elasticsearch>=8,<9` | **CHECK-08** (no unpinned specifier at a pull site) | Copied **byte-for-byte** from the real `example-search-benchmark/requirements.txt` on this machine (20 bytes, verified with `cmp`). It is a genuine shipped defect, not an invented one -- the shared pattern note's Conflicts row 9 names it as a ready-made committed known-bad input |
| `broken-figure-without-population/` | `results/figures.json` holds two figures; one carries a `population_label` and **no `population`** beside it. The README renders both inside a paired region, so the numeral rule has nothing to say and the record is the only thing wrong | **CHECK-01** (a figure appears without its population) | Invented, and deliberately a PAIR rather than a single bad figure: a check that refused the whole record would pass a one-figure fixture while discriminating nothing. The valid figure beside it is what makes `finding_ids == ["figure:cache_hit_ratio"]` an assertion worth making. The README also carries an ordered list, so the same expectation pins G-1's false positive shut |
| `broken-figure-in-prose/` | A figure **value** typed into un-rendered prose outside every region. Its shape is one the allow-list **permits** -- a bare integer after the word `port` classifies as a port -- so a shape-only rule reports the document clean and only the value check fires | **CHECK-01** (its value limb; a design rule paired with a design rule) | Invented from the project's own research summary, an earlier finding's named most-likely-executor-failure: deriving a number from a canon figure and typing it into a sentence. MEASURED against `canonkit.classify_numerals`: `unclassified=0, value_leaks=1`. This is the fixture that makes "both rules, not one" a claim a reader can check |
| `broken-unedited-limits/` | The `artifact:limits` region body is **byte-identical** to `templates/README-SKELETON.md`'s own placeholder. It fails four of CHECK-03's five conditions at once -- unedited, under the word floor, no scope vocabulary, and still carrying the skeleton's own marker | **CHECK-03** (an unedited template copy must not pass) | Invented by an earlier plan, but the defect shape is the one the inherited acceptance criterion could not see: a `grep -c` for the limitations heading **passes this tree**, because the heading survives every copy untouched. Its figures record is well formed on purpose, so **CHECK-01 passes over it** and "the checker refused it" says which check did the refusing. Its heading is deliberately NOT the skeleton's, so a check that quietly reverted to keying on heading text would report it clean |
| `broken-uncommitted-waiver/` | A waiver present in the run's `waivers.json` that is **not** in the last committed version of that file. What is committed here is the SHAPE -- a valid owner-authored waiver -- because the defect itself cannot be committed: a waiver that is uncommitted stops being uncommitted the moment it enters the index. `tools/tests/test_waivers.py` copies this tree, commits the copy through `conftest.committed_tree`, and adds a second waiver to the working copy only | **CHECK-10** (waivers are owner-authored and countable; a design rule, HARD) | Invented by an earlier plan from a design rule's stated reason: build agents run unattended, and a checker the thing being checked can silence is not a checker. This tree carries no `results/` directory and never will, so other checks report DID-NOT-RUN against it -- correctly, because they could not look |

## `expected-<CHECK-ID>.json` -- the anti-rot pin, and why it holds six keys

a design rule has two halves. The RED transcript under `red-transcripts/` is the first;
the second is "a test that re-runs each known-bad fixture and asserts the
captured output still matches", and it is the half that keeps the evidence from
rotting while the checker drifts.

A fixture that a check owns therefore carries `expected-<CHECK-ID>.json` beside
its `README.md` -- one file per check, so several checks can pin the same fixture
without sharing a write. an earlier plan established the shape with
`expected-CHECK-01.json`:

```json
{ "check_id": ..., "code": ..., "found": ..., "checked": ...,
  "finding_ids": [...], "schema_version": ... }
```

**Six keys, and not one wording-bearing field among them.** If the pin were
byte-for-byte over stdout prose, the first error-message improvement would break
it, and the standard repair -- weakening the assertion -- empties the mechanism.
a design rule gave every tool a `schema_version` precisely so this comparison stays stable
across versions; this is its first consumer.
`test_the_anti_rot_expectation_carries_no_prose_field` inspects the committed key
set itself rather than the comparison that reads it, so "the pin does not read
stdout" is checkable rather than asserted. The property was also demonstrated by
mutation: three human-readable messages were changed in a byte-snapshotted copy
of `check_01.py`, the pin stayed green, and the copy was restored from the
snapshot.

The expectation is **generated from a measured run and then defended by the
discriminating tests beside it** -- it freezes a verdict that
`test_a_figure_without_its_population_is_a_finding_naming_the_key` and
`test_a_figure_value_in_prose_is_caught_by_the_value_rule` establish
independently. On its own it would only prove the checker still agrees with
itself.

## `results/` inside this tree is committable, and only inside this tree

`.gitignore`'s broad `results/` rule was verified to swallow
`fixtures/broken-artifacts/**/results/*.json`, which would have meant an earlier plan
and an earlier plan could never commit the `results/figures.json` fixtures they need, and
an earlier plan's audit would have counted a population that silently excluded them. A
scoped negation admits **this tree only**; every other `results/` path in the
repository stays ignored, and
`test_fixture_results_are_committable` asserts both directions.
