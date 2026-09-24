"""CHECK-08 -- pins at pull sites, with provenance OUTPUTS scoped out and counted.

Every test here runs `tools/checks/check_08.py` AS A SUBPROCESS, by path,
through conftest.run_cli, for the two reasons test_check_01.py and
test_check_03.py do it: by path under a bare module name is exactly how the
vendored copy runs inside an artifact, and the thing under test is an EXIT CODE,
which run_cli returns from the child rather than from a pipeline stage.

WHAT MAKES THE RED IN red-transcripts/CHECK-08.txt A REAL RED. The module is
registered and RUNNABLE in the commit that captures the transcript, with its
detection stubbed to return no finding. It walks the tree, counts and prunes the
directories, opens every pull site, parses every specifier and image reference
into a site with its file and line, reads the provenance records and counts their
entries, and reports a population. Only `pin_findings()` is stubbed, so every
failure line in that transcript is an assertion about a VERDICT.

THE FALSE POSITIVE IS THE POINT OF HALF THIS FILE. A literal implementation of
"the floating tag anywhere" flags a CORRECT artifact: the shipped
results/provenance.json carries the KEY `grafana/k6:latest` whose VALUE is a
digest, and that record is the artifact documenting its own resolution. The
obvious "fix" a reader reaches for is deleting the provenance key -- destroying
evidence to silence a checker. test_a_correctly_digest_pinned_artifact_with_a_
floating_tag_provenance_key_passes is the assertion that stops it.

THIS FILE QUOTES THE BANNED STRING and the module under test does not. That is
deliberate and it is checkable: .py files are outside CHECK-08's default scope,
so a quotation is safe here and would not be safe in check_08.py, which builds
its needle from parts. test_the_module_under_test_carries_no_literal_floating_tag
asserts the difference rather than leaving it to habit.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT
CHECKS_DIR = REPO_ROOT / "tools" / "checks"
CHECK_08 = CHECKS_DIR / "check_08.py"

UNPINNED_FIXTURE = "broken-unpinned-dependency"
LATEST_FIXTURE = "broken-latest-image-tag"
EXPECTATION_FILE = "expected-CHECK-08.json"

# The real, committed defect a project requirement names, copied byte-for-byte from
# example-search-benchmark/requirements.txt by an earlier plan.
REAL_DEFECT = "elasticsearch>=8,<9"

# A real digest, used so the pinned fixtures are pinned the way an artifact
# actually pins. Its VALUE being a digest is the whole false-positive argument.
K6_DIGEST = ("grafana/k6@sha256:"
             "e7ee5a6b3e1f0a5f8c9d4b2a1e3f5c7d9b0a2c4e6f8a0b2d4f6081a3c5e7f9b1")

PINNED_FIELDS = ("check_id", "code", "found", "checked", "finding_ids",
                 "schema_version")

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


core = _load("frozen_core_for_check_08_tests", REPO_ROOT / "tools" / "canonkit.py")
check_08 = _load("check_08_under_test", CHECK_08)

# Built the same way the module builds it, so this constant and the module's
# cannot drift while the test still reads as if they agree.
FLOATING = ":" + "lat" + "est"


def write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="ascii", newline="\n")
    return path


def run_check(root, *extra, **kwargs):
    argv = [sys.executable, str(CHECK_08), str(root)]
    report = kwargs.pop("report", None)
    if report is not None:
        argv += ["--report", str(report)]
    argv += [str(token) for token in extra]
    assert not kwargs, "unexpected kwargs %r" % sorted(kwargs)
    return conftest.run_cli(argv, cwd=REPO_ROOT)


def ids(result):
    return result.report["finding_ids"]


def kinds(result):
    return sorted({finding["kind"] for finding in result.report["findings"]})


# ---------------------------------------------------------------------------
# The three finding kinds
# ---------------------------------------------------------------------------


def test_the_real_committed_range_specifier_is_a_finding_naming_file_and_line(tmp_path):
    """a project requirement's live instance, not an invented one."""
    root = Path(tmp_path) / "ranged"
    write(root / "requirements.txt", REAL_DEFECT + "\n")
    result = run_check(root, report=tmp_path / "ranged.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert "pins:unpinned-specifier:requirements.txt:1" in ids(result), ids(result)
    finding = result.report["findings"][0]
    assert finding["file"] == "requirements.txt", finding
    assert finding["line"] == 1, finding
    assert "requirements.txt:1" in result.stdout, result.stdout


def test_a_bare_requirement_with_no_specifier_is_a_finding(tmp_path):
    root = Path(tmp_path) / "bare"
    write(root / "requirements.txt", "pytest\n")
    result = run_check(root, report=tmp_path / "bare.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert kinds(result) == ["unpinned-specifier"], kinds(result)


def test_a_pinned_requirements_file_passes(tmp_path):
    root = Path(tmp_path) / "pinned"
    write(root / "requirements.txt",
          "# a comment\n"
          "pytest==9.1.1 \\\n"
          "    --hash=sha256:1088fbde8f2b49d95a549a195707afa7a76a3ce9bcadc26b6"
          "d71f0ffda5fe313\n"
          "    # via -r requirements.in\n"
          "packaging===26.3\n"
          "-r other.txt\n")
    result = run_check(root, report=tmp_path / "pinned.json")
    assert result.exit_code == core.EXIT_PASS, result.stdout
    assert result.report["checked"] == 2, (
        "expected two specifiers (the continuation is ONE requirement and the "
        "-r line is a pip option, not a pull site): %r" % result.report["sites"])


def test_a_tag_only_image_and_a_floating_tag_produce_two_different_finding_ids(tmp_path):
    fixture = conftest.broken_fixture(LATEST_FIXTURE)
    result = run_check(fixture, report=tmp_path / "two.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert kinds(result) == ["image-without-digest", "latest-tag"], kinds(result)
    assert len(set(ids(result))) == 2, ids(result)


def test_one_reference_that_is_both_produces_exactly_one_finding(tmp_path):
    """It is one defect with one repair -- resolve the digest -- so `found=`
    stays a count of things that are wrong rather than of rules that matched."""
    root = Path(tmp_path) / "both"
    write(root / "docker-compose.yml",
          "services:\n  probe:\n    image: grafana/k6" + FLOATING + "\n")
    result = run_check(root, report=tmp_path / "both.json")
    assert result.report["found"] == 1, result.report["findings"]
    assert kinds(result) == ["latest-tag"], kinds(result)


def test_a_dockerfile_base_image_that_is_tag_only_is_a_finding(tmp_path):
    """A digest-pinned app image built FROM a tag is not pinned -- the base moved
    underneath it."""
    root = Path(tmp_path) / "based"
    write(root / "Dockerfile",
          "FROM --platform=linux/amd64 python:3.12\n"
          "RUN echo hello\n")
    result = run_check(root, report=tmp_path / "based.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert "pins:image-without-digest:Dockerfile:1" in ids(result), ids(result)


def test_the_floating_tag_is_a_finding_anywhere_not_only_at_an_image_key(tmp_path):
    """templates/docker-compose.yml's stated contract, and its reason: a
    commented-out service is one uncomment away from being a pull site."""
    root = Path(tmp_path) / "commented"
    write(root / "docker-compose.yml",
          "services:\n"
          "  db:\n"
          "    image: postgres@sha256:" + ("a" * 64) + "\n"
          "  # probe:\n"
          "  #   image: grafana/k6" + FLOATING + "\n")
    result = run_check(root, report=tmp_path / "commented.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert kinds(result) == ["latest-tag"], kinds(result)
    assert "pins:latest-tag:docker-compose.yml:5" in ids(result), ids(result)


def test_an_image_on_a_registry_with_a_port_is_parsed_rather_than_split(tmp_path):
    """`myregistry:5000/app:1.2` has two colons and only the second is a tag."""
    name, tag, digest = check_08.split_image("myregistry:5000/app:1.2")
    assert name == "myregistry:5000/app", (name, tag, digest)
    assert tag == "1.2", (name, tag, digest)
    assert digest == "", (name, tag, digest)
    name, tag, digest = check_08.split_image(K6_DIGEST)
    assert digest.startswith("sha256:"), (name, tag, digest)


# ---------------------------------------------------------------------------
# THE MEASURED FALSE POSITIVE
# ---------------------------------------------------------------------------


def pinned_artifact(root):
    """A CORRECT artifact: every pull site digest-pinned, and a provenance record
    that documents the resolution using the floating tag as its KEY."""
    root = Path(root)
    write(root / "requirements.txt", "pytest==9.1.1\n")
    write(root / "docker-compose.yml",
          "services:\n  probe:\n    image: " + K6_DIGEST + "\n")
    write(root / "results" / "provenance.json",
          json.dumps({"schema": "canonkit/provenance/1",
                      "images": {"grafana/k6" + FLOATING: K6_DIGEST}},
                     indent=2, sort_keys=True) + "\n")
    return root


def test_a_correctly_pinned_artifact_with_a_floating_tag_provenance_key_passes(tmp_path):
    """THE FALSE POSITIVE, and the reason CHECK-08 is scoped rather than literal.

    The KEY is the human-readable name of what was resolved; the VALUE is the
    digest it resolved TO. The record is the artifact DOCUMENTING its resolution,
    which is exactly what a provenance record is for.
    """
    root = pinned_artifact(Path(tmp_path) / "correct")
    provenance = (root / "results" / "provenance.json").read_text(encoding="ascii")
    assert FLOATING in provenance, (
        "the fixture no longer carries the floating tag in its provenance KEY, "
        "so this test asserts nothing")

    result = run_check(root, report=tmp_path / "correct.json")
    assert result.exit_code == core.EXIT_PASS, (
        "a CORRECTLY digest-pinned artifact was flagged. Check where the "
        "finding's path points before touching the artifact.\n%s" % result.stdout)
    assert result.report["found"] == 0, result.report["findings"]


def test_no_finding_may_ever_point_inside_results(tmp_path):
    """Warning sign one, asserted rather than documented: a CHECK-08 finding
    whose path:line is inside results/ is a SCOPING BUG in the checker."""
    root = pinned_artifact(Path(tmp_path) / "scoped")
    # Make results/ as tempting as possible: a compose-shaped file full of
    # unpinned references, parked where OUTPUTS live.
    write(root / "results" / "docker-compose.yml",
          "services:\n  x:\n    image: redis" + FLOATING + "\n")
    result = run_check(root, report=tmp_path / "scoped.json")
    offenders = [finding for finding in result.report["findings"]
                 if finding["file"].startswith("results/")]
    assert not offenders, (
        "CHECK-08 reported %d finding(s) inside results/. results/ is not a pull "
        "site and never becomes one: %r" % (len(offenders), offenders))
    assert result.exit_code == core.EXIT_PASS, result.stdout


def test_the_output_carries_the_pull_site_count_and_the_not_examined_count(tmp_path):
    """An exclusion that does not print is an exclusion list that grows
    silently -- and it must print in the RUNNER'S OWN VOCABULARY.

    canonkit declares `skipped` a BANNED VERDICT because it reads as
    "deliberately and safely omitted", which is how a zero population gets filed
    as a pass by a human reading the log. conformance.py owns `not-examined=` and
    CHECK-11 fails any run in which the banned word appears in a population line.
    This note is appended to that line, so it is inside the ban.
    """
    root = pinned_artifact(Path(tmp_path) / "counted")
    result = run_check(root, report=tmp_path / "counted.json")
    assert "pull-sites checked 2 file(s)" in result.stdout, result.stdout
    assert "provenance entries not-examined 1" in result.stdout, result.stdout
    assert result.report["pull_site_files"] == 2, result.report
    assert result.report["provenance_entries"] == 1, result.report
    assert result.report["not_examined"] == 1, result.report
    assert len(result.report["provenance_records"]) == 1, result.report


def test_the_note_never_uses_the_banned_verdict_word(tmp_path):
    """MEASURED, not anticipated: the first draft of scope_note() spelled the
    exclusion the banned way and turned CHECK-11 red across eight integration
    tests that had nothing to do with pins. The note travels INSIDE the runner's
    population line, so the runner's ban covers it."""
    root = pinned_artifact(Path(tmp_path) / "vocab")
    result = run_check(root, report=tmp_path / "vocab.json")
    assert core.BANNED_VERDICT not in result.report["note"], (
        "CHECK-08's note carries the banned verdict word %r, which CHECK-11 "
        "fails a full run over: %r" % (core.BANNED_VERDICT, result.report["note"]))


# ---------------------------------------------------------------------------
# Could not look
# ---------------------------------------------------------------------------


def test_an_artifact_with_no_pull_site_of_any_kind_is_did_not_run(tmp_path):
    root = Path(tmp_path) / "nothing"
    write(root / "README.md", "# nothing to pull\n")
    result = run_check(root, report=tmp_path / "nothing.json")
    assert result.exit_code == core.EXIT_DID_NOT_RUN, result.stdout
    assert result.report["checked"] == 0, result.report
    assert core.REFUSAL_PREFIX in result.stderr, result.stderr


# ---------------------------------------------------------------------------
# Scope: what was walked, what was pruned, and both counts
# ---------------------------------------------------------------------------


def test_the_broken_fixture_tree_is_pruned_from_a_walk_rooted_above_it(tmp_path):
    """Without the prune, a run rooted here reports the deliberately committed
    defect as a finding about the TOOLING repository -- a permanent wall of
    findings against files that are broken on purpose."""
    result = run_check(REPO_ROOT / "fixtures", report=tmp_path / "pruned.json")
    assert result.report["dirs_pruned_broken"] >= 1, result.report
    offenders = [finding for finding in result.report["findings"]
                 if "/" + check_08.BROKEN_PREFIX in ("/" + finding["file"])]
    assert not offenders, offenders
    assert "broken-*" in result.stdout, result.stdout


def test_pointing_the_check_straight_at_a_broken_fixture_still_checks_it(tmp_path):
    """The prune is on DESCENDANTS, never on the root."""
    fixture = conftest.broken_fixture(UNPINNED_FIXTURE)
    result = run_check(fixture, report=tmp_path / "direct.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert result.report["checked"] == 1, result.report


def test_driver_scripts_are_opt_in_and_the_scope_prints_either_way(tmp_path):
    """The capability exists and is covered, so an earlier plan's --self wiring is a
    configuration change rather than a rewrite."""
    root = Path(tmp_path) / "driven"
    write(root / "requirements.txt", "pytest==9.1.1\n")
    write(root / "launch.py",
          "IMAGE = 'grafana/k6" + FLOATING + "'\n")

    default = run_check(root, report=tmp_path / "default.json")
    assert default.exit_code == core.EXIT_PASS, default.stdout
    assert "drivers=excluded" in default.stdout, default.stdout

    opted = run_check(root, "--include-drivers", report=tmp_path / "opted.json")
    assert opted.exit_code == core.EXIT_FINDING, opted.stdout
    assert "drivers=scanned" in opted.stdout, opted.stdout
    assert "pins:latest-tag:launch.py:1" in ids(opted), ids(opted)


# ---------------------------------------------------------------------------
# a design rule: this repository's own root
# ---------------------------------------------------------------------------


def test_the_check_resolves_pull_sites_at_this_repositorys_own_root(tmp_path):
    """Nothing in the scope resolution assumes the artifact layout, so an earlier plan's
    --self wiring is configuration."""
    result = run_check(REPO_ROOT, report=tmp_path / "self.json")
    assert result.report is not None, result.stderr
    assert result.exit_code in (core.EXIT_PASS, core.EXIT_FINDING), result.stdout
    files = [site["file"] for site in result.report["sites"]]
    assert "requirements.txt" in files, files
    assert result.report["pull_site_files"] >= 1, result.report
    inside_results = [finding for finding in result.report["findings"]
                      if "results/" in finding["file"]]
    assert not inside_results, inside_results


def test_the_live_templates_own_pull_sites_are_all_pinned(tmp_path):
    """The kit an artifact is generated from must pass the check that artifact
    will be held to."""
    result = run_check(REPO_ROOT / "templates", report=tmp_path / "templates.json")
    assert result.exit_code == core.EXIT_PASS, (
        "templates/ does not pass CHECK-08, so every artifact generated from it "
        "starts life failing:\n%s" % result.stdout)
    assert result.report["checked"] >= 3, result.report["sites"]


# ---------------------------------------------------------------------------
# The committed fixtures and their anti-rot pins
# ---------------------------------------------------------------------------


def test_the_anti_rot_pin_holds_for_the_unpinned_fixture(tmp_path):
    fixture = conftest.broken_fixture(UNPINNED_FIXTURE)
    assert (fixture / "requirements.txt").read_text(
        encoding="ascii").strip() == REAL_DEFECT, (
        "the fixture no longer carries the real committed defect")
    expected = json.loads((fixture / EXPECTATION_FILE).read_text(encoding="ascii"))
    result = run_check(fixture, report=tmp_path / "pin1.json")
    measured = {field: result.report[field] for field in PINNED_FIELDS}
    assert measured == expected, (
        "the structured report drifted from its committed expectation.\n"
        "  expected: %r\n  measured: %r" % (expected, measured))


def test_the_anti_rot_pin_holds_for_the_latest_tag_fixture(tmp_path):
    fixture = conftest.broken_fixture(LATEST_FIXTURE)
    expected = json.loads((fixture / EXPECTATION_FILE).read_text(encoding="ascii"))
    result = run_check(fixture, report=tmp_path / "pin2.json")
    measured = {field: result.report[field] for field in PINNED_FIELDS}
    assert measured == expected, (
        "the structured report drifted from its committed expectation.\n"
        "  expected: %r\n  measured: %r" % (expected, measured))


def test_the_anti_rot_expectations_carry_no_prose_field():
    for name in (UNPINNED_FIXTURE, LATEST_FIXTURE):
        fixture = conftest.broken_fixture(name)
        expected = json.loads(
            (fixture / EXPECTATION_FILE).read_text(encoding="ascii"))
        prose = sorted(set(expected) & set(PROSE_FIELDS))
        assert not prose, (
            "%s's pin holds wording-bearing field(s) %r" % (name, prose))


def test_every_file_in_both_fixtures_is_tracked():
    for name in (UNPINNED_FIXTURE, LATEST_FIXTURE):
        fixture = conftest.broken_fixture(name)
        on_disk = sorted(path.relative_to(REPO_ROOT).as_posix()
                         for path in fixture.rglob("*") if path.is_file())
        listed = subprocess.run(
            ["git", "ls-files", "--", fixture.relative_to(REPO_ROOT).as_posix()],
            cwd=str(REPO_ROOT), capture_output=True, text=True, shell=False)
        tracked = sorted(line.strip() for line in listed.stdout.splitlines()
                         if line.strip())
        missing = [path for path in on_disk if path not in tracked]
        assert not missing, (
            "%s: %d file(s) present but UNTRACKED: %r" % (name, len(missing),
                                                          missing))


# ---------------------------------------------------------------------------
# The needle, and the protocol
# ---------------------------------------------------------------------------


def test_the_module_under_test_carries_no_literal_floating_tag():
    """check_08.py is a .py file inside the repository it can be pointed at, so
    a quotation of the banned string in its own source would be a hit for its own
    rule. templates/docker-compose.yml records that its first draft did exactly
    that and failed this check."""
    source = CHECK_08.read_text(encoding="ascii")
    assert FLOATING not in source, (
        "check_08.py quotes the banned floating tag. Assemble it from parts, as "
        "check_03.py does with the skeleton's marker.")
    assert check_08.FLOATING_REF == FLOATING, (
        "the module's assembled needle and this test's have drifted: %r vs %r"
        % (check_08.FLOATING_REF, FLOATING))


def test_the_module_satisfies_the_check_protocol():
    assert check_08.CHECK_ID == "CHECK-08"
    assert isinstance(check_08.DEFAULT_FLOOR, int)
    assert callable(check_08.run)
    contract = check_08.load_contract()
    assert check_08.CHECK_ID in contract.DECLARED_CHECK_IDS


def test_discovery_finds_the_module():
    contract = check_08.load_contract()
    report = contract.discover(CHECKS_DIR, verbose=False)
    assert "CHECK-08" in report.ids, report.ids
    assert not report.protocol_violations, report.protocol_violations


def test_the_population_floor_override_prints_and_demotes(tmp_path):
    root = Path(tmp_path) / "floored"
    write(root / "requirements.txt", "pytest==9.1.1\n")
    result = run_check(root, "--min-population", "9999",
                       report=tmp_path / "floor.json")
    assert result.report["floor"] == 9999, result.report
    assert "floor=9999" in result.stdout, result.stdout
    assert result.exit_code == core.EXIT_DID_NOT_RUN, result.stdout
