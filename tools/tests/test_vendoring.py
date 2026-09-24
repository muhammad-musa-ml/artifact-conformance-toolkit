"""Vendoring by copy-and-assert: tampering FAILS, staleness is COUNTED.

The three comparisons vendor.audit() keeps apart are the subject of most of
this module. Collapsing them would leave a check that passes on a tampered copy
because it was also stale, or fails a correctly pinned artifact because the
repository moved -- the check-that-cannot-discriminate shape, in the one tool
whose job is discriminating.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools import vendor
from tools.tests import conftest
from tools.tests.test_canonkit import load_core

REPO_ROOT = conftest.REPO_ROOT
core = load_core()


# ---------------------------------------------------------------------------
# The declared set and its committed literal
# ---------------------------------------------------------------------------


def test_the_vendored_set_literal_matches_the_declaration():
    assert vendor.VENDORED_SET_COUNT == len(vendor.VENDORED_SET) == 5


def test_dropping_a_name_from_the_set_makes_the_literal_assertion_raise(tmp_path):
    """a design rule's tripwire, demonstrated rather than asserted.

    A purely derived count stops checking the moment its input shrinks, because
    expected falls to match found. The literal is the tripwire on the
    derivation's own input, so it must FAIL when the derivation changes alone.
    """
    source = (REPO_ROOT / "tools" / "vendor.py").read_text(encoding="ascii")
    needle = '    "tools/render.py",'
    assert any(line.startswith(needle) for line in source.splitlines()), (
        "the declared set no longer looks as expected"
    )
    mangled = tmp_path / "vendor_mangled.py"
    mangled.write_text(
        "\n".join(line for line in source.splitlines()
                  if not line.startswith(needle)) + "\n",
        encoding="ascii", newline="\n")

    argv = [sys.executable, "-c",
            "import importlib.util,sys;"
            "spec=importlib.util.spec_from_file_location('m', r'%s');"
            "mod=importlib.util.module_from_spec(spec);"
            "spec.loader.exec_module(mod)" % mangled]
    result = conftest.run_cli(argv, cwd=tmp_path)
    assert result.exit_code != 0, "a shrunken declaration was accepted"
    assert "VENDORED_SET_COUNT" in result.stderr, result.stderr
    assert "4" in result.stderr and "5" in result.stderr, result.stderr


def test_conformance_is_in_the_declared_set():
    """a design rule: a handed-over directory must SELF-CHECK with no access to this repo."""
    assert "tools/conformance.py" in vendor.VENDORED_SET
    assert "tools/canonkit.py" in vendor.VENDORED_SET


def test_the_check_module_that_reads_the_live_store_never_ships():
    """The glob's exclusion, pinned by NAME rather than by count.

    A vendored artifact is a directory that may be handed to someone outside
    this programme. check_20.py reads the owner's live collections entries: it
    knows where that private record lives, how its rows are keyed and what its
    not-yet-measured disclosure says. Shipping it inside an artifact would put
    the shape of a private record into a repository whose whole point is that a
    stranger can read it.

    Asserted on three axes, because each one fails differently:

      the declaration   the module is NAMED as excluded, with a reason
      the derivation    check_modules() really does leave it out
      the population    what ships is strictly smaller than what is on disk,
                        by exactly the number of declared exclusions

    The third is what stops this from passing vacuously if the declaration is
    emptied: an exclusion set of zero would make the first two assertions
    unreachable and this one false.
    """
    excluded_names = sorted(vendor.NOT_VENDORED_CHECKS)
    assert excluded_names == ["check_20.py"], excluded_names
    for name, reason in vendor.NOT_VENDORED_CHECKS.items():
        assert reason.strip(), "%s is excluded with no reason recorded" % name

    shipped = vendor.check_modules()
    on_disk = vendor._all_check_modules()
    excluded = vendor.excluded_check_modules()

    assert "tools/checks/check_20.py" in on_disk, on_disk
    assert "tools/checks/check_20.py" not in shipped, shipped
    assert "tools/checks/check_20.py" not in vendor.resolve_vendored_set()
    assert excluded, "no exclusion is derived, so the assertions above are vacuous"
    assert len(on_disk) - len(shipped) == len(excluded), (
        "%d module(s) on disk, %d shipped, %d declared exclusion(s): the "
        "difference is not accounted for" % (len(on_disk), len(shipped),
                                             len(excluded)))


def test_a_vendored_artifact_records_what_deliberately_did_not_ship(tmp_path):
    """The artifact's own record answers "excluded, or did the vendoring break?".

    Without this the two are indistinguishable from inside the artifact, and the
    natural reading of a missing checker is that something went wrong.
    """
    artifact = tmp_path / "some-artifact"
    artifact.mkdir()
    report = vendor.vendor_into(artifact)
    record = json.loads(
        (artifact / vendor.VENDOR_RECORD_NAME).read_text(encoding="ascii"))

    assert record["excluded_check_count"] == len(vendor.excluded_check_modules())
    assert record["excluded_check_count"] > 0, (
        "nothing is recorded as excluded, so this assertion checks nothing")
    sources = [row["source"] for row in record["excluded_checks"]]
    assert "tools/checks/check_20.py" in sources, record["excluded_checks"]
    for row in record["excluded_checks"]:
        assert row["reason"].strip(), row
        assert row["source"] not in record["declared"], (
            "%s is recorded as both shipped and excluded" % row["source"])
    assert not (artifact / "checks" / "check_20.py").exists(), (
        "the excluded module was copied anyway")
    assert report.declared == len(record["declared"])


def test_the_audit_counts_and_names_what_deliberately_did_not_ship(
        tmp_path, capsys):
    """An exclusion nobody counts is an exclusion nobody can audit.

    The record carries it, and until this was added the AUDIT never read it out:
    both lines printed `checked=14 of 14` over a population the glob had
    silently narrowed by one, and a reader had to open the record by hand to
    learn that a check is missing ON PURPOSE rather than because the vendoring
    broke. Every input not examined is counted and given a reason beside it --
    which is the same rule every check module already holds itself to.
    """
    artifact, _ = _vendored(tmp_path, "audited-artifact")
    report = vendor.audit([artifact], core=core)
    out = capsys.readouterr().out

    verdict = report.artifacts[0]
    assert verdict.excluded, (
        "the audit derived no exclusion, so every assertion below is vacuous")
    assert [source for source, _reason in verdict.excluded] == [
        "tools/checks/check_20.py"], verdict.excluded
    assert all(reason.strip() for _source, reason in verdict.excluded), (
        "an exclusion is reported with no reason beside it")

    assert "not-vendored=%d" % len(verdict.excluded) in out, out
    assert "tools/checks/check_20.py" in out, out

    # It is a DECLARATION, not a verdict, so it must not become a fourth code:
    # inventing a finding out of a decision already made, or adding a PASS that
    # inflates the counts line without measuring anything, are both worse than
    # the silence this replaced.
    assert "core current 1 of 1" in out, out
    assert "checks: 2 pass, 0 finding, 0 did-not-run" in out, out


def test_an_artifact_declaring_no_exclusion_still_prints_the_zero(
        tmp_path, capsys):
    """Silence and a measured zero must not render identically.

    A record with an empty exclusion list is a real answer -- nothing was held
    back -- and an audit that simply says nothing about exclusions is not. The
    count prints on both branches for the same reason every population line in
    this repository does.
    """
    artifact, _ = _vendored(tmp_path, "no-exclusions-artifact")
    path = artifact / vendor.VENDOR_RECORD_NAME
    record = json.loads(path.read_text(encoding="ascii"))
    record["excluded_checks"] = []
    record["excluded_check_count"] = 0
    path.write_text(json.dumps(record, indent=2, sort_keys=True),
                    encoding="ascii", newline="\n")

    report = vendor.audit([artifact], core=core)
    out = capsys.readouterr().out

    assert report.artifacts[0].excluded == [], report.artifacts[0].excluded
    assert "not-vendored=0" in out, out
    assert "check_20.py" not in out, (
        "a module the record does not exclude was reported as excluded:\n%s" % out)
    # The zero is about the RECORD, never about this repository's current tree.
    assert vendor.excluded_check_modules(), (
        "the repository derives no exclusion, so this artifact's zero could "
        "have come from either side and the test proves nothing")


def test_the_copy_path_is_binary_not_text_mode():
    """A text-mode round trip re-translates line endings and breaks the assertion."""
    source = (REPO_ROOT / "tools" / "vendor.py").read_text(encoding="ascii")
    assert 'open(path, "wb")' in source
    assert 'open(path, "rb")' in source
    assert "shutil" not in source, (
        "shutil's copy helpers were introduced; the copy path must stay an "
        "explicit binary read/write so nothing can silently become text mode"
    )


def test_destination_strips_the_tools_prefix():
    assert vendor.destination_name("tools/canonkit.py") == "canonkit.py"
    assert vendor.destination_name("tools/checks/__init__.py") == "checks/__init__.py"


# ---------------------------------------------------------------------------
# vendor_into
# ---------------------------------------------------------------------------


def _vendored(tmp_path, name="demo-artifact"):
    artifact = Path(tmp_path) / name
    artifact.mkdir(parents=True, exist_ok=True)
    report = vendor.vendor_into(artifact, core=core)
    return artifact, report


def test_vendor_into_copies_the_present_files_and_records_every_number(tmp_path):
    artifact, report = _vendored(tmp_path)
    assert report.count >= 2, report.copied
    assert "canonkit.py" in report.copied
    assert "checks/__init__.py" in report.copied
    assert (artifact / "canonkit.py").is_file()
    assert (artifact / "checks" / "__init__.py").is_file()

    # Absent SOURCES are counted with a reason, never silently dropped: the
    # remaining ones arrive in later plans and an audit compares against this
    # record, not against the declaration.
    #
    # RE-KEYED BY AN EARLIER PLAN, the plan that created tools/render.py. This used
    # to read `sorted(report.missing_sources) == ["tools/conformance.py",
    # "tools/render.py"]`. That literal is a pin on a MOMENT rather than on a
    # property: it goes red in the commit that lands each remaining file, and
    # the repair a reader reaches for -- deleting the name that just arrived --
    # leaves nothing asserting the split is CORRECT.
    #
    # The derivation below is strictly STRONGER than the literal it replaces,
    # not a relaxation of it. The literal asserted only which names were absent;
    # these assert BOTH directions of the partition, so they fail when a
    # declared source that IS on disk is silently skipped -- the case the
    # literal caught only as a side effect of the identity on the last line.
    resolved = vendor.resolve_vendored_set()
    present = [rel for rel in resolved if (REPO_ROOT / rel).is_file()]
    absent = [rel for rel in resolved if not (REPO_ROOT / rel).is_file()]
    assert present, (
        "0 of %d declared source(s) are on disk; every assertion below would "
        "then compare two empty lists" % len(resolved))

    assert sorted(report.missing_sources) == sorted(absent), (
        "missing_sources says %s; the declared sources actually absent from "
        "disk are %s" % (sorted(report.missing_sources), sorted(absent)))
    assert sorted(report.copied) == sorted(
        vendor.destination_name(rel) for rel in present), (
        "copied %s; the declared sources actually present on disk are %s"
        % (sorted(report.copied), sorted(present)))
    assert report.count + len(report.missing_sources) == report.declared


def test_the_vendored_copy_is_byte_identical_to_the_source(tmp_path):
    artifact, _ = _vendored(tmp_path)
    assert (artifact / "canonkit.py").read_bytes() == \
        (REPO_ROOT / "tools" / "canonkit.py").read_bytes()
    assert core.sha256_file(artifact / "canonkit.py") == \
        core.sha256_file(REPO_ROOT / "tools" / "canonkit.py")


def test_the_vendor_record_parses_and_carries_a_bundle_sha(tmp_path):
    artifact, report = _vendored(tmp_path)
    record = json.loads((artifact / ".vendor.json").read_text(encoding="ascii"))
    assert record["bundle_sha256"] == report.bundle_sha256
    assert len(record["bundle_sha256"]) == 64
    assert record["schema"] == vendor.VENDOR_SCHEMA
    assert record["declared_static_count"] == vendor.VENDORED_SET_COUNT
    assert set(record["files"]) == set(report.copied)
    assert record["vendored_at"] and record["vendored_at_utc"]


def test_the_vendor_record_sits_at_the_artifact_root_not_under_results(tmp_path):
    """a design rule: a checker output under results/ becomes an input to hashes over the tree."""
    artifact, report = _vendored(tmp_path)
    assert Path(report.record_path).parent == artifact
    assert not (artifact / "results" / ".vendor.json").exists()


def test_vendor_into_refuses_a_zero_file_vendoring(tmp_path):
    """A record over an empty set asserts nothing, and every later audit passes."""
    empty_root = tmp_path / "empty-repo"
    (empty_root / "tools").mkdir(parents=True)
    (empty_root / "tools" / "canonkit.py").write_bytes(
        (REPO_ROOT / "tools" / "canonkit.py").read_bytes())
    # A source root whose declared files are all absent EXCEPT the core we need
    # to load: point vendoring at a directory holding only that file, then hide
    # it from the declared set by vendoring from a root with nothing to copy.
    bare = tmp_path / "bare-repo"
    (bare / "tools").mkdir(parents=True)
    with pytest.raises(RuntimeError) as excinfo:
        vendor.vendor_into(tmp_path / "artifact", source_root=bare, core=core)
    assert "REFUSING" in str(excinfo.value)
    assert "0 of" in str(excinfo.value)


# ---------------------------------------------------------------------------
# audit -- the three comparisons
# ---------------------------------------------------------------------------


def test_a_clean_artifact_is_current_and_exits_zero(tmp_path, capsys):
    artifact, _ = _vendored(tmp_path)
    report = vendor.audit([artifact], core=core)
    out = capsys.readouterr().out
    assert report.code == core.EXIT_PASS, out
    assert report.current == 1 and report.audited == 1
    assert "core current 1 of 1" in out, out


def test_a_tampered_copy_is_reported_as_mismatch_and_NAMED(tmp_path, capsys):
    """a design rule: a MISMATCH against the artifact's OWN record is tampering and FAILS.

    One byte. The file still parses, still imports, still looks right. The only
    thing that changed is the thing the record pinned.
    """
    artifact, _ = _vendored(tmp_path)
    target = artifact / "canonkit.py"
    payload = bytearray(target.read_bytes())
    index = payload.index(b"EXIT_PASS = 0")
    payload[index + len("EXIT_PASS = ")] = ord("9")
    target.write_bytes(bytes(payload))

    report = vendor.audit([artifact], core=core)
    out = capsys.readouterr().out
    assert report.code != core.EXIT_PASS, (
        "a flipped byte in a vendored copy was not detected:\n%s" % out
    )
    assert "canonkit.py" in out, out
    assert "MISMATCH" in out, out
    assert report.current == 0

    verdict = report.artifacts[0]
    mismatched = [f.name for f in verdict.tampered]
    assert mismatched == ["canonkit.py"], mismatched
    assert verdict.integrity_code == core.EXIT_FINDING
    assert verdict.stale == [], (
        "tampering was also reported as staleness; the two comparisons have "
        "collapsed into one"
    )


def test_a_stale_copy_is_counted_and_is_not_reported_as_tampering(tmp_path, capsys):
    """a design rule + a design rule, the pair that only works when the checks are SEPARATE.

    The artifact's copy is byte-identical to its own record -- nothing was
    touched. The REPOSITORY moved. VENDOR-INTEGRITY must therefore PASS (this
    is not tampering) while VENDOR-CURRENT FAILS and is counted, and the audit
    continues to the remaining artifacts with a non-zero overall exit.
    """
    artifact, _ = _vendored(tmp_path)

    # A source root whose core differs from the one the artifact was built
    # against: the repository moved on, the artifact did not.
    moved = tmp_path / "moved-repo"
    (moved / "tools" / "checks").mkdir(parents=True)
    original = (REPO_ROOT / "tools" / "canonkit.py").read_bytes()
    (moved / "tools" / "canonkit.py").write_bytes(
        original + b"\n# a later edit in this repository\n")
    (moved / "tools" / "checks" / "__init__.py").write_bytes(
        (REPO_ROOT / "tools" / "checks" / "__init__.py").read_bytes())

    report = vendor.audit([artifact], source_root=moved, core=core)
    out = capsys.readouterr().out

    verdict = report.artifacts[0]
    assert verdict.tampered == [], "a stale copy was reported as tampering"
    assert verdict.absent == []
    assert verdict.integrity_code == core.EXIT_PASS, (
        "VENDOR-INTEGRITY failed on a copy that matches its own record exactly. "
        "a design rule is pinned-at-build: only a mismatch with the artifact's OWN "
        "recorded sha is tampering.\n%s" % out
    )
    assert [f.name for f in verdict.stale] == ["canonkit.py"]
    assert verdict.current_code == core.EXIT_FINDING, (
        "a design rule: a stale core FAILS ITS OWN CHECK"
    )
    assert report.code != core.EXIT_PASS, "the artifact-level exit is non-zero"
    assert report.current == 0
    assert "core current 0 of 1" in out, out


def _moved_repo(tmp_path, name="moved-repo"):
    """A source root whose CORE differs from this repository's by one comment."""
    moved = Path(tmp_path) / name
    (moved / "tools" / "checks").mkdir(parents=True)
    (moved / "tools" / "canonkit.py").write_bytes(
        (REPO_ROOT / "tools" / "canonkit.py").read_bytes()
        + b"\n# a later edit in this repository\n")
    (moved / "tools" / "checks" / "__init__.py").write_bytes(
        (REPO_ROOT / "tools" / "checks" / "__init__.py").read_bytes())
    return moved


