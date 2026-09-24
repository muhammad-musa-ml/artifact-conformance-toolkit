"""CHECK-06 -- every results file carries a machine-emitted run record.

Every test here runs `tools/checks/check_06.py` AS A SUBPROCESS, by path,
through conftest.run_cli, for the two reasons the sibling check suites record:
by path under a bare module name is exactly how the vendored copy runs inside an
artifact, and the thing under test is an EXIT CODE, which run_cli returns from
the CHILD rather than from a pipeline stage.

WHAT MAKES THE RED IN red-transcripts/CHECK-06.txt A REAL RED. The module is
registered and RUNNABLE in the commit that captures the transcript, with
`record_findings()` -- and only that -- stubbed to return no finding. It walks
results/, classifies every file, counts both kinds of exclusion with a reason,
indexes the run records under raw/ by their gate token, LOCATES each results
file's run record and prints which of the three locations it came from. Every
failure line in that transcript is an assertion about a VERDICT.

THE TWO ASSERTIONS THIS SUITE EXISTS FOR.

test_a_recorded_zero_passes_and_an_omitted_key_is_a_finding is an earlier step. The two
differ by nothing a defaulting read can see, and a project requirement re-derives each path's
metered spend from exactly this field before the owner approves the path.

test_a_naive_timestamp_with_an_appended_z_is_rejected_by_name is an earlier step, and it
is the half of that threat a tzinfo test alone cannot reach. MEASURED on this
interpreter: fromisoformat("2026-01-01T00:00:00Z") returns an AWARE datetime, so
the hand-assembled string sails through a tzinfo check. What catches it is that
datetime.isoformat() NEVER emits a literal Z -- it writes an offset -- so the
suffix is proof the string was assembled rather than clocked.
"""

import datetime
import importlib.util
import json
import sys
from pathlib import Path

from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT
CHECKS_DIR = REPO_ROOT / "tools" / "checks"
CHECK_06 = CHECKS_DIR / "check_06.py"
CHECK_01 = CHECKS_DIR / "check_01.py"
CHECK_02 = CHECKS_DIR / "check_02.py"
CHECK_03 = CHECKS_DIR / "check_03.py"
CHECK_04 = CHECKS_DIR / "check_04.py"

FIXTURE = "broken-no-run-record"
EXPECTATION_FILE = "expected-CHECK-06.json"

PINNED_FIELDS = ("check_id", "code", "found", "checked", "finding_ids",
                 "schema_version")

PROSE_FIELDS = ("note", "notes", "stdout", "stderr", "message", "messages",
                "summary", "detail", "details", "findings", "text", "line",
                "context", "description", "not_examined_entries", "sources")


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


core = _load("frozen_core_for_check_06_tests", REPO_ROOT / "tools" / "canonkit.py")
checks = _load("check_contract_for_check_06_tests", CHECKS_DIR / "__init__.py")
check_06 = _load("check_06_under_test", CHECK_06)


# ---------------------------------------------------------------------------
# Fixture material
# ---------------------------------------------------------------------------

TOKEN = "6" * 64

LOCAL_START = "2026-09-15T21:00:00-05:00"
UTC_START = "2026-09-16T02:00:00+00:00"
LOCAL_FINISH = "2026-09-15T21:05:00-05:00"
UTC_FINISH = "2026-09-16T02:05:00+00:00"

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


def full_run_record(run_id="run-0001", token=TOKEN, **overrides):
    """A COMPLETE machine run record: all seven fields, both timestamp forms."""
    record = {
        "api_spend_usd": 0.0,
        "env": {"platform": "win32"},
        "finished_at": LOCAL_FINISH,
        "finished_at_utc": UTC_FINISH,
        "gate_token": token,
        "gpu_minutes": 0.0,
        "run_id": run_id,
        "schema": "canonkit/run/1",
        "schema_version": "canonkit/1",
        "started_at": LOCAL_START,
        "started_at_utc": UTC_START,
        "wall_seconds": 300.0,
    }
    record.update(overrides)
    for key, value in list(record.items()):
        if value is _DROP:
            del record[key]
    return record


class _Drop(object):
    """Sentinel: an override that DELETES a key rather than nulling it.

    A deleted key and a key set to None are different defects, and this suite
    has to be able to build each of them deliberately.
    """


_DROP = _Drop()
DROP = _DROP


