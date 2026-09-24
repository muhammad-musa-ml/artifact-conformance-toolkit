"""The conformance runner: populations, the report, the census and its identities.

Every test here runs `tools/conformance.py` AS A SUBPROCESS, by path, through
conftest.run_cli, for the same two reasons test_check_01.py does it:

  * by path, under a bare module name, is exactly how the vendored copy is run
    inside an artifact. A test that imported it as a dotted package module would
    exercise a code path no artifact ever takes, and a repository guard forbids
    that spelling outright.
  * the thing under test is an EXIT CODE, and run_cli returns the CHILD's own
    return code, so a lost status is structurally impossible here.

A few pure helpers are also exercised in-process. Those are loaded with
spec_from_file_location, which is the load mechanism the split mandates and is
deliberately not one of the two calls the repository's import guard flags.

WHAT THE RED TRANSCRIPTS THIS MODULE FEEDS ARE ABOUT. The runner is REGISTERED
AND RUNNABLE in the commit that captures them, with five named stub points -- the
waiver round trip, the printed waiver count, the zero-population normalization,
the empty-scan verdict and CHECK-11's detection. Every failure line in those
transcripts is therefore an assertion about a VERDICT produced by a runner that
really ran, over inputs that really exist.
"""

import contextlib
import importlib.util
import io
import json
import sys
from pathlib import Path

from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT
CONFORMANCE = REPO_ROOT / "tools" / "conformance.py"
CHECKS_DIR = REPO_ROOT / "tools" / "checks"
MANIFEST = REPO_ROOT / "tools" / "manifest.json"


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


core = _load("frozen_core_for_conformance_tests", REPO_ROOT / "tools" / "canonkit.py")
conformance = _load("conformance_under_test", CONFORMANCE)
checks = _load("check_contract_for_conformance_tests", CHECKS_DIR / "__init__.py")

# an earlier plan open item 12, CLOSED here.
#
# `conftest.REPO_ROOT` is the WORKING root -- the checkout this file happens to
# be read from. Inside an agent worktree that is `<repo>/agent-worktrees/worktrees/<id>`,
# whose parent is `agent-worktrees/worktrees` and NOT `<home>/Research`. Every assertion
# about the SCAN ROOT anchors on the MAIN checkout instead, because that is the
# root the manifest's `..` is declared relative to and it is already how
# `conftest.SCAN_ROOT` resolves.
#
# The cost of getting this wrong was measured twice: from the main checkout the
# two anchors coincide, so a scan-root test written against the working root
# reported GREEN over the right population by accident; from a worktree the same
# tests enumerated `agent-worktrees/worktrees` and failed. The conventions document, section 8,
# rule 8 is the rule -- derive such an anchor from a main_repo_root() that walks
# a worktree's `.git` FILE back to the checkout it was linked from, and compare
# by PATH RESOLUTION rather than by string equality.
MAIN_REPO_ROOT = Path(conformance.main_repo_root()).resolve()


# ---------------------------------------------------------------------------
# Fixture material
# ---------------------------------------------------------------------------

# A limits paragraph that CLEARS the word floor and carries scope vocabulary, so
# these artifacts stay green once CHECK-03 lands in the next task of this plan.
# Deliberately free of numerals: CHECK-01 lints every numeral in the document,
# and a hand-typed number here would make a test about waivers fail for a reason
# having nothing to do with waivers.
LIMITS_BODY = (
    "This fixture measures nothing real. It does not show throughput, latency\n"
    "under load, or behaviour on any machine other than this one. The population\n"
    "is a hermetic test corpus, so the figures here cannot be compared with a\n"
    "production system and must never be read as a capacity claim.\n"
)

README = (
    "# demo-artifact\n"
    "\n"
    "<!-- artifact:figures:begin -->\n"
    "The median was {{figures.median_latency_ms}} ms.\n"
    "<!-- artifact:figures:end -->\n"
    "\n"
    "## What this does not show\n"
    "\n"
    "<!-- artifact:limits:begin -->\n"
    + LIMITS_BODY +
    "<!-- artifact:limits:end -->\n"
    "\n"
    "Dated: 2026-09-15\n"
)

EMPTY_WAIVERS = {
    "schema": "canonkit/waivers/1",
    "schema_version": "canonkit/1",
    "rule": "OWNER-AUTHORED ONLY.",
    "waivers": [],
}


def figures_record(slug="demo-artifact", population=500):
    """A well-formed figures record. `population=None` drops the denominator."""
    figure = {
        "value": 12.5,
        "unit": "ms",
        "population_label": "replayed requests",
    }
    if population is not None:
        figure["population"] = population
    return {
        "schema": "canonkit/figures/1",
        "schema_version": "canonkit/1",
        "artifact": slug,
        "dated_at": "2026-09-15",
        "figures": {"median_latency_ms": figure},
    }


def artifact(tmp_path, slug="demo-artifact", population=500, waivers=EMPTY_WAIVERS,
             readme=README):
    """A hermetic artifact that PASSES every check implemented at this wave."""
    root = conftest.tmp_artifact(
        tmp_path, slug=slug, readme=readme,
        figures=figures_record(slug=slug, population=population))
    if waivers is not None:
        write_json(root / "waivers.json", waivers)
    return root


def write_json(path, payload):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                          encoding="ascii", newline="\n")
    return Path(path)


def synthetic_manifest(path, slugs, depth=1):
    """An expected set written for ONE test, so a synthetic scan is closed.

    `slugs` is a list of (slug, status) pairs. Written rather than derived from
    the real manifest, because a test that mutated the committed expected set
    would be editing an owner/plan-set file a build agent may never write.
    """
    return write_json(path, {
        "schema": "manifest/1",
        "schema_version": 1,
        "scan_root": {"relative_to_repo_root": "..", "depth": depth},
        "min_population_overrides": {},
        "slugs": [{"slug": slug, "scanned": True, "status": status,
                   "register_row": True, "bullets": [], "backs_bullets": []}
                  for slug, status in slugs],
    })


# The row shape every slug starts from in `manifest_with_rows`. It maps a
# bullet through NEITHER field and records NO reason, which is the state that
# must keep a check RUNNING -- so a test that forgets to override anything gets
# the strict case rather than the exempt one.
DEFAULT_SLUG_ROW = {
    "scanned": True,
    "status": "built",
    "register_row": True,
    "bullets": [],
    "backs_bullets": [],
    "gpu_required": False,
}


