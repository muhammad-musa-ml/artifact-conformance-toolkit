"""The exit-code contract: a zero population is a FAIL that survives aggregation.

a design rule (HARD) in three sentences. A check that examined zero inputs returns 2 at
the check level. The runner aggregates that 2 UP to 1, so the artifact-level
verdict is unambiguously a finding rather than a quiet pass. And because one
integer destroys the distinction by construction, the distinction lives in two
places the aggregate cannot erase -- the summary counts line, and the per-check
`code` in the structured report.

THE TESTS THAT CARRY THE RED, in the order they appear below:

    test_zero_population_aggregates_to_one
    test_zero_artifacts_is_did_not_run
    test_check_11_detects_a_pass_over_zero_inputs
    test_check_11_detects_a_line_carrying_no_population
    test_check_11_detects_a_verdict_that_contradicts_its_code

Each of them fails, in the RED commit, on an ASSERTION ABOUT A VERDICT produced
by a runner that was registered and runnable over inputs that really exist.
`all([])` is True, which is how a filter that removed everything reports every
input passing; the five assertions above are what make that impossible here.

ADDED BY AN EARLIER PLAN, at the end of this module:

    test_exit_zero_requires_a_non_zero_checked_on_every_check
    test_a_check_that_does_not_apply_is_not_a_check_that_passed_over_zero
    test_an_artifact_that_owes_nothing_reaches_exit_zero

The first is the one every later `EXIT=0` acceptance criterion earlier rests
on, and it has been observed FAILING: mutating the design rule lift in
`canonkit.aggregate()` so a check-level 2 no longer rises to 1 turns its fixture
into an exit-0 run, which is precisely the reading the pin exists to forbid. A
pin nobody has seen fail is a pin nobody knows is wired up.
"""

import json
import sys
from pathlib import Path

from tools.tests import conftest
from tools.tests.test_skeleton_roundtrip import build_conformant_world
from tools.tests.test_conformance import (
    CONFORMANCE,
    artifact,
    conformance,
    core,
    discovered,
    entry,
    run_conformance,
    run_scan,
    synthetic_manifest,
)

REPO_ROOT = conftest.REPO_ROOT

# The recorded reason the exempting fixture's manifest row carries. Held as a
# constant because three assertions read it back out of the runner's output, and
# the property under test is that the MANIFEST's own text arrives there -- which
# two independently typed copies of a sentence cannot show.
OWES_NOTHING_REASON = (
    "Cited by no bullet in either canon. Verified with a bullet-scoped probe, "
    "and recorded here so the absence is stated rather than inferred.")


def _record(check_id, verdict, code, checked, listed=None, line=None):
    """One printed population line, as the runner retained it for CHECK-11."""
    listed = checked if listed is None else listed
    if line is None:
        line = ("%-16s %-11s found=0 checked=%d of %d not-examined=0 floor=1 "
                "waived=0" % (check_id, verdict, checked, listed))
    return conformance.PopulationRecord(
        check_id=check_id, verdict=verdict, code=code, found=0, checked=checked,
        listed=listed, not_examined=0, floor=1, waived=0, note="", line=line,
        source="module:check_stub.py")


# ---------------------------------------------------------------------------
# The zero-population verdict
# ---------------------------------------------------------------------------