def test_a_stale_core_does_not_stop_the_audit_of_the_remaining_artifacts(
        tmp_path, capsys):
    """a design rule: the stale core fails its own check and the run CONTINUES.

    THE TWO ARTIFACTS ARE VENDORED FROM DIFFERENT CORES, which is what makes
    exactly one of them stale under a single audit. An earlier draft of this
    test forged the stale artifact's own RECORD instead -- which produces a
    MISMATCH, not staleness, so a test named for a design rule was exercising a design rule and
    would have passed with the two comparisons collapsed. Caught by running an
    end-to-end demonstration and reading what it actually printed.
    """
    moved = _moved_repo(tmp_path)
    moved_core = vendor.load_core(moved)

    stale_artifact = Path(tmp_path) / "stale-artifact"
    stale_artifact.mkdir()
    vendor.vendor_into(stale_artifact, core=core)          # built against v1

    clean_artifact = Path(tmp_path) / "clean-artifact"
    clean_artifact.mkdir()
    vendor.vendor_into(clean_artifact, source_root=moved, core=moved_core)  # v2

    report = vendor.audit([stale_artifact, clean_artifact], source_root=moved,
                          core=core)
    out = capsys.readouterr().out

    assert report.audited == 2, "the audit stopped early"
    assert len(report.artifacts) == 2

    first = report.artifacts[0]
    assert [f.name for f in first.stale] == ["canonkit.py"]
    assert first.tampered == [] and first.absent == [], (
        "the stale artifact was reported as tampered with:\n%s" % out
    )
    assert first.integrity_code == core.EXIT_PASS
    assert first.current_code == core.EXIT_FINDING

    assert report.artifacts[1].current, (
        "the second artifact was not audited on its own terms -- the stale one "
        "stopped the run, which a design rule forbids:\n%s" % out
    )
    assert report.current == 1
    assert "core current 1 of 2" in out, out
    assert report.code != core.EXIT_PASS