def manifest_with_rows(path, rows, depth=1):
    """An expected set written from EXPLICIT per-slug rows.

    `synthetic_manifest` writes ONE fixed row shape, which is right for the
    tests that only need a slug NAMED. The per-artifact applicability predicate
    reads four more fields off the row -- `bullets`, `backs_bullets`,
    `register_row` and `no_row_reason` -- so a test about it has to be able to
    set each one independently. A row shape nobody can vary cannot express the
    NEGATIVE cases, and those are the ones that stop the predicate being built
    as a blanket exemption.

    `counts.register_rows_expected` is written too, DERIVED from the rows and
    not typed: check_05 REFUSES without it (`expected_literal` raises), which
    would make every CHECK-05 assertion here fail for a reason having nothing to
    do with applicability.
    """
    slugs = []
    for row in rows:
        merged = dict(DEFAULT_SLUG_ROW)
        merged.update(row)
        slugs.append(merged)
    register_rows = sum(1 for row in slugs if row.get("register_row"))
    built = sum(1 for row in slugs if row.get("status") == "built")
    return write_json(path, {
        "schema": "manifest/1",
        "schema_version": 1,
        "scan_root": {"relative_to_repo_root": "..", "depth": depth},
        "min_population_overrides": {},
        "counts": {
            "register_rows_expected": register_rows,
            "register_rows_derived": register_rows,
            "built_expected": built,
            "built_derived": built,
            "pending_expected": len(slugs) - built,
            "pending_derived": len(slugs) - built,
            "scanned_expected": len(slugs),
            "scanned_derived": len(slugs),
        },
        "slugs": slugs,
    })


def write_register(artifacts_root, slugs):
    """A minimal register document beside the artifact directories.

    MEASURED, and the reason this helper exists: with no register reachable,
    `check_05.run()` REFUSES ("no backing-artifacts.md is reachable from ...")
    before it can report a missing row. So a test that wants to observe
    CHECK-05 finding a missing row has to give it a register to miss the row
    FROM -- otherwise the assertion is about an absent document, not about the
    row. A row is a `## <slug>` heading; `ROW_RE` in check_05.py reads nothing
    else, so nothing more is fabricated here.
    """
    root = Path(artifacts_root)
    root.mkdir(parents=True, exist_ok=True)
    body = ["# Backing artifacts register", "",
            "- scanned: `%s`" % root.as_posix(), ""]
    for slug in slugs:
        body += ["## %s" % slug, "", "- status: built", ""]
    target = root / "backing-artifacts.md"
    target.write_text("\n".join(body) + "\n", encoding="utf-8", newline="\n")
    return target


def not_applicable_entry(report, check_id):
    """The `not_applicable_checks[]` row for `check_id`, or None."""
    for row in (report or {}).get("not_applicable_checks") or []:
        if row.get("check_id") == check_id:
            return row
    return None


def run_conformance(target, *flags, report=None, cwd=None, log_dir=None):
    argv = [sys.executable, str(CONFORMANCE), str(target)]
    if report is not None:
        argv += ["--report", str(report)]
    argv += [str(flag) for flag in flags]
    return conftest.run_cli(argv, cwd=cwd or REPO_ROOT, log_dir=log_dir)


def run_scan(scan_root, *flags, manifest=None, report=None, cwd=None,
             log_dir=None):
    argv = [sys.executable, str(CONFORMANCE), "--scan",
            "--scan-root", str(scan_root)]
    if manifest is not None:
        argv += ["--manifest", str(manifest)]
    if report is not None:
        argv += ["--report", str(report)]
    argv += [str(flag) for flag in flags]
    return conftest.run_cli(argv, cwd=cwd or REPO_ROOT, log_dir=log_dir)


def entry(report, check_id):
    """The checks[] row for `check_id`, or None. Never a positional index."""
    for row in (report or {}).get("checks") or []:
        if row.get("check_id") == check_id:
            return row
    return None


def discovered():
    return checks.discover(CHECKS_DIR, verbose=False)


# ---------------------------------------------------------------------------
# The committed literal and the identity it exists to make assertable
# ---------------------------------------------------------------------------


def test_runner_check_ids_is_the_committed_pair():
    """The pair is a literal a later plan reads, not a value it re-types."""
    assert conformance.RUNNER_CHECK_IDS == ("CHECK-10", "CHECK-11")
    assert len(conformance.RUNNER_CHECK_IDS) == conformance.RUNNER_CHECK_COUNT
    for check_id in conformance.RUNNER_CHECK_IDS:
        assert check_id not in checks.DECLARED_CHECK_IDS, (
            "%s is declared as a MODULE id as well as a runner property; one of "
            "the two declarations is looking for a file that will never exist"
            % check_id)


def test_checks_array_is_the_module_count_plus_the_runner_properties(tmp_path):
    """len(checks) == discover().found + len(RUNNER_CHECK_IDS), on a real run.

    Never `== discover().found`. That pairing equates the checks[] count with the
    MODULE count, and left standing it would force a later eleven-check assertion
    down to ten -- the ten-of-twelve narrowing this phase has already rejected
    once, arriving through the report schema instead of through the audit.
    """
    root = artifact(tmp_path)
    result = run_conformance(root, report=tmp_path / "report.json")
    report = result.report
    assert report is not None, result.stdout + result.stderr

    found = discovered().found
    assert found >= 1, "discovery found 0 modules; the identity below is vacuous"
    assert len(report["checks"]) == found + len(conformance.RUNNER_CHECK_IDS), (
        "checks[] holds %d row(s); %d module(s) plus %d runner property(ies) is %d"
        % (len(report["checks"]), found, len(conformance.RUNNER_CHECK_IDS),
           found + len(conformance.RUNNER_CHECK_IDS)))


def test_the_identity_fails_when_a_runner_row_is_removed(tmp_path):
    """An identity never observed FAILING is an assertion about arithmetic.

    The copy below is in memory: the run itself is untouched, and what is
    demonstrated is that the identity discriminates rather than that it holds.
    """
    root = artifact(tmp_path)
    result = run_conformance(root, report=tmp_path / "report.json")
    report = result.report
    found = discovered().found

    shortened = [row for row in report["checks"]
                 if row["check_id"] != "CHECK-11"]
    assert len(shortened) == len(report["checks"]) - 1, (
        "CHECK-11 had no row to remove, so this demonstration proves nothing")
    assert len(shortened) != found + len(conformance.RUNNER_CHECK_IDS), (
        "the identity still held with a runner row removed, so it is not "
        "measuring the array at all")


