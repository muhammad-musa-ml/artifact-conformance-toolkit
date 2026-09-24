"""CHECK-03 -- an unedited template copy must not pass.

Every test here runs `tools/checks/check_03.py` AS A SUBPROCESS, by path,
through conftest.run_cli, for the same two reasons test_check_01.py does it: by
path under a bare module name is exactly how the vendored copy runs inside an
artifact, and the thing under test is an EXIT CODE, which run_cli returns from
the child rather than from a pipeline stage.

WHAT MAKES THE RED IN red-transcripts/CHECK-03.txt A REAL RED. The module is
registered and RUNNABLE in the commit that captures the transcript, with its
detection stubbed to return no finding. It reads the document, extracts the
region, counts its words and reports a population; only `limits_findings()` is
stubbed. Every failure line in that transcript is therefore an assertion about a
VERDICT, not a module that could not be loaded or an input that was not there.

THE ANTI-PATTERN THIS REPLACES, and it is measured rather than supposed. The
inherited acceptance criterion was a `grep -c` for the heading text. An unedited
template copy passes it: the heading survives every copy untouched. And the
heading is not even stable -- the two artifacts that shipped before this program
existed use two DIFFERENT limitations headings, so a check keyed on either
literal passes one and fails the other. test_the_check_keys_on_the_anchor_not_
the_heading asserts both of those real headings pass, which is the assertion a
heading-keyed check cannot satisfy.

WHAT THIS MODULE CLOSED, AND WHO ASSIGNED IT. an earlier plan open item 6 / deferred item
a known hazard -- CHECK-03 read `README.md` only, and `results/RESULTS.md` shipped the same
limits placeholder unchecked. Its owner line read "the plan that next edits
`tools/checks/check_03.py`". an earlier plan is that plan, under a design rule. The section
near the end of this file carries the tests; the audit trail is here so it sits
beside the assertions rather than only in a summary somebody has to go and find.
"""

import importlib.util
import json
import sys
from pathlib import Path

from tools.tests import conftest
from tools.tests.test_template_generate import (
    LIMITS_PLACEHOLDER_SHA256,
    LIMITS_WORD_FLOOR,
)

REPO_ROOT = conftest.REPO_ROOT
CHECKS_DIR = REPO_ROOT / "tools" / "checks"
CHECK_03 = CHECKS_DIR / "check_03.py"

FIXTURE = "broken-unedited-limits"
EXPECTATION_FILE = "expected-CHECK-03.json"

PINNED_FIELDS = ("check_id", "code", "found", "checked", "finding_ids",
                 "schema_version")

# Every field name that would make the pin sensitive to WORDING. A pin holding
# any of these is the byte-for-byte-over-prose failure wearing a JSON hat.
PROSE_FIELDS = ("note", "notes", "stdout", "stderr", "message", "messages",
                "summary", "detail", "details", "findings", "text", "line",
                "context", "description")


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


core = _load("frozen_core_for_check_03_tests", REPO_ROOT / "tools" / "canonkit.py")
check_03 = _load("check_03_under_test", CHECK_03)


# ---------------------------------------------------------------------------
# Fixture material
# ---------------------------------------------------------------------------

# The two real limitations headings, measured from the artifacts that shipped
# before this program existed. A check keyed on either literal passes one and
# fails the other; both must pass here.
HEADING_A = "## What this benchmark is NOT"
HEADING_B = "## Honest limits on these numbers"

# A filled-in paragraph: over the word floor, carrying scope vocabulary, free of
# the skeleton's marker, and free of numerals so CHECK-01 has nothing to say
# about an artifact this module builds.
FILLED_IN = (
    "This fixture measures nothing real. It does not show throughput, latency\n"
    "under load, or behaviour on any machine other than this one. The population\n"
    "is a hermetic test corpus, so the figures here cannot be compared with a\n"
    "production system and must never be read as a capacity claim.\n"
)

# Over the word floor and clear of the skeleton's marker, but bounding nothing.
# Every sentence is about what WAS measured; none of them says what was not.
NO_SCOPE = (
    "This document reports what the measurement produced and where the numbers\n"
    "came from. Each figure was computed by the derive step from per item\n"
    "records written during the run, and every one of them carries the\n"
    "denominator it was computed over so a reader can weigh it against\n"
    "something.\n"
)

# Under the word floor, but carrying scope vocabulary, so only the thin arm fires.
THIN = "This does not show throughput.\n"