def test_zero_population_aggregates_to_one(tmp_path):
    """A check over zero inputs is code 2, the artifact exit is 1, and the
    did-not-run count is STILL a separate non-zero number afterwards.

    All three, because the first two alone are satisfied by an implementation
    that collapses everything to a finding and forgets which checks could not
    look -- the distinction a design rule exists to preserve.
    """
    root = artifact(tmp_path, slug="zero-population")
    (root / "results" / "figures.json").unlink()

    result = run_conformance(root, report=tmp_path / "report.json")
    report = result.report
    assert report is not None, result.stdout + result.stderr

    row = entry(report, "CHECK-01")
    assert row is not None, report["checks"]
    assert row["checked"] == 0, row
    assert row["code"] == core.EXIT_DID_NOT_RUN, (
        "a check that examined zero inputs reported code %d. Its printed line "
        "was:\n%s" % (row["code"], result.stdout))
    assert result.exit_code == core.EXIT_FINDING, (
        "the artifact-level exit was %d; a check-level 2 must aggregate UP to 1 "
        "so the verdict is unambiguously a finding.\n%s"
        % (result.exit_code, result.stdout))
    assert report["summary"]["did_not_run"] >= 1, (
        "the did-not-run count did not survive the aggregate: %r"
        % report["summary"])
    assert core.VERDICT_DID_NOT_RUN in result.stdout, result.stdout
    assert "did-not-run" in result.stdout, result.stdout


def test_zero_artifacts_is_did_not_run(tmp_path):
    """A scan that enumerated nothing is not a scan that found everything clean."""
    empty = tmp_path / "empty-scan-root"
    empty.mkdir()
    manifest = synthetic_manifest(tmp_path / "manifest.json", [])

    result = run_scan(empty, manifest=manifest, report=tmp_path / "report.json")
    assert result.exit_code == core.EXIT_DID_NOT_RUN, (
        "a scan over zero artifacts exited %d.\n%s"
        % (result.exit_code, result.stdout))
    assert result.report["scan"]["checked"] == 0, result.report["scan"]
    assert core.VERDICT_DID_NOT_RUN in result.stdout, result.stdout


def test_the_did_not_run_count_is_separate_from_the_finding_count(tmp_path):
    """Two checks, two different reasons, two different numbers."""
    root = artifact(tmp_path, population=None, slug="mixed")
    (root / "waivers.json").unlink()      # CHECK-10 then has nothing to resolve

    result = run_conformance(root, report=tmp_path / "report.json")
    summary = result.report["summary"]
    assert summary["finding"] >= 1, summary
    assert summary["did_not_run"] >= 1, summary
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert core.summary_line({
        "pass": summary["pass"], "finding": summary["finding"],
        "did_not_run": summary["did_not_run"],
        "guard_fail": summary["guard_fail"],
        "waived": summary["waived"]}) in result.stdout, result.stdout


def test_a_clean_artifact_exits_zero_over_a_real_population(tmp_path):
    """Without this, every assertion above is equally consistent with a runner
    that fails everything.

    THE ARTIFACT IS A CONFORMANT ONE, and it has to be. This test ran for a long
    time against `conftest.tmp_artifact`, which builds a MINIMAL artifact --
    README, figures, waivers -- and SEVEN checks correctly refused or failed it:
    CHECK-02 and 04 for want of a machine-emitted `started_at`, 06 for a run
    record, 07 for a git work tree, 09 for a claim table, 05 and 20 because
    `demo-artifact` is in no expected set at all. Not one of those is a defect.
    Each is a check reporting that it was handed nothing to look at, which is
    the property a design rule exists to preserve.

    So the repair is to SUPPLY WHAT THE CHECKS REQUIRE rather than to narrow the
    assertion -- the same move this repository already made for CHECK-05, 07 and
    09 in the skeleton round trip. `build_conformant_world` walks the documented
    steps and hands over the three inputs CHECK-20 reads from outside the
    artifact.

    The `checked > 0` loop is the load-bearing half: exit 0 alone is satisfiable
    by a tree of 0/0 passes, and that is the one reading this test must never
    give.
    """
    world = build_conformant_world(tmp_path)
    result = run_conformance(world.artifact, *world.flags(),
                             report=tmp_path / "report.json")
    assert result.exit_code == core.EXIT_PASS, result.stdout + result.stderr
    rows = result.report["checks"]
    assert rows, result.report
    for row in rows:
        assert row["checked"] > 0, (
            "%s passed over a population of %d" % (row["check_id"],
                                                   row["checked"]))
        assert row["code"] == core.EXIT_PASS, row
    assert len(rows) == discovered().found + len(conformance.RUNNER_CHECK_IDS)