def test_both_runner_ids_are_first_class_rows_with_a_population(tmp_path):
    """A runner property with no row is a checker an audit cannot see."""
    root = artifact(tmp_path)
    result = run_conformance(root, report=tmp_path / "report.json")
    report = result.report

    ids = {row["check_id"] for row in report["checks"]}
    assert set(conformance.RUNNER_CHECK_IDS) <= ids, sorted(ids)
    for check_id in conformance.RUNNER_CHECK_IDS:
        row = entry(report, check_id)
        assert row["checked"] > 0, (
            "%s carries a population of %d; a runner property with no population "
            "is the very thing it exists to refuse" % (check_id, row["checked"]))
        for name in conformance.REPORT_CHECK_FIELDS:
            assert name in row, (
                "%s is missing the field %r that every module-backed row "
                "carries; a consumer could tell a runner property from a module "
                "by the SHAPE of its row" % (check_id, name))
        assert row["source"] == conformance.SOURCE_RUNNER, row


def test_every_row_carries_all_eight_fields(tmp_path):
    root = artifact(tmp_path)
    result = run_conformance(root, report=tmp_path / "report.json")
    assert conformance.REPORT_CHECK_FIELD_COUNT == 8
    for row in result.report["checks"]:
        missing = [name for name in conformance.REPORT_CHECK_FIELDS
                   if name not in row]
        assert not missing, "%s is missing %s" % (row.get("check_id"), missing)


# ---------------------------------------------------------------------------
# The report (the design rules)
# ---------------------------------------------------------------------------


def test_the_report_parses_and_carries_a_schema_version(tmp_path):
    """an earlier round reads reports written as early as an earlier round."""
    root = artifact(tmp_path)
    target = tmp_path / "report.json"
    result = run_conformance(root, report=target)
    assert target.is_file(), result.stdout + result.stderr
    report = json.loads(target.read_text(encoding="utf-8"))
    assert report["schema_version"], report
    assert report["tool"] == "conformance"
    assert report["schema"] == conformance.SCHEMA
    assert report["summary"]["checked_artifacts"] == 1
    assert isinstance(report["generated_at"], str) and report["generated_at"]


def test_every_check_code_is_preserved_verbatim_in_the_report(tmp_path):
    """The aggregate collapses; the per-check code must not."""
    root = artifact(tmp_path, population=None)          # one CHECK-01 finding
    result = run_conformance(root, report=tmp_path / "report.json")
    row = entry(result.report, "CHECK-01")
    assert row["code"] == core.EXIT_FINDING, row
    assert row["found"] >= 1, row
    assert result.exit_code == core.EXIT_FINDING


def test_a_report_inside_the_artifact_is_refused_without_the_flag(tmp_path):
    """a design rule: the checker must not mutate what it checks."""
    root = artifact(tmp_path)
    inside = root / "conformance-report.json"
    refused = run_conformance(root, report=inside)
    assert refused.exit_code == core.EXIT_DID_NOT_RUN, refused.stdout
    assert not inside.exists(), "a report was written inside the artifact anyway"
    assert "--report-inside" in refused.stderr, refused.stderr

    allowed = run_conformance(root, "--report-inside", report=inside)
    assert inside.is_file(), allowed.stdout + allowed.stderr
    assert allowed.exit_code in (0, 1), allowed.stdout


# ---------------------------------------------------------------------------
# The population line
# ---------------------------------------------------------------------------


def test_the_population_line_agrees_with_the_core_it_wraps():
    """The runner owns the line's VOCABULARY; the core owns the VERDICT.

    Pinning the two together is what stops the rename from becoming a second,
    drifting implementation of the one branch that matters -- the zero-population
    branch that overrides `passed`.
    """
    grid = [
        (True, 0, 5, 1, 0, 0),
        (False, 3, 5, 1, 0, 0),
        (True, 0, 0, 1, 0, 0),            # the zero-population branch
        (False, 2, 7, 4, 1, 2),
        (True, 0, 1, 9, 0, 0),
    ]
    for passed, found, checked, floor, waived, not_examined in grid:
        buffer = io.StringIO()
        verdict, line = conformance.population_line(
            core, "CHECK-01", passed, found, checked, floor, waived=waived,
            not_examined=not_examined, stream=buffer)

        core_buffer = io.StringIO()
        with contextlib.redirect_stdout(core_buffer):
            core_verdict = core.report("CHECK-01", passed, found, checked, floor,
                                       waived=waived, not_examined=not_examined)
        assert verdict == core_verdict, (passed, checked, verdict, core_verdict)
        assert buffer.getvalue().strip() == line
        for token in ("found=%d" % found, "checked=%d" % checked,
                      "floor=%d" % floor, "waived=%d" % waived):
            assert token in line, (token, line)
            assert token in core_buffer.getvalue(), (token, core_buffer.getvalue())
        assert core.BANNED_VERDICT.lower() not in line.lower(), line


def test_the_banned_verdict_word_never_appears_in_a_full_run(tmp_path):
    """CHECK-11: a check that could not look must say so in those terms."""
    root = artifact(tmp_path, population=None)
    result = run_conformance(root, report=tmp_path / "report.json")
    combined = (result.stdout + result.stderr).lower()
    assert combined.strip(), "the run printed nothing at all"
    assert core.BANNED_VERDICT.lower() not in combined, (
        "the banned verdict word appears in the run's output:\n%s" % result.stdout)


def test_an_effective_floor_override_prints(tmp_path):
    """a design rule: the OVERRIDDEN value is what prints, or the line lies."""
    root = artifact(tmp_path)
    result = run_conformance(root, "--min-population", "CHECK-01=99",
                             report=tmp_path / "report.json")
    assert "floor=99" in result.stdout, result.stdout
    row = entry(result.report, "CHECK-01")
    assert row["floor"] == 99, row
    assert row["code"] == core.EXIT_DID_NOT_RUN, (
        "a population below the effective floor was not demoted: %r" % row)


def test_the_help_text_never_instructs_a_pipeline():
    """A tool whose exit code everything else trusts must not teach the trap."""
    result = conftest.run_cli([sys.executable, str(CONFORMANCE), "--help"],
                              cwd=REPO_ROOT)
    assert result.exit_code == 0, result.stderr
    assert "EXIT=$?" in result.stdout, result.stdout
    source = CONFORMANCE.read_text(encoding="ascii")
    for banned in ("| " + "tail", "| " + "head"):
        assert banned not in source, (
            "conformance.py's own source builds a pipeline (%r)" % banned)
        assert banned not in result.stdout, result.stdout