def test_the_integrity_line_and_the_currency_line_use_different_words(
        tmp_path, capsys):
    """A file can be BOTH tampered and stale; the two lines must not blur it.

    A shared formatter printed `canonkit.py STALE` on the VENDOR-INTEGRITY line
    for a file whose status was MISMATCH -- re-conflating, in the human-readable
    report, the two things this module exists to keep apart. The codes were
    right; the words were not, and the words are what a reader acts on.
    """
    artifact, _ = _vendored(tmp_path, "both-artifact")
    record = json.loads((artifact / ".vendor.json").read_text(encoding="ascii"))
    record["files"]["canonkit.py"] = "0" * 64
    (artifact / ".vendor.json").write_text(
        json.dumps(record, indent=2, sort_keys=True), encoding="ascii", newline="\n")

    vendor.audit([artifact], core=core)
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    integrity = [line for line in lines if line.startswith("VENDOR-INTEGRITY")][0]
    currency = [line for line in lines if line.startswith("VENDOR-CURRENT")][0]

    assert "MISMATCH" in integrity, integrity
    assert "STALE" not in integrity, (
        "the integrity line reports staleness: %s" % integrity
    )
    assert "STALE" in currency, currency


def test_an_absent_recorded_file_is_a_finding(tmp_path, capsys):
    artifact, _ = _vendored(tmp_path)
    (artifact / "canonkit.py").unlink()
    report = vendor.audit([artifact], core=core)
    out = capsys.readouterr().out
    assert report.code != core.EXIT_PASS
    assert [f.name for f in report.artifacts[0].absent] == ["canonkit.py"]
    assert "ABSENT" in out, out


