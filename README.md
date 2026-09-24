# artifact-conformance-toolkit

A verification toolkit for measured engineering artifacts.

Its job is narrow and unusual: make it **structurally impossible to publish a number you cannot
defend**. Twelve checks read a finished artifact - its documents, its machine records, its git
state and its dependency pins - and refuse it when a figure has no population behind it, when a
gate cannot be shown to have preceded the measurement it authorised, or when the per-item records
a published figure is derived from are not actually tracked.

The rule underneath all of it:

> A check that ran over zero inputs is reported as a **failure** - never as a pass, and never as
> "skipped." A verdict with no population is not a verdict.

Every check prints the population it examined and the floor it was held to, on success as well as
on failure. The runner's exit codes are `0` pass, `1` finding, `2` did-not-run, `3` guard-fail;
at the artifact level any `1` **or any `2`** lifts the whole run to `1`, so a check that examined
nothing can never be mistaken for a check that examined something and approved it.

---

## Why the checks are trustworthy

A checker that has never failed is a checker nobody has tested. So each one ships with a committed
**RED transcript** under `red-transcripts/`, captured before its implementation existed, recording
that check genuinely failing on a real defect. There are 13 transcripts, measured 2026-09-20 by
listing `red-transcripts/`: one for each of the twelve checks and one for the banned-name lint.

That requirement is easy to satisfy dishonestly, and the transcripts are built to close the two
obvious holes:

- **A non-zero exit is not evidence.** A missing module or an absent input also exits non-zero and
  says nothing about whether the check can tell right from wrong. So every check was registered and
  *runnable* - with its detection stubbed to return a passing verdict - before its transcript was
  captured. Each recorded failure is therefore an assertion about a **verdict** produced by a check
  that really ran over inputs that really existed.
- **A timestamp is not evidence either.** Committing a transcript beside a finished implementation
  produces the same ordering as writing the transcript first. So the audit additionally requires
  that the transcript's commit *be* a test commit, with an implementation commit after it.

Beyond that, `tools/mutate.py` breaks each guard on purpose and confirms that the **named** guard
fires - not merely that "some test failed." A mutant that does not express the failure mode proves
nothing, and several early mutants here passed for exactly that reason and had to be rebuilt.

The deliberately broken artifacts each checker is proven against live in
`fixtures/broken-artifacts/`. There are 14 of them, measured 2026-09-20 by counting the
directories under that path.

---

## What the twelve checks enforce

Ten are modules under `tools/checks/`; two are properties of the runner itself and are emitted as
first-class rows so that neither can be silently absent.

| Check | Enforces |
|---|---|
| CHECK-01 | Every figure lives inside a paired anchor region, and no figure value leaks into prose. This makes back-solving a numerator from a published percentage mechanically impossible rather than merely discouraged. |
| CHECK-02 | The document's stated date agrees with a machine-emitted timestamp. |
| CHECK-03 | The "what this does not show" section exists, is not the template's placeholder, and carries real scope vocabulary. |
| CHECK-04 | The gate provably preceded the measurement - proven by content and token identity, not by trusting two dates the same author wrote. |
| CHECK-05 | The register's row count reconciles against a committed literal. |
| CHECK-06 | Every published figure traces back to a per-item record. |
| CHECK-07 | The artifact is a real git work tree **and its per-item records are tracked** - not merely that some machine-written file exists. |
| CHECK-08 | No unpinned dependency and no tag-only container image reference. |
| CHECK-09 | The claim-under-test block names a real source claim. |
| CHECK-20 | A finished artifact actually **changed the claim record it was built to back**. Every other check asks whether an artifact is well formed; this one asks whether its existence made any difference. |
| CHECK-10 | A waiver present in a run but absent from the committed `waivers.json` is itself a finding. |
| CHECK-11 | No check may report success over zero examined inputs. |

CHECK-07's wording is deliberate. An earlier version was satisfied by the presence of a published
figure file - which passed while the per-item records that figure is derived from were being
silently excluded from the index by a dependency-licence ignore rule that matched at any depth. The
check stayed green while the property it stood for was broken. It now asserts the property.

CHECK-20 is the one check that reads inputs from **outside** the directory under test, and it has
to: whether an artifact changed anything is invisible from inside it, because nothing inside an
artifact records what the claim used to say. Those inputs are supplied on the command line or by
the runner and are **never** taken from inside the artifact being judged - a checker the subject
can point at its own evidence is not a checker. For the same reason CHECK-20 is the one check that
is deliberately **not** copied into an artifact: it asks a question about two files that live
nowhere near one, so a copy could never answer it.

---

## Not every check applies to every artifact, and the exceptions are counted

Three checks are conditional: CHECK-05, CHECK-09 and CHECK-20. An artifact that owes no register
row, or backs no source claim, is not judged on one.

The mechanism matters more than the list. Applicability is decided by the runner **before any
module runs**, from the expected set the runner resolved - never from a file inside the artifact,
because an artifact that can declare its own checks inapplicable has no checks. An unknown slug
resolves to an empty row, and every predicate reads an empty row as *applicable*, so the default
is always the strict one.

