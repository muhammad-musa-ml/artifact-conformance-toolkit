"""CHECK-07 -- a git work tree, with commits, whose results are TRACKED.

Every test here runs `tools/checks/check_07.py` AS A SUBPROCESS, by path,
through conftest.run_cli, for the two reasons test_check_01.py and
test_check_03.py do it: by path under a bare module name is exactly how the
vendored copy runs inside an artifact, and the thing under test is an EXIT CODE,
which run_cli returns from the child rather than from a pipeline stage.

WHAT MAKES THE RED IN red-transcripts/CHECK-07.txt A REAL RED. The module is
registered and RUNNABLE in the commit that captures the transcript, with its
detection stubbed to return no finding. It runs git, resolves the work tree,
measures the enclosing toplevel, counts the commits, lists the index, counts the
per-item records on disk and in the index, and reads the ignore rule swallowing
them out of `git check-ignore -v`. Only `worktree_findings()` is stubbed, so
every failure line in that transcript is an assertion about a VERDICT.

THE KNOWN-HAZARD PIN LIVES IN THIS FILE, and it is the reason the module exists in the
shape it does. `test_the_live_template_gitignore_does_not_swallow_the_per_item_
records` builds a throwaway repository carrying templates/.gitignore VERBATIM and
measures what `git add -A` actually stages. It fails if the scoped
`!results/raw/` negation in that template is ever reverted -- which is precisely
the state that was measured before the repair, and in which CHECK-07's weaker
form reported a PASS over an artifact whose evidence was missing from its own
index.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT
CHECKS_DIR = REPO_ROOT / "tools" / "checks"
CHECK_07 = CHECKS_DIR / "check_07.py"
TEMPLATE_GITIGNORE = REPO_ROOT / "templates" / ".gitignore"

FIXTURE = "broken-not-a-work-tree"
EXPECTATION_FILE = "expected-CHECK-07.json"

PINNED_FIELDS = ("check_id", "code", "found", "checked", "finding_ids",
                 "schema_version")

PROSE_FIELDS = ("note", "notes", "stdout", "stderr", "message", "messages",
                "summary", "detail", "details", "findings", "text", "line",
                "context", "description")

# Forced on every temp repository, so a test never depends on (or is broken by)
# the developer's global git config -- and never runs this repository's hooks.
GIT_FLAGS = [
    "-c", "user.name=artifact-conformance-toolkit tests",
    "-c", "user.email=tests@example.invalid",
    "-c", "commit.gpgsign=false",
    "-c", "core.hooksPath=",
    "-c", "core.autocrlf=false",
]


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


core = _load("frozen_core_for_check_07_tests", REPO_ROOT / "tools" / "canonkit.py")
check_07 = _load("check_07_under_test", CHECK_07)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def git(cwd, *args, **kwargs):
    check = kwargs.pop("check", True)
    assert not kwargs, sorted(kwargs)
    return subprocess.run(
        ["git"] + GIT_FLAGS + [str(arg) for arg in args],
        cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
        errors="replace", check=check, shell=False)


def write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="ascii", newline="\n")
    return path


def plain_artifact(root, records=3):
    """An artifact directory's CONTENTS. No git, no ignore rules."""
    root = Path(root)
    write(root / "README.md", "# demo\n\nA hermetic fixture.\n")
    write(root / "results" / "figures.json",
          json.dumps({"artifact": root.name, "schema": "canonkit/figures/1",
                      "figures": {}}, indent=2, sort_keys=True) + "\n")
    write(root / "results" / "gate.json",
          json.dumps({"ok": True, "schema": "canonkit/gate/1"},
                     indent=2, sort_keys=True) + "\n")
    for index in range(1, records + 1):
        write(root / "results" / "raw" / ("item-%04d.json" % index),
              json.dumps({"item_id": "item-%04d" % index, "ok": True},
                         indent=2, sort_keys=True) + "\n")
    return root