def test_an_artifact_with_no_vendor_record_did_not_run(tmp_path, capsys):
    bare = Path(tmp_path) / "never-vendored"
    bare.mkdir()
    report = vendor.audit([bare], core=core)
    out = capsys.readouterr().out
    assert report.code == core.EXIT_FINDING, out
    assert report.artifacts[0].integrity_code == core.EXIT_DID_NOT_RUN
    assert "DID-NOT-RUN" in out, out


def test_audit_over_zero_artifacts_is_did_not_run_not_zero_of_zero(capsys):
    """`core current 0 of 0` as a pass is the 0/0 pass in its purest form."""
    report = vendor.audit([], core=core)
    out = capsys.readouterr().out
    assert report.code == core.EXIT_DID_NOT_RUN, out
    assert "DID-NOT-RUN" in out, out
    assert "core current 0 of 0" not in out, (
        "an audit that enumerated nothing printed a summary indistinguishable "
        "from one where everything was current:\n%s" % out
    )


def test_audit_prints_both_numbers_and_a_summary_counts_line(tmp_path, capsys):
    first, _ = _vendored(tmp_path, "artifact-one")
    second, _ = _vendored(tmp_path, "artifact-two")
    vendor.audit([first, second], core=core)
    out = capsys.readouterr().out
    assert "core current 2 of 2" in out, out
    assert "checks: " in out and "did-not-run" in out, out