def figures_record(token=TOKEN):
    return {
        "artifact": "demo-artifact",
        "dated_at": "2026-09-15",
        "figures": {"median_latency_ms": {
            "canon_bullet": "example-alpha:P2-B1",
            "canon_value": 12.0,
            "derived_from": ["results/raw/items/#replay.median"],
            "not_shown": "A hermetic test corpus.",
            "population": 500,
            "population_label": "replayed requests",
            "reproduce_criterion": {"kind": "relative", "tolerance": 0.05},
            "runs": [],
            "similar": "CONFIRMS",
            "similar_reason_ref": "register-fragments/demo.md",
            "threshold_claim": False,
            "tier_achieved": "recompute",
            "unit": "ms",
            "value": 12.5}},
        "gate_token": token,
        "schema": "canonkit/figures/1",
        "schema_version": "canonkit/1",
        "started_at": LOCAL_START,
        "started_at_utc": UTC_START,
    }


def provenance_record(**run_overrides):
    run = {
        "api_spend_usd": 0.0,
        "finished_at": LOCAL_FINISH,
        "finished_at_utc": UTC_FINISH,
        "gpu_minutes": 0.0,
        "started_at": LOCAL_START,
        "started_at_utc": UTC_START,
        "wall_seconds": 300.0,
    }
    run.update(run_overrides)
    for key, value in list(run.items()):
        if value is _DROP:
            del run[key]
    return {
        "free_vram_mib": 5854,
        "host": {"platform": "win32"},
        "images": {},
        "run": run,
        "schema": "canonkit/provenance/1",
        "schema_version": "canonkit/1",
        "sources": {},
    }


def artifact(tmp_path, slug="demo-artifact", figures=True, raw=None,
             provenance=None, extra=None):
    """A hermetic artifact whose ONLY variable is its run metadata."""
    root = Path(tmp_path) / slug
    (root / "results").mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text(README, encoding="utf-8", newline="\n")
    if figures:
        write_json(root / "results" / "figures.json", figures_record())
    for record in (raw if raw is not None else [full_run_record()]):
        write_json(root / "results" / "raw" / ("%s.json" % record["run_id"]),
                   record)
    if provenance is not None:
        write_json(root / "results" / "provenance.json", provenance)
    for relative, payload in (extra or {}).items():
        write_json(root / relative, payload)
    return root


def run_check(target, *flags, report=None, cwd=None, script=CHECK_06):
    argv = [sys.executable, str(script), str(target)]
    if report is not None:
        argv += ["--report", str(report)]
    argv += [str(flag) for flag in flags]
    return conftest.run_cli(argv, cwd=cwd or REPO_ROOT)


def kinds(report):
    return sorted(finding["kind"] for finding in report["findings"])


# ---------------------------------------------------------------------------
# The protocol, and the constant this module restates
# ---------------------------------------------------------------------------


def test_the_module_satisfies_the_check_protocol_and_discovery_finds_it():
    assert check_06.CHECK_ID == "CHECK-06"
    assert isinstance(check_06.DEFAULT_FLOOR, int)
    assert callable(check_06.run)

    report = checks.discover(CHECKS_DIR, verbose=False)
    assert "CHECK-06" in report.ids, report.ids
    assert not report.protocol_violations, report.protocol_violations


def test_the_run_record_key_set_matches_the_cores_own():
    """The committed literal and the core's list cannot drift apart silently.

    check_06.py restates the seven fields rather than reading them from the
    core, so a vendored copy does not depend on the core's spelling of a list it
    can hold itself. This is the assertion that keeps the restatement honest.
    """
    assert tuple(check_06.RUN_RECORD_KEYS) == tuple(core.PROVENANCE_RUN_KEYS), (
        "check_06 declares %r; canonkit declares %r"
        % (check_06.RUN_RECORD_KEYS, core.PROVENANCE_RUN_KEYS))
    assert len(check_06.RUN_RECORD_KEYS) == check_06.RUN_RECORD_KEY_COUNT


# ---------------------------------------------------------------------------
# A complete record passes, in each of the three places it can live
# ---------------------------------------------------------------------------


def test_a_complete_record_passes_wherever_it_lives(tmp_path):
    """inline, in a run block, and located by token -- all three, one tree."""
    root = artifact(tmp_path, slug="complete", provenance=provenance_record())
    result = run_check(root, report=tmp_path / "complete.json")
    assert result.exit_code == core.EXIT_PASS, result.stdout
    assert result.report["found"] == 0, result.report

    sources = result.report["sources"]
    assert sources["results/raw/run-0001.json"] == check_06.SOURCE_INLINE, sources
    assert sources["results/provenance.json"] == check_06.SOURCE_RUN_BLOCK, sources
    assert sources["results/figures.json"] == check_06.SOURCE_BY_TOKEN, (
        "figures.json is a DERIVED view with no cost fields of its own; it must "
        "be tied to its run by token: %r" % sources)