# ---------------------------------------------------------------------------
# the banned-spelling rule
# ---------------------------------------------------------------------------


def test_the_banned_results_record_fails_and_names_the_path(tmp_path):
    root = artifact(tmp_path)
    write_json(root / "results" / conformance.BANNED_RESULTS_BASENAME,
               {"note": "the banned spelling"})
    result = run_conformance(root, report=tmp_path / "report.json")
    assert result.exit_code != 0, result.stdout
    assert conformance.BANNED_RESULTS_RELATIVE in result.stdout, result.stdout
    guards = result.report["artifacts"][0]["guards"]
    assert any(guard["code"] == core.EXIT_GUARD_FAIL for guard in guards), guards
    assert result.exit_code == core.EXIT_GUARD_FAIL, result.stdout
    assert len(result.report["checks"]) == \
        discovered().found + len(conformance.RUNNER_CHECK_IDS), (
        "the guard short-circuited the run and the checks[] identity stopped "
        "closing; a guard failure must not erase the per-check rows")


# ---------------------------------------------------------------------------
# The census (a design rule) and its identities
# ---------------------------------------------------------------------------


def test_the_scan_prints_the_directory_count_it_covered(tmp_path):
    """A scan root the reader cannot count is a population nobody stated."""
    root = tmp_path / "scan-root"
    root.mkdir()
    artifact(root, slug="alpha")
    (root / "an-unrelated-tree").mkdir()
    manifest = synthetic_manifest(tmp_path / "manifest.json", [("alpha", "built")])

    result = run_scan(root, manifest=manifest, report=tmp_path / "report.json")
    assert "2 directory(ies) at depth 1" in result.stdout, result.stdout
    assert "enumerated" in result.stdout and "scan root" in result.stdout
    scan = result.report["scan"]
    assert scan["enumerated"] == 2, scan
    assert scan["unrelated"] == 1, scan
    assert scan["artifact_shaped"] == 1, scan


def test_the_census_identity_closes_over_a_synthetic_scan(tmp_path):
    """checked + waived + extras + missing == expected, printed and asserted."""
    root = tmp_path / "scan-root"
    root.mkdir()
    artifact(root, slug="alpha")
    artifact(root, slug="stranger")
    manifest = synthetic_manifest(
        tmp_path / "manifest.json",
        [("alpha", "built"), ("gone", "built"), ("later", "pending")])

    result = run_scan(root, "--census-only", manifest=manifest,
                      report=tmp_path / "report.json")
    scan = result.report["scan"]
    assert scan["checked"] == 1 and scan["extras"] == 1, scan
    assert scan["missing"] == 1 and scan["pending"] == 1, scan
    assert (scan["checked"] + scan["waived"] + scan["extras"] + scan["missing"]
            == scan["expected"]), scan
    assert (scan["checked"] + scan["waived"] + scan["extras"] + scan["missing"]
            + scan["pending"] == scan["listed"]), scan
    assert scan["identity_closes"] is True, scan
    assert "identity" in result.stdout and "closes" in result.stdout


def test_an_unknown_artifact_shaped_directory_is_counted_and_not_a_finding(tmp_path):
    """a design rule: the scan root holds unrelated trees; a checker that cries wolf on
    day one is a checker nobody reads."""
    root = tmp_path / "scan-root"
    root.mkdir()
    artifact(root, slug="alpha")
    manifest = synthetic_manifest(tmp_path / "manifest.json", [("alpha", "built")])

    before = run_scan(root, manifest=manifest, report=tmp_path / "before.json")
    artifact(root, slug="stranger")
    after = run_scan(root, manifest=manifest, report=tmp_path / "after.json")

    assert after.report["scan"]["extras"] == 1, after.report["scan"]
    assert "extras" in after.stdout
    assert after.exit_code == before.exit_code, (
        "an extra directory moved the exit code from %d to %d"
        % (before.exit_code, after.exit_code))


def test_a_missing_built_slug_is_a_finding(tmp_path):
    """The MISSING direction still FAILS, against a control that PASSES.

    BOTH ARMS MATTER and the control is the harder one. `bad` exiting 1 proves
    nothing on its own: over a minimal artifact every scan exits 1, for seven
    reasons that have nothing to do with a missing slug. The control had to
    become a CONFORMANT world before "missing makes the difference" was a claim
    this test could support at all.

    The conformant artifact is built inside the scan root and the manifest is
    the world's own, with a second `gone` slug added for the broken arm -- so
    the two runs differ in exactly one thing: whether the expected set names a
    built slug that is not on disk.
    """
    from tools.tests.test_skeleton_roundtrip import build_conformant_world

    root = tmp_path / "scan-root"
    root.mkdir()
    world = build_conformant_world(root)

    clean = json.loads(Path(world.manifest_path).read_text(encoding="ascii"))
    broken = json.loads(json.dumps(clean))
    broken["slugs"].append({"slug": "gone", "scanned": True, "status": "built",
                            "register_row": False, "bullets": [],
                            "backs_bullets": [],
                            "no_row_reason": "declared built, never built"})
    broken_path = tmp_path / "broken.json"
    write_json(broken_path, broken)

    shared = ["--scan-root", str(root), "--live-store", world.live_store,
              "--records-dir", world.records_dir]
    ok = run_scan(root, *shared[2:], manifest=world.manifest_path,
                  report=tmp_path / "ok.json")
    bad = run_scan(root, *shared[2:], manifest=broken_path,
                   report=tmp_path / "bad.json")

    assert ok.exit_code == 0, ok.stdout
    assert bad.exit_code == core.EXIT_FINDING, bad.stdout
    assert bad.report["scan"]["missing"] == 1, bad.report["scan"]
    assert "gone" in bad.stdout


def test_a_pending_slug_whose_directory_exists_is_a_finding(tmp_path):
    """The status rule's anti-silencer rule: a stale manifest is a finding."""
    root = tmp_path / "scan-root"
    root.mkdir()
    artifact(root, slug="alpha")
    artifact(root, slug="later")
    manifest = synthetic_manifest(tmp_path / "manifest.json",
                                  [("alpha", "built"), ("later", "pending")])
    result = run_scan(root, manifest=manifest, report=tmp_path / "report.json")
    assert result.report["scan"]["stale_pending"] == 1, result.report["scan"]
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert "stale manifest" in result.stdout