# ---------------------------------------------------------------------------
# The measured arm-C failure, as a REGRESSION test
# ---------------------------------------------------------------------------


def _git(*args, cwd):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
         "-c", "commit.gpgsign=false", "-c", "core.hooksPath="] + list(args),
        cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
        errors="replace", check=True, shell=False)


def test_vendoring_across_two_cloned_repositories_preserves_the_sha(tmp_path):
    """The research note's Pitfall 1 arm C, reproduced rather than trusted.

    The measured failure: with no .gitattributes, a file authored at 46 bytes
    with 0 CRLF comes back from a clone at 52 bytes with 6 CRLF on this machine,
    because core.autocrlf=true is set at BOTH system and global scope. Vendoring
    that clone's core into another repository then makes the sha256 assertion
    FAIL for a reason that has nothing to do with the core's content.

    conftest.committed_tree commits `.gitattributes` FIRST in both trees, which
    is a design rule's commit ORDER and the whole point. Cloning is what actually
    exercises the checkout filter -- a work tree that was never cloned has not
    been through it -- so both trees are cloned before the vendoring runs.
    """
    source = tmp_path / "source-repo"
    (source / "tools" / "checks").mkdir(parents=True)
    for relative in ("tools/canonkit.py", "tools/checks/__init__.py"):
        (source / relative).write_bytes((REPO_ROOT / relative).read_bytes())

    artifact_src = tmp_path / "artifact-repo"
    artifact_src.mkdir()
    (artifact_src / "README.md").write_text("# demo\n", encoding="ascii",
                                            newline="\n")

    source_work = conftest.committed_tree(tmp_path, source)
    artifact_work = conftest.committed_tree(tmp_path, artifact_src)

    source_clone = tmp_path / "source-clone"
    artifact_clone = tmp_path / "artifact-clone"
    _git("clone", "-q", str(source_work), str(source_clone), cwd=tmp_path)
    _git("clone", "-q", str(artifact_work), str(artifact_clone), cwd=tmp_path)

    expected = core.sha256_file(REPO_ROOT / "tools" / "canonkit.py")
    cloned_source_sha = core.sha256_file(source_clone / "tools" / "canonkit.py")
    assert cloned_source_sha == expected, (
        "the SOURCE clone's core already differs from this repository's -- the "
        "checkout filter changed the bytes, which is arm A of the measured "
        "experiment and means .gitattributes did not take effect"
    )

    cloned_core = vendor.load_core(source_clone)
    report = vendor.vendor_into(artifact_clone, source_root=source_clone,
                                core=cloned_core)
    assert "canonkit.py" in report.copied

    vendored_sha = core.sha256_file(artifact_clone / "canonkit.py")
    assert vendored_sha == expected, (
        "the vendoring assertion failed across two clones. Authored sha %s, "
        "vendored sha %s -- byte-identical content hashing two ways is arm C of "
        "the research note's Pitfall 1." % (expected, vendored_sha)
    )
    assert b"\r" not in (artifact_clone / "canonkit.py").read_bytes()

    audit_report = vendor.audit([artifact_clone], source_root=source_clone,
                                core=cloned_core, verbose=False)
    assert audit_report.code == core.EXIT_PASS
    assert audit_report.current == 1