def repo_artifact(tmp_path, name="art", gitignore=None, records=3,
                  commit=True, add=True):
    """An artifact that IS a git work tree of its own, optionally committed."""
    root = plain_artifact(Path(tmp_path) / name, records=records)
    if gitignore is not None:
        write(root / ".gitignore", gitignore)
    git(root, "init", "-q", "-b", "main")
    if add:
        git(root, "add", "-A", "--", ".")
    if commit and add:
        status = git(root, "status", "--porcelain")
        if status.stdout.strip():
            git(root, "commit", "-q", "-m", "chore: the tree")
    return root


def run_check(artifact, *extra, **kwargs):
    argv = [sys.executable, str(CHECK_07), str(artifact)]
    report = kwargs.pop("report", None)
    if report is not None:
        argv += ["--report", str(report)]
    argv += [str(token) for token in extra]
    assert not kwargs, "unexpected kwargs %r" % sorted(kwargs)
    return conftest.run_cli(argv, cwd=REPO_ROOT)


def staged(root):
    """What `git ls-files` reports -- the INDEX, not the disk."""
    listed = git(root, "ls-files")
    return sorted(line.strip().replace("\\", "/")
                  for line in listed.stdout.splitlines() if line.strip())


# ---------------------------------------------------------------------------
# Branch one: is it a work tree at all?
# ---------------------------------------------------------------------------


def test_a_standalone_directory_with_no_git_anywhere_is_not_a_work_tree(tmp_path):
    root = plain_artifact(Path(tmp_path) / "loose")
    result = run_check(root, report=tmp_path / "loose.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert "worktree:not-a-work-tree" in result.report["finding_ids"], (
        result.report["finding_ids"])
    assert result.report["is_work_tree"] is False, result.report


def test_a_directory_nested_in_this_repository_is_not_a_work_tree(tmp_path):
    """`git rev-parse --is-inside-work-tree` answers TRUE for any directory
    beneath any repository, so omitting a nested .git is not enough on its own.
    The message must NAME the enclosing toplevel."""
    nested = plain_artifact(REPO_ROOT / ".reports" / "nested-probe-07")
    try:
        result = run_check(nested, report=tmp_path / "nested.json")
        assert result.exit_code == core.EXIT_FINDING, result.stdout
        assert ("worktree:enclosed-by-other-toplevel"
                in result.report["finding_ids"]), result.report["finding_ids"]
        enclosing = result.report["enclosing_toplevel"]
        assert enclosing, result.report
        assert Path(enclosing).resolve() == REPO_ROOT.resolve(), enclosing
        assert enclosing.replace("\\", "/") in result.stdout, result.stdout
    finally:
        import shutil
        shutil.rmtree(nested, ignore_errors=True)


def test_tracked_ness_is_not_evaluated_when_the_work_tree_branch_fires(tmp_path):
    """`git ls-files` inside a nested directory answers about the ENCLOSING
    repository's index. Reporting that would be a reassuring truth about an
    artifact with no version control at all."""
    root = plain_artifact(Path(tmp_path) / "loose2")
    result = run_check(root, report=tmp_path / "loose2.json")
    assert result.report["tracked_evaluated"] is False, result.report
    assert result.report["not_evaluated_reason"], result.report
    assert check_07.NOT_EVALUATED in result.stdout, result.stdout
    assert result.report["tracked_results"] == [], result.report


# ---------------------------------------------------------------------------
# Branch two: commits
# ---------------------------------------------------------------------------


def test_a_work_tree_with_zero_commits_is_a_distinct_finding(tmp_path):
    root = repo_artifact(tmp_path, name="uncommitted", commit=False)
    result = run_check(root, report=tmp_path / "zero.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert "worktree:zero-commits" in result.report["finding_ids"], (
        result.report["finding_ids"])
    assert result.report["is_work_tree"] is True, result.report
    assert result.report["commits"] == 0, result.report


# ---------------------------------------------------------------------------
# Branch three: existence versus TRACKED-NESS, on the same bytes
# ---------------------------------------------------------------------------


