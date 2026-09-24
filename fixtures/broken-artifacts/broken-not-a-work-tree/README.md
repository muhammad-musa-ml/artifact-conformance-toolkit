# `broken-not-a-work-tree/` -- the one-known-bad input for CHECK-07

**The defect:** a complete, plausible artifact directory that is **not a git work
tree**. It carries a README, a well-formed `results/figures.json`, a
`results/gate.json` and three per-item run records under `results/raw/` -- and no
repository of its own.

CHECK-07 must refuse it.

## This is not an invented shape, it is the shape BOTH shipped artifacts have

Measured and recorded in the shared pattern note: `ls -d <artifact>/.git` returns "No
such file or directory" for both artifacts that existed before this programme
did. Zero of the fourteen manifest slugs would pass CHECK-07 today. This fixture
is a faithful model of that state rather than a contrivance, which is why it is
worth committing.

## Why it cannot simply omit a nested `.git`, and what the check does instead

A plain directory sitting inside a repository is *inside a work tree* as far as
git is concerned: `git rev-parse --is-inside-work-tree` answers `true` here,
because it walks up and finds **this** repository. Omitting a nested `.git` is
therefore not enough on its own -- a naive branch one would report this tree as a
perfectly good work tree.

CHECK-07 compares `git rev-parse --show-toplevel` against the artifact directory
and treats "inside a work tree whose root is somewhere else" as NOT a work tree,
**naming the enclosing toplevel** in its message. That is the difference between
a check that works in a fixture and one that works on disk, and it is why this
fixture's expected finding id is `worktree:enclosed-by-other-toplevel` rather
than `worktree:not-a-work-tree`. Both are the same condition; they differ in what
the message can tell an author.

`test_a_directory_nested_in_this_repository_is_not_a_work_tree` asserts the same
thing against a throwaway directory, so the property is pinned independently of
this tree.

## What is NOT evaluated here, and why that is printed rather than assumed

Because this directory is not a work tree of its own, CHECK-07 does **not**
evaluate its tracked-ness branches, and says so in its population line:

```
tracked-ness not-evaluated (the artifact is not a work tree of its own, so
`git ls-files` here would answer about <toplevel>'s index rather than this
artifact's)
```

That restraint is the point. `git ls-files` run inside this directory answers
about the ENCLOSING repository's index -- and these files genuinely *are* tracked
by `artifact-conformance-toolkit`. A check that reported that would print a reassuring
truth about an artifact with no version control at all. An input that was not
examined is counted and given a reason; it is never folded into a pass.

## The chain is real, so the fixture demonstrates what tracked-ness is FOR

`results/raw/` carries three per-item records. Two have `ok: true`. The figures
record's `items_ok` is **value 2, population 3**, and its `derived_from` names
`results/raw/*.json#count(ok)`. The numerator was derived from the records by the
generator and asserted, not typed.

That chain is what `verify.py --tier derive` re-walks, and it is exactly what
a known hazard showed can go missing from a clone while CHECK-07 still reports a pass. This
fixture keeps the chain intact so the only thing wrong with it is the absence of
a repository.

## Defect count: one

Its figures record is well formed and every figure carries its denominator, so
CHECK-01 passes over it. Its README carries no `artifact:` region, so CHECK-03
reports DID-NOT-RUN rather than a finding -- it could not look, which is correct
and is not a defect of this tree. A fixture that failed several checks at once
would make "the checker refused it" unable to say which check did the refusing.
