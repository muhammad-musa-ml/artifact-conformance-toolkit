"""CHECK-05 -- a missing register row, reported as `expected N, found M`.

Every test here runs `tools/checks/check_05.py` AS A SUBPROCESS, by path,
through conftest.run_cli, for the two reasons test_check_01.py and
test_check_03.py do it: by path under a bare module name is exactly how the
vendored copy runs inside an artifact, and the thing under test is an EXIT CODE,
which run_cli returns from the child rather than from a pipeline stage.

WHAT MAKES THE RED IN red-transcripts/CHECK-05.txt A REAL RED. The module is
registered and RUNNABLE in the commit that captures the transcript, with its
detection stubbed to return no finding. It reads the manifest, reads the
committed literal, derives the expected set, locates the register, parses its
rows, probes the status directories and reports a population. Only
`register_findings()` is stubbed. Every failure line in that transcript is
therefore an assertion about a VERDICT, not a module that could not be loaded or
an input that was not there.

THE NUMBER IS NEVER TYPED, AND THAT IS ASSERTED TWO WAYS. Once positively --
the expected count the check prints must equal `counts.register_rows_expected`
read from tools/manifest.json AT TEST TIME, so a manifest edit moves both ends of
the assertion together. Once negatively -- the check's source is grepped for the
literal, because a positive assertion alone is satisfied by a hard-coded constant
that happens to agree today.
"""

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT
CHECKS_DIR = REPO_ROOT / "tools" / "checks"
CHECK_05 = CHECKS_DIR / "check_05.py"
MANIFEST = REPO_ROOT / "tools" / "manifest.json"

FIXTURE = "broken-missing-register-row"
EXPECTATION_FILE = "expected-CHECK-05.json"
OMITTED_SLUG = "alpha-artifact-3"

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


core = _load("frozen_core_for_check_05_tests", REPO_ROOT / "tools" / "canonkit.py")
check_05 = _load("check_05_under_test", CHECK_05)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def live_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def expected_slugs(manifest=None):
    manifest = manifest or live_manifest()
    return sorted(s["slug"] for s in manifest["slugs"] if s.get("register_row"))


def built_slugs(manifest=None):
    manifest = manifest or live_manifest()
    return sorted(s["slug"] for s in manifest["slugs"]
                  if s.get("status") == check_05.STATUS_BUILT)


def scoped_slug(manifest=None):
    """A slug that is BOTH built AND expected to carry a register row.

    Every case below points the check at an artifact directory, and until plan
    an earlier plan it did not matter which one -- the check answered about the whole
    expected set whatever it was handed, so the first built slug was as good as
    any name. That is exactly the defect an earlier plan closes, and the moment the check
    is scoped, the choice becomes load-bearing.

    The first built slug sorts to `example-search-benchmark`, which carries
    `register_row: false` and a recorded `no_row_reason` -- deliberately NOT in
    the expected set, because it genuinely backs no bullet. Pointing a
    per-artifact check at it asks about a row that is correct to be absent, which
    is an earlier plan's NOT-APPLICABLE case and not a verdict this module can give.

    So these tests target a slug whose row the expected set really does require.
    This is derived from the manifest rather than spelled, so it cannot rot when
    a status changes.
    """
    manifest = manifest or live_manifest()
    both = sorted(set(built_slugs(manifest)) & set(expected_slugs(manifest)))
    assert both, (
        "no slug in the expected set is both built and register_row-carrying; "
        "built=%r expected=%r" % (built_slugs(manifest), expected_slugs(manifest)))
    return both[0]


def write_manifest(tmp_path, manifest, name="manifest.json"):
    path = Path(tmp_path) / name
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8", newline="\n")
    return path