def test_the_same_bytes_yield_a_finding_untracked_and_a_pass_tracked(tmp_path):
    """The distinction the requirement names explicitly: verified with
    `git ls-files`, not with "the file exists". Nothing about the files changes
    between the two verdicts -- only whether git has seen them."""
    root = repo_artifact(tmp_path, name="bytes", add=False, commit=False)
    git(root, "commit", "-q", "--allow-empty", "-m", "chore: an empty root commit")

    before_bytes = (root / "results" / "figures.json").read_bytes()
    untracked = run_check(root, report=tmp_path / "untracked.json")
    assert untracked.exit_code == core.EXIT_FINDING, untracked.stdout
    assert "worktree:no-tracked-results" in untracked.report["finding_ids"], (
        untracked.report["finding_ids"])
    assert untracked.report["results_on_disk"], (
        "the files must be ON DISK, or this proves nothing about tracked-ness")

    git(root, "add", "-A", "--", ".")
    git(root, "commit", "-q", "-m", "chore: track the results")

    after_bytes = (root / "results" / "figures.json").read_bytes()
    assert after_bytes == before_bytes, (
        "the bytes changed between the two runs, so the verdicts differ for the "
        "wrong reason")

    tracked = run_check(root, report=tmp_path / "tracked.json")
    assert tracked.exit_code == core.EXIT_PASS, tracked.stdout
    assert tracked.report["results_on_disk"] == untracked.report["results_on_disk"], (
        "the population changed between the two runs")


def test_a_complete_tracked_artifact_passes(tmp_path):
    root = repo_artifact(tmp_path, name="good")
    result = run_check(root, report=tmp_path / "good.json")
    assert result.exit_code == core.EXIT_PASS, result.stdout
    assert result.report["figures_tracked"] is True, result.report
    assert len(result.report["records_tracked"]) == 3, result.report


# ---------------------------------------------------------------------------
# a known hazard: the per-item records, and the property behind the proxy
# ---------------------------------------------------------------------------


def test_the_live_template_gitignore_does_not_swallow_the_per_item_records(tmp_path):
    """THE KNOWN-HAZARD PIN. Measured against the LIVE template, not its text.

    Before the repair, this was the measured state of a throwaway repository
    carrying templates/.gitignore verbatim:

        git check-ignore -v results/raw/item-0001.json
          -> .gitignore:56:raw/    results/raw/item-0001.json
        git add -A   staged only:  .gitignore, results/figures.json

    CHECK-07's weaker form PASSED over that artifact, because figures.json was
    tracked. This test fails the moment the scoped negation is reverted.
    """
    assert TEMPLATE_GITIGNORE.is_file(), TEMPLATE_GITIGNORE
    rules = TEMPLATE_GITIGNORE.read_text(encoding="utf-8")

    root = plain_artifact(Path(tmp_path) / "verbatim")
    write(root / ".gitignore", rules)
    # Source corpora the licence block MUST still keep out of the index, plus a
    # frozen id list it MUST let in. Asserting the negation did not over-reach is
    # half the pin: a negation that admitted everything would satisfy the
    # admission half and defeat the rule.
    write(root / "raw" / "source-corpus.json", "{}\n")
    write(root / "data" / "landed.json", "{}\n")
    write(root / "corpus" / "docs.json", "{}\n")
    write(root / "ids" / "frozen.ids.txt", "1\n2\n")

    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A", "--", ".")
    listed = staged(root)

    assert "results/raw/item-0001.json" in listed, (
        "THE PER-ITEM RECORDS ARE NOT IN THE INDEX. templates/.gitignore is "
        "swallowing results/raw/ again -- the scoped `!results/raw/` negation "
        "has been reverted or broken. A reader who clones an artifact built from "
        "this template gets figures.json and none of the evidence behind it, and "
        "CHECK-07's proxy form would still report a PASS.\nstaged: %r" % listed)
    assert "results/figures.json" in listed, listed

    for swallowed in ("raw/source-corpus.json", "data/landed.json",
                      "corpus/docs.json"):
        assert swallowed not in listed, (
            "%r entered the index. The licence rule -- derived corpora are NEVER "
            "redistributed -- has been broken by the results/raw/ negation "
            "over-reaching.\nstaged: %r" % (swallowed, listed))
    assert "ids/frozen.ids.txt" in listed, listed

    probe = git(root, "check-ignore", "-v", "--", "results/raw/item-0001.json",
                check=False)
    assert probe.returncode != 0, (
        "git check-ignore matched a rule against the per-item records: %r"
        % probe.stdout)