def test_the_closeout_criterion_prints_its_own_count(tmp_path):
    root = tmp_path / "scan-root"
    root.mkdir()
    artifact(root, slug="alpha")
    manifest = synthetic_manifest(
        tmp_path / "manifest.json",
        [("alpha", "built"), ("later", "pending"), ("also", "pending")])
    result = run_scan(root, "--census-only", manifest=manifest,
                      report=tmp_path / "report.json")
    assert "pending=2" in result.stdout, result.stdout
    assert "a project requirement" in result.stdout, result.stdout


def test_the_runner_never_writes_the_manifest_status_field(tmp_path):
    """`status` is owner/plan-set and never build-agent-set."""
    root = tmp_path / "scan-root"
    root.mkdir()
    artifact(root, slug="alpha")
    manifest = synthetic_manifest(tmp_path / "manifest.json",
                                  [("alpha", "built"), ("later", "pending")])
    before = manifest.read_bytes()
    run_scan(root, manifest=manifest, report=tmp_path / "report.json")
    assert manifest.read_bytes() == before, (
        "the runner rewrote the expected set it was handed")


# ---------------------------------------------------------------------------
# The scan root itself
# ---------------------------------------------------------------------------


def test_the_worktree_main_root_matches_the_census_helper():
    """The copy in conformance.py must not drift from the one in the repo tool.

    conformance.py is vendored into artifacts that have no tools/ package, so it
    carries its own copy of the worktree resolution rather than importing one.
    A copy nobody compares is a copy that drifts, so the two are pinned here on
    the same inputs.
    """
    from tools import census_live_store

    repo = str(REPO_ROOT)
    fake_worktree = str(REPO_ROOT / "agent-worktrees" / "worktrees" / "agent-x")
    cases = [
        (repo, ""),
        (repo, "not a gitdir marker"),
        (fake_worktree, "gitdir: %s/.git/worktrees/agent-x"
                        % REPO_ROOT.as_posix()),
        (fake_worktree, "gitdir: ../../.git/worktrees/agent-x"),
    ]
    for repo_root, marker in cases:
        mine = conformance.resolve_worktree_main_root(repo_root, marker)
        theirs = census_live_store.resolve_worktree_main_root(repo_root, marker)
        assert mine == theirs, (repo_root, marker, mine, theirs)


def test_the_worktree_spelling_resolves_to_the_same_scan_root():
    """a recorded defect in one assertion: the same population from either location."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    from_main = conformance.declared_scan_root(manifest, MAIN_REPO_ROOT)
    marker = "gitdir: %s/.git/worktrees/agent-x" % MAIN_REPO_ROOT.as_posix()
    worktree_root = conformance.resolve_worktree_main_root(
        str(MAIN_REPO_ROOT / "agent-worktrees" / "worktrees" / "agent-x"), marker)
    from_worktree = conformance.declared_scan_root(manifest, worktree_root)
    assert from_main == from_worktree, (from_main, from_worktree)


def test_the_live_scan_root_agrees_with_the_committed_constant():
    """The manifest's rule and the suite's constant are ONE assertion, two ends."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    derived = Path(
        conformance.declared_scan_root(manifest, MAIN_REPO_ROOT)).resolve()
    assert derived == conftest.SCAN_ROOT.resolve(), (derived, conftest.SCAN_ROOT)
    assert conformance.declared_scan_depth(manifest) == conftest.SCAN_DEPTH


def test_the_fixture_tree_is_never_enumerated_by_the_runner():
    """a design rule -> a design rule, asserted against the RUNNER's own enumeration.

    The property is NON-ENUMERATION, not non-containment: this repository lives
    inside the scan root, so the fixture tree IS a descendant of it. Enumeration
    stops at the immediate children, and the fixture tree sits three levels down.
    """
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    scan_root = Path(conformance.declared_scan_root(manifest, MAIN_REPO_ROOT))
    report = conformance.census(scan_root, manifest)

    # RE-KEYED by an earlier plan. `report.enumerated >= 10` asserted a fact about
    # ONE MACHINE'S LAYOUT: the owner's scan root holds the artifact slugs, the
    # live data dir and ~22 unrelated trees. It cannot hold in a published
    # export, whose parent directory holds one entry, nor on anyone else's
    # checkout -- and it was only ever a proxy for "you are looking at the
    # parent of the MAIN checkout", which is asserted directly below and is
    # strictly stronger, because a wrong anchor with eleven children satisfied
    # the old floor and fails the new one.
    assert scan_root.resolve() == (MAIN_REPO_ROOT / "..").resolve(), (
        "the runner's declared scan root is %s; the MAIN checkout's parent is "
        "%s" % (scan_root, (MAIN_REPO_ROOT / "..").resolve()))
    assert (MAIN_REPO_ROOT / "tools" / "conformance.py").is_file(), MAIN_REPO_ROOT
    assert MAIN_REPO_ROOT.name in {p.name for p in scan_root.iterdir()
                                   if p.is_dir()}, (
        "the main checkout %r is not among the scan root's children, so this "
        "root is not its parent" % MAIN_REPO_ROOT.name)
    assert report.enumerated >= 1, (
        "the runner enumerated %d director(ies) under %s, so every assertion "
        "below would be vacuous" % (report.enumerated, scan_root))

    names = (report.checked + report.waived + report.extras
             + report.unrelated + report.stale_pending)
    assert "fixtures" not in names, names
    children = sorted(p.name for p in conftest.BROKEN_FIXTURES_DIR.iterdir()
                      if p.is_dir())
    assert len(children) >= 5, (
        "the fixture tree holds %d subdirector(ies); an unseeded tree makes "
        "the loop below iterate zero times and report a pass" % len(children))
    for child in children:
        assert child not in names, (
            "%s was enumerated as an artifact candidate" % child)