def write_register(root, slugs, summary_expected=None, summary_found=None):
    """A register document carrying one `## <slug>` row per entry in `slugs`."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    lines = ["# Backing artifacts register", ""]
    if summary_expected is not None:
        lines.append("- expected %d, found %d"
                     % (summary_expected,
                        summary_found if summary_found is not None else len(slugs)))
        lines.append("")
    for slug in slugs:
        lines.append("## %s" % slug)
        lines.append("")
        lines.append("### Similarity judgment")
        lines.append("")
        lines.append("Test row.")
        lines.append("")
    path = root / check_05.REGISTER_NAME
    path.write_text("\n".join(lines).rstrip("\n") + "\n",
                    encoding="ascii", newline="\n")
    return path


def make_artifacts_root(tmp_path, manifest=None, slugs=None, name="artifacts",
                        present_dirs=None, summary_expected=None,
                        summary_found=None):
    """An artifacts root holding a register and the `built` slug directories."""
    manifest = manifest or live_manifest()
    root = Path(tmp_path) / name
    root.mkdir(parents=True, exist_ok=True)
    rows = expected_slugs(manifest) if slugs is None else slugs
    write_register(root, rows, summary_expected, summary_found)
    dirs = built_slugs(manifest) if present_dirs is None else present_dirs
    for slug in dirs:
        (root / slug).mkdir(parents=True, exist_ok=True)
        (root / slug / ".keep").write_text("", encoding="ascii", newline="\n")
    return root


def run_check(artifact, *extra, **kwargs):
    argv = [sys.executable, str(CHECK_05), str(artifact)]
    report = kwargs.pop("report", None)
    if report is not None:
        argv += ["--report", str(report)]
    argv += [str(token) for token in extra]
    assert not kwargs, "unexpected kwargs %r" % sorted(kwargs)
    return conftest.run_cli(argv, cwd=REPO_ROOT)


def kinds(report):
    return sorted({finding["kind"] for finding in report["findings"]})


# ---------------------------------------------------------------------------
# The expected number is READ, not typed
# ---------------------------------------------------------------------------


def test_the_expected_count_equals_the_manifests_committed_literal(tmp_path):
    """Read at TEST time, so a manifest edit moves both ends together."""
    literal = live_manifest()["counts"]["register_rows_expected"]
    root = make_artifacts_root(tmp_path)
    result = run_check(root / scoped_slug(), report=tmp_path / "live.json")
    assert result.report is not None, result.stdout
    assert result.report["expected"] == literal, (
        "the check reported expected=%r against a manifest literal of %r\n%s"
        % (result.report["expected"], literal, result.stdout))
    assert result.report["expected_literal"] == literal, result.report
    assert "expected %d," % literal in result.stdout, result.stdout


def test_the_expected_count_is_not_typed_into_the_check_source():
    """The negative half. A positive assertion alone passes over a constant
    that happens to agree today."""
    literal = live_manifest()["counts"]["register_rows_expected"]
    source = CHECK_05.read_text(encoding="ascii")
    pattern = re.compile(r"\b%d\b" % literal)
    hits = [line for line in source.splitlines() if pattern.search(line)]
    assert not hits, (
        "tools/checks/check_05.py carries the literal %d on %d line(s): %r. The "
        "expected count is READ from the manifest; a copy here is a third value "
        "that can drift from both and the drift would be invisible."
        % (literal, len(hits), hits[:5]))


# ---------------------------------------------------------------------------
# The verdicts
# ---------------------------------------------------------------------------


def test_a_missing_row_is_a_finding_naming_the_slug(tmp_path):
    """RE-KEYED by an earlier plan: the ABSENT row is now the artifact's OWN.

    This used to omit OMITTED_SLUG and point the check somewhere else, which was
    a sound test of a programme-scoped check and is a vacuous one of a scoped
    check -- a missing row belonging to another slug is that slug's finding.
    What the test discriminates is unchanged: a register short a row must not
    read as a complete one.
    """
    absent = scoped_slug()
    rows = [slug for slug in expected_slugs() if slug != absent]
    root = make_artifacts_root(tmp_path, slugs=rows)
    result = run_check(root / absent, report=tmp_path / "missing.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert "register:missing-row:%s" % absent in result.report["finding_ids"], (
        result.report["finding_ids"])
    assert result.report["found_rows"] == len(rows), result.report


def test_the_check_counts_rows_rather_than_believing_the_documents_own_summary(tmp_path):
    """The shortcut the requirement's own wording invites.

    `expected N, found M` reads like two numbers to print, and the shortest way
    to print them is to read them off the document. This register CLAIMS the
    full count in its own summary line while carrying one row fewer.
    """
    literal = live_manifest()["counts"]["register_rows_expected"]
    absent = scoped_slug()
    rows = [slug for slug in expected_slugs() if slug != absent]
    root = make_artifacts_root(tmp_path, slugs=rows, summary_expected=literal,
                               summary_found=literal)
    register = (root / check_05.REGISTER_NAME).read_text(encoding="ascii")
    assert "found %d" % literal in register, (
        "the fixture register no longer lies about its own row count, so this "
        "test asserts nothing")
    result = run_check(root / absent, report=tmp_path / "liar.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert result.report["found_rows"] == len(rows), (
        "the check believed the document's summary line (%r) instead of counting "
        "its rows (%d)" % (result.report["found_rows"], len(rows)))


def test_an_extra_row_for_an_unexpected_slug_is_a_finding(tmp_path):
    """Without this the set comparison collapses back into a count comparison."""
    absent = scoped_slug()
    rows = [slug for slug in expected_slugs() if slug != absent]
    rows.append("not-a-manifest-slug")
    root = make_artifacts_root(tmp_path, slugs=sorted(rows))
    result = run_check(root / absent, report=tmp_path / "extra.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    ids = result.report["finding_ids"]
    # extra-row stays PROGRAMME-wide (it can never be about the slug under test,
    # which would have refused above); missing-row is the SCOPED one, so the
    # omitted row has to be this artifact's for both halves to fire.
    assert "register:extra-row:not-a-manifest-slug" in ids, ids
    assert "register:missing-row:%s" % absent in ids, ids
    assert len(result.report["rows"]) == live_manifest()["counts"][
        "register_rows_expected"], (
        "the row COUNT is right and the row SET is wrong -- exactly the state a "
        "count comparison reports as clean")


def test_a_complete_register_passes(tmp_path):
    root = make_artifacts_root(tmp_path)
    result = run_check(root / scoped_slug(), report=tmp_path / "ok.json")
    assert result.exit_code == core.EXIT_PASS, result.stdout
    assert result.report["found"] == 0, result.report["findings"]


# ---------------------------------------------------------------------------
# PER-ARTIFACT SCOPE (a design rule, and an earlier plan open item 9)
#
# Until an earlier plan the first two of these fail. The check delivers a verdict
# about the WHOLE expected set while pointed at one artifact, so it reports
# `expected 12, found 1` identically on redis and on es-log -- a programme-level
# fact about eleven paths nobody has built, which no per-artifact fix can move
# and which no artifact can therefore clear. Measured in an earlier plan and
# committed at _records/pre-fix/.
# ---------------------------------------------------------------------------


def test_this_slugs_row_present_passes_even_when_every_other_row_is_missing(tmp_path):
    """The live defect, in one test.

    The register carries exactly ONE row -- this artifact's -- and the expected
    set names twelve. Today that is `expected 12, found 1` and a FINDING. It is
    the correct answer to a question nobody asked: the artifact in front of the
    check is complete, and eleven paths that have not been built yet cannot be
    made to appear by anything this artifact does.
    """
    slug = scoped_slug()
    root = make_artifacts_root(tmp_path, slugs=[slug])
    result = run_check(root / slug, report=tmp_path / "scoped.json")
    assert result.exit_code == core.EXIT_PASS, (
        "the artifact's own row is present and correct, so a check scoped to "
        "the artifact must PASS\n%s" % (result.stdout + result.stderr))
    report = result.report
    assert report["checked"] == 1, report
    assert report["found"] == 0, report["findings"]


def test_a_built_slug_with_no_row_is_a_finding_naming_only_itself(tmp_path):
    """Scoped does not mean blind: this artifact's own missing row still fails.

    And the finding must name THIS slug and no other -- a report that names a
    sibling is the verdict travelling between artifacts again, one level down.
    """
    slug = scoped_slug()
    others = [s for s in expected_slugs() if s != slug]
    root = make_artifacts_root(tmp_path, slugs=others)
    result = run_check(root / slug, report=tmp_path / "missing.json")
    assert result.exit_code == core.EXIT_FINDING, (
        result.stdout + result.stderr)
    report = result.report
    assert report["checked"] == 1, report
    named = {finding.get("slug") for finding in report["findings"]}
    assert named == {slug}, (
        "the report names slugs other than the artifact under test: %r" % (named,))


def test_an_artifact_outside_the_expected_set_refuses(tmp_path):
    """A directory no expected set names is not an artifact this check judges.

    Refuse, with the slug in the reason. Passing would be a verdict over a slug
    that does not exist, which is the 0/0 pass wearing a directory name.
    """
    root = make_artifacts_root(tmp_path)
    stray = root / "not-in-any-expected-set"
    stray.mkdir(parents=True, exist_ok=True)
    result = run_check(stray, report=tmp_path / "stray.json")
    assert result.exit_code == core.EXIT_DID_NOT_RUN, (
        result.stdout + result.stderr)
    combined = result.stdout + result.stderr
    assert "not-in-any-expected-set" in combined, combined


# ---------------------------------------------------------------------------
# Could not look
# ---------------------------------------------------------------------------


def test_an_expected_set_of_zero_is_did_not_run_not_a_pass(tmp_path):
    """`expected 0, found 0` is the 0/0 pass wearing a different hat."""
    manifest = live_manifest()
    for slug in manifest["slugs"]:
        slug["register_row"] = False
        slug.setdefault("no_row_reason", "filtered to zero by this test")
    manifest["counts"]["register_rows_expected"] = 0
    path = write_manifest(tmp_path, manifest)
    root = make_artifacts_root(tmp_path, manifest=manifest, slugs=[])
    result = run_check(root / scoped_slug(), "--manifest", path,
                       report=tmp_path / "zero.json")
    assert result.exit_code == core.EXIT_DID_NOT_RUN, result.stdout


def test_no_min_population_override_can_buy_a_pass_over_zero(tmp_path):
    """The floor is consulted AFTER the zero refusal, never instead of it."""
    manifest = live_manifest()
    for slug in manifest["slugs"]:
        slug["register_row"] = False
    manifest["counts"]["register_rows_expected"] = 0
    path = write_manifest(tmp_path, manifest)
    root = make_artifacts_root(tmp_path, manifest=manifest, slugs=[])
    result = run_check(root / scoped_slug(), "--manifest", path,
                       "--min-population", "0", report=tmp_path / "bought.json")
    assert result.exit_code == core.EXIT_DID_NOT_RUN, (
        "--min-population 0 talked the check into a pass over a population of "
        "nothing\n%s" % result.stdout)


def test_an_absent_register_is_did_not_run(tmp_path, monkeypatch):
    """The check could not look, so it refuses rather than giving a verdict.

    RE-KEYED BY AN EARLIER PLAN, AND THE REASON IS THE WHOLE POINT OF THE TEST.

    This used to build a tmp root with no register, shell out to the CLI, and
    expect 2. Its docstring called that "the programme's CORRECT state today:
    nothing has run, so nothing is published". Something HAS now run and a
    register IS published -- `<repo>/backing-artifacts.md`, the tracked copy --
    and `resolve_register` has THREE candidates, of which that is the second.
    So a tmp root with no register no longer produces an absent register: the
    resolver falls through to the repository's own copy, and the check returned
    PASS over a synthetic empty tree while printing `artifacts-root=<the tmp
    root>` beside a verdict read from somewhere else entirely.

    The old test could only ever have passed while that second candidate did
    not exist on disk. It was green for three phases because the file was
    missing, not because the branch was covered -- an absence supplying the
    result the assertion read as a measurement.

    So the absence is made REAL for every candidate, by pointing SOURCE_ROOT at
    an empty directory for the duration. `resolve_register` reads the global at
    call time, so this reaches the code under test rather than a copy of it.

    The CLI's `REFUSING:`-on-stderr half moves to
    test_an_absent_manifest_is_did_not_run, which exercises the same printing
    path through a refusal this repository's own tree cannot satisfy.
    """
    root = Path(tmp_path) / "no-register"
    for slug in built_slugs():
        (root / slug).mkdir(parents=True, exist_ok=True)

    elsewhere = Path(tmp_path) / "empty-source-root"
    elsewhere.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(check_05, "SOURCE_ROOT", str(elsewhere))

    # DISCRIMINATING: assert the premise before asserting the conclusion. If any
    # candidate still resolves, the refusal below would be about something else.
    assert check_05.resolve_register(
        str(root / scoped_slug()), str(root)) is None, (
        "a register is still reachable, so this test is not exercising the "
        "absent branch it is named for")

    # THE MANIFEST IS PASSED EXPLICITLY, and leaving it out was a trap the
    # premise assertion above did not cover. SOURCE_ROOT anchors
    # default_manifest_path() too, so moving it aside also hides the expected
    # set -- and the check then refuses for the WRONG REASON, with exit code 2
    # either way. A test asserting only the code would have gone green over a
    # branch it never reached.
    result = check_05.run(str(root / scoped_slug()),
                          manifest_path=str(MANIFEST),
                          artifacts_root=str(root))
    assert result.code == core.EXIT_DID_NOT_RUN, (
        "an unreachable register did not refuse: code=%r note=%r"
        % (result.code, result.note))
    assert check_05.REGISTER_NAME in result.note, (
        "the refusal does not name what it could not find, so it is refusing "
        "for some other reason: %r" % result.note)


def test_an_absent_manifest_is_did_not_run(tmp_path):
    """A vendored copy inside an artifact cannot reach the expected set."""
    root = make_artifacts_root(tmp_path)
    result = run_check(root / scoped_slug(),
                       "--manifest", tmp_path / "nothing-here.json",
                       report=tmp_path / "nomanifest.json")
    assert result.exit_code == core.EXIT_DID_NOT_RUN, result.stdout


# ---------------------------------------------------------------------------
# Excluded slugs are printed with their reasons
# ---------------------------------------------------------------------------


def test_the_excluded_count_and_every_reason_appear_in_the_output(tmp_path):
    manifest = live_manifest()
    excluded = [s for s in manifest["slugs"] if not s.get("register_row")]
    assert excluded, "the live manifest excludes nothing, so this asserts nothing"
    root = make_artifacts_root(tmp_path)
    result = run_check(root / scoped_slug(), report=tmp_path / "excl.json")
    assert "excluded: %d (reasons recorded)" % len(excluded) in result.stdout, (
        result.stdout)
    for slug in excluded:
        assert slug["slug"] in result.stdout, (
            "excluded slug %r was dropped silently" % slug["slug"])
        reason = (slug.get("no_row_reason") or "").split(".")[0]
        if reason:
            assert reason[:40] in result.stdout, (
                "excluded slug %r printed without its reason" % slug["slug"])
    assert result.report["not_examined"] == len(excluded), result.report


# ---------------------------------------------------------------------------
# The status rule -- the three anti-silencer rules for `status`
# ---------------------------------------------------------------------------


def test_a_pending_slug_whose_directory_exists_is_a_finding(tmp_path):
    """the status rule, rule one: something was built and the expected set was not told."""
    manifest = live_manifest()
    pending = sorted(s["slug"] for s in manifest["slugs"]
                     if s.get("status") == check_05.STATUS_PENDING)
    assert pending, "the live manifest has no pending slug"
    stale = pending[0]
    root = make_artifacts_root(tmp_path,
                               present_dirs=built_slugs() + [stale])
    result = run_check(root / scoped_slug(), report=tmp_path / "stale.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert "register:stale-pending:%s" % stale in result.report["finding_ids"], (
        result.report["finding_ids"])


def test_a_built_slug_whose_directory_is_missing_is_a_finding(tmp_path):
    """the status rule, rule two: the manifest claims a build that is not on disk."""
    built = built_slugs()
    root = make_artifacts_root(tmp_path, present_dirs=built[1:])
    # RE-KEYED by an earlier plan: `anything` is not a slug any expected set names, so a
    # scoped check refuses before it can report. Point at a real one whose own
    # directory DOES exist -- the finding under test is about a DIFFERENT slug,
    # and missing-built stays programme-wide precisely because a slug with no
    # directory can never be the artifact a run is pointed at.
    result = run_check(root / scoped_slug(), report=tmp_path / "unbuilt.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert "register:missing-built:%s" % built[0] in result.report["finding_ids"], (
        result.report["finding_ids"])


def test_pending_reaching_zero_prints_the_closeout_criterion(tmp_path):
    """the status rule, rule three: a project requirement's milestone is read off the run, not tracked by
    hand."""
    manifest = live_manifest()
    for slug in manifest["slugs"]:
        slug["status"] = check_05.STATUS_BUILT
    manifest["counts"]["built_expected"] = len(manifest["slugs"])
    manifest["counts"]["pending_expected"] = 0
    path = write_manifest(tmp_path, manifest)
    everything = sorted(s["slug"] for s in manifest["slugs"])
    root = make_artifacts_root(tmp_path, manifest=manifest,
                               present_dirs=everything)
    # THE RUN IS POINTED AT A SLUG THAT CARRIES A REGISTER ROW, not at the
    # alphabetically first one. A scoped check refuses -- correctly, with
    # DID-NOT-RUN -- when it is aimed at a `register_row: false` slug, and
    # there is no verdict to read a closeout note off. `everything[0]` happened
    # to be a register-row slug and was never required to be one, so this
    # passed for a reason nobody had asserted; renaming a slug in an unrelated
    # change moved a `register_row: false` entry to the front of sorted order
    # and the assertion failed with a message about the wrong subject. The
    # directories still cover EVERY slug, because the closeout figure under
    # test is programme-wide.
    scoped = expected_slugs(manifest)
    assert scoped, "no slug in the expected set carries a register row"
    result = run_check(root / scoped[0], "--manifest", path,
                       report=tmp_path / "closeout.json")
    assert "pending reached 0" in result.stdout, result.stdout
    assert "a project requirement" in result.stdout, result.stdout
    assert result.report["pending"] == 0, result.report


def test_the_check_never_writes_the_status_field(tmp_path):
    """`status` is owner-set and plan-set. A checker the thing being checked can
    edit is not a checker -- the same posture a design rule gives waivers."""
    manifest = live_manifest()
    path = write_manifest(tmp_path, manifest)
    before = path.read_bytes()
    root = make_artifacts_root(tmp_path, present_dirs=built_slugs()
                               + [s["slug"] for s in manifest["slugs"]
                                  if s.get("status") == check_05.STATUS_PENDING])
    run_check(root / scoped_slug(), "--manifest", path,
              report=tmp_path / "nowrite.json")
    assert path.read_bytes() == before, (
        "the check rewrote the expected set it was reading")
    source = CHECK_05.read_text(encoding="ascii")
    assert 'json.dump' not in source, (
        "check_05.py carries a JSON WRITE. It reads the expected set and must "
        "never author it.")


# ---------------------------------------------------------------------------
# The manifest's own derive-and-assert
# ---------------------------------------------------------------------------


def test_a_manifest_whose_literal_disagrees_with_its_derivation_is_a_finding(tmp_path):
    """THAT disagreement is the finding, never a value to pick between."""
    manifest = live_manifest()
    manifest["counts"]["register_rows_expected"] += 1
    path = write_manifest(tmp_path, manifest)
    root = make_artifacts_root(tmp_path, manifest=manifest)
    result = run_check(root / scoped_slug(), "--manifest", path,
                       report=tmp_path / "drift.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert any(fid.startswith("register:manifest-drift:")
               for fid in result.report["finding_ids"]), result.report["finding_ids"]


# ---------------------------------------------------------------------------
# The committed fixture and its anti-rot pin
# ---------------------------------------------------------------------------


def test_the_committed_fixture_fails_with_exactly_one_finding(tmp_path):
    fixture = conftest.broken_fixture(FIXTURE)
    result = run_check(fixture / OMITTED_SLUG, report=tmp_path / "fix.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert result.report["finding_ids"] == [
        "register:missing-row:%s" % OMITTED_SLUG], result.report["finding_ids"]
    assert result.report["found"] == 1, (
        "the fixture carries more than one defect, so \"CHECK-05 refused it\" "
        "cannot say which one did the refusing: %r" % result.report["findings"])


def test_the_register_is_found_at_the_artifacts_roots_own_root(tmp_path):
    """The scope half of the measured search-negative failure: a resolver that
    only searched <artifacts-root>/<slug>/ would miss the aggregate file at
    <artifacts-root>'s own root."""
    fixture = conftest.broken_fixture(FIXTURE)
    register = fixture / check_05.REGISTER_NAME
    assert register.is_file(), register
    result = run_check(fixture / OMITTED_SLUG, report=tmp_path / "where.json")
    assert Path(result.report["register"]) == register.resolve(), (
        result.report["register"])