# ---------------------------------------------------------------------------
# an earlier step -- an omitted key and a zero are different claims
# ---------------------------------------------------------------------------


def test_a_recorded_zero_passes_and_an_omitted_key_is_a_finding(tmp_path):
    """The pair, in one test, so they cannot quietly collapse into one rule."""
    zero = run_check(
        artifact(tmp_path, slug="spent-zero",
                 raw=[full_run_record(api_spend_usd=0.0)]),
        report=tmp_path / "zero.json")
    assert zero.exit_code == core.EXIT_PASS, (
        "a run that recorded spending nothing was refused; 0.0 is a RECORD:\n%s"
        % zero.stdout)

    omitted = run_check(
        artifact(tmp_path, slug="spent-unknown",
                 raw=[full_run_record(api_spend_usd=DROP)]),
        report=tmp_path / "omitted.json")
    assert omitted.exit_code == core.EXIT_FINDING, (
        "an OMITTED cost key passed. Read with the ordinary defaulting idiom it "
        "is indistinguishable from a zero, and a project requirement re-derives metered spend "
        "from exactly this field:\n%s" % omitted.stdout)
    assert kinds(omitted.report) == ["partial-record"], (
        omitted.report["findings"])
    assert "api_spend_usd" in omitted.report["findings"][0]["detail"], (
        "the finding does not name the missing key: %r"
        % omitted.report["findings"][0]["detail"])


