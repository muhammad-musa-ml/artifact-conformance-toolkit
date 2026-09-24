"""CHECK-20 -- a built slug that left its collections entry uncorrected.

Every test here runs `tools/checks/check_20.py` AS A SUBPROCESS, by path,
through conftest.run_cli, for the reason every other check test does it: by path
under a bare module name is exactly how the vendored copy runs inside an
artifact, and the thing under test is an EXIT CODE, which run_cli returns from
the child rather than from a pipeline stage.

WHAT THIS CHECK IS FOR, AND WHY IT IS THE ONE THAT READS OUTSIDE THE ARTIFACT
-----------------------------------------------------------------------------
Every other checker asks whether an artifact is well-formed. This one asks
whether the artifact's existence CHANGED ANYTHING -- whether the claims it was
built to back have been corrected to what was actually measured. Without it a
path can run end to end, satisfy all eleven other checkers, take its register
row, and leave the collections entry exactly as it was, with every light green and
the entire deliverable skipped. That is the failure it discriminates, and it is
invisible from inside the artifact by construction.

THE THREE INPUTS ARE PASSED BY FLAG, NEVER FOUND INSIDE THE ARTIFACT
---------------------------------------------------------------------
The expected set, the live entries and the correction records all live outside
the directory under test. This module supplies all three explicitly on every
run. It is not a convenience: a checker that discovered its own evidence inside
the artifact it is judging could be handed a clean answer by the artifact, and
this programme has already written down once that a checker the thing being
checked can edit is not a checker.

WHAT MAKES THE RED IN red-transcripts/CHECK-20.txt A REAL RED
--------------------------------------------------------------
The module is registered and RUNNABLE in the commit that captures the
transcript. It imports, it parses its arguments, it prints a population line and
it writes a structured report -- its run() simply returns a PASS over a
population of zero. Every failure line in that transcript is therefore an
assertion about a VERDICT, never a module that could not be loaded or an input
that was not there.

THE POPULATION IS THE BUILT SLUGS, AND BOTH NUMBERS ARE PRINTED
----------------------------------------------------------------
the project requirements document's failure condition names a SLUG -- "a slug the manifest marks
built has left its collections entry uncorrected" -- so the population the verdict
rests on is the built slugs, and zero of them is the refusal. The OBLIGATIONS
those slugs carry are a second number and it is printed beside the first, so a
reader can never mistake "two slugs, no obligations" for "two slugs checked".
test_the_note_prints_both_populations asserts exactly that, because one number
standing in for the other is how a decided-and-clean run and a run that examined
nothing become indistinguishable.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT
CHECKS_DIR = REPO_ROOT / "tools" / "checks"
CHECK_20 = CHECKS_DIR / "check_20.py"

FIXTURE = "broken-uncorrected-entry"
EXPECTATION_FILE = "expected-CHECK-20.json"

# WHICH slug inside the fixture the check is pointed at, load-bearing since plan
# an earlier plan scoped this check to the artifact it is handed. The fixture declares TWO
# built slugs, and before the re-scope one run reported both -- which is exactly
# the behaviour an earlier plan retired. `measured-path` is the richer of the two (three
# findings across two kinds, including marker-present); `cited-path`'s
# backs_bullets union is covered by its own test above, so nothing is lost.
FIXTURE_SLUG = "measured-path"

PINNED_FIELDS = ("check_id", "code", "found", "checked", "finding_ids",
                 "schema_version")

# The marker a not-yet-measured row carries. Written here as the two halves the
# live entries use, because a needle that interpolated an example project id would
# match one canon's wording and silently miss the other's -- the measured trap
# tools/check_canon_backing.py documents at length.
MARKER = "[BACKING:"

DESIGNED = ("[BACKING: designed, not yet measured -- %s has no reproducing "
            "artifact yet]")


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


core = _load("frozen_core_for_check_20_tests", REPO_ROOT / "tools" / "canonkit.py")
check_20 = _load("check_20_under_test", CHECK_20)


# ---------------------------------------------------------------------------
# A synthetic world. Nothing here touches the owner's live entries.
# ---------------------------------------------------------------------------


def write_json(path, payload):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                          encoding="ascii", newline="\n")
    return Path(path)


def manifest(slugs):
    """An expected set from (slug, status, canon, bullets, backs) tuples."""
    return {
        "schema": "manifest/1",
        "schema_version": 1,
        "min_population_overrides": {},
        "scan_root": {"relative_to_repo_root": "..", "depth": 1},
        "slugs": [
            {"slug": slug, "status": status, "canon": canon,
             "project": project, "scanned": True, "register_row": True,
             "bullets": list(bullets), "backs_bullets": list(backs)}
            for slug, status, canon, project, bullets, backs in slugs
        ],
    }


def entry(rows):
    """One live collections entry carrying `rows` as its detail.metrics."""
    return {
        "slug": "synthetic",
        "kind": "experience",
        "display_name": "Synthetic engagement",
        "company": "A Company",
        "role": "Example Role One",
        "dates": "Month YYYY - Month YYYY",
        "detail": {"done": "synthetic", "how": "synthetic",
                   "metrics": list(rows)},
    }


def live_store(tmp_path, alpha_rows=(), beta_rows=(), name="live"):
    """Both entries, at the relative paths the live store actually uses.

    BOTH are always written. A live store holding one of the two would make a
    missing entry indistinguishable from an entry with nothing to correct, which
    is the smaller-population-with-no-error shape this programme refuses.
    """
    root = Path(tmp_path) / name
    write_json(root / "collections" / "collection-one" / "example-alpha" / "raw.json",
               entry(alpha_rows))
    write_json(root / "collections" / "collection-two" / "example-beta" / "raw.json",
               entry(beta_rows))
    return root


def records(tmp_path, fragments=(), name="corrections"):
    """A records directory holding `fragments` as (filename, text) pairs."""
    root = Path(tmp_path) / name
    root.mkdir(parents=True, exist_ok=True)
    for filename, text in fragments:
        (root / filename).write_text(text, encoding="ascii", newline="\n")
    return root


def fragment(rows, plan="an earlier plan", dated_at="2026-09-17", record_id="synthetic"):
    """A correction record. `rows` is (bullet, verdict, before, after)."""
    lines = ["---", "id: %s" % record_id, "plan: %s" % plan,
             "dated_at: %s" % dated_at, "---", ""]
    for bullet, verdict, before, after in rows:
        lines.append("bullet: %s" % bullet)
        lines.append("verdict: %s" % verdict)
        if before is not None:
            lines.append("before: %s" % before)
        if after is not None:
            lines.append("after: %s" % after)
        lines.append("")
    return "\n".join(lines) + "\n"


def artifact_dir(tmp_path, slug):
    """A directory NAMED for the slug under test.

    The check is scoped to the artifact it was handed, and the only thing a
    standalone CLI run can derive a slug from is the directory's own name --
    which is also how conformance.py's self_module_check derives one. So the
    target is never a bare tmp_path: a temp directory's name is not a slug in
    any expected set, and pointing the check at one is asking it about an
    artifact that does not exist.
    """
    root = Path(tmp_path) / slug
    root.mkdir(parents=True, exist_ok=True)
    return root


DEFAULT_SLUG = "measured-path"


def run_check(tmp_path, manifest_payload, live, record_dir, *flags,
              artifact=None, slug=None, report=True):
    """Run the module by path with all three inputs supplied explicitly.

    `slug` names the artifact directory to create and point at; `artifact`
    overrides it with a path outright. Defaults to DEFAULT_SLUG, the built slug
    ONE_BUILT declares, so each test below still differs from the clean case in
    exactly one way.
    """
    manifest_path = write_json(Path(tmp_path) / "slugs.json", manifest_payload)
    if artifact is not None:
        target = artifact
    else:
        target = artifact_dir(tmp_path, slug if slug is not None else DEFAULT_SLUG)
    report_path = Path(tmp_path) / "report.json"
    argv = [sys.executable, str(CHECK_20), str(target),
            "--manifest", str(manifest_path),
            "--live-store", str(live),
            "--records-dir", str(record_dir)]
    if report:
        argv += ["--report", str(report_path)]
    argv += [str(flag) for flag in flags]
    return conftest.run_cli(argv, cwd=REPO_ROOT)


def report_of(result):
    assert result.report is not None, result.stdout + result.stderr
    return result.report


# A built slug with one obligation, and the record that satisfies it. Reused so
# each test below differs from the clean case in exactly ONE way.
ONE_BUILT = [("measured-path", "built", "example-alpha", "P1",
              ["example-alpha:P1-B3"], [])]

CORRECTED_ROW = ("example-alpha:P1-B3", "corrected",
                 "the figure as it was designed",
                 "the figure as it was measured")


def clean_world(tmp_path):
    """The passing case: one built slug, one obligation, corrected and recorded."""
    live = live_store(tmp_path, alpha_rows=["P1-B3: a measured figure"])
    record_dir = records(tmp_path, [(
        "2026-09-17-101738--measured-path--corrections.md",
        fragment([CORRECTED_ROW]))])
    return manifest(ONE_BUILT), live, record_dir


# ---------------------------------------------------------------------------
# The contract's own shape
# ---------------------------------------------------------------------------


def test_the_module_declares_the_id_the_universe_knows():
    contract = _load("check_contract_for_check_20_tests",
                     CHECKS_DIR / "__init__.py")
    assert check_20.CHECK_ID == "CHECK-20"
    assert check_20.CHECK_ID in contract.DECLARED_CHECK_IDS
    assert isinstance(check_20.DEFAULT_FLOOR, int)
    assert callable(check_20.run)


# ---------------------------------------------------------------------------
# The clean case, so every failing case below differs in exactly one way
# ---------------------------------------------------------------------------


def test_a_corrected_and_recorded_obligation_passes(tmp_path):
    payload, live, record_dir = clean_world(tmp_path)
    result = run_check(tmp_path, payload, live, record_dir)
    assert result.exit_code == core.EXIT_PASS, result.stdout + result.stderr
    report = report_of(result)
    assert report["found"] == 0, report
    assert report["checked"] == 1, report
    assert report["obligations"] == 1, report


def test_a_confirmation_is_a_result_and_passes(tmp_path):
    """"The measurement agreed" is a RESULT, and stating it is what makes it one."""
    live = live_store(tmp_path, alpha_rows=["P1-B3: a measured figure"])
    record_dir = records(tmp_path, [(
        "2026-09-17-101738--measured-path--corrections.md",
        fragment([("example-alpha:P1-B3", "confirmed",
                   "the figure as it was designed",
                   "the same figure, measured")]))])
    result = run_check(tmp_path, manifest(ONE_BUILT), live, record_dir)
    assert result.exit_code == core.EXIT_PASS, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# The three conditions the project requirements document names, one test each
# ---------------------------------------------------------------------------


def test_an_obligation_with_no_record_at_all_is_a_finding(tmp_path):
    """Condition one: a recorded correction OR confirmation, never silence."""
    live = live_store(tmp_path, alpha_rows=["P1-B3: a measured figure"])
    record_dir = records(tmp_path)
    result = run_check(tmp_path, manifest(ONE_BUILT), live, record_dir)
    assert result.exit_code == core.EXIT_FINDING, result.stdout + result.stderr
    report = report_of(result)
    assert any("no-correction" in fid for fid in report["finding_ids"]), report
    assert any("example-alpha:P1-B3" in fid for fid in report["finding_ids"]), report


def test_a_row_still_carrying_its_marker_is_a_finding(tmp_path):
    """Condition two: the designed-not-yet-measured marker must be GONE.

    Recorded AND still marked is the state that proves the two conditions are
    independent: a check that stopped at the record would call this clean.
    """
    live = live_store(tmp_path, alpha_rows=[
        "P1-B3: a figure " + (DESIGNED % "P1")])
    record_dir = records(tmp_path, [(
        "2026-09-17-101738--measured-path--corrections.md",
        fragment([CORRECTED_ROW]))])
    result = run_check(tmp_path, manifest(ONE_BUILT), live, record_dir)
    assert result.exit_code == core.EXIT_FINDING, result.stdout + result.stderr
    report = report_of(result)
    assert any("marker-present" in fid for fid in report["finding_ids"]), report


def test_a_record_without_before_and_after_is_a_finding(tmp_path):
    """Condition three: the record carries the BEFORE/AFTER rows.

    A record naming a verdict and nothing else says a measurement happened and
    leaves no way to see what it changed, which is the half a later reader needs.
    """
    live = live_store(tmp_path, alpha_rows=["P1-B3: a measured figure"])
    record_dir = records(tmp_path, [(
        "2026-09-17-101738--measured-path--corrections.md",
        fragment([("example-alpha:P1-B3", "corrected", None, None)]))])
    result = run_check(tmp_path, manifest(ONE_BUILT), live, record_dir)
    assert result.exit_code == core.EXIT_FINDING, result.stdout + result.stderr
    report = report_of(result)
    assert any("no-before-after" in fid for fid in report["finding_ids"]), report


def test_an_obligation_whose_row_is_absent_is_a_finding(tmp_path):
    """A declared bullet id with no row in the entry is not a clean row.

    The marker is gone, trivially, because there is nothing to carry it -- so a
    check that asked only "is the marker gone" would report this as corrected.
    """
    live = live_store(tmp_path, alpha_rows=["P9-B9: an unrelated figure"])
    record_dir = records(tmp_path, [(
        "2026-09-17-101738--measured-path--corrections.md",
        fragment([CORRECTED_ROW]))])
    result = run_check(tmp_path, manifest(ONE_BUILT), live, record_dir)
    assert result.exit_code == core.EXIT_FINDING, result.stdout + result.stderr
    report = report_of(result)
    assert any("missing-row" in fid for fid in report["finding_ids"]), report


# ---------------------------------------------------------------------------
# Scope: built only, and both fields of the mapping
# ---------------------------------------------------------------------------


def test_a_pending_slug_is_not_under_obligation_yet(tmp_path):
    """A path that has not run owes no correction, and must not be reported.

    Reported the other way round this check would fire on every pending path
    from day one, and a checker that is red before any work starts is a checker
    people learn to ignore.
    """
    payload = manifest([("not-yet-run", "pending", "example-alpha", "P2",
                         ["example-alpha:P2-B1"], [])] + ONE_BUILT)
    live = live_store(tmp_path, alpha_rows=[
        "P1-B3: a measured figure",
        "P2-B1: a figure " + (DESIGNED % "P2")])
    record_dir = records(tmp_path, [(
        "2026-09-17-101738--measured-path--corrections.md",
        fragment([CORRECTED_ROW]))])
    result = run_check(tmp_path, payload, live, record_dir)
    assert result.exit_code == core.EXIT_PASS, result.stdout + result.stderr
    report = report_of(result)
    assert report["checked"] == 1, report
    assert report["obligations"] == 1, report


def test_a_bullet_reached_only_through_backs_bullets_is_still_an_obligation(tmp_path):
    """BOTH mapping fields count, and this one is the live case.

    The expected set splits the mapping in two: `bullets` is what a path is
    responsible for backing, `backs_bullets` is what an already-existing
    artifact is CITED as backing. A check reading only the first would be blind
    to exactly the slug in the real expected set that is already `built` and
    already cited -- a confident zero produced by the scope of the needle rather
    than by the state of the world.
    """
    payload = manifest([("cited-path", "built", "example-beta", None,
                         [], ["example-beta:P5-B3"])])
    live = live_store(tmp_path, beta_rows=[
        "P5-B3: a figure " + (DESIGNED % "P5")])
    # The only built slug in this expected set is `cited-path`, so that is the
    # artifact to point at; the default target names a slug this manifest does
    # not declare, and a scoped check refuses on one.
    result = run_check(tmp_path, payload, live, records(tmp_path),
                       slug="cited-path")
    assert result.exit_code == core.EXIT_FINDING, result.stdout + result.stderr
    report = report_of(result)
    assert report["obligations"] == 1, report
    assert any("example-beta:P5-B3" in fid for fid in report["finding_ids"]), report


# ---------------------------------------------------------------------------
# a design rule: the refusals, and the population line that makes them readable
# ---------------------------------------------------------------------------


def test_zero_built_slugs_refuses_rather_than_passing(tmp_path):
    """The 0/0 trap in its CHECK-20 clothes.

    An expected set with nothing built produces a comparison in which every
    built path has corrected its entry -- vacuously, over no paths at all. That
    sentence is TRUE and it is not a result.
    """
    payload = manifest([("not-yet-run", "pending", "example-alpha", "P2",
                         ["example-alpha:P2-B1"], [])])
    live = live_store(tmp_path, alpha_rows=["P2-B1: a figure"])
    result = run_check(tmp_path, payload, live, records(tmp_path))
    assert result.exit_code == core.EXIT_DID_NOT_RUN, (
        result.stdout + result.stderr)
    report = report_of(result)
    assert report["checked"] == 0, report


def test_a_min_population_override_cannot_buy_a_pass_over_zero(tmp_path):
    """a design rule sets a floor; it may never talk a refusal into a verdict."""
    payload = manifest([("not-yet-run", "pending", "example-alpha", "P2",
                         ["example-alpha:P2-B1"], [])])
    live = live_store(tmp_path, alpha_rows=["P2-B1: a figure"])
    result = run_check(tmp_path, payload, live, records(tmp_path),
                       "--min-population", "0")
    assert result.exit_code == core.EXIT_DID_NOT_RUN, (
        result.stdout + result.stderr)


def test_an_unreachable_live_store_refuses_rather_than_reporting_clean(tmp_path):
    """An entry that cannot be read is not an entry with nothing to correct."""
    payload, _live, record_dir = clean_world(tmp_path)
    missing = Path(tmp_path) / "no-such-store"
    result = run_check(tmp_path, payload, missing, record_dir)
    assert result.exit_code == core.EXIT_DID_NOT_RUN, (
        result.stdout + result.stderr)


def test_the_note_prints_both_populations(tmp_path):
    """Built slugs AND obligations, so neither can stand in for the other."""
    payload, live, record_dir = clean_world(tmp_path)
    result = run_check(tmp_path, payload, live, record_dir)
    report = report_of(result)
    assert "built" in report["note"], report["note"]
    assert "obligation" in report["note"], report["note"]
    assert str(report["obligations"]) in report["note"], report["note"]


def test_a_built_slug_with_no_obligation_is_listed_rather_than_dropped(tmp_path):
    """A slug that owes nothing is a stated fact, never a silent absence.

    The expected set really does carry built slugs that back no claim, and they
    must stay countable: an input that is excluded without being counted is an
    input that was silently dropped.
    """
    payload = manifest(ONE_BUILT + [("backs-nothing", "built", None, None,
                                     [], [])])
    live = live_store(tmp_path, alpha_rows=["P1-B3: a measured figure"])
    record_dir = records(tmp_path, [(
        "2026-09-17-101738--measured-path--corrections.md",
        fragment([CORRECTED_ROW]))])
    result = run_check(tmp_path, payload, live, record_dir)
    assert result.exit_code == core.EXIT_PASS, result.stdout + result.stderr
    report = report_of(result)
    assert report["slugs_without_obligation"] == ["backs-nothing"], report
    assert report["built_slugs"] == 2, report
    assert report["checked"] == 1, report


# ---------------------------------------------------------------------------
# PER-ARTIFACT SCOPE (a design rule's disease, arriving under a second id)
#
# Until an earlier plan these three fail. The check answers about the whole expected
# set whatever directory it is handed, so its report is identical for two
# unrelated artifacts -- measured in an earlier plan and committed at
# _records/pre-fix/, where the redis and es-log captures carry the same CHECK-20
# line byte for byte, including the trailing slug name.
# ---------------------------------------------------------------------------


def test_two_artifacts_do_not_produce_the_same_report(tmp_path):
    """THE discriminating test: a verdict must not travel between artifacts.

    A test that only asserts "CHECK-20 fails" passes today and proves nothing
    about scope. This one builds two built slugs in ONE expected set, one of
    which has corrected its entry and one of which has not, and points the check
    at each in turn. If the check is scoped, exactly one of the two reports
    carries a finding. If it is not, both reports are the same.
    """
    payload = manifest([
        ("measured-path", "built", "example-alpha", "P1",
         ["example-alpha:P1-B3"], []),
        ("other-path", "built", "example-beta", "BP-1",
         ["example-beta:BP-1-B1"], []),
    ])
    # P1-B3 is corrected and recorded; BP-1-B1 still carries its marker.
    live = live_store(
        tmp_path,
        alpha_rows=["P1-B3: a measured figure"],
        beta_rows=["BP-1-B1: a figure " + (DESIGNED % "BP-1")])
    record_dir = records(tmp_path, [(
        "2026-09-17-101738--measured-path--corrections.md",
        fragment([CORRECTED_ROW]))])

    clean = run_check(tmp_path, payload, live, record_dir, slug="measured-path")
    dirty = run_check(tmp_path, payload, live, record_dir, slug="other-path")

    clean_report = report_of(clean)
    dirty_report = report_of(dirty)

    assert clean_report["finding_ids"] != dirty_report["finding_ids"], (
        "both artifacts produced the SAME finding_ids, so the verdict does not "
        "depend on the artifact: %r" % (clean_report["finding_ids"],))
    assert clean.exit_code == core.EXIT_PASS, clean.stdout + clean.stderr
    assert dirty.exit_code == core.EXIT_FINDING, dirty.stdout + dirty.stderr
    assert clean_report["finding_ids"] == [], clean_report
    assert not any("measured-path" in fid for fid in dirty_report["finding_ids"]), (
        "the report for other-path names measured-path: %r"
        % (dirty_report["finding_ids"],))


def test_an_artifact_outside_the_expected_set_refuses(tmp_path):
    """A slug no expected set names is not an artifact this check can judge.

    It must REFUSE rather than pass: a verdict over a slug that does not exist
    is the 0/0 pass wearing a directory name.
    """
    payload, live, record_dir = clean_world(tmp_path)
    result = run_check(tmp_path, payload, live, record_dir,
                       slug="not-in-any-expected-set")
    assert result.exit_code == core.EXIT_DID_NOT_RUN, (
        result.stdout + result.stderr)
    combined = result.stdout + result.stderr
    assert "not-in-any-expected-set" in combined, combined


def test_the_note_names_this_artifacts_obligations_and_the_programme_count(tmp_path):
    """The narrower scope must not hide the wider fact.

    Re-scoping the verdict is right; dropping the programme-level number is a
    population line lying by omission. Both appear, as separate numbers.
    """
    payload = manifest([
        ("measured-path", "built", "example-alpha", "P1",
         ["example-alpha:P1-B3"], []),
        ("other-path", "built", "example-beta", "BP-1",
         ["example-beta:BP-1-B1"], []),
    ])
    live = live_store(
        tmp_path,
        alpha_rows=["P1-B3: a measured figure"],
        beta_rows=["BP-1-B1: a figure " + (DESIGNED % "BP-1")])
    record_dir = records(tmp_path, [(
        "2026-09-17-101738--measured-path--corrections.md",
        fragment([CORRECTED_ROW]))])
    result = run_check(tmp_path, payload, live, record_dir, slug="measured-path")
    report = report_of(result)
    # This artifact owes exactly one obligation and it is satisfied.
    assert report["checked"] == 1, report
    assert report["artifact_obligations"] == 1, report
    assert report["slug_under_test"] == "measured-path", report
    # The programme-wide counts survive as structured fields for a project requirement, and
    # `obligations` keeps its PROGRAMME meaning rather than being narrowed --
    # two built slugs owing one claim each is two, not one. Narrowing a
    # published number in place is how two populations get compared as one.
    assert report["built_slugs"] == 2, report
    assert report["obligations"] == 2, report
    # And both numbers are legible in the note, not just in the JSON.
    assert "built" in report["note"], report["note"]
    assert "obligation" in report["note"], report["note"]


# ---------------------------------------------------------------------------
# The committed fixture, and its pin
# ---------------------------------------------------------------------------


def fixture_root():
    return conftest.broken_fixture(FIXTURE)


def test_the_committed_fixture_reproduces_its_pinned_report(tmp_path):
    """The known-bad fixture, re-run, against the expectation committed beside it."""
    fixture = fixture_root()
    expectation = json.loads(
        (fixture / EXPECTATION_FILE).read_text(encoding="ascii"))
    report_path = Path(tmp_path) / "report.json"
    result = conftest.run_cli(
        [sys.executable, str(CHECK_20), str(fixture / FIXTURE_SLUG),
         "--manifest", str(fixture / "slugs.json"),
         "--live-store", str(fixture / "live"),
         "--records-dir", str(fixture / "corrections"),
         "--report", str(report_path)],
        cwd=REPO_ROOT)
    assert result.exit_code != core.EXIT_PASS, result.stdout + result.stderr
    report = report_of(result)
    measured = {field: report[field] for field in PINNED_FIELDS}
    assert measured == expectation, (
        "the structured report drifted from its committed expectation.\n"
        "  expected: %r\n  measured: %r" % (expectation, measured))


def test_the_fixture_carries_all_three_of_its_own_inputs():
    """A fixture missing one of them would resolve that one somewhere else."""
    fixture = fixture_root()
    for relative in ("slugs.json", "live", "corrections"):
        assert (fixture / relative).exists(), (
            "%s is missing from %s, so the check would resolve it from the "
            "repository instead and the pin would move when unrelated work "
            "landed" % (relative, fixture))
    assert not sorted((fixture / "corrections").glob("*--corrections.md")), (
        "the fixture's records directory carries a fragment; every obligation "
        "in it is supposed to be unrecorded")


# ---------------------------------------------------------------------------
# A RECORD IS A FRAGMENT, NOT ANY .md -- measured 2026-09-20
#
# `read_records` selected on the `.md` suffix, so it read
# `_records/corrections/README.md`, whose worked example is a fenced block
# naming the real claim id. `parse_record` cannot see a fence, so the
# documentation that explains the format SATISFIED the check that reads it: with
# the live marker cleared and no fragment on disk, CHECK-20 reported
# `PASS found=0`, while the same run against an empty directory reported
# `FAIL found=1 no-correction`.
#
# These two tests are a PAIR on purpose. The defect was invisible from a green
# run -- the block the check wanted was supplied by the wrong file -- so proving
# the README is refused is only half of it; the other half proves a correctly
# named fragment with the SAME content is still accepted, which is what stops
# the fix from being a check that refuses everything.
# ---------------------------------------------------------------------------


def test_documentation_in_the_records_directory_cannot_satisfy_the_check(tmp_path):
    """THE RED THIS CATCHES: a README whose example names a real claim."""
    live = live_store(tmp_path, alpha_rows=["P1-B3: a measured figure"])
    record_dir = records(tmp_path, [("README.md", fragment([CORRECTED_ROW]))])
    result = run_check(tmp_path, manifest(ONE_BUILT), live, record_dir)
    assert result.exit_code == core.EXIT_FINDING, result.stdout + result.stderr
    report = report_of(result)
    assert report["found"] == 1, report
    assert "no-correction" in result.stdout, result.stdout
    # Ignored, COUNTED and NAMED. A scan that does not say what it skipped
    # cannot be audited, and this is the file that did the damage.
    assert "records read=0 ignored=1: README.md" in result.stdout, result.stdout


def test_a_correctly_named_fragment_with_that_same_content_is_still_read(tmp_path):
    """The other half of the pair: the fix must not refuse real records."""
    live = live_store(tmp_path, alpha_rows=["P1-B3: a measured figure"])
    record_dir = records(tmp_path, [
        ("README.md", fragment([CORRECTED_ROW])),
        ("2026-09-17-101738--measured-path--corrections.md",
         fragment([CORRECTED_ROW]))])
    result = run_check(tmp_path, manifest(ONE_BUILT), live, record_dir)
    assert result.exit_code == core.EXIT_PASS, result.stdout + result.stderr
    assert report_of(result)["found"] == 0
    assert "records read=1 ignored=1: README.md" in result.stdout, result.stdout