def test_every_file_in_the_fixture_is_tracked():
    """Present is not tracked. A fixture git never saw is a fixture a fresh
    clone does not have."""
    fixture = conftest.broken_fixture(FIXTURE)
    on_disk = sorted(
        p.relative_to(REPO_ROOT).as_posix()
        for p in fixture.rglob("*") if p.is_file())
    listed = subprocess.run(
        ["git", "ls-files", "--", fixture.relative_to(REPO_ROOT).as_posix()],
        cwd=str(REPO_ROOT), capture_output=True, text=True, shell=False)
    tracked = sorted(line.strip() for line in listed.stdout.splitlines()
                     if line.strip())
    assert on_disk, "the fixture holds no files"
    missing = [path for path in on_disk if path not in tracked]
    assert not missing, (
        "%d fixture file(s) are present but UNTRACKED: %r. git ls-files returned "
        "%d path(s)." % (len(missing), missing, len(tracked)))


def test_the_anti_rot_pin_holds_for_the_known_bad_fixture(tmp_path):
    fixture = conftest.broken_fixture(FIXTURE)
    expectation_path = fixture / EXPECTATION_FILE
    assert expectation_path.is_file(), (
        "%s carries no %s, so its RED evidence has nothing pinning it"
        % (FIXTURE, EXPECTATION_FILE))
    expected = json.loads(expectation_path.read_text(encoding="ascii"))

    result = run_check(fixture / OMITTED_SLUG, report=tmp_path / "pin.json")
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
    prose = sorted(set(expected) & set(PROSE_FIELDS))
    assert not prose, (
        "the pin holds wording-bearing field(s) %r, so the first error-message "
        "improvement breaks it and the standard repair empties the mechanism"
        % prose)