def test_a_null_cost_field_is_not_a_recorded_zero(tmp_path):
    """None is what an unfinished run leaves behind, not what a free run wrote."""
    root = artifact(tmp_path, slug="null-cost",
                    raw=[full_run_record(api_spend_usd=None)])
    result = run_check(root, report=tmp_path / "null.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert kinds(result.report) == ["partial-record"], result.report["findings"]


def test_an_unfinished_run_is_a_partial_record(tmp_path):
    """start_run writes finished_at as null; finish_run fills it in."""
    root = artifact(tmp_path, slug="unfinished",
                    raw=[full_run_record(finished_at=None,
                                         finished_at_utc=None)])
    result = run_check(root, report=tmp_path / "unfinished.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert kinds(result.report) == ["partial-record"], result.report["findings"]


# ---------------------------------------------------------------------------
# an earlier step -- a naive timestamp presented as UTC
# ---------------------------------------------------------------------------


def test_a_naive_timestamp_with_an_appended_z_is_rejected_by_name(tmp_path):
    """The failure the research note names, built the way it is actually produced.

    The string is assembled from a NAIVE datetime exactly as the bug does it,
    and this test first MEASURES that the resulting string defeats a tzinfo
    test -- so the assertion below is about the half of the threat that a
    tzinfo check cannot reach, and not about a case that was already covered.
    """
    naive = datetime.datetime(2026, 1, 1, 0, 0, 0)
    assert naive.tzinfo is None, "the fixture datetime is not naive"
    hand_assembled = naive.isoformat() + "Z"
    assert hand_assembled == "2026-01-01T00:00:00Z", hand_assembled
    assert datetime.datetime.fromisoformat(hand_assembled).tzinfo is not None, (
        "fromisoformat no longer reads a trailing Z as aware on this "
        "interpreter, so this test is not exercising what it claims")

    root = artifact(tmp_path, slug="appended-z",
                    raw=[full_run_record(started_at=hand_assembled)])
    result = run_check(root, report=tmp_path / "appended-z.json")

    assert result.exit_code == core.EXIT_FINDING, (
        "a naive datetime with a hand-appended Z passed:\n%s" % result.stdout)
    assert kinds(result.report) == ["naive-timestamp"], (
        result.report["findings"])

    detail = result.report["findings"][0]["detail"].lower()
    assert "naive" in detail, (
        "the message does not name the naive case, so an author reads it as a "
        "typo: %r" % result.report["findings"][0]["detail"])
    assert "isoformat" in detail, (
        "the message does not say WHY a Z is evidence, which is the only part "
        "an author cannot work out alone: %r"
        % result.report["findings"][0]["detail"])


def test_a_stamp_with_no_offset_at_all_is_rejected_by_name(tmp_path):
    """The other arm: it does not even parse as aware."""
    root = artifact(tmp_path, slug="no-offset",
                    raw=[full_run_record(started_at="2026-01-01T00:00:00")])
    result = run_check(root, report=tmp_path / "no-offset.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert kinds(result.report) == ["naive-timestamp"], result.report["findings"]
    assert "naive" in result.report["findings"][0]["detail"].lower(), (
        result.report["findings"][0]["detail"])


def test_an_offset_bearing_stamp_is_accepted(tmp_path):
    """The fix widened nothing: a real offset, in either form, still passes."""
    root = artifact(tmp_path, slug="offset-ok",
                    raw=[full_run_record(started_at="2026-01-01T00:00:00+00:00",
                                         started_at_utc="2026-01-01T00:00:00+00:00")])
    result = run_check(root, report=tmp_path / "offset-ok.json")
    assert result.exit_code == core.EXIT_PASS, result.stdout


# ---------------------------------------------------------------------------
# missing vs partial
# ---------------------------------------------------------------------------


def test_a_results_file_with_no_record_behind_it_is_a_finding(tmp_path):
    root = artifact(tmp_path, slug="unbacked", raw=[])
    result = run_check(root, report=tmp_path / "unbacked.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert kinds(result.report) == ["missing-record"], result.report["findings"]
    assert result.report["sources"]["results/figures.json"] == "none", (
        result.report["sources"])


def test_one_broken_record_is_one_finding_however_many_files_point_at_it(
        tmp_path):
    """`found` counts DEFECTS, not references to them.

    Caught during the GREEN commit, and it is not cosmetic. A derived figures
    record and the raw record it came from both reach the SAME run record --
    that is the normal shape of a real artifact, not an edge case. Keying the
    finding on the referencing FILE reported one incomplete record twice here,
    and would report it once per derived view on an artifact publishing several.
    `found` would then grow with how much an artifact publishes rather than with
    what is wrong with it, which is a count that misleads in the direction of
    looking worse the more honest work you do.

    Both files below are in the population and both locate the same record. The
    finding is keyed on the RECORD, so there is exactly one.
    """
    root = artifact(tmp_path, slug="one-defect",
                    raw=[full_run_record(api_spend_usd=DROP)])
    result = run_check(root, report=tmp_path / "one-defect.json")

    sources = result.report["sources"]
    assert sources["results/figures.json"] == check_06.SOURCE_BY_TOKEN, sources
    assert sources["results/raw/run-0001.json"] == check_06.SOURCE_INLINE, sources
    assert result.report["checked"] == 2, (
        "both files must be IN the population, or this test proves nothing "
        "about de-duplication: %r" % result.report)

    assert result.report["found"] == 1, (
        "one incomplete record was reported %d time(s), once per file that "
        "points at it: %r"
        % (result.report["found"], result.report["finding_ids"]))
    assert result.report["finding_ids"] == [
        "run-record:partial-record:results/raw/run-0001.json"], result.report


def test_the_missing_and_partial_branches_produce_different_finding_ids(tmp_path):
    """Merging them would make the second repair invisible behind the first."""
    missing = run_check(artifact(tmp_path, slug="ids-missing", raw=[]),
                        report=tmp_path / "ids-missing.json")
    partial = run_check(
        artifact(tmp_path, slug="ids-partial",
                 raw=[full_run_record(gpu_minutes=DROP)]),
        report=tmp_path / "ids-partial.json")

    missing_ids = set(missing.report["finding_ids"])
    partial_ids = set(partial.report["finding_ids"])
    assert missing_ids, missing.report
    assert partial_ids, partial.report
    assert not missing_ids & partial_ids, (missing_ids, partial_ids)


# ---------------------------------------------------------------------------
# The population, and what is deliberately outside it
# ---------------------------------------------------------------------------


def test_the_zero_input_fixture_is_did_not_run_and_is_neither_pass_nor_finding(
        tmp_path):
    """An empty results/ directory. Nothing claims a measurement, so nothing said."""
    root = artifact(tmp_path, slug="zero-input", figures=False, raw=[])
    assert (root / "results").is_dir()

    result = run_check(root, report=tmp_path / "zero.json")
    assert result.exit_code == core.EXIT_DID_NOT_RUN, result.stdout
    assert result.exit_code != core.EXIT_PASS, (
        "a check that examined nothing reported a PASS: %s" % result.stdout)
    assert result.exit_code != core.EXIT_FINDING, (
        "a check that examined nothing reported a FINDING: %s" % result.stdout)
    assert result.report["checked"] == 0, result.report

    line = next(row for row in result.stdout.splitlines()
                if row.startswith("CHECK-06"))
    assert line.split()[1] == core.VERDICT_DID_NOT_RUN, line


def test_per_item_records_are_excluded_and_counted(tmp_path):
    """Their run record is the run that wrote them, not one of their own."""
    root = artifact(tmp_path, slug="with-items")
    items = root / "results" / "raw" / "items"
    items.mkdir(parents=True, exist_ok=True)
    write_json(items / "item-0000.json", {"item_id": "item-0000",
                                          "latency_ms": 10.0, "ok": True})

    result = run_check(root, report=tmp_path / "items.json")
    assert result.exit_code == core.EXIT_PASS, result.stdout
    excluded = [row["path"] for row in result.report["not_examined_entries"]]
    assert "results/raw/items/item-0000.json" in excluded, (
        result.report["not_examined_entries"])
    assert "results/raw/items/item-0000.json" not in result.report["sources"], (
        "a per-item record entered the population: %r" % result.report["sources"])


def test_a_document_that_claims_no_measurement_is_outside_the_population(
        tmp_path):
    """A waivers file holds integers and measures nothing."""
    root = artifact(tmp_path, slug="non-measuring",
                    extra={"results/notes.json": {"reviewed": True,
                                                  "count": 3}})
    result = run_check(root, report=tmp_path / "non-measuring.json")
    assert result.exit_code == core.EXIT_PASS, result.stdout
    excluded = {row["path"]: row["reason"]
                for row in result.report["not_examined_entries"]}
    assert "results/notes.json" in excluded, result.report["not_examined_entries"]


def test_the_gate_is_excluded_and_the_exclusion_names_check_04(tmp_path):
    root = artifact(tmp_path, slug="with-gate",
                    extra={"results/gate.json": {"passed": True,
                                                 "run_token": TOKEN,
                                                 "dated_at": LOCAL_START}})
    result = run_check(root, report=tmp_path / "with-gate.json")
    excluded = {row["path"]: row["reason"]
                for row in result.report["not_examined_entries"]}
    assert "results/gate.json" in excluded, result.report["not_examined_entries"]
    assert "CHECK-04" in excluded["results/gate.json"], excluded


# ---------------------------------------------------------------------------
# The committed fixture and its anti-rot pin
# ---------------------------------------------------------------------------


def test_the_committed_fixture_fails_and_names_both_defects(tmp_path):
    fixture = conftest.broken_fixture(FIXTURE)
    result = run_check(fixture, report=tmp_path / "fixture.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert kinds(result.report) == ["missing-record", "partial-record"], (
        result.report["findings"])
    assert result.report["checked"] == 2, result.report


def test_only_check_06_refuses_the_check_06_fixture(tmp_path):
    """Two defects, both CHECK-06's -- or the fixture stops discriminating."""
    fixture = conftest.broken_fixture(FIXTURE)
    for script in (CHECK_01, CHECK_02, CHECK_03, CHECK_04):
        result = run_check(fixture, report=tmp_path / (script.stem + ".json"),
                           script=script)
        assert result.exit_code == core.EXIT_PASS, (
            "%s also refuses the CHECK-06 fixture, so the fixture no longer "
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
    root = artifact(tmp_path, slug="floor", raw=[])
    strict = run_check(root, "--min-population", "99",
                       report=tmp_path / "strict.json")
    assert "floor=99" in strict.stdout, strict.stdout
    assert strict.report["floor"] == 99, strict.report
    assert strict.exit_code == core.EXIT_DID_NOT_RUN, strict.stdout


def test_a_waiver_suppresses_one_named_finding(tmp_path):
    root = artifact(tmp_path, slug="waived", raw=[])
    contract = check_06.load_contract()
    waived = check_06.run(root, contract.CheckContext(waivers=[{
        "check_id": "CHECK-06",
        "finding_id": "run-record:missing-record:results/figures.json",
        "reason": "the fixture's figures record is deliberately unbacked",
        "dated_at": "2026-09-15T00:00:00-05:00"}]))
    assert waived.waived == 1, waived
    assert waived.found == 0, waived
    assert waived.code == core.EXIT_PASS, waived
