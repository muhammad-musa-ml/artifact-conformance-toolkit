"""The walking skeleton, end to end: generate -> commit -> FAIL -> fill in -> PASS.

This is the acceptance shape a project requirement states, run against a TEMPLATE-GENERATED
artifact rather than against a real one. Verified first-hand and recorded so the
choice is not mistaken for convenience: neither existing artifact under the scan
root is a git work tree, so zero of the fourteen manifest slugs would pass
CHECK-07 today, and an unqualified `expected 14, found 2` is a permanent red that
trains the owner to ignore the checker.

EVERY EXECUTABLE STEP RUNS THE ARTIFACT'S OWN COPY.
`<artifact>/gate.py`, `<artifact>/runmeta.py`, `<artifact>/derive.py`,
`<artifact>/render.py`, `<artifact>/verify.py` and the artifact's vendored
`<artifact>/conformance.py` -- the files the generator placed there. Running the
kit's copies instead would test the kit and leave the vendoring claim entirely
unexercised: a handed-over artifact directory must self-check with no access to
this repository, and that is the only claim this module can prove. `INVOKED`
below records the resolved path of every step and a test asserts each one lives
under the generated artifact.

`runmeta.py` ships no command line -- it is a library the driver and `derive.py`
import as a SIBLING -- so its entry in `INVOKED` is the module `__file__` that
really executed rather than an argv. That is a stronger claim, not a weaker one:
an argv says which path was named, a `__file__` says which file ran.

WHAT THIS MODULE DOES NOT YET COVER, AND WHO OWNS IT
------------------------------------------------------
Stated here so no reader mistakes an omission for an oversight.

  THE MUTATION LEG -- an earlier plan owns it. That plan owns a design rule and a design rule and
      a success criterion, and it extends this round trip with a mutant-to-guard catalogue.
      Step 11 below is a byte-snapshot hand edit, not a mutation campaign.

  THE ELEVEN-CHECK COMPLETION -- DONE, by an earlier plan, and this module owns it
      from here. At an earlier round only CHECK-01, CHECK-03 and the two runner properties
      existed, so the literal was `EXPECTED_CHECKS_AT_WAVE_7 = 4`. an earlier round landed
      the remaining seven and three of them did not pass on the artifact as
      built here. All three are now closed BY SUPPLYING WHAT THE CHECK REQUIRES
      -- never by narrowing a check:

        CHECK-07  closed already: step 6 commits the results/ tree, so
                  `git ls-files results/` inside the artifact returns tracked
                  machine-written files and the per-item records with them.
                  Step 6b re-asserts it rather than assuming it.
        CHECK-05  the generated slug is not a manifest slug, so the register
                  comparison resolved to `expected 0, found 0` -- which plan
                  an earlier plan correctly makes code 2. Step 6b writes a ONE-SLUG
                  expected set in the work directory with `register_row: true`
                  and generates the row with tools/build_register.py, so the
                  check runs over a real population of 1. The slug is NOT
                  marked `register_row: false`: that converts a real comparison
                  into `expected 0, found 0`, which is the 0/0 pass wearing a
                  different hat.
        CHECK-09  the skeleton ships no claim-under-test block. Step 5 fills it
                  in the SAME edit as the other region bodies, using a REAL
                  compound-keyed bullet read from tools/canon-bullets.json with
                  its verbatim text, the measured counterpart and a legal
                  verdict.

  AND ONE GAP THAT WAS NOT THIS MODULE'S TO CLOSE -- CLOSED 2026-09-17 BY PLAN
      an earlier plan, and the paragraph is kept because the shape is worth reading.
      `tools/canon-bullets.json` USED TO BE absent from `tools/vendor.py`'s
      VENDORED_SET, so `vendor_into()` did not place it in a generated
      artifact and the artifact's own CHECK-09 REFUSED:

          the canon snapshot is not at <artifact>/canon-bullets.json, so no
          bullet text can be compared against anything. REPAIR: vendor
          canon-bullets.json beside the checks package.

      a design rule requires a handed-over directory to self-check with NO access to this
      repository, so a check that is inert inside every artifact the programme
      ships is a real defect. CLOSED by an earlier plan: `tools/canon-bullets.json`
      joined VENDORED_SET and its committed count moved 4 -> 5, so the generator
      now places the snapshot itself. Step 4b no longer copies it in -- it
      ASSERTS that the vendoring did, which is strictly stronger, because a
      hand-copy proved only that this fixture can place a file. Raised by plan
      an earlier plan, carried as an earlier plan open item 8, discharged by an earlier plan.

  Naming them is the point. An assertion that "conformance passes" is only as
  strong as the set of checks that existed when it ran, and that set is written
  down here rather than implied.

WHY THE LITERAL AND THE IDENTITY ARE BOTH ASSERTED. A green "all checks pass"
over an unstated population is the 0/0 pass wearing a different hat. Stating the
number makes the later gap a FAILING assertion rather than an invisible one --
and stating `len(checks) == discover().found + len(RUNNER_CHECK_IDS)` beside it
is what stops that gap from ever being closed by LOWERING the number.
"""

import hashlib
import importlib.util
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from tools.tests import conftest
from tools.tests.test_template_generate import TOOL_04_REQUIRED

REPO_ROOT = conftest.REPO_ROOT
CHECKS_DIR = REPO_ROOT / "tools" / "checks"

SLUG = "walking-skeleton"
ITEM_COUNT = 8

# EVERY check an ARTIFACT carries: the nine modules discover() finds inside a
# vendored copy plus the two RUNNER PROPERTIES conformance.py emits as
# first-class checks[] rows. The repository itself holds ten modules; the tenth
# is a programme check that is deliberately not vendored (tools/vendor.py's
# NOT_VENDORED_CHECKS names it with its reason).
#
# RAISED 4 -> 11 BY AN EARLIER PLAN, and the route matters as much as the number.
# an earlier plan committed this literal as `EXPECTED_CHECKS_AT_WAVE_7 = 4` -- two
# modules plus two runner properties -- precisely so that an earlier round landing seven
# more modules would make it a FAILING assertion rather than an invisible gap.
# It failed, exactly as designed, and its own message forbade the cheap repair:
# "an earlier plan task 2 owns raising this literal to eleven -- never lowering it to
# match."
#
# Eleven was reached by ELEVEN CHECKERS ACTUALLY REPORTING, never by lowering.
# Three of them did not pass on the artifact as an earlier plan built it, and all
# three were closed by SUPPLYING WHAT THE CHECK REQUIRES rather than by narrowing
# any of them -- see build_round_trip()'s steps 4b, 5 and 6b.
#
# The wave-independent identity is asserted BESIDE this literal and is the
# reason lowering it could never have produced a green run: `len(checks) ==
# discover().found + len(RUNNER_CHECK_IDS)` read 2 + 2 == 4 and reads
# 9 + 2 == 11 here, unchanged. The literal moves; the identity does not.
#
# IT DID NOT MOVE WHEN check_20.py LANDED, and the reason is the interesting
# half. The repository now holds TEN check modules, but this artifact carries
# NINE: tools/vendor.py declares check_20.py as deliberately NOT vendored,
# because it reads the owner's live collections entries and a vendored artifact is
# a directory that may be handed to a stranger. So the identity holds at 9 + 2
# and this number is unchanged -- which is exactly what an identity that
# survives the wave should do when a module count moves for a reason that never
# reaches the artifact.
EXPECTED_CHECKS = 12


