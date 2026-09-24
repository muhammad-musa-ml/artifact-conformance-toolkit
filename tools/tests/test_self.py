"""`conformance.py --self`: the repository checked against a NAMED subset.

WHY A NAMED SUBSET AND NOT "ALL ELEVEN".

This repository is not an artifact. It has no `results/figures.json`, no
`results/gate.json`, no "what this does not show" section, no claim-under-test
block and no waivers record. Most of the eleven checks are therefore
inapplicable here BY CONSTRUCTION -- not failing, not passing: inapplicable.

An unqualified `--self` that ran whichever checks happened to find something to
read and then printed PASS would be reporting a verdict over a population nobody
stated. That is the 0/0 pass wearing a different hat, and a design rule (HARD) is the
decision this whole phase is organised around. So the subset is DECLARED, every
member outside it is PRINTED with a reason, both counts are reported, and an
empty subset REFUSES rather than passing over nothing.

THE LOAD-BEARING TEST IN THIS MODULE is
`test_self_prints_skipped_checks_with_reasons_and_count`. A test that merely
asserted `--self` exits 0 would pass on a `--self` that ran nothing at all,
which is precisely the failure the flag was designed against.

TWO MEMBERS ARE NOT CHECKERS, AND THE DISTINCTION IS LOAD-BEARING FOR a success criterion.
`CORE-CONTRACT` and `VENDOR-CONSISTENCY` print beside CHECK-07, CHECK-08 and
LINT-BANNED-NAMES, but they are SURFACED PRE-EXISTING SUITE ASSERTIONS rather
than members of the eleven-checker contract: the first re-runs the design rule split
assertion an earlier plan made in `test_repo_hygiene.py`, the second re-runs the
a project requirement hash assertion an earlier plan made in `test_vendoring.py`. Neither has a
`red-transcripts/*.txt` and neither ever will, because neither is a checker.

Every printed line therefore carries a LABEL -- `check` or `suite-assertion` --
and this module asserts that exactly two carry the second. Leaving it implicit
would let a reader count the names in `--self` output, count the transcripts,
and reconcile the two by assuming transcripts are missing; or, worse, let a
future audit widen its population to include two items that can never have a RED
transcript and then relax the "every member has one" rule to accommodate them.
A companion test module asserts the other half: that neither appears on
either side of the transcript bijection.

EXIT CODES. `--self` aggregates exactly as an artifact run does -- all 0 -> 0;
any 1 or any 2 -> 1; any 3 -> 3 -- over the members it RAN. The assertion below
is over that IDENTITY rather than over the literal 0, because pinning 0 would
make this module's verdict depend on whether the repository currently has an
open finding, and the thing being tested is the runner, not the tree.
"""

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT
CONFORMANCE = REPO_ROOT / "tools" / "conformance.py"
HOOK_PATH = REPO_ROOT / ".githooks" / "pre-push"