# ---------------------------------------------------------------------------
# The CLI
# ---------------------------------------------------------------------------


def test_the_cli_returns_the_audit_code_and_writes_a_report(tmp_path, capsys):
    artifact, _ = _vendored(tmp_path)
    report_path = tmp_path / "audit-report.json"
    code = vendor.main(["audit", str(artifact), "--report", str(report_path)])
    capsys.readouterr()
    assert code == core.EXIT_PASS
    payload = json.loads(report_path.read_text(encoding="ascii"))
    assert payload["audited"] == 1 and payload["current"] == 1
    assert payload["schema_version"] == core.SCHEMA_VERSION
    assert payload["artifacts"][0]["files"], "the report carries no per-file rows"


def test_the_cli_refuses_to_vendor_into_zero_directories(capsys):
    with pytest.raises(SystemExit) as excinfo:
        vendor.main(["vendor"])
    assert excinfo.value.code == core.EXIT_DID_NOT_RUN
    assert core.REFUSAL_PREFIX in capsys.readouterr().err


# ---------------------------------------------------------------------------
# an earlier plan -- THE CLAIM CORPUS JOINS THE VENDORED SET (an earlier plan open item 8)
#
# CHECK-09 resolves every bullet reference against tools/canon-bullets.json, and
# that file was NOT vendored. Inside a vendored artifact the check therefore
# REFUSED for want of its corpus -- a checker that cannot answer, shipped in
# every artifact, reporting a refusal nobody reads as a defect.
#
# Where the copy must land is not a choice: check_09.load_snapshot() reads
# os.path.join(CORE_ROOT, "canon-bullets.json"), and CORE_ROOT is the directory
# ABOVE the checks package -- `tools/` in this repository, `<artifact>/` in a
# vendored copy. destination_name() strips the `tools/` prefix, so the declared
# `tools/canon-bullets.json` lands at the artifact root, which is exactly where
# the check looks. Verified by running the check, not by reading the tuple.
# ---------------------------------------------------------------------------