def test_the_minimal_artifact_is_still_refused_by_the_checks_it_starves(tmp_path):
    """The other direction, so the test above cannot be read as "any artifact
    passes now".

    `conftest.tmp_artifact` is deliberately minimal and MOST TESTS DEPEND ON
    THAT -- it is how a check is observed REFUSING. This pins that a minimal
    artifact still does not reach exit 0, and names the checks that starve on
    it, so a future change that quietly made them tolerant would be visible here
    rather than only as a conformant run that got easier.
    """
    root = artifact(tmp_path)
    result = run_conformance(root, report=tmp_path / "report.json")
    assert result.exit_code != core.EXIT_PASS, result.stdout

    verdicts = {row["check_id"]: row["code"] for row in result.report["checks"]}
    starved = sorted(check_id for check_id, code in verdicts.items()
                     if code != core.EXIT_PASS)
    assert starved, result.report["checks"]
    for check_id in ("CHECK-02", "CHECK-04", "CHECK-06", "CHECK-07", "CHECK-09"):
        assert check_id in starved, (
            "%s passed over the minimal artifact; it used to refuse for want of "
            "an input the fixture does not build: %r" % (check_id, starved))


def test_the_artifact_level_mapping_is_the_documented_contract():
    """all 0 -> 0 ; any 1 or any 2 -> 1 ; any 3 -> 3 ; no codes at all -> 2."""
    assert core.aggregate([0, 0, 0]) == core.EXIT_PASS
    assert core.aggregate([0, 2]) == core.EXIT_FINDING
    assert core.aggregate([0, 1]) == core.EXIT_FINDING
    assert core.aggregate([1, 3]) == core.EXIT_GUARD_FAIL
    assert core.aggregate([]) == core.EXIT_DID_NOT_RUN


# ---------------------------------------------------------------------------
# CHECK-11's detection, exercised on the records the runner retained
# ---------------------------------------------------------------------------


def test_check_11_detects_a_pass_over_zero_inputs():
    """The 0/0 pass, named by the check whose whole job is refusing it."""
    records = [_record("CHECK-02", core.VERDICT_PASS, core.EXIT_PASS, 0)]
    findings = conformance.check_11_findings(core, records)
    assert "pass-over-zero:CHECK-02" in findings, (
        "a PASS printed over a population of zero was not reported: %r"
        % (findings,))


def test_check_11_detects_a_line_carrying_no_population():
    """A verdict with no count is an unrun check."""
    records = [_record("CHECK-04", core.VERDICT_PASS, core.EXIT_PASS, 5,
                       line="CHECK-04         PASS        (no numbers at all)")]
    findings = conformance.check_11_findings(core, records)
    assert "population-absent:CHECK-04" in findings, (
        "a printed line carrying no population was not reported: %r" % (findings,))


def test_check_11_detects_a_verdict_that_contradicts_its_code():
    """A line that says one thing while the exit code says another."""
    records = [_record("CHECK-06", core.VERDICT_DID_NOT_RUN, core.EXIT_PASS, 0)]
    findings = conformance.check_11_findings(core, records)
    assert "verdict-code-mismatch:CHECK-06" in findings, (
        "a printed verdict that does not map to its own code was not reported: "
        "%r" % (findings,))


def test_check_11_detects_the_banned_verdict_word():
    records = [_record("CHECK-08", core.VERDICT_PASS, core.EXIT_PASS, 4,
                       line="CHECK-08         PASS        checked=4 of 4 "
                            + core.BANNED_VERDICT + "=0")]
    findings = conformance.check_11_findings(core, records)
    assert "banned-verdict:CHECK-08" in findings, findings


def test_check_11_reports_nothing_on_well_formed_records():
    """The other half: closing four holes must not report a clean run."""
    records = [_record("CHECK-01", core.VERDICT_PASS, core.EXIT_PASS, 3),
               _record("CHECK-03", core.VERDICT_FAIL, core.EXIT_FINDING, 2)]
    assert conformance.check_11_findings(core, records) == []


