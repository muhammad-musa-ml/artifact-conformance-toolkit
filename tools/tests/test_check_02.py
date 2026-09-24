"""CHECK-02 -- the README's date must be a date a MACHINE wrote.

Every test here runs `tools/checks/check_02.py` AS A SUBPROCESS, by path,
through conftest.run_cli, for the two reasons test_check_01.py and
test_check_03.py both record: by path under a bare module name is exactly how
the vendored copy runs inside an artifact, and the thing under test is an EXIT
CODE, which run_cli returns from the CHILD rather than from a pipeline stage.

WHAT MAKES THE RED IN red-transcripts/CHECK-02.txt A REAL RED. The module is
registered and RUNNABLE in the commit that captures the transcript, with
`date_findings()` -- and only that -- stubbed to return no finding. It walks
results/, parses every machine stamp, locates the artifact:date region, extracts
the date, counts the local-versus-UTC divergences and prints a real population.
Every failure line in that transcript is therefore an assertion about a VERDICT,
not a module that could not be loaded or an input that was not there.

THE ASSERTION THIS SUITE IS BUILT AROUND, and it is the one a weaker check
cannot satisfy: `test_the_comparison_is_against_the_local_date_not_the_utc_one`.
Both stored stamps are present, both are well formed, both are genuinely
machine-written, and they name DIFFERENT DAYS. A check that compared against
`started_at_utc` would pass the tree this suite expects it to refuse and refuse
the tree it expects it to pass. Measured on this machine while the check was
written: local 2026-09-15T19:57:50-05:00, UTC 2026-09-16T00:57:50+00:00, one
instant, two dates.
"""

import importlib.util
import json
import sys
from pathlib import Path

from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT
CHECKS_DIR = REPO_ROOT / "tools" / "checks"
CHECK_02 = CHECKS_DIR / "check_02.py"
CHECK_01 = CHECKS_DIR / "check_01.py"
CHECK_03 = CHECKS_DIR / "check_03.py"

FIXTURE = "broken-readme-date-mismatch"
EXPECTATION_FILE = "expected-CHECK-02.json"

PINNED_FIELDS = ("check_id", "code", "found", "checked", "finding_ids",
                 "schema_version")

# Every field name that would make the pin sensitive to WORDING. A pin holding
# any of these is the byte-for-byte-over-prose failure wearing a JSON hat.
PROSE_FIELDS = ("note", "notes", "stdout", "stderr", "message", "messages",
                "summary", "detail", "details", "findings", "text", "line",
                "context", "description", "not_examined_entries")


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


core = _load("frozen_core_for_check_02_tests", REPO_ROOT / "tools" / "canonkit.py")
checks = _load("check_contract_for_check_02_tests", CHECKS_DIR / "__init__.py")
check_02 = _load("check_02_under_test", CHECK_02)


# ---------------------------------------------------------------------------
# Fixture material
#
# THE TWO STAMPS BELOW NAME DIFFERENT DAYS ON PURPOSE. Half past ten at night on
# the fifteenth, at an offset of minus five, is half past three in the morning on
# the SIXTEENTH in UTC. Every test that turns on which field the check reads uses
# this pair.
# ---------------------------------------------------------------------------

LOCAL_STAMP = "2026-09-15T22:30:00-05:00"
UTC_STAMP = "2026-09-16T03:30:00+00:00"
LOCAL_DATE = "2026-09-15"
UTC_DATE = "2026-09-16"

GATE_TOKEN = "2" * 64

# A limits paragraph that clears CHECK-03's word floor, carries its scope
# vocabulary and holds no numeral, so an artifact built here is refused by
# CHECK-02 and by nothing else.
LIMITS_BODY = (
    "This fixture measures nothing real. It does not show throughput, latency\n"
    "under load, or behaviour on any machine other than this one. The population\n"
    "is a hermetic test corpus, so the figures here cannot be compared with a\n"
    "production system and must never be read as a capacity claim.\n"
)