CORPUS_RELATIVE = "tools/canon-bullets.json"
CORPUS_BASENAME = "canon-bullets.json"


def test_the_claim_corpus_is_declared_in_the_vendored_set():
    assert CORPUS_RELATIVE in vendor.VENDORED_SET, (
        "the claim corpus is not declared, so CHECK-09 ships inert: %r"
        % (vendor.VENDORED_SET,))


def test_the_claim_corpus_lands_at_the_artifact_root(tmp_path):
    """Beside canonkit.py, NOT under a tools/ subdirectory.

    An artifact has no `tools/`. A copy landing there would be invisible to
    load_snapshot(), which would refuse exactly as it does today -- a fix that
    ships the bytes and changes nothing.
    """
    artifact, report = _vendored(tmp_path)
    assert CORPUS_BASENAME in report.copied, report.copied
    assert (artifact / CORPUS_BASENAME).is_file(), sorted(
        p.name for p in artifact.iterdir())
    assert not (artifact / "tools").exists(), (
        "the corpus was vendored into a tools/ subdirectory an artifact does "
        "not have")


def test_the_vendored_corpus_is_byte_identical_to_the_source(tmp_path):
    """By sha256 on both sides, because a project requirement's whole assertion is byte
    identity and a text-mode copy re-translates line endings on Windows."""
    artifact, _ = _vendored(tmp_path)
    source = REPO_ROOT / "tools" / CORPUS_BASENAME
    # Assert PRESENCE before reading. Letting the read raise FileNotFoundError
    # would make the RED transcript carry `No such file or directory`, which is
    # one of the signatures that distinguishes a real assertion failure from a
    # module that could not load -- and a crash is not an assertion about a
    # verdict either way.
    assert (artifact / CORPUS_BASENAME).is_file(), (
        "the corpus did not vendor, so byte-identity cannot be compared")
    assert (artifact / CORPUS_BASENAME).read_bytes() == source.read_bytes()
    assert core.sha256_file(artifact / CORPUS_BASENAME) == \
        core.sha256_file(source)