# ---------------------------------------------------------------------------
# Protocol and population
# ---------------------------------------------------------------------------


def trimmed_manifest(keep=3):
    """A supplied expected set the DISK copy does not match, so the two cannot be
    confused for one another."""
    manifest = live_manifest()
    manifest["slugs"] = [s for s in manifest["slugs"] if s.get("register_row")][:keep]
    manifest["counts"]["register_rows_expected"] = keep
    manifest["counts"]["built_expected"] = len(
        [s for s in manifest["slugs"] if s.get("status") == check_05.STATUS_BUILT])
    manifest["counts"]["pending_expected"] = len(
        [s for s in manifest["slugs"] if s.get("status") == check_05.STATUS_PENDING])
    return manifest


def test_the_runners_supplied_expected_set_is_preferred_over_a_second_disk_read(tmp_path):
    """conformance.py resolves the expected set ONCE and hands it to every check
    through CheckContext(manifest=...). Re-reading it from disk would give this
    check a SECOND source of truth that can disagree with the one the runner
    printed its scan root from -- and the disagreement would be silent, because
    both reads succeed."""
    contract = check_05.load_contract()
    manifest = trimmed_manifest()
    rows = expected_slugs(manifest)
    root = make_artifacts_root(tmp_path, manifest=manifest, slugs=rows,
                               present_dirs=built_slugs(manifest))

    result = check_05.run(root / rows[0], contract.CheckContext(manifest=manifest))
    # RE-KEYED by an earlier plan. `checked` used to be the size of the expected set and
    # was therefore a usable proxy for WHICH manifest was read; it is now always
    # 1, the artifact's own row, so it can no longer discriminate. The programme
    # count survives in detail for exactly this kind of reader, and it is what
    # the precedence question was ever really asking about.
    assert result.detail["expected"] == len(rows), (
        "the check re-read the disk manifest instead of using the one the runner "
        "supplied: %r" % result.note)
    assert "supplied by the runner" in result.detail["manifest"], result.detail
    assert result.code == core.EXIT_PASS, result.detail["findings"]