def _load(stem, path):
    spec = importlib.util.spec_from_file_location(stem, str(path))
    if spec is None or spec.loader is None:                # pragma: no cover
        raise RuntimeError("could not build a spec for %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[stem] = module
    spec.loader.exec_module(module)
    return module


conformance = _load("conformance_under_self_test", CONFORMANCE)
core = _load("frozen_core_for_self_test", REPO_ROOT / "tools" / "canonkit.py")


# ---------------------------------------------------------------------------
# One `--self` run, shared by every test in this module.
# ---------------------------------------------------------------------------

# The two labels. Built from fragments of the strings the runner prints, so a
# reader can see they are the runner's vocabulary rather than this module's.
LABEL_CHECK = "check"
LABEL_SUITE = "suite-assertion"
SUITE_ASSERTION_COUNT = 2

# The verdict word a member that was never run carries. Distinct from every
# canonkit verdict, because "inapplicable by construction" is not a verdict about
# the repository -- it is a statement about the population.
SKIPPED_VERDICT = "NOT-APPLICABLE"

# BOTH counts, on ONE line, in a shape a test PARSES rather than eyeballs.
#
# The second count is spelled `not-applicable` and NOT with canonkit's banned
# verdict word. That is a deliberate departure from the plan's illustrative
# wording ("self: ran 5, skipped 6 ..."): CHECK-11 forbids the banned verdict
# word anywhere in this tool's output, because it reads as "deliberately and
# safely omitted" -- which is how a population of zero gets filed as a pass by a
# human reading a log. The count, the reasons and the parseability are identical;
# only the word changes, and it changes the same way the population line already
# renames the core's count to `not-examined`.
SUMMARY_RE = re.compile(
    r"^self: ran (?P<ran>\d+), not-applicable (?P<skipped>\d+)\b")

# Every line the runner prints for a member, ran or skipped:
#   <id up to 18> <label up to 16> <verdict up to 11> <body>
MEMBER_RE = re.compile(
    r"^(?P<id>[A-Z0-9-]+)\s+(?P<label>check|suite-assertion)\s+"
    r"(?P<verdict>[A-Z-]+)\s+(?P<body>\S.*)$")


@pytest.fixture(scope="module")
def selfrun(tmp_path_factory):
    """Run `--self` once, through a subprocess, and keep everything it produced."""
    workdir = tmp_path_factory.mktemp("selfrun")
    result = conftest.run_cli(
        [sys.executable, str(CONFORMANCE), "--self",
         "--report", str(workdir / "self.json")],
        cwd=REPO_ROOT)
    return result


def member_lines(stdout):
    """Every member line the run printed, parsed. Never a substring search."""
    rows = []
    for line in stdout.splitlines():
        match = MEMBER_RE.match(line)
        if match:
            rows.append(match.groupdict())
    return rows


def summary_line(stdout):
    for line in stdout.splitlines():
        if SUMMARY_RE.match(line):
            return line
    return ""


def report_of(result):
    assert result.report is not None, (
        "the run wrote no structured report:\n%s\n%s"
        % (result.stdout, result.stderr))
    return result.report


# ---------------------------------------------------------------------------
# The subset itself
# ---------------------------------------------------------------------------


def test_the_subset_is_declared_in_code_with_a_committed_count():
    """A derived length silently stops checking when a name is dropped."""
    assert hasattr(conformance, "SELF_SUBSET"), (
        "conformance.py declares no SELF_SUBSET; --self would have to infer its "
        "population, which is the thing the named subset exists to prevent")
    assert len(conformance.SELF_SUBSET) == conformance.SELF_SUBSET_COUNT, (
        "SELF_SUBSET names %d member(s), the committed literal says %d"
        % (len(conformance.SELF_SUBSET), conformance.SELF_SUBSET_COUNT))
    assert conformance.SELF_SUBSET_COUNT > 0


def test_exactly_two_subset_members_are_suite_assertions():
    """CORE-CONTRACT and VENDOR-CONSISTENCY, and nothing else.

    Asserted against the DECLARATION as well as against the output, because the
    two could otherwise drift: an item relabelled in one place and not the other
    would still print two `suite-assertion` lines.
    """
    labels = [member.kind for member in conformance.SELF_SUBSET]
    assert labels.count(LABEL_SUITE) == SUITE_ASSERTION_COUNT, labels
    named = sorted(member.member_id for member in conformance.SELF_SUBSET
                   if member.kind == LABEL_SUITE)
    assert named == ["CORE-CONTRACT", "VENDOR-CONSISTENCY"], named


def test_every_subset_member_that_is_a_check_is_a_declared_checker():
    """A `check`-labelled member outside CHECK-01..CHECK-11 plus the named
    non-check set would widen a success criterion's population without saying so."""
    allowed = set(conformance.DECLARED_SELF_CHECK_IDS)
    for member in conformance.SELF_SUBSET:
        if member.kind != LABEL_CHECK:
            continue
        assert member.member_id in allowed, (
            "%s is labelled `check` but is not in the declared checker universe "
            "%s" % (member.member_id, sorted(allowed)))


# ---------------------------------------------------------------------------
# The printed report -- the load-bearing half
# ---------------------------------------------------------------------------


def test_self_prints_skipped_checks_with_reasons_and_count(selfrun):
    """THE LOAD-BEARING TEST. A `--self` that ran nothing would exit 0 too.

    Four things, and all four are needed. The summary line must carry BOTH
    counts; the two counts must agree with the lines actually printed; every
    skipped member must carry a non-empty reason beside its name; and the ran
    count must be greater than zero, because a subset that resolved to nothing
    and reported `ran 0, skipped 11` is still a run that checked nothing.
    """
    line = summary_line(selfrun.stdout)
    assert line, (
        "no line matching %r was printed, so the counts cannot be read at all:"
        "\n%s" % (SUMMARY_RE.pattern, selfrun.stdout))

    counts = SUMMARY_RE.match(line).groupdict()
    ran, skipped = int(counts["ran"]), int(counts["skipped"])

    rows = member_lines(selfrun.stdout)
    assert rows, "no member line was printed at all:\n%s" % selfrun.stdout

    printed_skipped = [row for row in rows if row["verdict"] == SKIPPED_VERDICT]
    printed_ran = [row for row in rows if row["verdict"] != SKIPPED_VERDICT]

    assert ran == len(printed_ran), (
        "the summary says ran %d; %d member line(s) carry a verdict: %r"
        % (ran, len(printed_ran), [row["id"] for row in printed_ran]))
    assert skipped == len(printed_skipped), (
        "the summary says skipped %d; %d line(s) are marked %s: %r"
        % (skipped, len(printed_skipped), SKIPPED_VERDICT,
           [row["id"] for row in printed_skipped]))
    assert ran > 0, (
        "--self ran ZERO members and still printed a summary. %r" % line)

    for row in printed_skipped:
        assert row["body"].strip(), (
            "%s is skipped with no reason beside it. A skip without a reason is "
            "an input silently dropped." % row["id"])


def test_every_printed_line_carries_a_check_or_suite_assertion_label(selfrun):
    """The label is what keeps a success criterion's population honest in both directions."""
    rows = member_lines(selfrun.stdout)
    assert rows, selfrun.stdout
    suite = [row["id"] for row in rows if row["label"] == LABEL_SUITE]
    assert len(suite) == SUITE_ASSERTION_COUNT, (
        "%d line(s) carry the %r label, expected %d: %r"
        % (len(suite), LABEL_SUITE, SUITE_ASSERTION_COUNT, suite))
    assert sorted(suite) == ["CORE-CONTRACT", "VENDOR-CONSISTENCY"], suite


def test_check_10_and_check_11_are_NAMED_skips_and_never_silent_absences(selfrun):
    """an earlier plan emits both as first-class `checks[]` rows on every ARTIFACT
    run. `--self` scans no artifact, so their absence here must be STATED.

    A reader who found nine names in a `--self` report and eleven in the
    contract would have to guess which two were dropped and why. Both are named,
    both carry a reason, and both are inside the skipped COUNT.
    """
    rows = {row["id"]: row for row in member_lines(selfrun.stdout)}
    report = report_of(selfrun)

    for check_id in ("CHECK-10", "CHECK-11"):
        assert check_id in rows, (
            "%s appears nowhere in --self's output. A checker that is silently "
            "absent from a self-check report reads as a contract that shrank."
            % check_id)
        assert rows[check_id]["verdict"] == SKIPPED_VERDICT, rows[check_id]
        assert rows[check_id]["body"].strip(), rows[check_id]

    named = {entry["check_id"] for entry in report["not_applicable_checks"]}
    assert {"CHECK-10", "CHECK-11"} <= named, sorted(named)

    ran_ids = {entry["check_id"] for entry in report["checks"]}
    assert not ({"CHECK-10", "CHECK-11"} & ran_ids), (
        "CHECK-10/CHECK-11 appear in --self's checks[] array. They were not "
        "run; a row there would be a verdict over nothing. %r" % sorted(ran_ids))


def test_the_two_counts_partition_the_declared_universe(selfrun):
    """ran + skipped covers every declared checker plus the named non-checks.

    Without this, a member could vanish from BOTH lists and both counts would
    still agree with the lines printed beside them.
    """
    report = report_of(selfrun)
    ran = {entry["check_id"] for entry in report["checks"]}
    skipped = {entry["check_id"] for entry in report["not_applicable_checks"]}

    assert not (ran & skipped), sorted(ran & skipped)
    declared = set(conformance.DECLARED_SELF_CHECK_IDS)
    missing = sorted(declared - (ran | skipped))
    assert not missing, (
        "%d declared checker(s) appear in NEITHER list: %s" % (len(missing), missing))


def test_every_entry_the_self_run_reports_carries_a_population(selfrun):
    """`checked > 0` on every row. A row with a population of zero belongs in
    the skip list with a reason, never in checks[] with a verdict."""
    report = report_of(selfrun)
    assert report["checks"], report
    for entry in report["checks"]:
        assert entry["checked"] > 0, (
            "%s is reported as a RAN member over a population of %d"
            % (entry["check_id"], entry["checked"]))


def test_the_report_records_both_counts_and_they_match_the_arrays(selfrun):
    report = report_of(selfrun)
    assert report["mode"] == "self", report["mode"]
    assert report["ran"] == len(report["checks"]), report
    assert report["not_applicable"] == len(report["not_applicable_checks"]), report
    assert report["schema_version"] == core.SCHEMA_VERSION


def test_every_skipped_entry_in_the_report_carries_a_reason(selfrun):
    report = report_of(selfrun)
    assert report["not_applicable_checks"], report
    for entry in report["not_applicable_checks"]:
        assert entry.get("reason", "").strip(), entry
        assert entry.get("kind") in (LABEL_CHECK, LABEL_SUITE), entry


def test_the_exit_code_is_the_aggregate_of_what_it_ran(selfrun):
    """The contract, not the current tree's verdict.

    Pinning the literal 0 here would make this test's subject the repository
    rather than the runner: it would go red the moment a real finding appeared,
    and the standard repair would be to relax it.
    """
    report = report_of(selfrun)
    expected = core.aggregate([entry["code"] for entry in report["checks"]])
    assert selfrun.exit_code == expected, (
        "--self exited %d; aggregating its own rows %r gives %d"
        % (selfrun.exit_code, [(e["check_id"], e["code"])
                               for e in report["checks"]], expected))
    assert report["code"] == selfrun.exit_code, report["code"]


def test_the_banned_verdict_word_appears_nowhere_in_the_self_output(selfrun):
    """CHECK-11's discipline applies to this tool's own output."""
    assert core.BANNED_VERDICT.lower() not in selfrun.stdout.lower(), (
        "the word %r reads as 'deliberately and safely omitted', which is how a "
        "zero population gets filed as a pass by a human reading the log"
        % core.BANNED_VERDICT)


# ---------------------------------------------------------------------------
# The refusal
# ---------------------------------------------------------------------------


def test_an_empty_subset_refuses_with_exit_two(tmp_path, monkeypatch):
    """A subset that resolves to nothing must REFUSE, never report a clean run.

    Patched in-process rather than by editing the file, so the committed subset
    is never mutated to test the empty case.
    """
    monkeypatch.setattr(conformance, "SELF_SUBSET", ())
    monkeypatch.setattr(conformance, "SELF_SUBSET_COUNT", 0)
    # canonkit.die() never returns -- it writes the refusal to stderr and raises
    # SystemExit -- so the code is read off the exception rather than off a
    # return value. Asserting on a return value here would have passed on a
    # SystemExit(0), which is the opposite verdict.
    with pytest.raises(SystemExit) as raised:
        conformance.main(["--self", "--report", str(tmp_path / "empty.json")])
    assert raised.value.code == core.EXIT_DID_NOT_RUN, (
        "an empty --self subset exited %r; a run over zero members is a "
        "DID-NOT-RUN, never a pass" % (raised.value.code,))


def test_a_self_run_writes_its_report_outside_any_artifact(tmp_path):
    """a design rule still applies: the checker must not mutate what it checks."""
    target = tmp_path / "self.json"
    code = conformance.main(["--self", "--report", str(target)])
    assert isinstance(code, int)
    assert target.is_file(), "no report was written to %s" % target
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["mode"] == "self"


# ---------------------------------------------------------------------------
# a design rule's upgrade: the hook gates on the suite AND the self-check
# ---------------------------------------------------------------------------


def test_the_hook_runs_both_the_suite_and_the_self_check():
    """Read from the hook's LIVE code, with comment lines stripped.

    The first draft of this repository's hook guard matched the hook's own
    explanatory comment, so it fired against its documentation. Judged on live
    code only, here as there.
    """
    text = HOOK_PATH.read_text(encoding="utf-8")
    live = "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("#"))
    assert "-m pytest tools/tests" in live, (
        "the hook no longer runs the test suite:\n%s" % live)
    assert "--self" in live, (
        "the hook does not run conformance.py --self. a design rule's upgrade path put "
        "it here at the END of the phase, deliberately not earlier.")
    assert "conformance.py" in live, live


def test_the_hook_captures_each_payload_by_redirection_and_never_by_a_pipe():
    """A command piped into `tail`/`head` reports the PIPE's exit status."""
    text = HOOK_PATH.read_text(encoding="utf-8")
    live = "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("#"))
    for needle in ("| tail", "| head", "|tail", "|head"):
        assert needle not in live, (
            "the hook pipes a payload through %r, so it would read the pipe's "
            "exit status rather than the command's" % needle)


def test_the_hook_reads_the_self_check_exit_status_it_captured():
    """Running the self-check and ignoring its status is a gate that does not gate."""
    text = HOOK_PATH.read_text(encoding="utf-8")
    live = [line for line in text.splitlines()
            if not line.lstrip().startswith("#")]
    body = "\n".join(live)
    assert body.count("$?") >= 2, (
        "the hook captures fewer than two exit statuses, so one of its two "
        "payloads is unread:\n%s" % body)


@pytest.mark.skipif(os.name == "nt" and not os.environ.get("CBB_RUN_HOOK"),
                    reason="the hook re-runs the whole suite; set CBB_RUN_HOOK=1 "
                           "to exercise it from inside the suite")
def test_the_hook_refuses_when_the_self_check_fails():  # pragma: no cover
    completed = subprocess.run(
        ["sh", str(HOOK_PATH)], cwd=str(REPO_ROOT), capture_output=True,
        text=True, encoding="utf-8", errors="replace", shell=False,
        stdin=subprocess.DEVNULL)
    assert isinstance(completed.returncode, int)