def test_per_item_records_that_git_ignores_are_a_finding_naming_the_rule(tmp_path):
    """a known hazard reproduced, and caught.

    The negation is stripped from a COPY of the live template -- never from the
    template itself -- so this rebuilds the exact pre-repair state and asserts
    CHECK-07 refuses it and names the rule doing the swallowing.
    """
    rules = TEMPLATE_GITIGNORE.read_text(encoding="utf-8")
    reverted = "\n".join(
        line for line in rules.splitlines()
        if line.strip() not in ("!results/raw/", "!results/raw/**"))
    assert reverted != rules, (
        "the negation lines were not found in templates/.gitignore, so this test "
        "did not reconstruct the pre-repair state and asserts nothing")

    root = repo_artifact(tmp_path, name="swallowed", gitignore=reverted)
    result = run_check(root, report=tmp_path / "swallowed.json")

    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert "worktree:records-untracked" in result.report["finding_ids"], (
        result.report["finding_ids"])
    assert result.report["figures_tracked"] is True, (
        "figures.json must still be tracked here -- that is the whole point: the "
        "PROXY is satisfied while the PROPERTY is broken")
    assert result.report["records_on_disk"], result.report
    assert result.report["records_tracked"] == [], result.report

    rule = result.report["records_ignore_rule"]
    assert rule, (
        "the finding did not name the ignore rule. That one line of "
        "`git check-ignore -v` output is the entire diagnosis of a known hazard.")
    assert "raw/" in rule, rule
    assert rule in result.stdout, result.stdout


def test_a_tracked_figures_record_with_no_per_item_records_is_a_finding(tmp_path):
    """A figure is a claim about a population. With no records under
    results/raw/, nothing under results/ holds the items it counted."""
    root = repo_artifact(tmp_path, name="evidenceless", records=0)
    result = run_check(root, report=tmp_path / "absent.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert "worktree:records-absent" in result.report["finding_ids"], (
        result.report["finding_ids"])
    assert result.report["figures_tracked"] is True, result.report


def test_the_records_branch_is_gated_on_a_tracked_figures_record(tmp_path):
    """Precision, not leniency: the records are required BECAUSE a figure claims
    to rest on them. Without a figures record the no-tracked-results branch is
    the one that speaks, and the records branches stay quiet."""
    root = plain_artifact(Path(tmp_path) / "nofigures", records=0)
    (root / "results" / "figures.json").unlink()
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A", "--", ".")
    git(root, "commit", "-q", "-m", "chore: no figures record")
    result = run_check(root, report=tmp_path / "nofigures.json")
    ids = result.report["finding_ids"]
    assert "worktree:records-absent" not in ids, ids
    assert "worktree:records-untracked" not in ids, ids


# ---------------------------------------------------------------------------
# Could not look
# ---------------------------------------------------------------------------


def test_a_directory_with_no_results_at_all_is_did_not_run(tmp_path):
    """The zero-input fixture. The check could not look, rather than found a
    problem: a verdict on a directory that is not an artifact at all would be a
    finding about something this check was never pointed at."""
    root = Path(tmp_path) / "empty"
    root.mkdir(parents=True)
    (root / "README.md").write_text("# nothing\n", encoding="ascii", newline="\n")
    result = run_check(root, report=tmp_path / "empty.json")
    assert result.exit_code == core.EXIT_DID_NOT_RUN, result.stdout
    assert result.report["checked"] == 0, result.report
    assert core.REFUSAL_PREFIX in result.stderr, result.stderr