def test_check_11_does_not_flag_the_documented_demotion():
    """Closing a hole must not open one, and this is the hole it could open.

    A population below its effective floor is DEMOTED: the printed line says
    FAIL (the core has no verdict for "too small to mean anything") and the code
    says 2, with a DEMOTED line printed beside it. That pairing is a design rule working,
    not a defect, so the mismatch rule is one-directional -- it fires only when
    the CODE is the forgiving one.
    """
    demoted = _record("CHECK-01", core.VERDICT_FAIL, core.EXIT_DID_NOT_RUN, 1)
    assert conformance.check_11_findings(core, [demoted]) == []

    forgiving = _record("CHECK-01", core.VERDICT_FAIL, core.EXIT_PASS, 1)
    assert conformance.check_11_findings(core, [forgiving]) == \
        ["verdict-code-mismatch:CHECK-01"]


def test_the_demotion_is_printed_beside_the_line_it_demotes(tmp_path):
    """A FAIL beside code 2 with no explanation is unreadable."""
    root = artifact(tmp_path)
    result = run_conformance(root, "--min-population", "CHECK-01=99",
                             report=tmp_path / "report.json")
    assert "DEMOTED to %s" % core.VERDICT_DID_NOT_RUN in result.stdout, \
        result.stdout
    assert "floor 99" in result.stdout, result.stdout
    eleven = entry(result.report, "CHECK-11")
    assert eleven["code"] == core.EXIT_PASS, (
        "CHECK-11 reported the documented demotion as a finding: %r" % (eleven,))


def test_check_11_over_zero_records_is_did_not_run():
    contract = conformance.load_contract()
    result = conformance.check_11_result(core, contract, [], 1)
    assert result.checked == 0
    assert result.code == core.EXIT_DID_NOT_RUN


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_a_directory_that_does_not_exist_is_did_not_run(tmp_path):
    result = run_conformance(tmp_path / "absent-artifact",
                             report=tmp_path / "report.json")
    assert result.exit_code == core.EXIT_DID_NOT_RUN, result.stdout
    assert core.REFUSAL_PREFIX in result.stderr, result.stderr


def test_the_runner_finds_its_core_as_a_sibling_from_any_cwd(tmp_path):
    """Run BY PATH from an unrelated working directory, as a vendored copy is.

    The core and the check package are located relative to THIS FILE, never
    relative to the caller's cwd. A runner that resolved them from cwd would
    work in the repository and fail inside a handed-over artifact -- which is
    the one place a design rule says it has to work.
    """
    source = CONFORMANCE.read_text(encoding="ascii")
    assert "spec_from_file_location" in source, (
        "the runner does not load its core by path")
    assert "import canonkit" not in source, source[:200]

    world = build_conformant_world(tmp_path)
    elsewhere = tmp_path / "unrelated-cwd"
    elsewhere.mkdir()
    result = conftest.run_cli(
        [sys.executable, str(CONFORMANCE), str(world.artifact)]
        + world.flags() + ["--report", str(tmp_path / "report.json")],
        cwd=elsewhere)
    assert result.exit_code == core.EXIT_PASS, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# The pin every later EXIT=0 acceptance criterion leans on
# ---------------------------------------------------------------------------


def _all_pass_or_zero_artifact(tmp_path):
    """A tree whose checks are all PASS or a zero population -- no findings.

    MEASURED, and the construction matters. The minimal fixture on its own
    carries TWO findings (CHECK-06 for a results file with no run record,
    CHECK-07 for not being a work tree), and a finding keeps the artifact at
    exit 1 for a reason that has nothing to do with a design rule -- which would make
    the pin below pass no matter what the zero-population rule did.

    So: commit the tree (CHECK-07 then passes) and remove the figures record
    before committing (CHECK-06 then has nothing carrying a figure to want a
    run record for). What is left, read from the report rather than predicted:
    4 rows PASS, 8 rows examined ZERO inputs, 0 findings.
    """
    src = artifact(tmp_path / "src")
    (src / "results" / "figures.json").unlink()
    return conftest.committed_tree(tmp_path, src)