PLACEHOLDER = (
    "TODO(" + "artifact:limits" + "): replace this paragraph before any figure "
    "is published.\nThis placeholder is the skeleton's own text. It is here to "
    "be refused.\n")


def readme(limits=FILLED_IN, heading="## What this does not show",
           include_limits=True, include_regions=True):
    parts = ["# demo-artifact\n", "\n"]
    if include_regions:
        parts += ["<!-- artifact:figures:begin -->\n",
                  "The median was {{figures.median_latency_ms}} ms.\n",
                  "<!-- artifact:figures:end -->\n", "\n"]
    parts += [heading, "\n", "\n"]
    if include_limits:
        parts += ["<!-- artifact:limits:begin -->\n", limits,
                  "<!-- artifact:limits:end -->\n"]
    else:
        parts += ["A paragraph with no region around it at all.\n"]
    parts += ["\n", "Dated: 2026-09-15\n"]
    return "".join(parts)


def artifact(tmp_path, slug="demo-artifact", **kwargs):
    return conftest.tmp_artifact(tmp_path, slug=slug, readme=readme(**kwargs))


def run_check(target, *flags, report=None, cwd=None):
    argv = [sys.executable, str(CHECK_03), str(target)]
    if report is not None:
        argv += ["--report", str(report)]
    argv += [str(flag) for flag in flags]
    return conftest.run_cli(argv, cwd=cwd or REPO_ROOT)


def kinds(report):
    return sorted(finding["kind"] for finding in report["findings"])


# ---------------------------------------------------------------------------
# The five conditions
# ---------------------------------------------------------------------------


def test_an_absent_region_in_a_region_bearing_document_is_a_finding(tmp_path):
    """The document IS addressed by this mechanism and the region was removed."""
    root = artifact(tmp_path, include_limits=False, slug="absent-region")
    result = run_check(root, report=tmp_path / "absent.json")
    assert result.exit_code == core.EXIT_FINDING, (
        "a region-bearing README with no limits region reported exit %d\n%s"
        % (result.exit_code, result.stdout))
    assert "limits:absent:README.md" in result.report["finding_ids"], \
        result.report["finding_ids"]
    assert result.report["checked"] == 1, result.report