# ---------------------------------------------------------------------------
# git, not the filesystem
# ---------------------------------------------------------------------------


def executable_lines(source):
    """`source` with COMMENTS and DOCSTRINGS blanked, line numbers preserved.

    A GUARD THAT CANNOT DISCRIMINATE IS NOT A GUARD, and this helper exists
    because the first version of the test below could not. It scanned raw source
    for a filesystem predicate near `.git` and matched check_07.py's own
    prohibition comment -- the line that says never to do this thing was itself
    the hit. That is the fourth recorded instance of the shape in this phase:
    an earlier plan's hook check matched `exit 0` in its own comment, an earlier plan's RED
    transcript failed its own gate by pasting the pattern it documented, and
    an earlier plan's `startswith("canonkit.")` matched the FILENAME and produced 26
    confident false findings.

    The repair is the one an earlier plan made: replace the text match with a STRUCTURAL
    predicate. Comments are located with `tokenize` (so a trailing comment on a
    real line of code is trimmed rather than blanking the code beside it) and
    docstrings with `ast`. What remains is code, and only code.
    """
    import ast
    import io
    import tokenize

    lines = source.splitlines()
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            row = token.start[0] - 1
            lines[row] = lines[row][:token.start[1]]
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body or not isinstance(body[0], ast.Expr):
            continue
        value = body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            for row in range(body[0].lineno - 1, body[0].end_lineno):
                lines[row] = ""
    return lines


def test_executable_lines_blanks_a_comment_but_keeps_the_code_beside_it():
    """The helper above is load-bearing for the test below, so it is checked
    rather than trusted. A stripper that blanked whole lines would hide a real
    violation that happened to carry a trailing comment."""
    sample = ('"""doc with os.path.isdir(\'.git\')."""\n'
              "# never os.path.isdir('.git')\n"
              "value = os.path.isdir('.git')  # trailing\n")
    lines = executable_lines(sample)
    assert lines[0] == "", lines
    assert lines[1].strip() == "", lines
    assert "os.path.isdir('.git')" in lines[2], lines
    assert "trailing" not in lines[2], lines


def test_the_check_asks_git_rather_than_the_filesystem_about_version_control():
    """`os.path.exists` answers "is this on this disk right now". `git ls-files`
    answers "will a reader who clones this have it"."""
    source = CHECK_07.read_text(encoding="ascii")
    assert source.count("exists()") == 0, (
        "check_07.py calls .exists(); every git fact must come from a subprocess")
    for needle in ("ls-files", "rev-parse", "--is-inside-work-tree",
                   "--show-toplevel", "rev-list", "check-ignore"):
        assert needle in source, "check_07.py never runs %r" % needle

    code = executable_lines(source)
    adjacency = [(number, line) for number, line in enumerate(code, start=1)
                 if ".git" in line and ("isdir" in line or "isfile" in line
                                        or "exists" in line or "islink" in line)]
    assert not adjacency, (
        "check_07.py asks the FILESYSTEM about .git on %d line(s) of real code "
        "(comments and docstrings already excluded): %r"
        % (len(adjacency), adjacency))


# ---------------------------------------------------------------------------
# The committed fixture and its anti-rot pin
# ---------------------------------------------------------------------------


def test_the_committed_fixture_fails_naming_the_enclosing_toplevel(tmp_path):
    fixture = conftest.broken_fixture(FIXTURE)
    result = run_check(fixture, report=tmp_path / "fix.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert result.report["finding_ids"] == [
        "worktree:enclosed-by-other-toplevel"], result.report["finding_ids"]
    assert result.report["found"] == 1, (
        "the fixture carries more than one defect: %r" % result.report["findings"])
    assert Path(result.report["enclosing_toplevel"]).resolve() == REPO_ROOT.resolve()


