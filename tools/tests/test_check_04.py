"""CHECK-04 -- the gate was recorded, ordered first, and its token stamped.

Every test here runs `tools/checks/check_04.py` AS A SUBPROCESS, by path,
through conftest.run_cli, for the two reasons the sibling check suites record:
by path under a bare module name is exactly how the vendored copy runs inside an
artifact, and the thing under test is an EXIT CODE, which run_cli returns from
the CHILD rather than from a pipeline stage.

WHAT MAKES THE RED IN red-transcripts/CHECK-04.txt A REAL RED. The module is
registered and RUNNABLE in the commit that captures the transcript, with
`gate_findings()` -- and only that -- stubbed to return no finding. It walks
results/, excludes the gate and the per-item records and counts both, parses
every timestamp on both sides, loads every token and prints a real population.
Every failure line in that transcript is an assertion about a VERDICT.

TWO ASSERTIONS HERE CARRY MORE THAN THE REST.

test_a_correctly_recorded_failed_gate_is_a_pass is the requirement's own
carve-out, and it is the one a check written to "refuse anything that looks
wrong" gets backwards. A failed gate that wrote a full record, minted its token
and stamped it is a correctly closed path, not a defect.

test_a_misleading_mtime_does_not_move_the_verdict is the mitigation for an earlier step
executed rather than asserted. The measurement's modification time is set an
hour BEFORE the gate's while the recorded stamps stay correct, so a check
ordering by the filesystem would report a finding and this one must not.
"""

import importlib.util
import json
import os
import sys
import tokenize
from pathlib import Path

from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT
CHECKS_DIR = REPO_ROOT / "tools" / "checks"
CHECK_04 = CHECKS_DIR / "check_04.py"
CHECK_01 = CHECKS_DIR / "check_01.py"
CHECK_02 = CHECKS_DIR / "check_02.py"
CHECK_03 = CHECKS_DIR / "check_03.py"

FIXTURE = "broken-gate-after-measurement"
EXPECTATION_FILE = "expected-CHECK-04.json"

PINNED_FIELDS = ("check_id", "code", "found", "checked", "finding_ids",
                 "schema_version")

PROSE_FIELDS = ("note", "notes", "stdout", "stderr", "message", "messages",
                "summary", "detail", "details", "findings", "text", "line",
                "context", "description", "not_examined_entries")

# The filesystem attribute this check must never consult, assembled from parts
# so this module's own source is not a hit for the sweep it performs. A pasted
# literal here would make the guard match its own test file if the sweep were
# ever widened, which is the shape an earlier plan had to withdraw five guards over.
FS_TIME_ATTR = "m" + "time"