def test_exit_zero_requires_a_non_zero_checked_on_every_check(tmp_path):
    """`EXIT=0` may never be satisfiable by a tree of 0/0 passes.

    THIS IS THE PIN EVERY LATER `EXIT=0` ACCEPTANCE CRITERION IN THIS PHASE
    RESTS ON, and it is not the same assertion as
    `test_a_clean_artifact_exits_zero_over_a_real_population`. That one walks a
    CONFORMANT world, where every check has a real population, so a regression
    in the zero-population rule cannot show up in it at all -- there is no zero
    population for the rule to mishandle. This one hands the runner a tree that
    is clean EXCEPT that eight of its twelve checks examined nothing, and
    demands a non-zero exit anyway.

    Three assertions, and the first two are what stop the third being vacuous:

      (a) the population really is zero somewhere -- otherwise the fixture is
          just another conformant artifact and (c) is about nothing;
      (b) NOTHING here is a finding, and some rows PASS -- otherwise the
          non-zero exit is explained by a defect rather than by a design rule, and the
          pin would stay green with the rule removed. The passing rows are the
          positive control: the runner is demonstrably able to pass on this
          tree;
      (c) the exit is not 0.

    OBSERVED FAILING, on 2026-09-18, which is the only reason anyone knows this
    pin is wired up. The design rule lift in `canonkit.aggregate()` -- the line that
    makes a check-level 2 rise to an artifact-level 1 -- was mutated to treat
    EXIT_DID_NOT_RUN as a pass:

        if all(code == EXIT_PASS for code in codes):
        ->  if all(code in (EXIT_PASS, EXIT_DID_NOT_RUN) for code in codes):

    and this test failed with "conformance.py exited 0 over an artifact whose
    checks ['CHECK-01', 'CHECK-02', 'CHECK-04', 'CHECK-05', 'CHECK-06',
    'CHECK-08', 'CHECK-09', 'CHECK-20'] examined ZERO inputs". The file was
    restored from a BYTE SNAPSHOT taken before the edit -- never with
    `git checkout -- <file>`, which restores from HEAD and can make the thing
    under test the restored implementation rather than the edit -- and the
    sha256 was read on both sides and was IDENTICAL before and after, and
    DIFFERENT while mutated. The core has moved since, and the historical
    pair is left as it was: a reading edited to agree with a later file is
    no longer evidence of anything. Every digest here is DESCRIBED rather
    than quoted -- a hash in prose documents the file beside it and goes
    stale silently the moment either one changes.
    """
    root = _all_pass_or_zero_artifact(tmp_path)
    result = run_conformance(root, report=tmp_path / "report.json")
    rows = result.report["checks"]
    assert rows, result.report

    starved = sorted(row["check_id"] for row in rows if row["checked"] == 0)
    passing = sorted(row["check_id"] for row in rows
                     if row["code"] == core.EXIT_PASS)
    findings = sorted(row["check_id"] for row in rows
                      if row["code"] == core.EXIT_FINDING)

    assert starved, (
        "no check on this tree examined zero inputs, so the pin below is "
        "vacuous: %r" % ([(row["check_id"], row["checked"]) for row in rows],))
    assert passing, (
        "no check passed on this tree, so a non-zero exit proves nothing about "
        "the zero-population rule: %r"
        % ([(row["check_id"], row["code"]) for row in rows],))
    assert not findings, (
        "this tree was supposed to be clean apart from its empty populations, "
        "and %r reported a finding -- the exit below would then be explained "
        "by that instead of by a design rule" % (findings,))

    assert result.exit_code != core.EXIT_PASS, (
        "conformance.py exited 0 over an artifact whose checks %r examined "
        "ZERO inputs. Exit 0 is what every gate in this programme branches on, "
        "and a tree of 0/0 passes must never produce it.\n%s"
        % (starved, result.stdout))

    for check_id in starved:
        row = next(row for row in rows if row["check_id"] == check_id)
        assert row["code"] == core.EXIT_DID_NOT_RUN, (
            "%s examined zero inputs and reported code %d"
            % (check_id, row["code"]))