def test_a_tampered_corpus_is_named_as_tampering_not_counted_as_stale(tmp_path, capsys):
    """The corpus is evidence, so a silently edited copy is the worst case.

    An artifact that could edit the claim list it is checked against could make
    any bullet text `match`. It must be reported as TAMPERING against the
    artifact's own record, never as staleness against the repository.
    """
    artifact, _ = _vendored(tmp_path)
    target = artifact / CORPUS_BASENAME
    assert target.is_file(), (
        "the corpus did not vendor, so there is nothing here to tamper with")
    payload = bytearray(target.read_bytes())
    payload.extend(b" ")
    target.write_bytes(bytes(payload))

    report = vendor.audit([artifact], core=core)
    out = capsys.readouterr().out
    assert report.code != core.EXIT_PASS, (
        "an edited claim corpus was not detected:%s%s" % (chr(10), out))
    assert CORPUS_BASENAME in out, out
    assert "MISMATCH" in out, out
    verdict = report.artifacts[0]
    assert [f.name for f in verdict.tampered] == [CORPUS_BASENAME], (
        [f.name for f in verdict.tampered])
    assert verdict.stale == [], (
        "tampering was also reported as staleness; the two comparisons have "
        "collapsed into one")


def test_check_09_inside_a_vendored_artifact_can_reach_the_corpus(tmp_path):
    """The round trip, which is the only thing that proves the fix.

    Reading the tuple proves the declaration moved. Running the vendored check
    proves the file landed where the check looks -- and that is a different
    claim, which is why the plan asks for this one specifically.
    """
    artifact, _ = _vendored(tmp_path)
    assert (artifact / "checks" / "check_09.py").is_file(), (
        "check_09 did not vendor, so this test would prove nothing")
    result = conftest.run_cli(
        [sys.executable, str(artifact / "checks" / "check_09.py"), str(artifact)],
        cwd=tmp_path)
    combined = result.stdout + result.stderr
    assert "canon snapshot is not at" not in combined, (
        "the vendored CHECK-09 still cannot find its corpus:%s%s"
        % (chr(10), combined))