def test_an_explicit_manifest_argument_beats_the_supplied_one(tmp_path):
    """A caller naming a file means it."""
    contract = check_05.load_contract()
    path = write_manifest(tmp_path, live_manifest())
    root = make_artifacts_root(tmp_path)

    result = check_05.run(root / scoped_slug(),
                          contract.CheckContext(manifest=trimmed_manifest()),
                          manifest_path=path)
    literal = live_manifest()["counts"]["register_rows_expected"]
    # RE-KEYED by an earlier plan, same reason as the test above: `checked` is the
    # artifact's own row now, so the programme count is what says which manifest
    # won.
    assert result.detail["expected"] == literal, result.note
    assert "supplied by the runner" not in result.detail["manifest"], result.detail


def test_the_module_satisfies_the_check_protocol():
    assert check_05.CHECK_ID == "CHECK-05"
    assert isinstance(check_05.DEFAULT_FLOOR, int)
    assert callable(check_05.run)
    contract = check_05.load_contract()
    assert check_05.CHECK_ID in contract.DECLARED_CHECK_IDS


def test_discovery_finds_the_module():
    contract = check_05.load_contract()
    report = contract.discover(CHECKS_DIR, verbose=False)
    assert "CHECK-05" in report.ids, report.ids
    assert not report.protocol_violations, report.protocol_violations


def test_the_population_floor_override_prints_and_demotes(tmp_path):
    """a design rule: the EFFECTIVE floor is what prints, or the line lies about what it
    applied."""
    root = make_artifacts_root(tmp_path)
    result = run_check(root / scoped_slug(), "--min-population", "9999",
                       report=tmp_path / "floor.json")
    assert result.report["floor"] == 9999, result.report
    assert "floor=9999" in result.stdout, result.stdout
    assert result.exit_code == core.EXIT_DID_NOT_RUN, result.stdout


def test_the_summary_prints_the_built_pending_and_row_counts(tmp_path):
    """The status rule's printed form: built N of 14, pending M, rows N of 12."""
    manifest = live_manifest()
    total = len(manifest["slugs"])
    built = len(built_slugs())
    pending = total - built
    literal = manifest["counts"]["register_rows_expected"]
    root = make_artifacts_root(tmp_path)
    result = run_check(root / scoped_slug(), report=tmp_path / "summary.json")
    assert "built %d of %d" % (built, total) in result.stdout, result.stdout
    assert "pending %d" % pending in result.stdout, result.stdout
    assert "rows %d of %d" % (literal, literal) in result.stdout, result.stdout
    assert result.report["slugs_probed"] == total, result.report