def test_a_check_that_does_not_apply_is_not_a_check_that_passed_over_zero(
        tmp_path):
    """The mechanism a design rule needs must not become a hole in the pin above.

    A NOT-APPLICABLE member contributes no code, which is exactly what lets an
    artifact that backs nothing reach EXIT=0. The risk that buys is obvious and
    is asserted here rather than assumed: if the declaration could be satisfied
    without a recorded reason, every starved check could be renamed into
    inapplicability and the pin above would be satisfiable again. So the tree
    from the pin -- whose slug the expected set does not even name -- must come
    back with NOTHING declared not applicable.
    """
    root = _all_pass_or_zero_artifact(tmp_path)
    result = run_conformance(root, report=tmp_path / "report.json")
    assert result.report.get("not_applicable_checks") == [], (
        "a slug the expected set does not name had checks declared not "
        "applicable: %r" % (result.report.get("not_applicable_checks"),))
    assert result.exit_code != core.EXIT_PASS, result.stdout


def test_an_artifact_that_owes_nothing_reaches_exit_zero(tmp_path):
    """a design rule and a design rule together, on the shape `example-search-benchmark` has.

    The whole reason the applicability mechanism is runner-side rather than an
    in-module refusal. This artifact is conformant and backs no published claim,
    and the expected set records WHY in the slug's own row. Before the
    declaration existed, three checks refused -- CHECK-05 for a register row it
    does not owe, CHECK-09 for a claim table it should not have, CHECK-20 for a
    correction it cannot owe -- each a code 2 the aggregate lifts to 1. So
    "both artifacts exit 0" was unreachable no matter what else was fixed, and
    a design rule explicitly refused to buy it with a waiver: backing nothing is
    CORRECT here, not tolerated.

    `0 waived` is asserted for that reason, beside the exit code.
    """
    world = build_conformant_world(tmp_path)
    manifest_path = Path(world.manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    row = manifest["slugs"][0]
    row["bullets"] = []
    row["backs_bullets"] = []
    row["register_row"] = False
    row["no_row_reason"] = OWES_NOTHING_REASON
    manifest["counts"]["register_rows_expected"] = 0
    manifest["counts"]["register_rows_derived"] = 0
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="ascii", newline="\n")

    result = run_conformance(world.artifact, *world.flags(),
                             report=tmp_path / "report.json")
    assert result.exit_code == core.EXIT_PASS, result.stdout + result.stderr

    named = {row["check_id"]: row["reason"]
             for row in result.report["not_applicable_checks"]}
    for check_id in ("CHECK-05", "CHECK-09", "CHECK-20"):
        assert check_id in named, (
            "%s was not declared not applicable: %r" % (check_id, sorted(named)))
        assert OWES_NOTHING_REASON in named[check_id], (
            "%s's reason is not the manifest's own text: %r"
            % (check_id, named[check_id]))

    rows = result.report["checks"]
    assert rows, result.report
    for entry_row in rows:
        assert entry_row["checked"] > 0, (
            "%s contributed a code over a population of %d"
            % (entry_row["check_id"], entry_row["checked"]))
        assert entry_row["code"] == core.EXIT_PASS, entry_row
    assert result.report["summary"]["waived"] == 0, result.report["summary"]

    # The population did not shrink: every declared check is in exactly one of
    # the two lists, and the two together are the full contract.
    total = len(rows) + len(named)
    assert total == discovered().found + len(conformance.RUNNER_CHECK_IDS), (
        "checks[] holds %d and not_applicable_checks[] holds %d, which is %d "
        "against a contract of %d module(s) plus %d runner propert(ies)"
        % (len(rows), len(named), total, discovered().found,
           len(conformance.RUNNER_CHECK_IDS)))