def test_a_byte_identical_placeholder_is_a_finding(tmp_path):
    """The condition a heading count cannot see."""
    root = artifact(tmp_path, limits=PLACEHOLDER, slug="unedited")
    result = run_check(root, report=tmp_path / "unedited.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert "limits:unedited:README.md" in result.report["finding_ids"], \
        result.report["finding_ids"]
    assert result.report["body_sha256"] == LIMITS_PLACEHOLDER_SHA256, \
        result.report


def test_a_body_under_the_word_floor_is_a_finding(tmp_path):
    """Thin, and nothing else: it carries scope vocabulary and no marker."""
    root = artifact(tmp_path, limits=THIN, slug="thin")
    result = run_check(root, report=tmp_path / "thin.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert kinds(result.report) == ["thin"], result.report["findings"]
    assert result.report["words"] < result.report["word_floor"], result.report


def test_a_body_with_no_scope_vocabulary_is_a_finding(tmp_path):
    """Long enough, edited, marker-free -- and it bounds nothing."""
    root = artifact(tmp_path, limits=NO_SCOPE, slug="no-scope")
    result = run_check(root, report=tmp_path / "no-scope.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert kinds(result.report) == ["no-scope-vocabulary"], \
        result.report["findings"]
    assert result.report["words"] >= result.report["word_floor"], result.report
    assert result.report["scope_terms"] == [], result.report


def test_a_body_still_carrying_the_skeletons_marker_is_a_finding(tmp_path):
    """Padded past the floor, with scope terms, still saying `replace this`."""
    root = artifact(tmp_path, limits=check_03.SENTINEL + ": " + FILLED_IN,
                    slug="sentinel")
    result = run_check(root, report=tmp_path / "sentinel.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert kinds(result.report) == ["sentinel"], result.report["findings"]


# ---------------------------------------------------------------------------
# "could not look" stays distinct from "found a problem"
# ---------------------------------------------------------------------------


def test_a_document_carrying_no_region_at_all_is_did_not_run(tmp_path):
    """Not a rendered artifact. A finding about a paragraph never read is not
    a finding."""
    root = artifact(tmp_path, include_regions=False, include_limits=False,
                    slug="no-regions")
    result = run_check(root, report=tmp_path / "no-regions.json")
    assert result.exit_code == core.EXIT_DID_NOT_RUN, (
        "a README with no region of any kind reported exit %d\n%s"
        % (result.exit_code, result.stdout))
    assert result.report["checked"] == 0, result.report
    assert core.VERDICT_DID_NOT_RUN in result.stdout, result.stdout


def test_an_absent_readme_is_did_not_run(tmp_path):
    root = Path(tmp_path) / "no-readme"
    (root / "results").mkdir(parents=True)
    result = run_check(root, report=tmp_path / "no-readme.json")
    assert result.exit_code == core.EXIT_DID_NOT_RUN, result.stdout
    assert core.REFUSAL_PREFIX in result.stderr, result.stderr


# ---------------------------------------------------------------------------
# The anchor, not the heading
# ---------------------------------------------------------------------------


def test_the_check_keys_on_the_anchor_not_the_heading(tmp_path):
    """Both REAL headings, measured from the two shipped artifacts, must pass.

    This is the assertion a heading-keyed check cannot satisfy: whichever
    literal it keyed on, one of the two would fail.
    """
    for index, heading in enumerate((HEADING_A, HEADING_B)):
        root = artifact(tmp_path, heading=heading, slug="heading-%d" % index)
        result = run_check(root, report=tmp_path / ("heading-%d.json" % index))
        assert result.exit_code == core.EXIT_PASS, (
            "the heading %r was refused:\n%s" % (heading, result.stdout))
        assert result.report["found"] == 0, result.report


def test_a_filled_in_paragraph_passes(tmp_path):
    """The discriminating counterpart. Without it every finding above is
    equally consistent with a check that refuses everything."""
    root = artifact(tmp_path, slug="filled-in")
    result = run_check(root, report=tmp_path / "filled-in.json")
    assert result.exit_code == core.EXIT_PASS, result.stdout + result.stderr
    assert result.report["found"] == 0, result.report
    assert result.report["checked"] == 1, result.report
    assert result.report["scope_terms"], result.report


# ---------------------------------------------------------------------------
# The committed fixture and the constants it is pinned to
# ---------------------------------------------------------------------------


def test_the_committed_fixture_fails_and_names_every_condition(tmp_path):
    fixture = conftest.broken_fixture(FIXTURE)
    result = run_check(fixture, report=tmp_path / "fixture.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert kinds(result.report) == ["no-scope-vocabulary", "sentinel", "thin",
                                    "unedited"], result.report["findings"]
    assert result.report["found"] == 4, result.report


def test_the_fixture_body_hashes_to_the_constant_plan_01_04_recorded(tmp_path):
    """IMPORTED rather than re-typed, so the two plans cannot drift apart."""
    fixture = conftest.broken_fixture(FIXTURE)
    result = run_check(fixture, report=tmp_path / "fixture.json")
    assert result.report["body_sha256"] == LIMITS_PLACEHOLDER_SHA256, (
        "the fixture's limits body hashes %s; the constant recorded by the plan "
        "that authored the placeholder is %s"
        % (result.report["body_sha256"], LIMITS_PLACEHOLDER_SHA256))


def test_the_module_constant_equals_the_one_the_skeleton_plan_recorded():
    """A vendored copy cannot reach that test module, so the value is restated
    in the check -- and the two are asserted equal HERE, where both exist."""
    assert check_03.LIMITS_PLACEHOLDER_SHA256 == LIMITS_PLACEHOLDER_SHA256
    assert check_03.DEFAULT_WORD_FLOOR == LIMITS_WORD_FLOOR


def test_the_live_skeleton_still_hashes_to_the_committed_constant():
    """The byte comparison, performed against the skeleton's OWN bytes.

    The module hashes a body and compares it to a literal because a vendored
    copy has no templates/ directory to read. This is the arm that keeps that
    literal honest, run in the one place where both files exist.
    """
    live = check_03.skeleton_placeholder_sha256(REPO_ROOT)
    assert live is not None, (
        "no skeleton was reachable from %s, so this comparison ran over nothing"
        % REPO_ROOT)
    assert live == check_03.LIMITS_PLACEHOLDER_SHA256, (
        "the live skeleton's limits body hashes %s; the committed constant is "
        "%s. Update BOTH in the same commit." % (live,
                                                 check_03.LIMITS_PLACEHOLDER_SHA256))


def test_the_scope_vocabulary_is_the_list_the_skeleton_plan_asserted():
    """Widening the list weakens the check, so the two are pinned equal."""
    declared = set(check_03.SCOPE_TERMS)
    asserted = {"not shown", "does not", "excludes", "limited to", "only",
                "cannot", "untested", "unmeasured", "out of scope", "never"}
    assert declared == asserted, (
        "the check's vocabulary is %r; the skeleton plan asserted its "
        "placeholder carries none of %r. A term in one list and not the other "
        "means one of the two stopped checking."
        % (sorted(declared), sorted(asserted)))
    for term, reason in check_03.SCOPE_VOCABULARY:
        assert reason.strip(), "%r carries no reason" % term
    assert len(check_03.SCOPE_TERMS) == check_03.SCOPE_TERM_COUNT == 10


def test_the_fixture_is_named_broken_and_is_never_enumerated():
    scan_root = conftest.SCAN_ROOT
    enumerated = sorted(child.resolve() for child in scan_root.iterdir()
                        if child.is_dir())
    assert enumerated, "enumerated 0 directories under %s" % scan_root
    fixture = conftest.broken_fixture(FIXTURE).resolve()
    assert fixture.name.startswith("broken-"), fixture
    assert fixture not in enumerated, fixture
    assert (fixture / "results" / "figures.json").is_file(), fixture


def test_the_fixtures_only_defect_is_its_limits_paragraph(tmp_path):
    """A fixture that failed several checks at once would stop discriminating."""
    check_01 = CHECKS_DIR / "check_01.py"
    fixture = conftest.broken_fixture(FIXTURE)
    result = conftest.run_cli(
        [sys.executable, str(check_01), str(fixture),
         "--report", str(tmp_path / "c01.json")], cwd=REPO_ROOT)
    assert result.exit_code == core.EXIT_PASS, (
        "the CHECK-03 fixture also fails CHECK-01, so a test asserting 'the "
        "checker refused it' would not say which check did the refusing:\n%s"
        % result.stdout)


# ---------------------------------------------------------------------------
# a design rule -- both floors, both overridable, both printed
# ---------------------------------------------------------------------------


def test_the_population_floor_override_prints(tmp_path):
    root = artifact(tmp_path, slug="floor-override")
    result = run_check(root, "--min-population", "99",
                       report=tmp_path / "floor.json")
    assert "floor=99" in result.stdout, result.stdout
    assert result.report["floor"] == 99, result.report
    assert result.exit_code == core.EXIT_DID_NOT_RUN, result.stdout
    assert "DEMOTED" in result.stdout, result.stdout


def test_the_word_floor_override_is_effective_and_prints(tmp_path):
    """The EFFECTIVE value prints, or the line lies about what it applied."""
    root = artifact(tmp_path, limits=THIN, slug="word-floor")
    lenient = run_check(root, "--word-floor", "3",
                        report=tmp_path / "lenient.json")
    assert "words=5 of 3" in lenient.stdout, lenient.stdout
    assert lenient.report["word_floor"] == 3, lenient.report
    assert "thin" not in kinds(lenient.report), lenient.report["findings"]

    strict = run_check(root, "--word-floor", "500",
                       report=tmp_path / "strict.json")
    assert "words=5 of 500" in strict.stdout, strict.stdout
    assert "thin" in kinds(strict.report), strict.report["findings"]


# ---------------------------------------------------------------------------
# Waivers, and the anti-rot pin
# ---------------------------------------------------------------------------


def test_a_waiver_suppresses_one_named_finding(tmp_path):
    """The waiver is honoured by the CHECK; whether it was COMMITTED is the
    runner's question, and the two are deliberately separate."""
    root = artifact(tmp_path, limits=THIN, slug="waived")
    contract = check_03.load_contract()
    waived = check_03.run(root, contract.CheckContext(waivers=[{
        "check_id": "CHECK-03", "finding_id": "limits:thin:README.md",
        "reason": "the fixture is deliberately short",
        "dated_at": "2026-09-15T00:00:00+03:00"}]))
    assert waived.waived == 1, waived
    assert waived.found == 0, waived
    assert waived.code == core.EXIT_PASS, waived


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
    path = conftest.broken_fixture(FIXTURE) / EXPECTATION_FILE
    expectation = json.loads(path.read_text(encoding="ascii"))
    keys = set(expectation)
    assert keys == set(PINNED_FIELDS), (
        "%s pins %r; the six stable fields are %r"
        % (FIXTURE, sorted(keys), sorted(PINNED_FIELDS)))
    leaked = sorted(keys & set(PROSE_FIELDS))
    assert not leaked, (
        "%s pins wording-bearing field(s) %r -- an error-message improvement "
        "would then break this pin, and the standard repair is to weaken it"
        % (FIXTURE, leaked))


# ---------------------------------------------------------------------------
# The module contract
# ---------------------------------------------------------------------------


def test_the_module_satisfies_the_check_protocol():
    assert check_03.CHECK_ID == "CHECK-03"
    assert isinstance(check_03.DEFAULT_FLOOR, int)
    assert callable(check_03.run)

    contract = check_03.load_contract()
    assert check_03.CHECK_ID in contract.DECLARED_CHECK_IDS
    discovered = contract.discover(CHECKS_DIR, verbose=False)
    assert "CHECK-03" in discovered.ids, discovered.ids
    assert not discovered.protocol_violations, discovered.protocol_violations


def test_the_two_floors_are_different_numbers_with_different_jobs():
    """Collapsing them would demote every run: a population of one document is
    always below a word floor of forty."""
    assert check_03.DEFAULT_FLOOR != check_03.DEFAULT_WORD_FLOOR
    assert check_03.DEFAULT_FLOOR == 1
    assert check_03.DEFAULT_WORD_FLOOR == 40


# ---------------------------------------------------------------------------
# an earlier plan / a design rule -- CHECK-03 SCANS BOTH DOCUMENTS (an earlier plan open item 6)
#
# The gap, in an earlier plan's own words: the check reads `README.md` only, and
# `results/RESULTS.md` ships the SAME limits placeholder unchecked. The round
# trip masks it -- it fills the RESULTS region as a real author would -- so the
# gap is unreachable from the walking skeleton and fully reachable from a
# hand-authored artifact, which is exactly what both of this phase's artifacts
# are.
#
# The shape is copied from check_09, which already scans the same two documents
# through a SCANNED_DOCUMENTS tuple and a read_documents() loop, and prints
# `documents=N of M`. Two checks disagreeing about which documents an artifact
# has is the kind of split that produces a confident verdict over half a tree.
# ---------------------------------------------------------------------------


RESULTS_RELATIVE = "results/RESULTS.md"


def _write_results(target, body, heading="## What this does not show"):
    """Write results/RESULTS.md carrying a limits region with `body`."""
    path = Path(target) / "results" / "RESULTS.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join([
        "# demo-artifact results" + chr(10), chr(10),
        heading, chr(10), chr(10),
        "<!-- artifact:limits:begin -->" + chr(10),
        body,
        "<!-- artifact:limits:end -->" + chr(10),
    ])
    path.write_text(text, encoding="utf-8", newline=chr(10))
    return path


def test_an_unedited_placeholder_in_results_is_a_finding(tmp_path):
    """an earlier plan item 6, in one test.

    The README is filled in correctly and RESULTS.md carries the skeleton's
    byte-identical placeholder. Today the check reads only the README and
    reports PASS, so the placeholder ships.
    """
    target = artifact(tmp_path)
    _write_results(target, PLACEHOLDER)
    result = run_check(target, report=tmp_path / "results-placeholder.json")
    assert result.exit_code == core.EXIT_FINDING, (
        "the unedited placeholder in %s was not examined" % RESULTS_RELATIVE)
    report = result.report
    assert any(finding.get("document", "").endswith("RESULTS.md")
               for finding in report["findings"]), report["findings"]


def test_both_documents_filled_passes_and_says_it_scanned_two(tmp_path):
    """The population travels into the note; a scan nobody counted is a claim."""
    target = artifact(tmp_path)
    _write_results(target, FILLED_IN)
    result = run_check(target, report=tmp_path / "both.json")
    assert result.exit_code == core.EXIT_PASS, result.stdout + result.stderr
    assert "documents=2 of 2" in result.report["note"], result.report["note"]


def test_only_a_readme_is_examined_rather_than_refused(tmp_path):
    """An OPTIONAL document that is absent is absent, not a refusal.

    RESULTS.md is not required -- plenty of artifacts will not carry one -- so
    its absence must not turn a real examination into a DID-NOT-RUN. What it
    must do is show in the count, so a reader can tell a 1-document scan from a
    2-document one.
    """
    target = artifact(tmp_path)
    result = run_check(target, report=tmp_path / "readme-only.json")
    assert result.exit_code == core.EXIT_PASS, result.stdout + result.stderr
    assert "documents=1 of 2" in result.report["note"], result.report["note"]


def test_an_absent_readme_refuses_even_when_results_is_present_and_correct(tmp_path):
    """The REQUIRED document is required, and a correct optional one is not a
    substitute for it. Otherwise an artifact could delete its README and pass."""
    target = conftest.tmp_artifact(tmp_path, slug="demo-artifact",
                                   readme=readme())
    _write_results(target, FILLED_IN)
    (Path(target) / "README.md").unlink()
    result = run_check(target, report=tmp_path / "no-readme.json")
    assert result.exit_code == core.EXIT_DID_NOT_RUN, (
        result.stdout + result.stderr)
    assert "REPAIR:" in (result.stdout + result.stderr), (
        result.stdout + result.stderr)


def test_a_non_utf8_scanned_document_refuses_rather_than_being_dropped(tmp_path):
    """A document that cannot be read is not a document with nothing in it.

    Dropped silently it would shrink the population with no error, which is the
    smaller-population-with-no-error shape this programme refuses everywhere.
    """
    target = artifact(tmp_path)
    path = Path(target) / "results" / "RESULTS.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"# results\n\xff\xfe not utf-8 at all\n")
    result = run_check(target, report=tmp_path / "bad-bytes.json")
    assert result.exit_code == core.EXIT_DID_NOT_RUN, (
        result.stdout + result.stderr)


def test_every_refusal_branch_still_carries_its_document_count(tmp_path):
    """The conventions document, section 2: ONE line on EVERY branch, count WITH verdict.

    FOUND 2026-09-17, while running this plan's task 3 over the two artifacts
    this phase owns. The earlier step change carried `documents=N of M` into the PASS
    and FINDING notes and left the three DID-NOT-RUN notes without it -- and a
    DID-NOT-RUN is the branch BOTH artifacts currently land on, because neither
    README carries an `artifact:` region yet. So the one line a reader of this
    phase actually sees was the one line with no population on it.

    All three refusal branches are asserted, not one: a fix applied to the
    branch that happened to be measured is a fix that leaves two behind.
    """
    cases = {}

    # 1. No README at all, with a correct optional document beside it.
    no_readme = conftest.tmp_artifact(tmp_path, slug="no-readme",
                                      readme=readme())
    _write_results(no_readme, FILLED_IN)
    (Path(no_readme) / "README.md").unlink()
    cases["absent required document"] = run_check(
        no_readme, report=tmp_path / "branch-no-readme.json")

    # 2. A README that carries no artifact: region of any kind. This is the
    #    shape both of this programme's existing artifacts are in.
    region_free = conftest.tmp_artifact(
        tmp_path, slug="region-free",
        readme="# region-free" + chr(10) * 2 + "Prose and nothing else." + chr(10))
    cases["no region-bearing document"] = run_check(
        region_free, report=tmp_path / "branch-region-free.json")

    # 3. A scanned document that is not valid UTF-8.
    bad_bytes = artifact(tmp_path, slug="bad-bytes")
    bad = Path(bad_bytes) / "results" / "RESULTS.md"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b"# results\n\xff\xfe not utf-8 at all\n")
    cases["unreadable document"] = run_check(
        bad_bytes, report=tmp_path / "branch-bad-bytes.json")

    assert len(cases) == 3, (
        "only %d refusal branch(es) were built; a loop over fewer than the "
        "branches that exist proves nothing about the ones it skipped"
        % len(cases))

    for label, result in sorted(cases.items()):
        assert result.exit_code == core.EXIT_DID_NOT_RUN, (
            "%s: expected a refusal, got exit %d\n%s"
            % (label, result.exit_code, result.stdout))
        note = result.report["note"]
        assert "documents=0 of 2" in note, (
            "%s: the refusal note carries no document count, so the one line "
            "this branch prints says nothing about its population: %r"
            % (label, note))
        assert result.report["documents_declared"] == 2, (
            "%s: %r" % (label, result.report))
        assert result.report["documents_scanned"] == 0, (
            "%s: %r" % (label, result.report))
        assert "documents=0 of 2" in result.stdout, (
            "%s: the count reached the report and not the PRINTED line, which "
            "is the half a reader sees:\n%s" % (label, result.stdout))


def test_the_scalar_document_constant_is_gone_not_shadowed(tmp_path):
    """The shape change is real rather than a tuple laid beside a live scalar.

    Two sources of truth for `which documents do we scan` is the split this
    change exists to close, so the old one must not survive as a fallback.
    """
    source = CHECK_03.read_text(encoding="ascii")
    assert "SCANNED_DOCUMENTS" in source, source[:200]
    scalar = [line for line in source.splitlines()
              if line.startswith("DOCUMENT = ")]
    assert not scalar, (
        "the scalar DOCUMENT constant is still live: %r" % scalar)