Each inapplicable check is then **named in the output with its reason**, given the verdict word
`NOT-APPLICABLE`, and counted on a line of its own:

```
artifact: ran 12, not-applicable 0 (every one is named above with its reason)
```

Both numbers print on every run. A reader told only how many checks ran cannot tell a run that
narrowed its own population from one that had nothing to narrow, and `NOT-APPLICABLE` is
deliberately not one of the four exit-code verdicts so that it can never be totalled as a pass.

---

## Getting started

Developed and measured on CPython 3.13.5 with pytest 9.1.1. `pyproject.toml` declares
`requires-python = ">=3.12,<3.14"`. The lock is hash-pinned.

```
py -3.13 -m venv .venv
.venv/Scripts/python.exe -m pip install --require-hashes -r requirements.txt
git config core.hooksPath .githooks
.venv/Scripts/python.exe -m pytest tools/tests
```

All four were run against this tree on 2026-09-20, in that order, into a throwaway virtual
environment created from scratch - not into an already-populated one, because an install step
verified against an environment that already had the packages verifies nothing. Each exited 0. The
install reported `Successfully installed colorama-0.4.6 iniconfig-2.3.0 packaging-26.3
pluggy-1.6.0 pygments-2.21.0 pytest-9.1.1`.

Pick the interpreter your launcher actually has. `py -3.12` is equally supported by
`requires-python` but is not a universal alias: on the machine these figures were measured on it
exits 103, `No suitable Python runtime found`, because the 3.12 present there is managed by a tool
the launcher does not enumerate. Run `py -0p` and use a version it lists.

The third line activates a fail-closed pre-push hook that runs the suite. It is tracked and
versioned rather than local-only, so it travels with the repository.

---

## The tools

Every command in this section was executed against this tree on 2026-09-20 and its exit status is
recorded beside it. None is transcribed from a design document.

| Command | Exit | What it does |
|---|---|---|
| `python tools/conformance.py --self` | 0 | Point the checker at this repository. |
| `python tools/conformance.py --help` | 0 | Full option list, including the population floor override. |
| `python tools/conformance.py <artifact-dir>` | 1 | Run all twelve checks over one artifact. Exit 1 here is the tool working: it was pointed at a deliberately broken fixture. |
| `python tools/render.py --help` | 0 | Re-render a document's anchored regions. Reporting is the default and rewriting requires `--write`; there is deliberately no `--force`. |
| `python tools/vendor.py --help` | 0 | `vendor` copies the frozen core into an artifact; `audit` asserts the copy is byte-identical. |
| `python tools/lint_banned_names.py` | 0 | A banned-name lint with a live / frozen / detector role census. |
| `python tools/mutate.py --help` | 0 | The mutation harness. Requires `--tree`, and the tree must be committed. |
| `python tools/build_register.py --help` | 0 | Generate the register from the artifacts themselves. |
| `python -m tools.new_artifact --help` | 0 | Generate a new artifact directory as its own git work tree. |
| `python tools/new_artifact.py --help` | **1** | **Does not work.** See below. |

**Note the last row, because it is the whole reason this section carries exit statuses.**
`new_artifact` must be invoked as a **module**, not by path: running `python tools/new_artifact.py`
fails with `ModuleNotFoundError: No module named 'tools'`, because it imports `tools.vendor` and
running a file by path puts that file's own directory on the import path instead of the repository
root. Every other tool runs by path. A console entry point is a known gap.

---

## Design notes worth knowing

**`tools/canonkit.py` is a frozen core.** A single dependency-free ASCII file holding everything
that must not differ between artifacts: the exit-code contract, the population printer, the gate
token, the schema validators, sha256 and atomic write. It is copied byte-identical into every
artifact and its hash asserted there, so an artifact can self-check with no access to this
repository. It refuses to be imported under a dotted module name, which keeps the copied file and
the packaged one from silently diverging.

**The vendored set is declared, counted and asserted.** Five files are named explicitly - the
frozen core, the runner, the renderer, the check-module contract and the claim corpus - and the
per-check modules are globbed, because they arrived one at a time and their population is not
knowable at declaration time. The two numbers are printed separately rather than summed into one,
and a module deliberately left out of the set is **named with its reason** rather than filtered
silently. Measured 2026-09-20 by `tools/conformance.py --self`:

```
VENDOR-CONSISTENCY  PASS  vendored-set files hashed=14 of 14 (declared 5 + check modules 9)
```

The declared five carry a committed literal that is asserted against the derivation at import
time. A purely derived count silently stops checking when a name is dropped, because the expected
figure falls to match the found one - an emptied list would make every derived count agree with
zero and every audit pass over nothing.