def readme(date_text=LOCAL_DATE, include_date_region=True,
           include_regions=True, date_body=None):
    """`date_body`, when given, IS the region body, verbatim.

    That exists so a test can reproduce the form render.py actually writes --
    a key hole carrying a full timestamp -- rather than only the prose form a
    test author would think to type.
    """
    parts = ["# demo-artifact\n", "\n"]
    if include_regions:
        parts += ["<!-- artifact:figures:begin -->\n",
                  "The median was {{figures.median_latency_ms}} ms.\n",
                  "<!-- artifact:figures:end -->\n", "\n"]
    if include_date_region:
        parts += ["<!-- artifact:date:begin -->\n"]
        if date_body is not None:
            parts += [date_body if date_body.endswith("\n")
                      else date_body + "\n"]
        elif date_text:
            parts += ["Measured %s on the owner's own machine.\n" % date_text]
        else:
            parts += ["Measured on the owner's own machine.\n"]
        parts += ["<!-- artifact:date:end -->\n", "\n"]
    parts += ["## What this does not show\n", "\n",
              "<!-- artifact:limits:begin -->\n", LIMITS_BODY,
              "<!-- artifact:limits:end -->\n"]
    return "".join(parts)


def figures_record(slug="demo-artifact", started_at=LOCAL_STAMP,
                   started_at_utc=UTC_STAMP):
    figure = {
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
        "value": 12.5,
    }
    record = {
        "artifact": slug,
        "dated_at": LOCAL_DATE,
        "figures": {"median_latency_ms": figure},
        "gate_token": GATE_TOKEN,
        "schema": "canonkit/figures/1",
        "schema_version": "canonkit/1",
    }
    if started_at is not None:
        record["started_at"] = started_at
    if started_at_utc is not None:
        record["started_at_utc"] = started_at_utc
    return record


def artifact(tmp_path, slug="demo-artifact", figures=True, **readme_kwargs):
    """A hermetic artifact whose ONLY variable is its date and its stamps."""
    started_at = readme_kwargs.pop("started_at", LOCAL_STAMP)
    started_at_utc = readme_kwargs.pop("started_at_utc", UTC_STAMP)
    record = (figures_record(slug=slug, started_at=started_at,
                             started_at_utc=started_at_utc)
              if figures else None)
    return conftest.tmp_artifact(tmp_path, slug=slug,
                                 readme=readme(**readme_kwargs),
                                 figures=record)


def run_check(target, *flags, report=None, cwd=None, script=CHECK_02):
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
    """Adding check_NN.py is the whole registration step (an earlier plan)."""
    assert check_02.CHECK_ID == "CHECK-02"
    assert isinstance(check_02.DEFAULT_FLOOR, int)
    assert callable(check_02.run)

    report = checks.discover(CHECKS_DIR, verbose=False)
    assert "CHECK-02" in report.ids, report.ids
    assert not report.protocol_violations, report.protocol_violations


# ---------------------------------------------------------------------------
# The two branches
# ---------------------------------------------------------------------------


def test_a_date_equal_to_the_local_component_of_a_machine_stamp_passes(tmp_path):
    root = artifact(tmp_path, date_text=LOCAL_DATE, slug="agrees")
    result = run_check(root, report=tmp_path / "agrees.json")
    assert result.exit_code == core.EXIT_PASS, result.stdout
    assert result.report["found"] == 0, result.report
    assert result.report["checked"] >= 1, result.report