def _load(stem, path):
    """Load a module BY PATH under a bare stem, the local convention."""
    if stem in sys.modules:
        return sys.modules[stem]
    spec = importlib.util.spec_from_file_location(stem, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError("could not build a spec for %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[stem] = module
    spec.loader.exec_module(module)
    return module


def load_from_artifact(stem, artifact, name):
    """Load a module the ARTIFACT carries, with the artifact root importable.

    The run-chain files import their siblings by bare name -- `import canonkit`,
    `import runmeta` -- which is exactly how they run inside a handed-over
    directory. The artifact root therefore goes on the path for the duration of
    the load and comes straight back off, and any `canonkit` this leaves behind
    is removed: a sibling load here must not change what another test module's
    core resolves to.
    """
    path = Path(artifact) / name
    root = str(artifact)
    had = {key: sys.modules[key] for key in ("canonkit",) if key in sys.modules}
    sys.path.insert(0, root)
    try:
        spec = importlib.util.spec_from_file_location(stem, str(path))
        if spec is None or spec.loader is None:
            raise RuntimeError("could not build a spec for %s" % path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[stem] = module
        spec.loader.exec_module(module)
    finally:
        if root in sys.path:
            sys.path.remove(root)
        for key in ("canonkit",):
            if key in had:
                sys.modules[key] = had[key]
            else:
                sys.modules.pop(key, None)
    return module


core = _load("frozen_core_for_roundtrip", REPO_ROOT / "tools" / "canonkit.py")
conformance = _load("conformance_for_roundtrip", REPO_ROOT / "tools" / "conformance.py")
checks = _load("check_contract_for_roundtrip", CHECKS_DIR / "__init__.py")

RUNNER_CHECK_IDS = conformance.RUNNER_CHECK_IDS

GIT_IDENTITY = ["-c", "user.name=artifact-conformance-toolkit tests",
                "-c", "user.email=tests@example.invalid",
                "-c", "commit.gpgsign=false",
                "-c", "core.hooksPath="]


# ---------------------------------------------------------------------------
# What an author writes. Region bodies only; the regions themselves are the
# addressing mechanism and the headings above them are free prose.
# ---------------------------------------------------------------------------

# CHECK-09's claim-under-test block is keyed to a REAL canon bullet, read from
# the snapshot at run time rather than pasted here.
#
# Pasting the text would make this module a SECOND copy of the canon, and the
# check whose entire job is a byte-for-byte comparison against the snapshot would
# then be comparing the snapshot against a stale transcription of itself -- which
# is the paraphrase failure an earlier step exists to catch, arriving through the test
# instead of through an author.
#
# The id is COMPOUND (`canon:project-bullet`). A bare `P5-B5` is a finding in its
# own right (CHECK-09's `bare-bullet-id` kind) because two canons can carry the
# same bare id, and the fixture broken-bare-bullet-id pins exactly that.
CANON_SNAPSHOT_NAME = "canon-bullets.json"
CLAIM_BULLET_KEY = "example-alpha:P5-B5"


def canon_bullet(key=CLAIM_BULLET_KEY):
    """One bullet, READ from the committed snapshot with an explicit encoding.

    The snapshot is written with ensure_ascii=False; a default-locale read on
    this machine is cp1252 and would either raise or silently mojibake the very
    bytes the comparison depends on.
    """
    path = REPO_ROOT / "tools" / CANON_SNAPSHOT_NAME
    record = json.loads(path.read_text(encoding="utf-8"))
    bullets = record["bullets"]
    assert key in bullets, (
        "%s carries no bullet %r. Available compound keys: %d"
        % (path, key, len(bullets)))
    entry = bullets[key]
    text = entry.get("text")
    assert isinstance(text, str) and text, (
        "bullet %r carries no verbatim text, so the byte comparison would have "
        "nothing to compare" % key)
    return entry


HEADLINE_TABLE = (
    "| | Before | After |\n"
    "|---|---|---|\n"
    "| Mean per-item latency, ms | {{figures.mean_latency_ms}} | "
    "{{figures.mean_latency_ms}} |\n"
    "| Items meeting the predicate | {{figures.items_ok}} | "
    "{{figures.items_ok}} |\n"
    "| Share meeting it, percent | {{figures.ok_rate_pct}} | "
    "{{figures.ok_rate_pct}} |\n")

# The measured counterpart is a PROSE POINTER, not a `{{figures.*}}` reference,
# and that is the skeleton's own convention rather than a dodge:
# the RESULTS skeleton ships "the headline ratio rendered in the claim
# block at the top of this file" in exactly this cell. (Named without its kit
# path on purpose: test_this_module_never_reaches_for_the_kit_directory scans
# this file's source for that path, and a comment EXPLAINING the kit would
# otherwise fire the guard against its own documentation -- the sixth instance
# of that shape measured in this phase.) A key reference here would
# also put a rendered numeral inside a claim table, which is the one place in an
# artifact where a numeral belongs to the CANON rather than to this measurement.
MEASURED_COUNTERPART = ("the share meeting the predicate, rendered in the "
                        "figures block of this artifact")


def claim_table():
    """The claim-under-test table, keyed to a REAL bullet read from the snapshot."""
    entry = canon_bullet()
    return (
        "| Field | Value |\n"
        "|---|---|\n"
        "| Canon | %s |\n"
        "| Example project | %s |\n"
        "| Bullet id | %s |\n"
        "| Bullet text, verbatim | %s |\n"
        "| Measured counterpart | %s |\n"
        "| Verdict | DOES-NOT-SUPPORT |\n"
        % (entry["canon"], entry["id"].split("-")[0], CLAIM_BULLET_KEY,
           entry["text"], MEASURED_COUNTERPART))


def claim_body():
    """README.md's `artifact:claim` region: the headline table AND the claim table."""
    return (
        "This walking-skeleton artifact exists to prove the run chain end to "
        "end. It\nmeasures a deterministic stand-in rather than a real system.\n"
        "\n" + HEADLINE_TABLE + "\n"
        "**Claim under test.** This artifact measures a deterministic stand-in "
        "and\nbacks the bullet below only as a shape. The verdict records that.\n"
        "\n" + claim_table())


# THE BULLET-FREE CLAIM BODY, kept under its original name and its original
# bytes, and the split is deliberate rather than tidy.
#
# tools/tests/test_mutation.py imports `skeleton.CLAIM_BODY` to build ITS
# committed artifact -- one definition serving both modules, which is the
# property that would have been lost by turning this into a function only.
#
# But the mutation campaign's whole invariant is that EVERY probed guard is
# SILENT on the unmutated artifact, so that a guard firing afterwards attributes
# to the mutant rather than to the fixture. A real canon bullet cannot go in
# here: MEASURED over the committed snapshot, 0 of its 49 bullets have text
# canonkit.classify_numerals reads cleanly, so CHECK-01 would fire on the
# unmutated tree and every mutant it caught would be MISATTRIBUTED. (That is not
# hypothetical -- it was measured, in this exact module, the first time
# CLAIM_BODY carried a real bullet.)
#
# So the constant stays bullet-free and numeral-free, and `claim_body()` below
# builds the ROUND TRIP's version with a real bullet in it. The round trip runs
# CHECK-09; the mutation campaign runs neither and needs neither.
#
# WHAT AN EARLIER PLAN CHANGED HERE, AND WHAT IT DID NOT. The measurement above is
# frozen and still true -- 0 of 49 bullets have text classify_numerals reads
# cleanly. What is no longer true is the CONSEQUENCE: check_01.py now classifies
# a verbatim canon quotation against the same corpus CHECK-09 resolves against,
# so a real bullet here would no longer fire CHECK-01 (an earlier plan open item 13). The
# constant stays bullet-free anyway, because nothing about the mutation campaign
# needs a bullet and a fixture that depends on a second check's behaviour for
# its silence is a fixture with a second way to break. What DID go is the
# owner-authored waiver the round trip used to carry for these numerals: it is
# removed rather than renewed, which is the whole point of closing item 13.
CLAIM_BODY = """This walking-skeleton artifact exists to prove the run chain end to end. It
measures a deterministic stand-in rather than a real system.

| | Before | After |
|---|---|---|
| Mean per-item latency, ms | {{figures.mean_latency_ms}} | {{figures.mean_latency_ms}} |
| Items meeting the predicate | {{figures.items_ok}} | {{figures.items_ok}} |
| Share meeting it, percent | {{figures.ok_rate_pct}} | {{figures.ok_rate_pct}} |

**Claim under test.** This artifact backs no published claim. It exists so the
chain that backs the real ones can be run before any of them is built.

| Field | Value |
|---|---|
| Canon | none |
| Example project | none |
| Bullet id | none |
| Bullet text, verbatim | not applicable to a walking skeleton |
| Measured counterpart | {{figures.ok_rate_pct}} |
| Verdict | DOES-NOT-SUPPORT |
"""


def results_claim_body():
    """results/RESULTS.md's `artifact:claim` region: the headline table ONLY.

    The two skeletons put DIFFERENT things in the region of the same name --
    check_09.py's docstring records exactly that, which is why it finds claim
    tables structurally rather than by anchor. RESULTS-SKELETON.md carries its
    claim-under-test table FURTHER DOWN, outside every region; writing a second
    one into its claim region would give that one document two claim tables, one
    of them a duplicate of the README's.
    """
    return ("The run chain measured a deterministic stand-in. The table below is "
            "the\nheadline; the claim under test is recorded further down this "
            "file.\n\n" + HEADLINE_TABLE)

FIGURES_BODY = """| Guard | Population | Floor | Result |
|---|---|---|---|
| gate assertions | {{figures.items_ok}} | {{figures.items_ok}} | {{figures.ok_rate_pct}} |

| Figure | Value | Population | What it is a function of |
|---|---|---|---|
| share meeting the predicate | {{figures.ok_rate_pct}} | {{figures.items_ok}} | per-item records written by this run |
| mean per-item latency | {{figures.mean_latency_ms}} | {{figures.items_ok}} | the same per-item records |
"""

ENV_BODY = """| Field | Value |
|---|---|
| Measurement | a deterministic stand-in; nothing here touched a device |
| Run token | minted by the gate before anything was measured |
| Metered spend | none; no provider was called |
| GPU minutes | none; no device was opened |
"""

RESULTS_LIMITS_BODY = """This record does not show throughput, latency under load, or behaviour on any
machine other than the one that produced it. Its population is a deterministic
stand-in written by the reference driver, so nothing here can be compared with a
production system and none of it may ever be read as a capacity claim.
"""

# STEP 8's one change. Over the word floor, carrying bounding vocabulary, free of
# the skeleton's own marker, and free of numerals so it changes nothing CHECK-01
# has an opinion about.
FILLED_IN_LIMITS = """This is a walking skeleton. It does not show throughput, latency under load, or
behaviour on any machine other than the one that produced it. The population is
a deterministic stand-in written by the reference driver, so nothing here can be
compared with a production system and none of it may ever be read as a capacity
claim.
"""

# The one-slug expected set step 6b writes, and the fragment the register needs.
#
# Its committed literals AGREE WITH ITS OWN DERIVATION -- one register_row slug,
# one built slug, zero pending -- because check_05 reports a `manifest-drift`
# finding when they do not, and a synthetic expected set that drifts would make
# CHECK-05 fail here for a reason having nothing to do with the register.
ONE_SLUG_MANIFEST = {
    "schema": "manifest/1",
    "schema_version": 1,
    "scan_root": {"relative_to_repo_root": "..", "depth": 1},
    "min_population_overrides": {},
    "counts": {
        "register_rows_expected": 1,
        "register_rows_derived": 1,
        "built_expected": 1,
        "built_derived": 1,
        "pending_expected": 0,
        "pending_derived": 0,
        "scanned_expected": 1,
        "scanned_derived": 1,
    },
    "slugs": [{
        "slug": SLUG,
        "scanned": True,
        "status": "built",
        "register_row": True,
        "canon": "example-alpha",
        "project": "P5",
        # THE CLAIM THIS ROW OWES, and it is the one the artifact answers for.
        #
        # CORRECTED by an earlier plan, and the correction is the point rather than
        # a detail. This row used to read `bullets: []` with a `no_row_reason`
        # saying "it backs no claim" -- while the same fixture writes a
        # claim-under-test table naming CLAIM_BULLET_KEY and a figures record
        # carrying that key as its `canon_bullet`, which CHECK-09 then passes
        # over five references of. The two halves contradicted each other, and
        # answering a claim with the verdict DOES-NOT-SUPPORT is an OBLIGATION
        # discharged, never an absence: the artifact WAS pointed at that bullet
        # and reported that it does not support it.
        #
        # Nothing surfaced the contradiction until the runner started reading
        # this row to decide whether CHECK-09 APPLIES. It then correctly
        # declined to ask -- and the round trip silently stopped exercising the
        # check whose skeleton block it generates. The repair is to make the
        # row say what the fixture already does, not to narrow the test.
        #
        # `no_row_reason` is gone with it, and by the field's own definition it
        # never belonged here: check_05.excluded_slugs() reads it only for rows
        # with `register_row` FALSE, and this row carries one.
        "bullets": [CLAIM_BULLET_KEY],
        "backs_bullets": [],
        "gpu_required": False,
    }],
}

# Numeral-free on purpose: CHECK-01 lints every numeral in the documents it
# scans, and the register is generated into the WORK DIRECTORY rather than into
# the artifact, but the habit is the one this programme keeps everywhere.
REGISTER_FRAGMENT = """# walking-skeleton

verdict: DOES-NOT-SUPPORT

A deterministic stand-in written by the reference driver. It backs no published record
bullet; it exists so the chain that backs the real ones can be run before any of
them is built.
"""

FIGURE_SPECS = [
    {"key": "ok_rate_pct", "unit": "percent", "kind": "rate", "predicate": "ok",
     "population_label": "replayed items"},
    {"key": "items_ok", "unit": "items", "kind": "count", "predicate": "ok",
     "population_label": "replayed items"},
    {"key": "mean_latency_ms", "unit": "ms", "kind": "mean",
     "predicate": "latency_ms", "population_label": "replayed items"},
]

SPEC_COMMON = {
    # The SAME compound key the claim table names, and a real `canon_value`
    # beside the measured one. CHECK-09's figures limb reports `no-counterpart`
    # when exactly one side of the comparison is present -- `canon_value: null`
    # is "present with nothing in it", which is the case that branch exists for.
    "canon_bullet": CLAIM_BULLET_KEY,
    "canon_value": "nine GPU-hours of tuning against two days of prompt work",
    "similar": "SUPPORTS",
    "similar_reason_ref": "prior-run-note.md#the-round-trip",
    "tier_achieved": "T1",
    "reproduce_criterion": {"kind": "relative", "tolerance": 0.01},
    "threshold_claim": False,
    "not_shown": "A hermetic walking-skeleton run; it measures nothing real.",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def region_pattern(name):
    return re.compile(
        r"(<!--\s*artifact:%s:begin\s*-->\n).*?(<!--\s*artifact:%s:end\s*-->)"
        % (name, name), re.S)


def region_body(text, name):
    match = re.search(
        r"<!--\s*artifact:%s:begin\s*-->\n(.*?)<!--\s*artifact:%s:end\s*-->"
        % (name, name), text, re.S)
    return match.group(1) if match else None


def replace_region_body(path, name, body):
    text = Path(path).read_bytes().decode("utf-8")
    replaced, count = region_pattern(name).subn(
        lambda m: m.group(1) + body + m.group(2), text)
    assert count == 1, "region %r matched %d time(s) in %s" % (name, count, path)
    Path(path).write_bytes(replaced.encode("utf-8"))


def git(work, *args, check=True):
    result = conftest.run_cli(["git"] + GIT_IDENTITY + list(args), cwd=work)
    if check:
        assert result.exit_code == 0, (
            "git %s failed in %s: %s" % (" ".join(args), work, result.stderr))
    return result


def fill_results_claim_table(path):
    """Fill results/RESULTS.md's own claim-under-test table, IN PLACE.

    Each substitution is verified to have landed. A regex that silently matched
    nothing would leave the skeleton's `<...>` instructions in the shipped
    document while this function reported success, and CHECK-09's resulting
    findings would then read as a defect in the check.
    """
    entry = canon_bullet()
    rows = [
        (r"^\| Canon \|.*$", "| Canon | %s |" % entry["canon"]),
        (r"^\| Example project \|.*$",
         "| Example project | %s |" % entry["id"].split("-")[0]),
        (r"^\| Bullet id \|.*$", "| Bullet id | %s |" % CLAIM_BULLET_KEY),
        (r"^\| Bullet text, verbatim \|.*$",
         "| Bullet text, verbatim | %s |" % entry["text"]),
        (r"^\| Measured counterpart \|.*$",
         "| Measured counterpart | %s |" % MEASURED_COUNTERPART),
        (r"^\| Verdict \|.*$", "| Verdict | DOES-NOT-SUPPORT |"),
    ]
    text = path.read_bytes().decode("utf-8")
    written = []
    for pattern, replacement in rows:
        text, count = re.subn(pattern, replacement.replace("\\", "\\\\"),
                              text, count=1, flags=re.M)
        assert count == 1, (
            "the claim-table row %r matched %d line(s) in %s; a substitution "
            "that matched nothing would leave the skeleton's placeholder in the "
            "shipped document" % (pattern, count, path))
        written.append(replacement)
    path.write_bytes(text.encode("utf-8"))
    return written


# THE WAIVER THIS ROUND TRIP USED TO CARRY IS GONE (an earlier plan, an earlier plan item 13).
#
# It excused two CHECK-01 findings -- one per scanned document -- for the
# numerals inside the canon bullet the claim table quotes VERBATIM as CHECK-09
# requires. That was the sanctioned closure at the time and it was honest: the
# repair belonged in check_01.py, which was outside an earlier plan's file set.
#
# check_01.py now classifies those numerals against the same corpus CHECK-09
# resolves against, so there is no finding left to excuse. The waiver was
# REMOVED rather than renewed: a waiver carried forward past its repair is the
# documented-not-fixed shape this programme forbids, and it would also have gone
# silently inert -- `waived` falls to 0 on its own once the finding stops
# existing, which is exactly how a stale waiver hides.
#
# The record itself STAYS, empty and present, because that is a fact CHECK-10
# has a population over. Deleting the file would turn CHECK-10 into a
# DID-NOT-RUN and trade one silence for another.

# A hand-typed numeral that is NOT the canon bullet's, NOT a figure value, and
# not a date, version, port or list marker -- so a finding on it attributes to
# the sentence `scaffold_waiver` writes and to nothing else.
SCAFFOLD_NUMERAL = "41"
SCAFFOLD_SENTENCE = (
    "This fixture deliberately carries %s hand-typed items of scaffolding in "
    "un-rendered prose.\n" % SCAFFOLD_NUMERAL)
SCAFFOLD_WAIVER_REASON = (
    "The owner accepts this hand-typed numeral for the duration of the "
    "fixture. It exists so the design rule round trip has a REAL finding to complete "
    "over an otherwise conformant world: a waiver asserted over a world with "
    "nothing to waive proves nothing, and `waived == 0` is what a broken "
    "waiver and an unneeded one both look like.")


def commit_waivers(artifact, entries=()):
    """Write the artifact's waivers.json. COMMITTED at step 6, never a switch.

    a design rule (HARD): the run's waivers record is compared against the LAST COMMITTED
    copy read back through git, and a waiver present in the first and absent from
    the second is itself a finding. Writing it here and committing it at step 6
    is the owner round trip the decision describes; a build agent that could
    silence a check without that round trip would not be running a checker.

    EMPTY BY DEFAULT. The round trip needs no waiver since an earlier plan item 13 closed;
    the conformant WORLD asks for one by passing `waive=True`, because the test
    named for the round trip has to watch a waiver actually suppress something.
    """
    payload = {
        "schema": "canonkit/waivers/1",
        "schema_version": "canonkit/1",
        "rule": "OWNER-AUTHORED ONLY. Every entry needs check_id, reason, dated_at.",
        "waivers": list(entries),
    }
    (Path(artifact) / "waivers.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    return [waiver["finding_id"] for waiver in payload["waivers"]]


def scaffold_waiver(artifact):
    """A README sentence carrying one real CHECK-01 finding, and the waiver for it.

    Returns the waiver entry. The sentence goes into un-rendered prose ABOVE the
    claim block, so the finding is a plain unclassified numeral rather than
    anything the canon-text mask or the rendered-hole mask would touch.

    The numeral is asserted NOT to be a figure value first: a collision would
    make this a `leak:` finding under a different id, the waiver would not
    apply, and the test that reads `waived` would report a broken waiver as a
    broken mask.
    """
    figures = json.loads(
        (Path(artifact) / "results" / "figures.json").read_text(encoding="utf-8"))
    values = {str(entry.get("value"))
              for entry in (figures.get("figures") or {}).values()
              if isinstance(entry, dict)}
    assert SCAFFOLD_NUMERAL not in values, (
        "%r is also a measured figure value %r, so the finding it raises would "
        "carry a leak: id and this waiver would silently not apply"
        % (SCAFFOLD_NUMERAL, sorted(values)))

    readme = Path(artifact) / "README.md"
    text = readme.read_bytes().decode("utf-8")
    marker = "<!-- artifact:claim:begin -->"
    assert marker in text, "no claim region to insert above in %s" % readme
    text = text.replace(marker, SCAFFOLD_SENTENCE + "\n" + marker, 1)
    readme.write_bytes(text.encode("utf-8"))

    return {"check_id": "CHECK-01",
            "finding_id": "numeral:README.md:%s" % SCAFFOLD_NUMERAL,
            "reason": SCAFFOLD_WAIVER_REASON,
            "dated_at": "2026-09-17T00:00:00+03:00"}


def tracked_hashes(work):
    """sha256 of every TRACKED file, keyed by its repo-relative path.

    Tracked rather than present: the claim at step 9 is about the committed
    tree, and an untracked scratch file changing is not a change to the artifact
    a reader would receive.
    """
    listing = git(work, "ls-files").stdout.split("\n")
    digests = {}
    for relative in sorted(name.strip() for name in listing if name.strip()):
        path = Path(work) / relative
        if path.is_file():
            digests[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


@dataclass
class Trip:
    """Everything the round trip produced, so each property gets its own test."""

    artifact: Path = None
    invoked: dict = field(default_factory=dict)
    generate: object = None
    gate: object = None
    derive: object = None
    render_write: object = None
    render_check: object = None
    conformance_fail: object = None
    conformance_pass: object = None
    verify: object = None
    render_drift: object = None
    render_restored: object = None
    tracked_before: dict = field(default_factory=dict)
    tracked_after: dict = field(default_factory=dict)
    tracked_pre_edit: dict = field(default_factory=dict)
    tracked_post_restore: dict = field(default_factory=dict)
    runmeta_file: str = ""
    items_dir: str = ""
    raw_dir: str = ""
    limits_before: str = ""
    limits_after: str = ""
    root_commit_paths: list = field(default_factory=list)
    committed_results: list = field(default_factory=list)
    edited_hole: str = ""
    canon_snapshot: str = ""
    manifest_path: str = ""
    register_path: str = ""
    register: object = None
    results_claim_rows: list = field(default_factory=list)
    retractions_reviewed_on: str = ""
    waiver_ids: list = field(default_factory=list)


def build_conformant_artifact(workdir, fill_limits=True, waive=False):
    """Steps 1 through 6b: an artifact that satisfies every check, built the
    documented way.

    EXTRACTED so more than one test module can have a CONFORMANT artifact
    without re-deriving the recipe. Measured before the extraction, an artifact
    from `new_artifact` plus gate, measure and commit alone leaves SIX checks
    unsatisfied -- CHECK-01, 02, 03, 05, 09 and 20 -- because figures, a README
    date agreeing with a machine stamp, an edited limits paragraph, a register,
    a claim-under-test block and an expected-set row are all AUTHORED, not
    generated. Every one of those steps is below, in the order the documentation
    gives them.

    `fill_limits=False` stops one step short, leaving the artifact in the state
    step 7 needs: conformant in every respect EXCEPT the unedited limits
    paragraph, which is the single thing that round trip exists to watch fail
    and then pass. `build_round_trip` is the only caller that wants that.

    `waive=True` adds ONE hand-typed numeral to the README and an owner-authored,
    committed waiver naming the finding it raises. OFF by default, because this
    artifact is otherwise clean and a fixture that carries a deliberate defect
    for every caller would make that defect part of the recipe. It is on for
    exactly one caller -- test_waivers.py's committed-waiver round trip, which
    has to watch a waiver SUPPRESS something over a world that reaches exit 0,
    and which a clean world could not show at all.

    Returns the `Trip` it populated. `trip.artifact` and `trip.manifest_path`
    are the two a caller needs; the rest is the record of what each step
    returned.
    """
    trip = Trip()
    workdir = Path(workdir)
    reports = workdir / "reports"
    reports.mkdir(parents=True, exist_ok=True)

    # -- 1. GENERATE --------------------------------------------------------
    trip.generate = conftest.run_cli(
        [sys.executable, "-m", "tools.new_artifact", SLUG, "--into", str(workdir)],
        cwd=REPO_ROOT)
    artifact = workdir / SLUG
    trip.artifact = artifact

    trip.root_commit_paths = git(
        artifact, "show", "--pretty=format:", "--name-only",
        git(artifact, "rev-list", "--max-parents=0", "HEAD").stdout.strip()
    ).stdout.split()

    # -- 2. GATE ------------------------------------------------------------
    gate_path = artifact / "gate.py"
    trip.invoked["gate.py"] = str(gate_path)
    trip.gate = conftest.run_cli(
        [sys.executable, str(gate_path), "--slug", SLUG, "--root", str(artifact)],
        cwd=workdir)

    # -- 3. MEASURE, through the ARTIFACT's own runmeta.py -------------------
    runmeta = load_from_artifact("artifact_runmeta", artifact, "runmeta.py")
    trip.invoked["runmeta.py"] = str(runmeta.__file__)
    trip.runmeta_file = str(runmeta.__file__)

    results = artifact / "results"
    token = json.loads((results / "gate.json").read_text(encoding="utf-8"))["run_token"]
    handle = runmeta.start_run(str(results), "run-0001", token,
                               extra={"items": ITEM_COUNT})
    for index in range(ITEM_COUNT):
        runmeta.write_item(str(results), "item-%04d" % index,
                           {"index": index, "ok": index % 4 != 3,
                            "latency_ms": 10.0 + index})
    runmeta.finish_run(handle, api_spend_usd=0.0, gpu_minutes=0.0,
                       extra={"items_written": ITEM_COUNT})
    trip.items_dir = str(runmeta.items_dir(str(results)))
    trip.raw_dir = str(runmeta.raw_dir(str(results)))

    # -- 4. DERIVE ----------------------------------------------------------
    specs = [dict(SPEC_COMMON, **spec) for spec in FIGURE_SPECS]
    spec_path = artifact / "figure-specs.json"
    spec_path.write_bytes((json.dumps(specs, indent=2) + "\n").encode("ascii"))

    derive_path = artifact / "derive.py"
    trip.invoked["derive.py"] = str(derive_path)
    trip.derive = conftest.run_cli(
        [sys.executable, str(derive_path), "--root", str(artifact),
         "--specs", str(spec_path)], cwd=workdir)

    # -- 5. AUTHOR THE PROSE, THEN RENDER -----------------------------------
    # The skeleton ships key references for figures a real measurement may or
    # may not author -- including several no measurement CAN author, because
    # they are strings rather than counts. An author therefore writes the region
    # bodies down to what this run actually produced. The LIMITS region is left
    # untouched: it is the one thing step 7 must refuse.
    # -- 4b. THE VENDORING PLACES THE SNAPSHOT -- ASSERTED, NOT COPIED -------
    # RE-KEYED BY AN EARLIER PLAN, which closed an earlier plan open item 8.
    #
    # This step used to COPY `tools/canon-bullets.json` in by hand, because it
    # was not in tools/vendor.py's VENDORED_SET and CHECK-09 therefore refused
    # inside every artifact the programme ships. The copy was a workaround and
    # said so; it is now dead code, and the pin below fired the moment the real
    # repair landed -- which is exactly what that pin was written to do.
    #
    # The step survives as an ASSERTION rather than being deleted, and that is
    # strictly stronger than what it replaced: a hand-copy proves only that this
    # fixture can place a file, while this proves the GENERATOR places it, which
    # is the property a design rule actually needs. Delete the step and nothing in the
    # round trip would notice the corpus silently ceasing to ship.
    snapshot_source = REPO_ROOT / "tools" / CANON_SNAPSHOT_NAME
    placed = artifact / CANON_SNAPSHOT_NAME
    assert placed.is_file(), (
        "the generator did not place %s in the artifact, so CHECK-09 will "
        "refuse inside it. VENDORED_SET no longer carries the corpus."
        % CANON_SNAPSHOT_NAME)
    assert placed.read_bytes() == snapshot_source.read_bytes(), (
        "the vendored %s is not byte-identical to the source"
        % CANON_SNAPSHOT_NAME)
    trip.canon_snapshot = str(placed)

    for name, body in (("claim", claim_body()), ("figures", FIGURES_BODY),
                       ("env", ENV_BODY)):
        replace_region_body(artifact / "README.md", name, body)
        replace_region_body(results / "RESULTS.md", name,
                            results_claim_body() if name == "claim" else body)
    replace_region_body(results / "RESULTS.md", "limits", RESULTS_LIMITS_BODY)

    # RESULTS.md's OWN claim-under-test table sits OUTSIDE every region, so
    # replace_region_body cannot reach it and render.py never touches it. The
    # skeleton ships it with `<...>` author instructions and `{{artifact.*}}`
    # references; an author fills it by hand, which is what this does. Every
    # substitution is asserted to have landed -- a silent no-op here would leave
    # the placeholders in place and make CHECK-09's findings read as a defect in
    # the check rather than as an unfilled document.
    trip.results_claim_rows = fill_results_claim_table(results / "RESULTS.md")

    # -- 5b. DATE THE RETRACTION DECLARATION --------------------------------
    # The generator ships `results/retractions.json` with `reviewed_on` EMPTY,
    # for the reason substitutions() states about every date: one stamped in at
    # generation time would agree with everything by construction and the check
    # that reads it could never fail. So an author dates it, which is what this
    # does, and CHECK-16 then passes over an artifact that withdrew nothing.
    #
    # It is NOT held back for step 8. Step 8 exists to watch ONE authored thing
    # go from refused to accepted, and the limits paragraph is that one thing;
    # adding a second would make step 7's failure ambiguous about which authored
    # gap produced it, which is the property that whole round trip rests on.
    trip.retractions_reviewed_on = date_the_retraction_declaration(artifact)

    # THE OWNER ROUND TRIP, and what it no longer has to record.
    #
    # CHECK-09 requires the canon bullet's text VERBATIM, byte for byte, with no
    # normalization -- a paraphrase is precisely what it exists to catch.
    # CHECK-01 lints every numeral in the same documents. MEASURED over the
    # committed snapshot: ZERO of its 49 bullets have text that
    # canonkit.classify_numerals reads cleanly, because a canon bullet IS a
    # metric claim and metric claims carry numerals.
    #
    # That was a real conflict between two checks, not a property of this
    # fixture, and an earlier plan closed it the only way open to it -- an
    # OWNER-AUTHORED, COMMITTED waiver over two findings, one per scanned
    # document -- because check_01.py was outside its file set.
    #
    # AN EARLIER PLAN REPAIRED THE CHECK, so the waiver is gone rather than renewed.
    # check_01.py classifies a verbatim canon quotation against the same corpus
    # CHECK-09 resolves against, and prints the count it removed as
    # `canon-text=`. The record below is written EMPTY and still committed: an
    # owner declaring no waivers is a fact CHECK-10 counts, and deleting the file
    # would demote that check to DID-NOT-RUN.
    waivers = [scaffold_waiver(artifact)] if waive else []
    trip.waiver_ids = commit_waivers(artifact, waivers)

    render_path = artifact / "render.py"
    trip.invoked["render.py"] = str(render_path)
    trip.render_write = conftest.run_cli(
        [sys.executable, str(render_path), str(artifact), "--write"], cwd=workdir)
    trip.render_check = conftest.run_cli(
        [sys.executable, str(render_path), str(artifact)], cwd=workdir)

    # -- 6. COMMIT ----------------------------------------------------------
    git(artifact, "add", "-A", "--", ".")
    git(artifact, "commit", "-q", "-m",
        "chore: the authored documents and this run's records")
    trip.committed_results = [
        name.strip() for name in
        git(artifact, "ls-files", "results/").stdout.split("\n") if name.strip()]

    # -- 6b. GIVE CHECK-05 A REAL POPULATION OF ONE -------------------------
    # The generated slug is not one of tools/manifest.json's fourteen, so with
    # the programme's own expected set the register comparison resolves to
    # `expected 0, found 0` -- which an earlier plan correctly reports as code 2.
    #
    # The repair is to give the check something real to compare, NOT to mark the
    # slug `register_row: false`: that converts a real comparison into
    # `expected 0, found 0` and reports it as a pass, which is the 0/0 pass
    # wearing a different hat.
    #
    # So: a ONE-SLUG expected set in the work directory, with `register_row:
    # true` and `status: built` (the slug's directory exists, so the status rule's
    # missing-built arm is satisfied by fact rather than by declaration), its
    # committed literals agreeing with its own derivation, and the row GENERATED
    # by tools/build_register.py from the artifact's own figures record rather
    # than hand-written. CHECK-05 then runs over `checked == 1`.
    #
    # The register lands at the ARTIFACTS ROOT's own root -- beside the artifact
    # directory, not inside it -- which is where check_05.resolve_register looks
    # first and where the programme publishes it.
    fragments = workdir / "register-fragments"
    fragments.mkdir(parents=True, exist_ok=True)
    (fragments / ("%s.md" % SLUG)).write_text(REGISTER_FRAGMENT,
                                              encoding="utf-8", newline="\n")
    manifest_path = workdir / "manifest.json"
    manifest_path.write_text(
        json.dumps(ONE_SLUG_MANIFEST, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    trip.manifest_path = str(manifest_path)
    trip.register_path = str(workdir / "backing-artifacts.md")
    # --mirror IS NOT OPTIONAL HERE, and its absence was a real defect.
    #
    # build_register writes TWO files: the tracked register and a MIRROR beside
    # the artifacts. Without this flag the mirror used to resolve through the
    # repository anchor rather than through --artifacts-root, so this line --
    # running in a pytest temp directory -- overwrote the owner's real
    # `<home>/Research/backing-artifacts.md` on EVERY suite run, including the
    # pre-push hook's own. That file is outside every git repository and
    # versioned by nothing, so the damage was silent; three sessions measured it
    # before it was traced. an earlier plan fixed the resolution and added a guard
    # refusing a throwaway scan that publishes outside itself, and names the
    # mirror here too, so the trap is disarmed from both sides rather than one.
    trip.register = conftest.run_cli(
        [sys.executable, "-m", "tools.build_register",
         "--artifacts-root", str(workdir),
         "--fragments-dir", str(fragments),
         "--manifest", str(manifest_path),
         "--register", str(workdir / "backing-artifacts.md"),
         "--mirror", str(workdir / "backing-artifacts.md")],
        cwd=REPO_ROOT)

    if fill_limits:
        fill_limits_region(Path(trip.artifact))
    return trip


# The claim a conformant world's artifact answers for, and the row id inside it.
CONFORMANT_BULLET = "example-alpha:P1-B3"
CONFORMANT_ROW_ID = "P1-B3"


@dataclass
class ConformantWorld:
    """An artifact that passes EVERY check, plus the three inputs CHECK-20 needs.

    `manifest_path`, `live_store` and `records_dir` are handed to
    `conformance.py` by FLAG. None of them may live inside the artifact: a
    checker the thing being checked can point at its own evidence is not a
    checker.
    """

    artifact: str = ""
    artifacts_root: str = ""
    manifest_path: str = ""
    live_store: str = ""
    records_dir: str = ""
    slug: str = ""
    trip: object = None

    def flags(self):
        """The argv tail that points conformance at this world."""
        return ["--manifest", self.manifest_path,
                "--live-store", self.live_store,
                "--records-dir", self.records_dir]


def _world_entry(rows):
    return {"slug": "synthetic", "kind": "experience",
            "display_name": "Synthetic engagement", "company": "A Company",
            "role": "Example Role One", "dates": "Month YYYY - Month YYYY",
            "detail": {"done": "synthetic", "how": "synthetic",
                       "metrics": list(rows)}}


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                    encoding="ascii", newline="\n")


def build_conformant_world(workdir, waive=False):
    """A whole world in which `conformance.py` legitimately exits 0.

    MEASURED, and the reason this exists: an artifact alone is not enough. The
    four suite tests that assert a clean run were failing because
    `conftest.tmp_artifact` builds a MINIMAL artifact -- README, figures,
    waivers -- which SEVEN checks correctly refuse or fail. None of those
    refusals is a defect; each is a check saying it was handed nothing to look
    at. The repair is to supply what the checks require, which is what the
    documented steps do.

    CHECK-20 needs three things no artifact can carry, so they are built beside
    it and passed by flag:

      the expected set   a row marking this slug `built` with a real obligation
      the live entries   the claim's row, CLEAN -- its marker already gone
      the records        a fragment saying a measurement moved that figure

    The manifest is a COPY of the round trip's one-slug set with an obligation
    added, so CHECK-05's register comparison -- generated from the same set --
    is untouched and still runs over a population of one.
    """
    workdir = Path(workdir)
    trip = build_conformant_artifact(workdir, waive=waive)

    manifest = json.loads(json.dumps(ONE_SLUG_MANIFEST))
    manifest["slugs"][0]["bullets"] = [CONFORMANT_BULLET]
    manifest["slugs"][0].pop("no_row_reason", None)
    manifest_path = workdir / "manifest-with-obligation.json"
    _write_json(manifest_path, manifest)

    # BOTH live entries are written, always. One of two would make a missing
    # entry indistinguishable from an entry with nothing to correct.
    store = workdir / "live"
    _write_json(store / "collections" / "collection-one" / "example-alpha" / "raw.json",
                _world_entry(["%s: a measured figure" % CONFORMANT_ROW_ID]))
    _write_json(store / "collections" / "collection-two" / "example-beta" / "raw.json",
                _world_entry(["P9-B9: an unrelated measured figure"]))

    records = workdir / "records"
    records.mkdir(parents=True, exist_ok=True)
    (records / ("2026-09-17-101738--%s--corrections.md" % SLUG)).write_text(
        "---\nid: conformant-world\nplan: an earlier plan\ndated_at: 2026-09-17\n---\n\n"
        "bullet: %s\nverdict: corrected\n"
        "before: the figure as it was designed\n"
        "after: the figure as it was measured\n" % CONFORMANT_BULLET,
        encoding="ascii", newline="\n")

    return ConformantWorld(
        artifact=str(trip.artifact), artifacts_root=str(workdir),
        manifest_path=str(manifest_path), live_store=str(store),
        records_dir=str(records), slug=SLUG, trip=trip)


def date_the_retraction_declaration(artifact, reviewed_on="2026-09-21"):
    """Write `reviewed_on` into the generated retraction declaration, IN PLACE.

    The substitution is VERIFIED to have landed, for the reason
    fill_results_claim_table states: a write that silently matched nothing would
    leave the skeleton's empty value in the shipped document while this function
    reported success, and CHECK-16's resulting finding would then read as a
    defect in the check rather than as an unfinished file.
    """
    path = Path(artifact) / "results" / "retractions.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload.get("reviewed_on") == "", (
        "the generated declaration's `reviewed_on` is %r rather than empty. If "
        "the generator has started stamping a date, this step is a no-op and "
        "the check that reads it can no longer fail."
        % (payload.get("reviewed_on"),))
    assert payload.get("retracted") == [], payload.get("retracted")
    payload["reviewed_on"] = reviewed_on
    path.write_bytes((json.dumps(payload, indent=2, sort_keys=True) + "\n")
                     .encode("utf-8"))
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["reviewed_on"] == reviewed_on, written
    return reviewed_on


def fill_limits_region(artifact):
    """Step 8: write the limits paragraph and commit it.

    The one authored thing the generator cannot supply and the one thing
    CHECK-03 refuses a template copy of. Shared so the round trip and every
    conformant-artifact caller fill it the same way.
    """
    replace_region_body(artifact / "README.md", "limits", FILLED_IN_LIMITS)
    git(artifact, "add", "--", "README.md")
    git(artifact, "commit", "-q", "-m", "docs: write the limits paragraph")
    return region_body(
        (artifact / "README.md").read_bytes().decode("utf-8"), "limits")


def build_round_trip(workdir):
    """Walk every documented step once, recording what each one returned."""
    workdir = Path(workdir)
    reports = workdir / "reports"
    trip = build_conformant_artifact(workdir, fill_limits=False)
    artifact = Path(trip.artifact)
    results = artifact / "results"
    manifest_path = Path(trip.manifest_path)
    # Recovered from the record the builder already keeps rather than re-derived:
    # `trip.invoked` is the map of every executable step to the path it actually
    # resolved to, and steps 10 and 11 re-run the renderer from it.
    render_path = Path(trip.invoked["render.py"])

    # -- 7. CONFORMANCE FAILS ----------------------------------------------
    conformance_path = artifact / "conformance.py"
    trip.invoked["conformance.py"] = str(conformance_path)
    trip.tracked_before = tracked_hashes(artifact)
    trip.limits_before = region_body(
        (artifact / "README.md").read_bytes().decode("utf-8"), "limits")
    trip.conformance_fail = conftest.run_cli(
        [sys.executable, str(conformance_path), str(artifact),
         "--manifest", str(manifest_path),
         "--report", str(reports / "fail.json")], cwd=workdir)

    # -- 8. FILL IN THE ONE THING THAT WAS MISSING --------------------------
    # Through the SHARED helper, so a conformant artifact built for any other
    # test fills this the same way. Two copies of the one authored step would
    # drift, and the drift would show up as a check failing somewhere that has
    # nothing to do with the check.
    trip.limits_after = fill_limits_region(artifact)

    # -- 9. CONFORMANCE PASSES ---------------------------------------------
    trip.tracked_after = tracked_hashes(artifact)
    trip.conformance_pass = conftest.run_cli(
        [sys.executable, str(conformance_path), str(artifact),
         "--manifest", str(manifest_path),
         "--report", str(reports / "pass.json")], cwd=workdir)

    # -- 10. VERIFY ---------------------------------------------------------
    verify_path = artifact / "verify.py"
    trip.invoked["verify.py"] = str(verify_path)
    trip.verify = conftest.run_cli(
        [sys.executable, str(verify_path), "--root", str(artifact),
         "--tier", "derive"], cwd=workdir)

    # -- 11. HAND EDIT, THEN RESTORE FROM A BYTE SNAPSHOT -------------------
    # NEVER from git. A restore from HEAD destroys uncommitted work and can make
    # the thing under test the restored implementation rather than the edit.
    readme = artifact / "README.md"
    snapshot = workdir / "README.snapshot"
    snapshot.write_bytes(readme.read_bytes())
    trip.tracked_pre_edit = tracked_hashes(artifact)

    raw = readme.read_bytes().decode("utf-8")
    hole = re.search(
        r"(<!--artifact:key:[A-Za-z0-9_.]+-->)([^<]+)(<!--/artifact:key-->)", raw)
    assert hole is not None, "no rendered hole to edit; the render never happened"
    trip.edited_hole = hole.group(0)
    edited = raw[:hole.start(2)] + "9" + hole.group(2)[1:] + raw[hole.end(2):]
    readme.write_bytes(edited.encode("utf-8"))

    trip.render_drift = conftest.run_cli(
        [sys.executable, str(render_path), str(artifact)], cwd=workdir)

    readme.write_bytes(snapshot.read_bytes())
    trip.tracked_post_restore = tracked_hashes(artifact)
    trip.render_restored = conftest.run_cli(
        [sys.executable, str(render_path), str(artifact)], cwd=workdir)

    return trip


@pytest.fixture(scope="module")
def trip(tmp_path_factory):
    return build_round_trip(tmp_path_factory.mktemp("roundtrip"))


def report_of(result):
    assert result.report is not None, (
        "the run wrote no structured report:\n%s\n%s"
        % (result.stdout, result.stderr))
    return result.report


def row(report, check_id):
    for entry in report.get("checks") or []:
        if entry.get("check_id") == check_id:
            return entry
    return None


# ---------------------------------------------------------------------------
# Step 1 -- generation
# ---------------------------------------------------------------------------


def test_the_generator_produces_a_git_work_tree_whose_root_commit_is_one_path(trip):
    assert trip.generate.exit_code == 0, trip.generate.stdout + trip.generate.stderr
    assert (trip.artifact / ".git").exists(), trip.artifact
    assert trip.root_commit_paths == [".gitattributes"], (
        "the root commit touched %r. Nothing may be hashed before the "
        "end-of-line rule is in force." % (trip.root_commit_paths,))


def test_all_nine_required_files_are_tracked_inside_the_artifact(trip):
    """TOOL_04_REQUIRED is imported, never re-typed: one list, one definition."""
    assert len(TOOL_04_REQUIRED) == 9, TOOL_04_REQUIRED
    tracked = set(trip.tracked_after)
    missing = [name for name in TOOL_04_REQUIRED if name not in tracked]
    assert not missing, "missing from the artifact's index: %r" % (missing,)


# ---------------------------------------------------------------------------
# Steps 2 to 5 -- the run chain
# ---------------------------------------------------------------------------


def test_the_gate_mints_a_token_with_a_date_beside_it(trip):
    assert trip.gate.exit_code == core.EXIT_PASS, trip.gate.stdout + trip.gate.stderr
    record = json.loads(
        (trip.artifact / "results" / "gate.json").read_text(encoding="utf-8"))
    assert record["run_token"], record
    assert len(record["run_token"]) == 64, record["run_token"]
    assert record["dated_at"], record
    assert record["passed"] is True, record


def test_every_per_item_record_carries_the_gate_token(trip):
    items = sorted(Path(trip.items_dir).glob("*.json"))
    assert len(items) == ITEM_COUNT, (
        "wrote %d per-item record(s), expected %d" % (len(items), ITEM_COUNT))
    run_records = sorted(Path(trip.raw_dir).glob("run-*.json"))
    assert run_records, "no run record was written"
    record = json.loads(run_records[0].read_text(encoding="utf-8"))
    for field_name in ("api_spend_usd", "gpu_minutes", "wall_seconds"):
        assert field_name in record, (
            "the run record carries no %r; the cost triple is not optional"
            % field_name)
    gate = json.loads(
        (trip.artifact / "results" / "gate.json").read_text(encoding="utf-8"))
    assert record["gate_token"] == gate["run_token"], (record, gate)


def test_every_derived_figure_carries_a_population(trip):
    assert trip.derive.exit_code == 0, trip.derive.stdout + trip.derive.stderr
    figures = json.loads(
        (trip.artifact / "results" / "figures.json").read_text(encoding="utf-8")
    )["figures"]
    assert figures, "derive authored zero figures"
    for key, figure in sorted(figures.items()):
        assert isinstance(figure.get("population"), int), (key, figure)
        assert figure["population"] >= 1, (key, figure)


def test_render_writes_then_reports_no_drift(trip):
    assert trip.render_write.exit_code == 0, (
        trip.render_write.stdout + trip.render_write.stderr)
    assert trip.render_check.exit_code == 0, (
        "the renderer reported drift immediately after writing:\n%s"
        % trip.render_check.stdout)
    assert "references 30 of 30 resolved" in trip.render_check.stdout or \
        re.search(r"references (\d+) of \1 resolved", trip.render_check.stdout), \
        trip.render_check.stdout


# ---------------------------------------------------------------------------
# Step 6 -- the commit, asserted rather than assumed
# ---------------------------------------------------------------------------


def test_a_machine_written_results_file_is_tracked_and_committed(trip):
    """CHECK-07 verifies this with `git ls-files`, not with "the file exists"."""
    assert trip.committed_results, (
        "git ls-files results/ returned nothing inside the artifact, so a "
        "clean checkout would carry no evidence at all")
    machine_written = [name for name in trip.committed_results
                       if name.endswith(".json")]
    assert machine_written, trip.committed_results
    for name in machine_written:
        shown = git(trip.artifact, "show", "HEAD:%s" % name)
        assert shown.stdout.strip(), (
            "%s is listed by ls-files but HEAD carries no content for it -- "
            "staged is not committed" % name)


# ---------------------------------------------------------------------------
# Steps 7 to 9 -- FAIL, fill in, PASS
# ---------------------------------------------------------------------------


def test_step_seven_fails_and_names_the_unedited_placeholder(trip):
    """A bare non-zero exit could come from any check and would prove nothing."""
    assert trip.conformance_fail.exit_code != 0, (
        "an artifact whose limits paragraph was never edited PASSED:\n%s"
        % trip.conformance_fail.stdout)
    report = report_of(trip.conformance_fail)
    three = row(report, "CHECK-03")
    assert three is not None, report["checks"]
    assert three["code"] == core.EXIT_FINDING, three
    assert any("unedited" in finding for finding in three["finding_ids"]), (
        "CHECK-03 failed, but not on the unedited-placeholder condition: %r"
        % (three["finding_ids"],))


def test_step_nine_passes_over_a_stated_population(trip):
    """All four, not any one of them.

    The exit code and the `checked > 0` sweep say the run was clean. The literal
    and the identity say how big the population of checks was -- and the identity
    is the load-bearing one, because it SURVIVES THE WAVE: it reads
    9 + 2 == 11 unchanged while only the literal moves.
    """
    assert trip.conformance_pass.exit_code == core.EXIT_PASS, (
        "the filled-in artifact did not pass:\n%s\n%s"
        % (trip.conformance_pass.stdout, trip.conformance_pass.stderr))
    report = report_of(trip.conformance_pass)

    assert all(entry["checked"] > 0 for entry in report["checks"]), (
        "exit 0 with a did-not-run somewhere is the failure a design rule exists to make "
        "visible: %r" % ([(e["check_id"], e["checked"]) for e in report["checks"]],))

    assert len(report["checks"]) == EXPECTED_CHECKS, (
        "the report carries %d check row(s); the contract has %d. If this reads "
        "9, the finding is that conformance.py is not emitting its two "
        "runner-property rows -- NEVER that this literal should come down to "
        "match." % (len(report["checks"]), EXPECTED_CHECKS))

    # THE SECOND PLACE A ROW CAN GO, named so the literal above is never dragged
    # down to meet it. Since an earlier plan a check can be declared NOT-APPLICABLE
    # for this artifact's slug and land in `not_applicable_checks[]` instead --
    # which is a legitimate state, and was measured shrinking this very count
    # from 11 to 10 the first time the declaration existed. The union is what
    # survives that: if a row moves, THIS assertion still closes and names where
    # it went, and the one above fails with a reason rather than a number.
    inapplicable = report.get("not_applicable_checks") or []
    assert len(report["checks"]) + len(inapplicable) == EXPECTED_CHECKS, (
        "%d row(s) ran and %d were declared not applicable, which is %d against "
        "a contract of %d: %r"
        % (len(report["checks"]), len(inapplicable),
           len(report["checks"]) + len(inapplicable), EXPECTED_CHECKS,
           [row["check_id"] for row in inapplicable]))

    # DISCOVERED IN THE ARTIFACT, never in the repository. The report above came
    # from the artifact's OWN vendored conformance.py over its OWN checks/
    # directory, so the identity has to be evaluated against that module set. The
    # two agreed until a check was declared not-vendorable, at which point
    # comparing a vendored report against the repository's count would have been
    # an identity across two different populations -- true by coincidence for as
    # long as the coincidence lasted.
    vendored_checks_dir = Path(trip.artifact) / "checks"
    discovered = checks.discover(vendored_checks_dir, verbose=False)
    assert len(report["checks"]) == discovered.found + len(RUNNER_CHECK_IDS), (
        "%d row(s) against %d module(s) plus %d runner property(ies)"
        % (len(report["checks"]), discovered.found, len(RUNNER_CHECK_IDS)))

    # And the artifact really does carry fewer modules than the repository, for
    # a stated reason rather than because the vendoring dropped one.
    from tools import vendor

    repo_side = checks.discover(CHECKS_DIR, verbose=False)
    excluded = vendor.excluded_check_modules()
    assert repo_side.found - discovered.found == len(excluded), (
        "the repository holds %d module(s) and the artifact %d; %d exclusion(s) "
        "are declared: %r"
        % (repo_side.found, discovered.found, len(excluded),
           [relative for relative, _reason in excluded]))
    assert excluded, (
        "no exclusion is declared, so this assertion compares a number with "
        "itself")


def test_check_05_ran_over_a_real_population_of_one(trip):
    """SUPPLIED, never narrowed: `checked == 1`, and never `expected 0, found 0`.

    Marking the slug `register_row: false` would also have made CHECK-05 stop
    complaining -- by turning a real comparison into a comparison over nothing
    and reporting it as a pass. The population is asserted here precisely so
    that repair could not be mistaken for this one.
    """
    assert trip.register.exit_code == 0, (
        "the register was never generated:\n%s\n%s"
        % (trip.register.stdout, trip.register.stderr))
    assert Path(trip.register_path).is_file(), trip.register_path
    assert "## %s" % SLUG in Path(trip.register_path).read_text(
        encoding="utf-8"), "the register carries no row for %s" % SLUG

    entry = row(report_of(trip.conformance_pass), "CHECK-05")
    assert entry is not None, report_of(trip.conformance_pass)["checks"]
    assert entry["code"] == core.EXIT_PASS, entry
    assert entry["checked"] == 1, (
        "CHECK-05 examined %d slug(s). One is the whole point: `expected 0, "
        "found 0` is the 0/0 pass wearing a different hat." % entry["checked"])
    assert entry["found"] == 0, entry
    assert "expected 1, found 1" in entry["note"], entry["note"]


def test_check_07_passes_because_the_results_tree_is_TRACKED(trip):
    """`git ls-files results/`, not `os.path.exists`. Both halves asserted."""
    assert trip.committed_results, (
        "git ls-files results/ returned nothing inside the artifact, so CHECK-07 "
        "would have had no tracked machine-written file to find")
    entry = row(report_of(trip.conformance_pass), "CHECK-07")
    assert entry["code"] == core.EXIT_PASS, entry
    assert entry["checked"] > 0, entry
    assert "work-tree=yes" in entry["note"], entry["note"]
    assert "per-item-records on-disk=%d tracked=%d" % (ITEM_COUNT + 1,
                                                       ITEM_COUNT + 1) in \
        entry["note"], entry["note"]


def test_check_09_passes_against_a_compound_keyed_bullet_read_from_the_snapshot(trip):
    """The bullet is REAL, its key is COMPOUND, and its text was never re-typed."""
    entry = row(report_of(trip.conformance_pass), "CHECK-09")
    assert entry["code"] == core.EXIT_PASS, entry
    assert entry["checked"] > 0, entry

    assert ":" in CLAIM_BULLET_KEY, (
        "a bare bullet id is a CHECK-09 finding in its own right: two canons can "
        "carry the same bare id")
    snapshot = json.loads(
        (REPO_ROOT / "tools" / CANON_SNAPSHOT_NAME).read_text(encoding="utf-8"))
    assert CLAIM_BULLET_KEY in snapshot["bullets"], CLAIM_BULLET_KEY

    verbatim = snapshot["bullets"][CLAIM_BULLET_KEY]["text"]
    for document in ("README.md", "results/RESULTS.md"):
        body = (trip.artifact / document).read_bytes().decode("utf-8")
        assert verbatim in body, (
            "%s does not carry the bullet text byte for byte" % document)


def test_the_vendoring_places_the_canon_snapshot_in_the_artifact(trip):
    """a design rule: a handed-over directory self-checks with NO access to this repository.

    RE-KEYED BY AN EARLIER PLAN, and the rename is the point. This test was
    `..._the_vendoring_does_not_place`, and its second assertion pinned the
    ABSENCE of `tools/canon-bullets.json` from VENDORED_SET so that step 4b's
    hand-copy could not quietly outlive the defect it worked around. That pin
    did its job: it went red in the commit that vendored the corpus, naming the
    dead code and the stale comment.

    The repair is NOT to delete it. A retired workaround leaves behind a test
    asserting the OLD state EXISTS, and deleting such a test removes the only
    thing watching the surface. So both halves are inverted: the artifact still
    carries the snapshot, and the corpus IS declared -- which is now what makes
    the first half true.
    """
    assert Path(trip.canon_snapshot).is_file(), trip.canon_snapshot
    assert (REPO_ROOT / "tools" / CANON_SNAPSHOT_NAME).read_bytes() == \
        Path(trip.canon_snapshot).read_bytes(), (
        "the vendored snapshot is not byte-identical")

    from tools import vendor
    assert "tools/" + CANON_SNAPSHOT_NAME in vendor.VENDORED_SET, (
        "%s left VENDORED_SET, so CHECK-09 is inert inside every artifact "
        "again and step 4b's assertion is the only thing that would notice."
        % CANON_SNAPSHOT_NAME)


def test_the_round_trip_needs_no_waiver_because_the_canon_text_is_classified(trip):
    """an earlier plan item 13, closed by an earlier plan. RE-KEYED, and the rename is the point.

    This test was `test_the_waiver_round_trip_is_honoured_and_its_count_prints`
    and it asserted `waived > 0` over two owner-authored waivers for the
    numerals inside the canon bullet this artifact quotes verbatim. check_01.py
    now CLASSIFIES those numerals, so there is nothing left to waive and that
    assertion would be asserting over a waiver that no longer applies.

    The dangerous repair would have been to delete the test: `waived == 0` is
    also what a check that never ran reports, so the count alone says nothing.
    So the assertion is INVERTED and PAIRED -- zero waived AND a non-zero
    canon-text count in the checker's own line -- which is a measurement rather
    than a silence. a design rule's honoured direction did not lose its coverage here; it
    lives in test_waivers.py, over a conformant world that asks for a waiver on
    purpose.
    """
    entry = row(report_of(trip.conformance_pass), "CHECK-01")
    assert entry["code"] == core.EXIT_PASS, entry
    assert trip.waiver_ids == [], (
        "the round trip authored waiver(s) %r; item 13's repair means it needs "
        "none" % (trip.waiver_ids,))
    assert entry["waived"] == 0, (
        "CHECK-01 honoured %d waiver(s) over an artifact that authored none: %r"
        % (entry["waived"], entry))

    # The discriminating half. Two scanned documents each quote the bullet, so
    # the mask must report (numerals in the bullet) x (documents) findings
    # removed. A `waived=0` beside `canon-text=0` would be a check that looked
    # at nothing.
    #
    # RE-KEYED by an earlier plan from the literal 2. The 2 was (one numeral) x (two
    # documents), and the one was a property of ONE bullet of ONE corpus: the
    # authored example corpus the published toolkit ships puts four numerals in
    # the same bullet, so the literal read `canon-text=8` there and the test
    # failed over a corpus it was never told about. The count is now DERIVED
    # from the bullet the round trip actually quoted, through the same frozen
    # core the checker uses, and the per-document factor is asserted beside it
    # rather than folded into the number.
    quoted = canon_bullet()["text"]
    report = core.classify_numerals(quoted, {})
    per_document = sum(1 for hit in report.hits
                       if hit.kind == core.KIND_UNCLASSIFIED)
    assert per_document >= 1, (
        "the quoted bullet carries no numeral CHECK-01 would otherwise report, "
        "so masking it removes nothing and this assertion cannot discriminate: "
        "%r" % quoted[:120])
    assert "claim-cells=2 of 2" in entry["note"], entry["note"]
    expected = "canon-text=%d" % (per_document * 2)
    assert expected in entry["note"], (
        "CHECK-01 reported a different masked count than the %d numeral(s) in "
        "the quoted bullet across 2 document(s) predict (%s): %r"
        % (per_document, expected, entry["note"]))

    committed = git(trip.artifact, "show", "HEAD:waivers.json").stdout
    payload = json.loads(committed)
    assert payload["waivers"] == [], (
        "a waiver is still committed in the artifact: %r" % payload["waivers"])

    # The record is EMPTY and PRESENT, which is a population rather than a gap.
    ten = row(report_of(trip.conformance_pass), "CHECK-10")
    assert ten["code"] == core.EXIT_PASS, ten
    assert "uncommitted=0" in ten["note"], ten["note"]
    assert ten["checked"] >= 1, (
        "deleting the waivers record would have demoted CHECK-10 to a "
        "DID-NOT-RUN, trading one silence for another: %r" % ten)


def test_the_results_claim_table_was_really_filled_in(trip):
    """Six rows, each verified to have replaced a placeholder, none left behind."""
    assert len(trip.results_claim_rows) == 6, trip.results_claim_rows
    body = (trip.artifact / "results" / "RESULTS.md").read_bytes().decode("utf-8")
    for line in trip.results_claim_rows:
        assert line in body, line
    for placeholder in ("<paste the bullet", "<one of:", "{{artifact.canon}}",
                        "{{artifact.bullet_ids}}"):
        assert placeholder not in body, (
            "the skeleton's placeholder %r survived into the shipped document"
            % placeholder)


def test_both_runner_properties_are_rows_in_the_passing_report(trip):
    """The two checkers a check-module glob cannot see, asserted present BY ID.

    Never inferred from the runner having run: a runner property that never
    appears in checks[] is a checker with no row, and an earlier plan's audit could
    not see it.
    """
    report = report_of(trip.conformance_pass)
    ids = {entry["check_id"] for entry in report["checks"]}
    assert set(RUNNER_CHECK_IDS) <= ids, sorted(ids)
    for check_id in RUNNER_CHECK_IDS:
        entry = row(report, check_id)
        assert entry["checked"] > 0, (check_id, entry)
        assert entry["code"] == core.EXIT_PASS, entry


def test_the_only_file_changed_between_the_two_runs_is_the_readme(trip):
    """Compared by hashing every TRACKED file before and after."""
    assert trip.tracked_before, "hashed 0 tracked files, so this compares nothing"
    changed = sorted(
        name for name in set(trip.tracked_before) | set(trip.tracked_after)
        if trip.tracked_before.get(name) != trip.tracked_after.get(name))
    assert changed == ["README.md"], (
        "the diff between the failing and passing states is %r, not README.md "
        "alone" % (changed,))


def test_the_one_change_is_confined_to_the_limits_region(trip):
    """Not merely the same file -- the same REGION of it."""
    assert trip.limits_before != trip.limits_after
    assert trip.limits_after.strip() == FILLED_IN_LIMITS.strip()
    before = (trip.artifact / "README.md").read_bytes().decode("utf-8")
    for name in ("date", "claim", "figures", "env", "layout"):
        assert region_body(before, name) is not None, (
            "the %r region vanished from the README" % name)


# ---------------------------------------------------------------------------
# Step 10 -- re-derivation
# ---------------------------------------------------------------------------


def test_verify_re_derives_every_figure(trip):
    assert trip.verify.exit_code == 0, trip.verify.stdout + trip.verify.stderr
    match = re.search(r"re-derived (\d+) of (\d+)", trip.verify.stdout)
    assert match is not None, trip.verify.stdout
    assert match.group(1) == match.group(2), (
        "re-derived %s of %s figure(s)" % (match.group(1), match.group(2)))
    assert int(match.group(2)) == len(FIGURE_SPECS), (
        "re-derived over %s figure(s); %d were authored"
        % (match.group(2), len(FIGURE_SPECS)))


# ---------------------------------------------------------------------------
# Step 11 -- a hand edit is a detected error
# ---------------------------------------------------------------------------


def test_a_hand_edit_inside_a_rendered_region_is_refused_with_a_diff(trip):
    assert trip.edited_hole.startswith("<!--artifact:key:"), trip.edited_hole
    assert trip.render_drift.exit_code != 0, (
        "a hand edit inside a rendered region was not detected:\n%s"
        % trip.render_drift.stdout)
    assert "DIFFERS" in trip.render_drift.stdout, trip.render_drift.stdout
    assert "---" in trip.render_drift.stdout and "+++" in trip.render_drift.stdout, \
        trip.render_drift.stdout


def test_the_snapshot_restore_returns_every_hash_to_its_pre_edit_value(trip):
    assert trip.tracked_pre_edit, "hashed 0 tracked files before the edit"
    assert trip.tracked_post_restore == trip.tracked_pre_edit, (
        "the restore did not return the tree to its pre-edit bytes: %r"
        % (sorted(name for name in trip.tracked_pre_edit
                  if trip.tracked_pre_edit[name]
                  != trip.tracked_post_restore.get(name)),))
    assert trip.render_restored.exit_code == 0, trip.render_restored.stdout


# ---------------------------------------------------------------------------
# a design rule -- every step ran the ARTIFACT's own copy
# ---------------------------------------------------------------------------


def test_every_executable_step_resolved_under_the_generated_artifact(trip):
    """Otherwise the vendoring claim is never tested at all."""
    expected = {"gate.py", "runmeta.py", "derive.py", "render.py",
                "verify.py", "conformance.py"}
    assert set(trip.invoked) == expected, (
        "recorded %r; the round trip names %r" % (sorted(trip.invoked),
                                                  sorted(expected)))
    root = os.path.abspath(str(trip.artifact))
    for name, used in sorted(trip.invoked.items()):
        resolved = os.path.abspath(used)
        assert resolved == root or resolved.startswith(root + os.sep), (
            "%s ran from %s, which is outside the generated artifact at %s"
            % (name, resolved, root))
        assert os.path.isfile(resolved), resolved


def test_this_module_never_reaches_for_the_kit_directory():
    """A round trip that exercised the kit while claiming to exercise the
    artifact would leave a design rule's whole point unexercised."""
    source = Path(__file__).read_text(encoding="utf-8")
    needle = "temp" + "lates/"
    assert needle not in source, (
        "this module names the kit directory; every step must run the "
        "artifact's own copy")
    assert "checkout " + "--" not in source, (
        "this module restores from git. A restore from HEAD destroys "
        "uncommitted work and can make the thing under test the restored "
        "implementation rather than the edit.")