def test_the_live_census_closes_its_identities():
    """Run over the real scan root, with both counts printed by the caller."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    report = conformance.census(
        conformance.declared_scan_root(manifest, MAIN_REPO_ROOT), manifest)
    assert report.declared_scanned == \
        manifest["counts"]["scanned_expected"], (
        "the runner read %d scanned slug(s); the manifest's committed literal "
        "says %d" % (report.declared_scanned,
                     manifest["counts"]["scanned_expected"]))
    assert report.closes, report.as_dict()
    assert len(report.checked) + len(report.waived) + len(report.extras) \
        + len(report.missing) == report.expected


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _pinned_store(tmp_path):
    """A synthetic live store and an empty records directory, for CHECK-20.

    Copied from the committed fixture's SYNTHETIC entries rather than from the
    real ones, so nothing here can read a private record.
    """
    source = conftest.broken_fixture("broken-uncorrected-entry") / "live"
    store = Path(tmp_path) / "pinned-live"
    for spec_relative in ("collections/collection-one/example-alpha/raw.json",
                          "collections/collection-two/example-beta/raw.json"):
        target = store / spec_relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source / spec_relative).read_bytes())
    records = Path(tmp_path) / "pinned-records"
    records.mkdir(parents=True, exist_ok=True)
    return store, records


def test_the_runner_pins_check_20_away_from_the_real_private_record(tmp_path):
    """`--live-store` and `--records-dir` reach the check, and OVERRIDE it.

    THE RED THIS CATCHES is not a wrong verdict, it is a wrong INPUT. CHECK-20
    is the only check that reads outside the artifact, and until these flags
    existed it resolved the owner's live collections entries on every run --
    including from a pytest temp directory, which made the suite's verdict a
    function of a private record no test controls. The flags are how a caller
    says "read THIS instead", and the printed population line is where a reader
    can see which one was read.
    """
    store, records = _pinned_store(tmp_path)
    root = artifact(tmp_path)
    result = run_conformance(root, "--live-store", str(store),
                             "--records-dir", str(records),
                             report=tmp_path / "report.json")

    line = next((row for row in result.stdout.splitlines()
                 if row.startswith("CHECK-20")), None)
    assert line is not None, result.stdout
    assert str(store).replace("\\", "/") in line, line
    assert str(records).replace("\\", "/") in line, line
    assert "Research/information" not in line, (
        "the runner still resolved the real live store despite an explicit "
        "--live-store: %s" % line)


def test_without_the_flag_check_20_resolves_its_declared_default(tmp_path):
    """The override is an OVERRIDE, not the only path. Asserted so the pin above
    cannot be satisfied by a check that simply stopped reading anything."""
    root = artifact(tmp_path)
    result = run_conformance(root, report=tmp_path / "report.json")
    line = next((row for row in result.stdout.splitlines()
                 if row.startswith("CHECK-20")), None)
    assert line is not None, result.stdout
    assert "live-store=" in line, line
    assert "information" in line, (
        "with no --live-store the check should resolve its declared default: %s"
        % line)


def test_a_partial_module_set_is_reported_not_refused(tmp_path):
    """A partial module set is EXPECTED through the waves that add them."""
    root = artifact(tmp_path)
    result = run_conformance(root, report=tmp_path / "report.json")
    assert "of 11 declared" in result.stdout, result.stdout
    assert result.report["discovered"]["declared"] == checks.DECLARED_MODULE_COUNT
    assert result.report["discovered"]["found"] == discovered().found
    assert result.exit_code != core.EXIT_DID_NOT_RUN, (
        "a partial module set was refused; the runner could then never reach "
        "the step that proves the round trip")


# ---------------------------------------------------------------------------
# The scan root's anchor (an earlier plan open item 12)
# ---------------------------------------------------------------------------


def test_the_scan_root_anchor_is_the_main_checkout_not_the_working_one():
    """an earlier plan open item 12, closed and asserted by RESOLUTION.

    Three parts, and the third is the only one that discriminates.

    (a) the anchor this module uses and the one `conftest` derives are ONE
        path. Two copies of a resolution rule that nobody compares is how a recorded defect
        happened in the first place.
    (b) resolved from the MAIN root, the manifest's `..` is the scan root the
        suite's own constant names -- compared as RESOLVED PATHS, never as
        strings, because a worktree and its main checkout spell the same
        directory differently and only one of the two spellings is on disk.
    (c) the working root and the main root are NOT interchangeable here. From
        the main checkout they coincide, so (a) and (b) alone are satisfied by
        the very anchoring this item exists to remove. Part (c) resolves `..`
        from a WORKTREE spelling and asserts it lands somewhere else, then
        asserts that routing that same spelling through the resolver lands back
        on the main answer. That pair holds from either checkout.
    """
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert MAIN_REPO_ROOT == conftest.MAIN_REPO_ROOT.resolve(), (
        "this module and conftest resolve the main checkout differently: %s "
        "vs %s" % (MAIN_REPO_ROOT, conftest.MAIN_REPO_ROOT))

    derived = Path(
        conformance.declared_scan_root(manifest, MAIN_REPO_ROOT)).resolve()
    assert derived == conftest.SCAN_ROOT.resolve(), (derived, conftest.SCAN_ROOT)

    worktree = MAIN_REPO_ROOT / "agent-worktrees" / "worktrees" / "agent-x"
    from_worktree = Path(
        conformance.declared_scan_root(manifest, worktree)).resolve()
    assert from_worktree != derived, (
        "`..` resolved to the same directory from %s and from %s, so this "
        "assertion cannot tell the two anchors apart and the re-keying it "
        "guards is unverified" % (worktree, MAIN_REPO_ROOT))

    recovered = Path(conformance.declared_scan_root(
        manifest,
        conformance.resolve_worktree_main_root(
            str(worktree),
            "gitdir: %s/.git/worktrees/agent-x" % MAIN_REPO_ROOT.as_posix()))
    ).resolve()
    assert recovered == derived, (recovered, derived)


# ---------------------------------------------------------------------------
# The per-artifact applicability declaration (the design rules)
# ---------------------------------------------------------------------------
#
# The mechanism, and why it is this one rather than an in-module refusal.
# `run_artifact` aggregates every record's code and the conventions document section 1
# lifts any 2 to 1, so a check that REFUSES on an artifact makes that artifact's
# exit code 1 for as long as the refusal stands. For a slug that correctly backs
# nothing, that is a verdict about a directory the check was never pointed at,
# and it puts EXIT=0 permanently out of reach. `run_self` already ships the
# shape that works: a member whose predicate does not hold is NAMED with a
# reason and contributes NO CODE, which is why `--self` is EXIT=0 today over
# `ran 4, not-applicable 11`. These tests are that half's per-artifact twin.


ROW_REASON = ("Cited by no bullet in either canon. Recorded in the expected "
              "set's own row so the absence is stated rather than inferred.")

# A compound key that resolves to a real canon NAME and to no real claim, so a
# test about applicability never reaches a live bullet. `_pinned_store` supplies
# the entries; the id itself only has to be well-formed.
SYNTHETIC_BULLET = "example-alpha:P9-B9"


def _applicability_run(tmp_path, row, slug="alpha", register=None):
    """Point the runner at one artifact with ONE manifest row under test.

    `--live-store` and `--records-dir` are pinned on EVERY call, not only where
    a row names a claim. CHECK-20 is the one check that reads outside the
    artifact, and a row under obligation makes it resolve the owner's real
    collections entries from a pytest temp directory -- which would make these
    verdicts a function of a private record no test controls. Measured: a probe
    written without the flags came back with
    `backing:marker-present:example-beta:P5-B3`, read from the live store.
    """
    root = artifact(tmp_path, slug=slug)
    entry_row = {"slug": slug}
    entry_row.update(row)
    manifest = manifest_with_rows(tmp_path / "manifest.json", [entry_row])
    if register is not None:
        write_register(tmp_path, register)
    store, records = _pinned_store(tmp_path)
    return run_conformance(root, "--manifest", str(manifest),
                           "--live-store", str(store),
                           "--records-dir", str(records),
                           report=tmp_path / "report.json")


def test_the_artifact_subset_is_declared_with_a_committed_literal():
    """The declaration exists, beside `SELF_SUBSET`, and carries its own count.

    Same reason every other count in this repository carries one: a purely
    derived length silently stops checking when a member is dropped, because
    `expected` falls to match `found`.
    """
    assert hasattr(conformance, "ARTIFACT_SUBSET"), (
        "conformance.py declares no ARTIFACT_SUBSET, so `run_artifact` would "
        "have to infer applicability from somewhere that is not a declaration")
    assert len(conformance.ARTIFACT_SUBSET) == \
        conformance.ARTIFACT_SUBSET_COUNT, (
        "ARTIFACT_SUBSET names %d member(s), the committed literal says %d"
        % (len(conformance.ARTIFACT_SUBSET),
           conformance.ARTIFACT_SUBSET_COUNT))
    assert conformance.ARTIFACT_SUBSET_COUNT > 0
    for member in conformance.ARTIFACT_SUBSET:
        assert member.member_id, member
        assert callable(member.applies), member
        assert callable(member.reason), member
        assert member.what.strip(), (
            "%s declares no `what`; a member nobody can read is a member "
            "nobody can review" % member.member_id)

    # The printed verdict is the SAME CONSTANT the --self half prints, not a
    # second spelling of it. Two spellings of one state is how a reader learns
    # to scan for one and miss the other.
    assert conformance.ARTIFACT_NOT_APPLICABLE == conformance.SELF_NOT_APPLICABLE
    assert core.BANNED_VERDICT.lower() not in \
        conformance.ARTIFACT_NOT_APPLICABLE.lower()


def test_check_09_is_not_applicable_when_the_row_backs_nothing_and_says_why(
        tmp_path):
    """a design rule: empty `bullets` AND empty `backs_bullets` AND a recorded reason.

    Four assertions, because the first three are each satisfiable by a wrong
    implementation: a check silently dropped is absent from `checks[]`; a check
    named with an invented sentence is named; and a check whose code is 2 is
    still in the aggregate. What is pinned is the conjunction -- named, with the
    MANIFEST's own text, absent from `checks[]`, and contributing no code.
    """
    result = _applicability_run(tmp_path, {"no_row_reason": ROW_REASON})
    report = result.report
    assert report is not None, result.stdout + result.stderr

    named = not_applicable_entry(report, "CHECK-09")
    assert named is not None, (
        "CHECK-09 is not in not_applicable_checks[]: %r"
        % (report.get("not_applicable_checks"),))
    assert ROW_REASON in named["reason"], (
        "the printed reason is not the manifest's own text: %r" % (named,))
    assert entry(report, "CHECK-09") is None, (
        "CHECK-09 is in BOTH checks[] and not_applicable_checks[]; a member "
        "cannot have both run and not applied")

    line = next((row for row in result.stdout.splitlines()
                 if row.startswith("CHECK-09")), None)
    assert line is not None, result.stdout
    assert conformance.ARTIFACT_NOT_APPLICABLE in line, line
    assert ROW_REASON in line, line
    assert core.BANNED_VERDICT.lower() not in line.lower(), line


def test_an_unexplained_absence_is_not_an_exemption_for_check_09(tmp_path):
    """The NEGATIVE case, and the mechanism is wrong without it.

    A predicate keyed only on "this row backs nothing" would exempt every
    artifact that has not authored its claim block yet -- which converts a
    REFUSAL into a silent exemption, the exact demotion that the conventions document, section 1,
    and the `SelfMember` docstring both warn about. All THREE conjuncts are
    required, and this is the one that proves the third is read.
    """
    result = _applicability_run(tmp_path, {})
    report = result.report
    assert report is not None, result.stdout + result.stderr

    assert not_applicable_entry(report, "CHECK-09") is None, (
        "a row with empty mapping fields and NO recorded reason was exempted; "
        "an unexplained absence is not an exemption")
    row = entry(report, "CHECK-09")
    assert row is not None, report.get("checks")
    assert row["code"] == core.EXIT_DID_NOT_RUN, row
    assert row["checked"] == 0, row
    assert result.exit_code == core.EXIT_FINDING, result.stdout


def test_a_row_that_maps_a_bullet_still_runs_check_09(tmp_path):
    """The other direction: an artifact under obligation is still asked.

    Pinned through BOTH mapping fields, because the predicate reads the union
    and a implementation that read only `bullets` would exempt redis -- whose
    claim arrives through `backs_bullets`.
    """
    for field_name in ("bullets", "backs_bullets"):
        target = tmp_path / field_name
        target.mkdir()
        result = _applicability_run(
            target,
            {field_name: [SYNTHETIC_BULLET], "canon": "example-alpha",
             "no_row_reason": ROW_REASON})
        report = result.report
        assert report is not None, result.stdout + result.stderr
        assert not_applicable_entry(report, "CHECK-09") is None, (
            "%s named a claim and CHECK-09 was still exempted" % field_name)
        row = entry(report, "CHECK-09")
        assert row is not None, report.get("checks")
        assert row["code"] == core.EXIT_DID_NOT_RUN, (
            "%s: the claim table is missing, so the zero-reference refusal is "
            "the verdict this run should still reach: %r" % (field_name, row))


def test_check_11_still_counts_a_member_that_is_not_applicable(tmp_path):
    """an earlier step: the runner's own population must not silently shrink.

    A member excluded from the CODES must NOT be excluded from the RECORD LIST
    CHECK-11 counts. Asserted as a comparison between two runs of the same
    artifact under two manifest rows, because an absolute number here would
    move the next time a check module is added and would then be repaired by
    typing the new number rather than by asking why it moved.
    """
    strict = tmp_path / "strict"
    strict.mkdir()
    exempt = tmp_path / "exempt"
    exempt.mkdir()

    everything_runs = _applicability_run(strict, {})
    one_exempt = _applicability_run(exempt, {"no_row_reason": ROW_REASON})

    before = entry(everything_runs.report, "CHECK-11")
    after = entry(one_exempt.report, "CHECK-11")
    assert before is not None and after is not None
    assert after["checked"] == before["checked"], (
        "CHECK-11 inspected %d record(s) with every member running and %d with "
        "one not applicable; a not-applicable member must stay in the "
        "population it is counted in" % (before["checked"], after["checked"]))
    assert after["code"] == core.EXIT_PASS, after


def test_check_05_is_not_applicable_when_no_register_row_is_owed(tmp_path):
    """a design rule: `register_row: false` AND a recorded reason.

    MEASURED, and this is why a re-scope alone cannot reach it:
    `check_05.py`'s `expected_slugs` filters on a TRUTHY `register_row`, so a
    slug that owes no row is not in the expected set at all and the re-scoped
    check hits its own 0/0 refusal -- code 2, which the aggregate lifts to 1.
    A refusal is also the wrong VERDICT: owing no register row is correct here,
    which a design rule already encodes by naming the slug in the register's own
    `excluded: N (reasons recorded)` line.
    """
    result = _applicability_run(
        tmp_path, {"register_row": False, "no_row_reason": ROW_REASON})
    report = result.report
    assert report is not None, result.stdout + result.stderr

    named = not_applicable_entry(report, "CHECK-05")
    assert named is not None, (
        "CHECK-05 is not in not_applicable_checks[]: %r"
        % (report.get("not_applicable_checks"),))
    assert ROW_REASON in named["reason"], named
    assert entry(report, "CHECK-05") is None, report.get("checks")


def test_check_05_still_runs_when_a_register_row_is_owed(tmp_path):
    """`register_row: true` keeps the check, and a missing row is a FINDING.

    The register document is written for this test. Without one the module
    refuses for want of a register rather than reporting the row -- so a test
    that omitted it would assert nothing about the row at all.
    """
    result = _applicability_run(
        tmp_path, {"no_row_reason": ROW_REASON}, register=["somebody-else"])
    report = result.report
    assert report is not None, result.stdout + result.stderr

    assert not_applicable_entry(report, "CHECK-05") is None, (
        "a row that OWES a register row was exempted from CHECK-05")
    row = entry(report, "CHECK-05")
    assert row is not None, report.get("checks")
    assert row["code"] == core.EXIT_FINDING, (
        "the register carries no row for this slug, so a finding is the "
        "verdict: %r" % (row,))
    assert any("missing-row" in finding for finding in row["finding_ids"]), row


def test_an_unexplained_absent_register_row_still_runs_check_05(tmp_path):
    """The second NEGATIVE: `register_row: false` with NO reason recorded.

    Both conjuncts are required here too. A row that quietly opts out of the
    register with no recorded reason is an input silently dropped, and the check
    must keep asking about it.
    """
    result = _applicability_run(tmp_path, {"register_row": False})
    report = result.report
    assert report is not None, result.stdout + result.stderr

    assert not_applicable_entry(report, "CHECK-05") is None, (
        "a `register_row: false` row with NO recorded reason was exempted")
    row = entry(report, "CHECK-05")
    assert row is not None, report.get("checks")
    assert row["code"] != core.EXIT_PASS, row


def test_check_20_is_not_applicable_when_the_row_owes_no_correction(tmp_path):
    """The SAME predicate CHECK-09 uses, on the check that reads the entry.

    Why this member exists, measured rather than assumed. CHECK-20 asks whether
    a built slug corrected the collections entry its work was supposed to back. A
    slug that backs nothing owes no correction, and the module says so in its
    own refusal: "there is nothing whose correction could be checked ... which
    the runner's applicability mechanism states rather than this module passing
    over it." That sentence was written pointing AT this declaration, and until
    it existed the refusal was a code 2 the aggregate lifted to 1 -- so an
    artifact that correctly backs nothing could never reach EXIT=0 however many
    other checks were satisfied.
    """
    result = _applicability_run(tmp_path, {"no_row_reason": ROW_REASON})
    report = result.report
    assert report is not None, result.stdout + result.stderr

    named = not_applicable_entry(report, "CHECK-20")
    assert named is not None, (
        "CHECK-20 is not in not_applicable_checks[]: %r"
        % (report.get("not_applicable_checks"),))
    assert ROW_REASON in named["reason"], named
    assert entry(report, "CHECK-20") is None, report.get("checks")


def test_an_unexplained_absence_is_not_an_exemption_for_check_20(tmp_path):
    """The third NEGATIVE, for the same reason as the other two."""
    result = _applicability_run(tmp_path, {})
    report = result.report
    assert report is not None, result.stdout + result.stderr

    assert not_applicable_entry(report, "CHECK-20") is None, (
        "a row with empty mapping fields and NO recorded reason was exempted "
        "from CHECK-20")
    row = entry(report, "CHECK-20")
    assert row is not None, report.get("checks")
    assert row["code"] == core.EXIT_DID_NOT_RUN, row


def test_the_artifact_run_prints_both_counts_on_one_line(tmp_path):
    """`ran N, not-applicable M`, the same pair `--self` prints.

    A reader who is told only how many checks ran cannot tell a run that
    narrowed its own population from one that had nothing to narrow.
    """
    result = _applicability_run(tmp_path, {"no_row_reason": ROW_REASON})
    lines = [row for row in result.stdout.splitlines()
             if "not-applicable" in row and "ran" in row]
    assert lines, (
        "no line carried both counts:\n%s" % result.stdout)
    assert len(lines) == 1, lines

    ran = len(result.report["checks"])
    inapplicable = len(result.report["not_applicable_checks"])
    assert inapplicable >= 1, result.report["not_applicable_checks"]
    assert "ran %d" % ran in lines[0], (lines[0], ran)
    assert "not-applicable %d" % inapplicable in lines[0], (lines[0],
                                                            inapplicable)
