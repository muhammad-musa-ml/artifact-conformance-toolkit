# broken-uncommitted-waiver

A deliberately broken mini-artifact. The defect it carries is a **waiver
the owner never committed**, and the check expected to refuse it is **CHECK-10**.

## Why the defect is not in the committed bytes, and why that is not a cheat

Every other fixture in this tree commits its own defect. This one cannot, and
saying so plainly is cheaper than letting a reader discover it:

> A waiver that is **uncommitted** stops being uncommitted the moment it enters
> the index.

So the committed half of this fixture is the **baseline** -- a valid,
owner-authored waiver, present in `waivers.json` and therefore present in the
last committed version of it. `tools/tests/test_waivers.py` copies this tree,
commits the copy through `conftest.committed_tree`, and then writes a **second**
waiver into the working copy only. That second waiver is the defect, and the
checker must report it rather than honour it.

What is committed here is therefore the SHAPE -- the record a reviewer can open,
the entry keys, and a reason written as prose a reader can disagree with. What
the test adds is the one state the filesystem can hold and git cannot.

## What CHECK-10 does with this tree

| Input | Expected |
|-------|----------|
| the committed copy, unmodified | CHECK-10 PASS; one honoured waiver, counted and printed |
| the same tree with a waiver added to the working copy only | CHECK-10 FAIL, naming the uncommitted entry |
| a waiver missing `check_id`, `reason` or `dated_at` | not honoured, reported as malformed |

The waiver count prints in the summary line either way, because CHECK-10's
second half is that waivers are **countable rather than invisible**. A waived
check is reported as waived; it is never reported as a pass, and it never
disappears from the population.

## Why the round trip is the control rather than the friction

Build agents run unattended. A waiver a build agent can write is not a waiver,
it is an off switch on the checker that agent is being measured by. Requiring a
human, a reason and a commit is the whole mechanism, so the run's copy is
compared against `git show HEAD:./waivers.json` -- read back from git, never from
a cached copy the same process wrote.

## This tree carries no measurement

There is no `results/` directory here and there never will be. Other checks
therefore report DID-NOT-RUN against this fixture, which is correct: they could
not look. Only CHECK-10 has anything to examine, and it is the only verdict any
test here asserts on.
