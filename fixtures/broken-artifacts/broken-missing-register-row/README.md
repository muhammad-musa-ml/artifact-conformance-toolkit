# `broken-missing-register-row/` -- the one-known-bad input for CHECK-05

**The defect:** `backing-artifacts.md` carries one row fewer than
`tools/manifest.json`'s expected set requires. The omitted slug is
`alpha-artifact-3`, which the manifest marks `register_row: true`.

CHECK-05 must report `expected 12, found 11` and name the omitted slug in
`finding_ids`.

## This tree is an ARTIFACTS ROOT, not an artifact

Every other fixture under `fixtures/broken-artifacts/` is a mini-artifact. This
one is the directory artifacts live *in*, because that is where the register
sits: `tools/build_register.py` writes `backing-artifacts.md` at the artifacts
root's own root, beside the slug directories rather than inside one of them.

That engagement is the reason CHECK-05's resolver looks there FIRST. A resolver
that only searched `<artifacts-root>/<slug>/` would report a confident "no
register" against a register that is present -- the scope half of the measured
search-negative failure, where a glob at `<dir>/<x>/<y>/` silently excludes the
aggregate file at `<dir>`'s own root.

## The summary line inside it is DELIBERATELY WRONG, and that is the second half of the fixture's job

The generated register carries its own header summary. This fixture's says

```
- expected 12, found 12
```

while the body below it carries eleven `## <slug>` rows. **A check that read the
document's self-report rather than COUNTING ITS ROWS would report this tree
clean.**

That failure is not hypothetical, it is what the requirement's own wording
invites: "reported as `expected N, found M`" reads like two numbers to print, and
the shortest way to print them is to read them off the document. This fixture
makes that shortcut fail. `test_the_check_counts_rows_rather_than_believing_the_
documents_own_summary` is the assertion.

## Why the two `built` slug directories are here

`example-search-benchmark/` and `example-cache-benchmark/` each carry a
`.keep`. They exist because `tools/manifest.json` marks both `status: built`, and
the status rule makes **a `built` slug whose directory is MISSING**
a finding. Without them this tree would carry three defects instead of one and
"CHECK-05 refused it" could not say which one did the refusing -- the
discrimination failure `fixtures/broken-artifacts/README.md` warns about.

The twelve `pending` slugs deliberately have NO directory here, because the status rule's
other rule makes **a `pending` slug whose directory EXISTS** a finding too. The
fixture therefore satisfies both status rules and fails exactly one row check.

## What it is NOT

It carries no trailer. `tools/build_register.py` writes an `inputs-sha256` and a
`body-sha256` trailer and refuses to overwrite a hand-edited register;
that guard belongs to the generator, and CHECK-05 neither reads nor needs it.
Adding one here would make this fixture assert something about a mechanism it is
not testing.

It is also not a register any run produced. At the time it was committed, the
number of register rows carrying a `figures.json` was **zero of twelve**, so a
live `build_register.py` run exits 2 DID-NOT-RUN and publishes nothing. This tree
models the state *after* the twelve have run, minus one row -- which is the only
state in which a missing row is a defect rather than a schedule.

## Provenance

Generated from the live `tools/manifest.json` rather than typed: the slug list,
the expected literal and the excluded reasons were all read from that file, and
the generator asserts the omitted slug was in the derived expected set before
dropping it. A fixture that omitted a slug the manifest never expected would be
broken in a way no check could see.