def _load(stem, path):
    if stem in sys.modules:
        return sys.modules[stem]
    spec = importlib.util.spec_from_file_location(stem, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError("could not build a spec for %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[stem] = module
    spec.loader.exec_module(module)
    return module


core = _load("frozen_core_for_check_04_tests", REPO_ROOT / "tools" / "canonkit.py")
checks = _load("check_contract_for_check_04_tests", CHECKS_DIR / "__init__.py")
check_04 = _load("check_04_under_test", CHECK_04)


# ---------------------------------------------------------------------------
# Fixture material
# ---------------------------------------------------------------------------

TOKEN = "4" * 64
OTHER_TOKEN = "9" * 64

GATE_AT = "2026-09-15T20:00:00-05:00"
BEFORE_GATE = "2026-09-15T19:00:00-05:00"
AFTER_GATE = "2026-09-15T21:00:00-05:00"

LIMITS_BODY = (
    "This fixture measures nothing real. It does not show throughput, latency\n"
    "under load, or behaviour on any machine other than this one. The population\n"
    "is a hermetic test corpus, so the figures here cannot be compared with a\n"
    "production system and must never be read as a capacity claim.\n"
)

README = (
    "# demo-artifact\n"
    "\n"
    "<!-- artifact:date:begin -->\n"
    "Measured 2026-09-15 on the owner's own machine.\n"
    "<!-- artifact:date:end -->\n"
    "\n"
    "## What this does not show\n"
    "\n"
    "<!-- artifact:limits:begin -->\n"
    + LIMITS_BODY +
    "<!-- artifact:limits:end -->\n"
)


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                    encoding="ascii", newline="\n")
    return path


def gate_record(dated_at=GATE_AT, token=TOKEN, passed=True, failed_ids=None):
    """A gate record. `passed=False` with failed_ids is a CORRECTLY recorded
    failure -- a full record that minted its token, exactly as a design rule requires."""
    return {
        "artifact": "demo-artifact",
        "assertions": ["the fixture's own preconditions hold"],
        "dated_at": dated_at,
        "dated_at_utc": "2026-09-16T01:00:00+00:00",
        "env": {"platform": "win32"},
        "failed_ids": list(failed_ids or ([] if passed else ["free-vram"])),
        "fallback_source": {"path": "README.md", "read_at": dated_at,
                            "sha256": "0" * 64},
        "fallback_wording": "" if passed else "This path did not measure.",
        "inputs_hash": "3" * 64,
        "passed": passed,
        "realized": {"free_vram_mib": 5854},
        "run_token": token,
        "schema": "canonkit/gate/1",
        "schema_version": "canonkit/1",
    }


def run_record(run_id="run-0001", started_at=AFTER_GATE, token=TOKEN):
    record = {
        "api_spend_usd": 0.0,
        "env": {"platform": "win32"},
        "finished_at": "2026-09-15T21:05:00-05:00",
        "finished_at_utc": "2026-09-16T02:05:00+00:00",
        "gpu_minutes": 0.0,
        "run_id": run_id,
        "schema": "canonkit/run/1",
        "schema_version": "canonkit/1",
        "started_at": started_at,
        "started_at_utc": "2026-09-16T02:00:00+00:00",
        "wall_seconds": 300.0,
    }
    if token is not None:
        record["gate_token"] = token
    return record


def artifact(tmp_path, slug="demo-artifact", gate=True, runs=None, **gate_kwargs):
    """A hermetic artifact whose ONLY variables are its gate and its runs."""
    root = Path(tmp_path) / slug
    (root / "results").mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text(README, encoding="utf-8", newline="\n")
    if gate:
        write_json(root / "results" / "gate.json", gate_record(**gate_kwargs))
    for record in (runs if runs is not None else [run_record()]):
        write_json(root / "results" / "raw" / ("%s.json" % record["run_id"]),
                   record)
    return root


def run_check(target, *flags, report=None, cwd=None, script=CHECK_04):
    argv = [sys.executable, str(script), str(target)]
    if report is not None:
        argv += ["--report", str(report)]
    argv += [str(flag) for flag in flags]
    return conftest.run_cli(argv, cwd=cwd or REPO_ROOT)


def kinds(report):
    return sorted(finding["kind"] for finding in report["findings"])


# ---------------------------------------------------------------------------
# The protocol
# ---------------------------------------------------------------------------


def test_the_module_satisfies_the_check_protocol_and_discovery_finds_it():
    assert check_04.CHECK_ID == "CHECK-04"
    assert isinstance(check_04.DEFAULT_FLOOR, int)
    assert callable(check_04.run)

    report = checks.discover(CHECKS_DIR, verbose=False)
    assert "CHECK-04" in report.ids, report.ids
    assert not report.protocol_violations, report.protocol_violations


# ---------------------------------------------------------------------------
# The branch that must NOT fire
# ---------------------------------------------------------------------------


def test_a_gate_earlier_than_every_measurement_with_its_token_stamped_passes(
        tmp_path):
    root = artifact(tmp_path, slug="clean")
    result = run_check(root, report=tmp_path / "clean.json")
    assert result.exit_code == core.EXIT_PASS, result.stdout
    assert result.report["found"] == 0, result.report
    assert result.report["checked"] == 1, result.report


def test_a_correctly_recorded_failed_gate_is_a_pass(tmp_path):
    """The requirement's own carve-out, stated verbatim in the project requirements document.

    passed: false, a named failure, a MINTED token, dated before every
    measurement, and that token stamped on the run. All three facts CHECK-04
    asks about hold. a design rule makes a failed gate write exactly this record so that
    a measurement which ran anyway carries a key rather than no key at all.
    """
    root = artifact(tmp_path, slug="failed-gate", passed=False)
    gate = json.loads((root / "results" / "gate.json").read_text(encoding="ascii"))
    assert gate["passed"] is False, gate
    assert gate["failed_ids"], "a refusal that names nothing is not a record"
    assert gate["run_token"] == TOKEN, gate

    result = run_check(root, report=tmp_path / "failed-gate.json")
    assert result.exit_code == core.EXIT_PASS, (
        "a correctly recorded FAILED gate was refused, which collapses 'this "
        "path did not measure, and said so' into 'this path measured without "
        "authorisation':\n%s" % result.stdout)
    assert result.report["gate_passed"] is False, (
        "the report no longer says the gate failed, so a reader cannot tell "
        "the carve-out from an oversight: %r" % result.report)
    assert "gate-passed=False" in result.stdout, result.stdout


# ---------------------------------------------------------------------------
# The four branches
# ---------------------------------------------------------------------------


def test_an_absent_gate_is_a_finding(tmp_path):
    root = artifact(tmp_path, slug="no-gate", gate=False)
    result = run_check(root, report=tmp_path / "no-gate.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert kinds(result.report) == ["gate-absent"], result.report["findings"]
    assert result.report["gate_present"] is False, result.report


def test_a_gate_dated_after_a_measurement_is_a_finding_naming_it(tmp_path):
    root = artifact(tmp_path, slug="late-gate",
                    runs=[run_record(started_at=BEFORE_GATE)])
    result = run_check(root, report=tmp_path / "late-gate.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert kinds(result.report) == ["after-measurement"], (
        result.report["findings"])
    assert result.report["finding_ids"] == [
        "gate:after-measurement:results/raw/run-0001.json"], result.report


def test_a_gate_dated_at_the_same_instant_did_not_precede_the_run(tmp_path):
    """`not earlier than` is the requirement's wording. Equal is not earlier."""
    root = artifact(tmp_path, slug="same-instant",
                    runs=[run_record(started_at=GATE_AT)])
    result = run_check(root, report=tmp_path / "same-instant.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert kinds(result.report) == ["after-measurement"], (
        result.report["findings"])


def test_a_measurement_with_no_token_is_a_finding_naming_it(tmp_path):
    root = artifact(tmp_path, slug="no-token",
                    runs=[run_record(token=None)])
    result = run_check(root, report=tmp_path / "no-token.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert kinds(result.report) == ["token-absent"], result.report["findings"]


def test_a_measurement_with_the_wrong_token_is_a_finding_naming_it(tmp_path):
    root = artifact(tmp_path, slug="wrong-token",
                    runs=[run_record(token=OTHER_TOKEN)])
    result = run_check(root, report=tmp_path / "wrong-token.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert kinds(result.report) == ["token-mismatch"], result.report["findings"]


def test_an_unorderable_stamp_is_a_finding_rather_than_a_traceback(tmp_path):
    """A naive stamp beside an aware one cannot be compared, and Python RAISES
    while finding that out. The check must name it, not crash on it."""
    root = artifact(tmp_path, slug="unorderable",
                    runs=[run_record(started_at="2026-09-15T21:00:00")])
    result = run_check(root, report=tmp_path / "unorderable.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert kinds(result.report) == ["unorderable"], result.report["findings"]


def test_the_three_branches_produce_three_different_finding_ids(tmp_path):
    """One verdict for three defects would name the problem, not the repair."""
    absent = run_check(artifact(tmp_path, slug="ids-absent", gate=False),
                       report=tmp_path / "ids-absent.json")
    ordering = run_check(
        artifact(tmp_path, slug="ids-order",
                 runs=[run_record(started_at=BEFORE_GATE)]),
        report=tmp_path / "ids-order.json")
    token = run_check(artifact(tmp_path, slug="ids-token",
                               runs=[run_record(token=None)]),
                      report=tmp_path / "ids-token.json")

    sets = [set(absent.report["finding_ids"]),
            set(ordering.report["finding_ids"]),
            set(token.report["finding_ids"])]
    for one in sets:
        assert one, "a branch produced no finding id at all"
    assert not sets[0] & sets[1], (sets[0], sets[1])
    assert not sets[0] & sets[2], (sets[0], sets[2])
    assert not sets[1] & sets[2], (sets[1], sets[2])


# ---------------------------------------------------------------------------
# an earlier step -- the filesystem is not evidence
# ---------------------------------------------------------------------------


def test_a_misleading_mtime_does_not_move_the_verdict(tmp_path):
    """The mitigation EXECUTED, not asserted.

    The recorded stamps say the gate came first and the run followed. The
    FILESYSTEM is then made to say the opposite -- the measurement is stamped an
    hour before the gate -- and the verdict must not move. A check ordering by
    the filesystem would report `after-measurement` over this tree.
    """
    root = artifact(tmp_path, slug="touched")
    gate_path = root / "results" / "gate.json"
    run_path = root / "results" / "raw" / "run-0001.json"

    before = run_check(root, report=tmp_path / "before.json")
    assert before.exit_code == core.EXIT_PASS, before.stdout

    # The gate LAST written, the measurement written an hour earlier: exactly
    # the picture a naive ordering would call a gate recorded after the fact.
    old = 1_600_000_000.0
    os.utime(str(run_path), (old, old))
    os.utime(str(gate_path), (old + 3600, old + 3600))
    assert os.path.getmtime(str(run_path)) < os.path.getmtime(str(gate_path)), (
        "the test failed to establish the misleading picture it exists to test")

    after = run_check(root, report=tmp_path / "after.json")
    assert after.exit_code == core.EXIT_PASS, (
        "the verdict moved when only the FILESYSTEM changed, so this check is "
        "consulting it:\n%s" % after.stdout)
    assert after.report["found"] == before.report["found"], (
        before.report, after.report)


def test_the_filesystem_time_attribute_is_named_only_in_comments():
    """Asserted mechanically, in two forms, and neither of them is vacuous.

    The weaker form is the plan's own criterion: every LINE naming the
    attribute is a comment line. The stronger form uses the tokenizer, so
    `st_mtime` and `getmtime` are caught by the same assertion and a rename
    cannot slip past a line-based rule.
    """
    source = CHECK_04.read_bytes().decode("ascii")
    naming = [(number, line)
              for number, line in enumerate(source.splitlines(), 1)
              if FS_TIME_ATTR in line]
    assert naming, (
        "no line in %s names the attribute at all, so this guard would pass "
        "over a file that never mentions it and prove nothing. The reasoning "
        "belongs in the file, next to where someone would reach for it."
        % CHECK_04.name)

    not_comments = [(number, line) for number, line in naming
                    if not line.lstrip().startswith("#")]
    assert not not_comments, (
        "line(s) naming the filesystem time attribute outside a comment: %r"
        % not_comments)

    with open(CHECK_04, "rb") as handle:
        tokens = list(tokenize.tokenize(handle.readline))
    assert len(tokens) > 500, (
        "only %d token(s) were read from %s, so the tokenizer did not really "
        "scan it" % (len(tokens), CHECK_04.name))

    code_hits = [token for token in tokens
                 if FS_TIME_ATTR in token.string
                 and token.type not in (tokenize.COMMENT, tokenize.STRING)]
    assert not code_hits, (
        "a CODE token names the filesystem time attribute: %r"
        % [(t.start, t.string) for t in code_hits])

    comment_hits = [token for token in tokens
                    if FS_TIME_ATTR in token.string
                    and token.type == tokenize.COMMENT]
    assert comment_hits, (
        "no COMMENT token names it, so the code/comment split this asserts has "
        "nothing to discriminate")


# ---------------------------------------------------------------------------
# Could not look
# ---------------------------------------------------------------------------


def test_the_zero_input_fixture_is_did_not_run_and_is_neither_pass_nor_finding(
        tmp_path):
    """A gate with no measurement under it. Nothing to order, so nothing said."""
    root = artifact(tmp_path, slug="zero-input", runs=[])
    assert (root / "results" / "gate.json").is_file()

    result = run_check(root, report=tmp_path / "zero.json")
    assert result.exit_code == core.EXIT_DID_NOT_RUN, result.stdout
    assert result.exit_code != core.EXIT_PASS, (
        "a check that examined nothing reported a PASS: %s" % result.stdout)
    assert result.exit_code != core.EXIT_FINDING, (
        "a check that examined nothing reported a FINDING, which claims it "
        "looked: %s" % result.stdout)
    assert result.report["checked"] == 0, result.report

    line = next(row for row in result.stdout.splitlines()
                if row.startswith("CHECK-04"))
    assert line.split()[1] == core.VERDICT_DID_NOT_RUN, line


def test_a_results_file_with_no_started_at_is_counted_not_silently_dropped(
        tmp_path):
    """It is outside the population, and CHECK-06 is named as its owner."""
    root = artifact(tmp_path, slug="tokenless")
    write_json(root / "results" / "summary.json",
               {"gate_token": TOKEN, "total": 7})

    result = run_check(root, report=tmp_path / "tokenless.json")
    excluded = {row["path"]: row["reason"]
                for row in result.report["not_examined_entries"]}
    assert "results/summary.json" in excluded, result.report["not_examined_entries"]
    assert "CHECK-06" in excluded["results/summary.json"], (
        "the exclusion names no owner, so the gap reads as an oversight: %r"
        % excluded["results/summary.json"])
    assert result.report["checked"] == 1, result.report


# ---------------------------------------------------------------------------
# The committed fixture and its anti-rot pin
# ---------------------------------------------------------------------------


def test_the_committed_fixture_fails_and_names_both_defects(tmp_path):
    fixture = conftest.broken_fixture(FIXTURE)
    result = run_check(fixture, report=tmp_path / "fixture.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert kinds(result.report) == ["after-measurement", "token-absent"], (
        result.report["findings"])
    assert result.report["checked"] == 3, (
        "the fixture ships three measurements; the check examined %d"
        % result.report["checked"])


def test_only_check_04_refuses_the_check_04_fixture(tmp_path):
    """Two defects, both CHECK-04's -- or the fixture stops discriminating."""
    fixture = conftest.broken_fixture(FIXTURE)
    for script in (CHECK_01, CHECK_02, CHECK_03):
        result = run_check(fixture, report=tmp_path / (script.stem + ".json"),
                           script=script)
        assert result.exit_code == core.EXIT_PASS, (
            "%s also refuses the CHECK-04 fixture, so the fixture no longer "
            "discriminates:\n%s" % (script.name, result.stdout))


def test_the_anti_rot_pin_holds_for_the_known_bad_fixture(tmp_path):
    fixture = conftest.broken_fixture(FIXTURE)
    expectation_path = fixture / EXPECTATION_FILE
    assert expectation_path.is_file(), (
        "%s carries no %s, so its RED evidence has nothing pinning it"
        % (FIXTURE, EXPECTATION_FILE))
    expected = json.loads(expectation_path.read_text(encoding="ascii"))

    result = run_check(fixture, report=tmp_path / "pin.json")
    assert result.report is not None, "the check wrote no structured report"
    missing = [field for field in PINNED_FIELDS if field not in result.report]
    assert not missing, (
        "the live report no longer carries %r. A renamed field would otherwise "
        "make this pin compare nothing." % missing)
    measured = {field: result.report[field] for field in PINNED_FIELDS}
    assert measured == expected, (
        "the structured report drifted from its committed expectation.\n"
        "  expected: %r\n  measured: %r" % (expected, measured))


def test_the_anti_rot_expectation_carries_no_prose_field():
    fixture = conftest.broken_fixture(FIXTURE)
    expected = json.loads((fixture / EXPECTATION_FILE).read_text(encoding="ascii"))
    assert set(expected) == set(PINNED_FIELDS), (
        "the expectation holds %r; the pinned set is %r"
        % (sorted(expected), sorted(PINNED_FIELDS)))
    leaked = sorted(set(expected) & set(PROSE_FIELDS))
    assert not leaked, (
        "the pin holds wording-bearing field(s) %r" % leaked)


# ---------------------------------------------------------------------------
# a design rule and a design rule
# ---------------------------------------------------------------------------


def test_the_population_floor_override_is_effective_and_prints(tmp_path):
    root = artifact(tmp_path, slug="floor", gate=False)
    strict = run_check(root, "--min-population", "99",
                       report=tmp_path / "strict.json")
    assert "floor=99" in strict.stdout, strict.stdout
    assert strict.report["floor"] == 99, strict.report
    assert strict.exit_code == core.EXIT_DID_NOT_RUN, strict.stdout


def test_check_04_and_verify_answer_different_questions_about_one_token(
        tmp_path):
    """The two mechanisms DEMONSTRATED as complementary, not asserted to be.

    The chain here is built by running the real gate, so the token every record
    carries is one the gate genuinely minted from its own content.

    STATE ONE -- the gate FAILED and was correctly recorded, and the run carries
    that gate's token. CHECK-04 passes: the gate was recorded, it preceded the
    run, and its token is stamped. verify.py also has nothing to say, because
    the token the figures claim IS the token the gate in this artifact minted.
    Neither mechanism is broken here; they are both answering their own
    question truthfully.

    STATE TWO -- the gate is fixed and re-run. a design rule makes the token a function
    of gate CONTENT, so a changed gate mints a DIFFERENT token, and the
    measurement that ran under the failed one is now carrying a key that opens
    nothing. THAT is where the poisoned token a design rule describes becomes visible,
    and verify.py is what says so.
    """
    chain = _load("verify_chain_helpers", REPO_ROOT / "tools" / "tests"
                  / "test_verify_chain.py")
    root, minted = chain.build_chain(tmp_path)
    chain.derive_into(root, [chain.ok_rate_spec()])

    gate_path = Path(root) / "results" / "gate.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    assert gate["run_token"] == minted, gate

    # -- state one: a correctly recorded FAILED gate, same token -------------
    gate["passed"] = False
    gate["failed_ids"] = ["free-vram"]
    gate["fallback_wording"] = "This path did not measure."
    write_json(gate_path, gate)

    failed_state = run_check(root, report=tmp_path / "failed-state.json")
    assert failed_state.exit_code == core.EXIT_PASS, (
        "CHECK-04 refused a correctly recorded FAILED gate:\n%s"
        % failed_state.stdout)

    _, verify_code, verify_printed = chain.run_verify(root)
    assert "gate_token mismatch" not in verify_printed, (
        "verify.py reported a token mismatch while the tokens match, so this "
        "test is not measuring what it claims:\n%s" % verify_printed)

    # -- state two: the gate is fixed and re-run, minting a NEW token --------
    gate["passed"] = True
    gate["failed_ids"] = []
    gate["fallback_wording"] = ""
    gate["run_token"] = OTHER_TOKEN
    write_json(gate_path, gate)

    _, verify_code, verify_printed = chain.run_verify(root)
    assert verify_code == core.EXIT_FINDING, (
        "verify.py did not refuse a measurement carrying a token the current "
        "gate never minted:\n%s" % verify_printed)
    assert "gate_token mismatch" in verify_printed, verify_printed

    stale = run_check(root, report=tmp_path / "stale.json")
    assert stale.exit_code == core.EXIT_FINDING, stale.stdout
    assert "token-mismatch" in kinds(stale.report), stale.report["findings"]


def test_a_waiver_suppresses_one_named_finding(tmp_path):
    root = artifact(tmp_path, slug="waived", runs=[run_record(token=None)])
    contract = check_04.load_contract()
    waived = check_04.run(root, contract.CheckContext(waivers=[{
        "check_id": "CHECK-04",
        "finding_id": "gate:token-absent:results/raw/run-0001.json",
        "reason": "the fixture's run is deliberately unauthorised",
        "dated_at": "2026-09-15T00:00:00-05:00"}]))
    assert waived.waived == 1, waived
    assert waived.found == 0, waived
    assert waived.code == core.EXIT_PASS, waived