def test_the_fixtures_chain_is_re_walkable_from_its_own_records():
    """The fixture demonstrates what tracked-ness is FOR: the numerator is
    count(ok) over the committed per-item records."""
    fixture = conftest.broken_fixture(FIXTURE)
    records = sorted((fixture / "results" / "raw").glob("*.json"))
    assert records, "the fixture carries no per-item records"
    payloads = [json.loads(path.read_text(encoding="ascii")) for path in records]
    numerator = len([item for item in payloads if item.get("ok")])
    figures = json.loads(
        (fixture / "results" / "figures.json").read_text(encoding="ascii"))
    figure = figures["figures"]["items_ok"]
    assert figure["value"] == numerator, (
        "the figure claims %r and count(ok) over the records is %r"
        % (figure["value"], numerator))
    assert figure["population"] == len(payloads), (
        "the denominator claims %r and there are %r records"
        % (figure["population"], len(payloads)))


def test_every_file_in_the_fixture_is_tracked_including_results_raw():
    """Present is not tracked -- and results/raw/ inside the fixture tree is
    exactly the path a broad `results/` rule would swallow."""
    fixture = conftest.broken_fixture(FIXTURE)
    on_disk = sorted(p.relative_to(REPO_ROOT).as_posix()
                     for p in fixture.rglob("*") if p.is_file())
    listed = subprocess.run(
        ["git", "ls-files", "--", fixture.relative_to(REPO_ROOT).as_posix()],
        cwd=str(REPO_ROOT), capture_output=True, text=True, shell=False)
    tracked = sorted(line.strip() for line in listed.stdout.splitlines()
                     if line.strip())
    missing = [path for path in on_disk if path not in tracked]
    assert not missing, (
        "%d fixture file(s) are present but UNTRACKED: %r" % (len(missing), missing))
    records = [path for path in tracked if "/results/raw/" in path]
    assert len(records) == 3, (
        "expected three tracked per-item records in the fixture, git ls-files "
        "returned %d: %r" % (len(records), records))


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
    prose = sorted(set(expected) & set(PROSE_FIELDS))
    assert not prose, (
        "the pin holds wording-bearing field(s) %r, so the first error-message "
        "improvement breaks it and the standard repair empties the mechanism"
        % prose)


# ---------------------------------------------------------------------------
# Protocol and population
# ---------------------------------------------------------------------------


def test_the_module_satisfies_the_check_protocol():
    assert check_07.CHECK_ID == "CHECK-07"
    assert isinstance(check_07.DEFAULT_FLOOR, int)
    assert callable(check_07.run)
    contract = check_07.load_contract()
    assert check_07.CHECK_ID in contract.DECLARED_CHECK_IDS


def test_discovery_finds_the_module():
    contract = check_07.load_contract()
    report = contract.discover(CHECKS_DIR, verbose=False)
    assert "CHECK-07" in report.ids, report.ids
    assert not report.protocol_violations, report.protocol_violations


def test_the_population_floor_override_prints_and_demotes(tmp_path):
    """a design rule: the EFFECTIVE floor is what prints, or the line lies about what it
    applied."""
    root = repo_artifact(tmp_path, name="floored")
    result = run_check(root, "--min-population", "9999",
                       report=tmp_path / "floor.json")
    assert result.report["floor"] == 9999, result.report
    assert "floor=9999" in result.stdout, result.stdout
    assert result.exit_code == core.EXIT_DID_NOT_RUN, result.stdout


def test_the_population_line_carries_the_counts_it_measured(tmp_path):
    """A pass over a population nobody confirmed has verified nothing."""
    root = repo_artifact(tmp_path, name="counted")
    result = run_check(root, report=tmp_path / "counts.json")
    on_disk = len(result.report["results_on_disk"])
    assert "checked=%d of %d" % (on_disk, on_disk) in result.stdout, result.stdout
    assert "per-item-records on-disk=3 tracked=3" in result.stdout, result.stdout
    assert result.report["checked"] == on_disk, result.report