def test_a_date_that_disagrees_with_a_machine_stamp_is_a_finding(tmp_path):
    root = artifact(tmp_path, date_text="2026-01-01", slug="disagrees")
    result = run_check(root, report=tmp_path / "disagrees.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert kinds(result.report) == ["disagrees"], result.report["findings"]
    assert result.report["found"] == 1, result.report


def test_an_absent_date_region_is_a_finding(tmp_path):
    """A machine recorded a date and the document does not carry it."""
    root = artifact(tmp_path, include_date_region=False, slug="no-region")
    result = run_check(root, report=tmp_path / "no-region.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert kinds(result.report) == ["absent"], result.report["findings"]


def test_a_region_with_no_iso_date_is_a_finding(tmp_path):
    """The region is present and says nothing this check can compare."""
    root = artifact(tmp_path, date_text="", slug="no-date")
    result = run_check(root, report=tmp_path / "no-date.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert kinds(result.report) == ["absent"], result.report["findings"]


def test_a_malformed_date_in_the_region_is_absent_rather_than_a_crash(tmp_path):
    """2026-13-45 is well shaped and names no day. It is not a date."""
    root = artifact(tmp_path, date_text="2026-13-45", slug="malformed")
    result = run_check(root, report=tmp_path / "malformed.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert kinds(result.report) == ["absent"], result.report["findings"]


def test_a_rendered_key_hole_carrying_a_full_timestamp_is_read(tmp_path):
    """The form render.py ACTUALLY writes -- and the one that was missed.

    REGRESSION. The first ISO_DATE_RE ended in `\\b`, with a comment claiming it
    found the date component of a full timestamp. It did not: the character
    after the day is `T`, a WORD character, so no boundary exists there. Since
    render.py writes a region body as a key hole, the walking skeleton's own
    README -- the GENERATED artifact every path produces -- reported
    `readme-date=ABSENT` with its date sitting in plain sight. Every test in
    this suite passed while that was true, because all of them typed a bare
    date into prose, which is the one form the expression could read.
    """
    hole = ("<!--artifact:key:dated_at-->2026-09-15T20:08:11.856801-05:00"
            "<!--/artifact:key-->")
    agreeing = run_check(artifact(tmp_path, date_body=hole, slug="rendered"),
                         report=tmp_path / "rendered.json")
    assert agreeing.report["readme_date"] == LOCAL_DATE, (
        "the rendered key hole was not read as a date: %r" % agreeing.report)
    assert agreeing.exit_code == core.EXIT_PASS, agreeing.stdout

    # And the same form still DISAGREES when it should: the fix widened what the
    # check can read, not what it accepts.
    utc_hole = ("<!--artifact:key:dated_at-->2026-09-16T01:08:11.856801+00:00"
                "<!--/artifact:key-->")
    diverging = run_check(artifact(tmp_path, date_body=utc_hole,
                                   slug="rendered-utc"),
                          report=tmp_path / "rendered-utc.json")
    assert diverging.exit_code == core.EXIT_FINDING, diverging.stdout
    assert kinds(diverging.report) == ["disagrees"], diverging.report["findings"]


def test_a_longer_number_is_not_mistaken_for_a_date(tmp_path):
    """The lookahead must still refuse what the word boundary refused."""
    root = artifact(tmp_path, date_body="ref 2026-09-155 is not a day.",
                    slug="too-long")
    result = run_check(root, report=tmp_path / "too-long.json")
    assert result.report["readme_date"] == "", result.report
    assert kinds(result.report) == ["absent"], result.report["findings"]


def test_the_absent_and_disagreeing_branches_produce_different_finding_ids(tmp_path):
    """Collapsing them would name the problem without naming the repair."""
    absent = run_check(artifact(tmp_path, include_date_region=False,
                                slug="absent-ids"),
                       report=tmp_path / "absent-ids.json")
    disagrees = run_check(artifact(tmp_path, date_text="2026-01-01",
                                   slug="disagree-ids"),
                          report=tmp_path / "disagree-ids.json")

    absent_ids = absent.report["finding_ids"]
    disagree_ids = disagrees.report["finding_ids"]
    assert absent_ids, absent.report
    assert disagree_ids, disagrees.report
    assert not set(absent_ids) & set(disagree_ids), (
        "the two branches share a finding id, so a reader cannot tell which "
        "one fired: %r vs %r" % (absent_ids, disagree_ids))


# ---------------------------------------------------------------------------
# LOCAL versus UTC -- the assertion a weaker check cannot satisfy
# ---------------------------------------------------------------------------


def test_the_comparison_is_against_the_local_date_not_the_utc_one(tmp_path):
    """One instant, two dates. Which field the check reads IS the check.

    A check comparing against started_at_utc would invert both assertions
    below: it would pass the tree carrying the UTC date and refuse the tree
    carrying the local one.
    """
    local = run_check(artifact(tmp_path, date_text=LOCAL_DATE, slug="local-date"),
                      report=tmp_path / "local.json")
    assert local.exit_code == core.EXIT_PASS, (
        "the LOCAL date was refused, so the check is not comparing against "
        "started_at\n%s" % local.stdout)

    utc = run_check(artifact(tmp_path, date_text=UTC_DATE, slug="utc-date"),
                    report=tmp_path / "utc.json")
    assert utc.exit_code == core.EXIT_FINDING, (
        "the UTC date PASSED, so the check is comparing against "
        "started_at_utc rather than started_at\n%s" % utc.stdout)
    assert kinds(utc.report) == ["disagrees"], utc.report["findings"]


def test_the_divergence_between_local_and_utc_is_counted_in_the_note(tmp_path):
    """A legitimate difference is still worth printing."""
    diverging = run_check(artifact(tmp_path, date_text=LOCAL_DATE,
                                   slug="diverging"),
                          report=tmp_path / "diverging.json")
    assert "utc-date-differs=1" in diverging.stdout, diverging.stdout
    assert diverging.report["utc_date_differs"] == 1, diverging.report

    same_day = run_check(
        artifact(tmp_path, date_text=LOCAL_DATE, slug="same-day",
                 started_at="2026-09-15T09:00:00-05:00",
                 started_at_utc="2026-09-15T14:00:00+00:00"),
        report=tmp_path / "same-day.json")
    assert "utc-date-differs=0" in same_day.stdout, same_day.stdout
    assert same_day.report["utc_date_differs"] == 0, same_day.report


# ---------------------------------------------------------------------------
# Could not look
# ---------------------------------------------------------------------------


def test_the_zero_input_fixture_is_did_not_run_and_is_neither_pass_nor_finding(
        tmp_path):
    """No date region AND no machine stamp: "could not look", not "clean"."""
    root = artifact(tmp_path, figures=False, include_date_region=False,
                    slug="zero-input")
    result = run_check(root, report=tmp_path / "zero.json")

    assert result.exit_code == core.EXIT_DID_NOT_RUN, result.stdout
    assert result.exit_code != core.EXIT_PASS, (
        "a check that examined nothing reported a PASS: %s" % result.stdout)
    assert result.exit_code != core.EXIT_FINDING, (
        "a check that examined nothing reported a FINDING, which claims it "
        "looked: %s" % result.stdout)
    assert result.report["checked"] == 0, result.report

    # The banned word is banned as a VERDICT, and canonkit.report prints
    # `not_examined=N` as a legitimate COUNT label on the same line. A substring
    # test over the whole line cannot tell those apart -- it would fail on a
    # correct run -- so this reads the verdict COLUMN.
    line = next(row for row in result.stdout.splitlines()
                if row.startswith("CHECK-02"))
    verdict = line.split()[1]
    assert verdict == core.VERDICT_DID_NOT_RUN, line
    assert verdict.lower() != core.BANNED_VERDICT, (
        "the verdict column reads the banned word: %s" % line)


def test_a_gate_json_is_not_a_machine_measurement_and_the_exclusion_is_counted(
        tmp_path):
    """conftest's default gate carries a started_at. It is still not a run.

    Without the exclusion this artifact would have a machine side supplied by
    the gate record, and a README date agreeing with the gate's clock would
    report a clean run over an artifact that measured nothing.
    """
    root = artifact(tmp_path, figures=False, slug="gate-only")
    gate = root / "results" / "gate.json"
    assert gate.is_file(), "conftest stopped writing a default gate.json"
    assert "started_at" in json.loads(gate.read_text(encoding="utf-8")), (
        "conftest's default gate no longer carries a started_at, so this test "
        "no longer discriminates anything")

    result = run_check(root, report=tmp_path / "gate-only.json")
    assert result.exit_code == core.EXIT_DID_NOT_RUN, result.stdout

    excluded = [row["path"] for row in result.report["not_examined_entries"]]
    assert "results/gate.json" in excluded, result.report["not_examined_entries"]
    assert result.report["not_examined"] >= 1, result.report


def test_per_item_records_are_excluded_and_counted(tmp_path):
    """runmeta keeps items apart so a glob over runs does not count them."""
    root = artifact(tmp_path, slug="with-items")
    items = root / "results" / "raw" / "items"
    items.mkdir(parents=True, exist_ok=True)
    (items / "item-0000.json").write_text(
        json.dumps({"item_id": "item-0000", "latency_ms": 10.0}) + "\n",
        encoding="ascii", newline="\n")

    result = run_check(root, report=tmp_path / "items.json")
    excluded = [row["path"] for row in result.report["not_examined_entries"]]
    assert "results/raw/items/item-0000.json" in excluded, (
        result.report["not_examined_entries"])
    assert result.report["checked"] == 1, (
        "a per-item record entered the population: %r" % result.report)


# ---------------------------------------------------------------------------
# The committed fixture and its anti-rot pin
# ---------------------------------------------------------------------------


def test_the_committed_fixture_fails_and_names_every_disagreeing_file(tmp_path):
    fixture = conftest.broken_fixture(FIXTURE)
    result = run_check(fixture, report=tmp_path / "fixture.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert kinds(result.report) == ["disagrees", "disagrees"], (
        result.report["findings"])
    assert result.report["finding_ids"] == [
        "date:disagrees:results/figures.json",
        "date:disagrees:results/raw/run-0001.json"], result.report
    assert result.report["utc_date_differs"] == 2, (
        "the fixture's two stamps were built to straddle midnight in UTC; the "
        "check no longer notices: %r" % result.report)


def test_only_check_02_refuses_the_check_02_fixture(tmp_path):
    """One fixture, one defect -- or "the checker refused it" says nothing."""
    fixture = conftest.broken_fixture(FIXTURE)
    for script in (CHECK_01, CHECK_03):
        result = run_check(fixture, report=tmp_path / (script.stem + ".json"),
                           script=script)
        assert result.exit_code == core.EXIT_PASS, (
            "%s also refuses the CHECK-02 fixture, so the fixture no longer "
            "discriminates:\n%s" % (script.name, result.stdout))


def test_the_anti_rot_pin_holds_for_the_known_bad_fixture(tmp_path):
    """a design rule's second half: the evidence must not rot while the checker drifts."""
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
    """Inspect the COMMITTED key set, not the comparison that reads it."""
    fixture = conftest.broken_fixture(FIXTURE)
    expected = json.loads((fixture / EXPECTATION_FILE).read_text(encoding="ascii"))
    assert set(expected) == set(PINNED_FIELDS), (
        "the expectation holds %r; the pinned set is %r"
        % (sorted(expected), sorted(PINNED_FIELDS)))
    leaked = sorted(set(expected) & set(PROSE_FIELDS))
    assert not leaked, (
        "the pin holds wording-bearing field(s) %r, so the first message "
        "improvement breaks it" % leaked)


# ---------------------------------------------------------------------------
# a design rule and a design rule
# ---------------------------------------------------------------------------


def test_the_population_floor_override_is_effective_and_prints(tmp_path):
    """The EFFECTIVE value prints, or the line lies about what it applied."""
    root = artifact(tmp_path, date_text="2026-01-01", slug="floor")
    strict = run_check(root, "--min-population", "99",
                       report=tmp_path / "strict.json")
    assert "floor=99" in strict.stdout, strict.stdout
    assert strict.report["floor"] == 99, strict.report
    assert strict.exit_code == core.EXIT_DID_NOT_RUN, (
        "a population below the effective floor was not demoted:\n%s"
        % strict.stdout)


def test_a_waiver_suppresses_one_named_finding(tmp_path):
    """The waiver is honoured by the CHECK; whether it was COMMITTED is the
    runner's question, and the two are deliberately separate."""
    root = artifact(tmp_path, date_text="2026-01-01", slug="waived")
    contract = check_02.load_contract()
    waived = check_02.run(root, contract.CheckContext(waivers=[{
        "check_id": "CHECK-02",
        "finding_id": "date:disagrees:results/figures.json",
        "reason": "the fixture's date is deliberately wrong",
        "dated_at": "2026-09-15T00:00:00-05:00"}]))
    assert waived.waived == 1, waived
    assert waived.found == 0, waived
    assert waived.code == core.EXIT_PASS, waived