**The register is generated, and it refuses to overwrite an edit.** Every figure in it is read out
of an artifact's own machine-written results at generation time, so the last hop where a human
retypes a number is removed rather than policed. Its trailer carries two hashes, and the pair is
the point: one over the generation inputs, one over the register's own body. Only the second can
detect a hand edit, because a hand edit changes the body and leaves every input untouched - a
guard keyed on the inputs hash alone would compare equal after an edit and regenerate straight
over it. On a mismatch it prints the diff and **writes nothing**, and the check runs before the
write call rather than after, because a refusal that happens after the write is not a refusal.

**It also refuses to publish into a throwaway directory.** A round trip that legitimately scans a
temporary tree once wrote its generated register back into that temporary tree, which is a
generator reporting success into a directory about to be deleted. The guard is scoped rather than
blanket - refusing *every* temporary root would be a guard that cannot tell its two arms apart,
satisfied by refusing everything - and a test asserts it still accepts the legitimate case.

**Line endings are load-bearing**, and this is measured rather than assumed. In a controlled
two-arm experiment, a 46-byte zero-CRLF core file committed without a `.gitattributes` came back
out of a clone at 52 bytes, carrying 6 CRLF and a different sha256 - and the cross-repository hash
assertion then failed for a reason having nothing whatever to do with the file's content. An
artifact looks tampered with when it is not, and the failure comes from the *mismatch* between two
repositories' settings rather than from either one alone, so both ends need the rule. The tracked
`.gitattributes` at the root is that rule, and it carries the experiment in its own header comment
so the setting is never separated from the reason for it.

**A guard must be able to discriminate.** Several early guards here matched their own
documentation rather than live code - one matched the filename `canonkit.py` via a
`startswith("canonkit.")` prefix test and produced 26 confident false findings. Structural
predicates (AST, position-on-line) replaced text matching wherever a guard judges code. The
banned-name lint redacts its own needle from every span it echoes, and verifies its zero-hit
results against a live control that returns one.

**Guards are checked in both directions.** A check asserting some text is *absent* can be satisfied
by a documented mention of the thing it forbids; a check asserting text is *present* can be
satisfied by a quotation of it. Both directions are tested.

---

## Layout

| Path | Contents |
|---|---|
| `tools/canonkit.py` | The frozen core. |
| `tools/conformance.py` | The runner: discovery, applicability, population printing, aggregation, waivers, structured report. |
| `tools/checks/` | The ten check modules. CHECK-10 and CHECK-11 are runner properties and have no module. |
| `tools/tests/` | The suite. |
| `templates/` | The artifact kit: document skeletons, a pinned lock, and the run chain (`gate.py`, `runmeta.py`, `provenance.py`, `derive.py`, `verify.py`). |
| `fixtures/broken-artifacts/` | The 14 deliberately broken artifacts each checker is proven against. |
| `red-transcripts/` | The 13 committed RED transcripts. |
| `examples/` | The source documents the example claim corpus is derived from, so every declared byte count and sha256 in it is the digest of a file you can open and recompute. |
| `register-fragments/` | The hand-written similarity judgments. They are numeral-free by rule; every number in the register comes from a machine record. |
| `_records/` | Captured run records. |
| `.githooks/pre-push` | The fail-closed gate. |

---

## Status

Measured on 2026-09-20 against this tree, on CPython 3.13.5 with pytest 9.1.1:

| Reading | Value | Population |
|---|---|---|
| Suite | `861 passed, 11 skipped`, 0 failed, exit 0 | 871 tests collected |
| Self-check | exit 0; `4 pass, 0 finding, 0 did-not-run, 0 guard-fail, 0 waived` | 4 checks ran, 11 not-applicable, each named with its reason |
| Banned-name lint | exit 0; `live 0, frozen 1, detector 0, unclassified 0` | 171 tracked files listed, 171 scanned, 0 unreadable |
| Dependency pins | exit 0; `found=0` | 15 references checked of 15 (12 specifiers, 3 images) |

Wall-clock time is left out of that table on purpose. The suite was run three times on 2026-09-20
and took 233.72s, 237.08s and 267.10s - a 14% spread on an unchanged suite, because the figure is
a property of what else the machine was doing. A single timing quoted as though it were a property
of the code would be the one number in this file you could not reproduce.

**The two counts in the first row do not add up, and the reason is worth stating rather than
rounding away.** 861 passed plus 11 skipped is 872 outcomes, against 871 collected tests. The
extra outcome is a whole module skipping at import time: `tools/tests/test_publish_repo.py` tests
a publishing script that is deliberately not part of this repository, and a module-level skip
produces one outcome while contributing zero collected tests. 861 passed plus the other 10
ordinary skips is exactly 871. A guard in that same module asserts the skip is really module-level,
so the premise is checked rather than assumed.

Everything else passes. The self-check exits 0 while naming eleven checks it did not run, because
this repository is the tooling rather than a measured artifact: it publishes no figures, mints no
gate token and backs no claim, so those checks have no population here. They are named with their
reasons instead of being omitted, since a checker silently absent from a report reads as a contract
that quietly shrank.
