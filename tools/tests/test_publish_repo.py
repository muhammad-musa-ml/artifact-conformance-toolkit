"""`scripts/publish_repo.py` -- the publishing gate, which shipped with no tests.

It is the one tool in this repository with no test module, no population line
and no structured report, and three later plans edit it. It is also the only
tool here that WRITES OUTSIDE the repository and can PUSH, so "untested" is not
a tidiness complaint.

THREE PROPERTIES THIS MODULE EXISTS TO HOLD, each measured rather than assumed:

  1. The script can be run TWICE. `shutil.rmtree` cannot unlink a read-only file
     on this filesystem, git writes loose objects read-only, and the script's own
     `git init` inside the export is what creates them -- so the first run arms
     the trap for every later one. The fixture below sets a REAL read-only bit
     and proves the unlink genuinely fails before relying on it.

  2. The leak scan states its POPULATION. `leak scan: CLEAN` over an unknown file
     count cannot distinguish a clean export from an empty one, an unreadable
     one, or a needle set that matches nothing.

  3. The suite gate reads a COLLECTED COUNT, not only a return code. A run whose
     collection silently narrowed satisfies `returncode == 0`.

`--dry-run` IS NOT SIDE-EFFECT FREE, and the flag's name says otherwise. It
rebuilds the export directory and `git init`s it, which is exactly what writes
the read-only objects the next run has to delete. A dry run arms the trap as
readily as a real publish does. Every test here therefore points `export_root`
at a temp directory rather than at the repository's own export tree.

NO TEST IN THIS MODULE BUILDS A SHELL PIPELINE. A command piped into `tail`,
`head` or `grep` returns the PIPE's exit status, not the child's, which is a
measured trap on this machine. Every capture is an in-process `main([...])` call
or a `subprocess.run` with `shell=False`, and every assertion reads a real code.

THIS MODULE MUST NOT BE A HIT FOR THE SCAN IT TESTS. It is a tracked file, so it
travels into an export and is scanned there. Every banned token below is
ASSEMBLED FROM FRAGMENTS at run time and no forbidden literal appears in this
file's prose -- the same discipline the script itself uses, and the same one the
conventions record for the banned-name lint.
"""

import calendar
import hashlib
import importlib.util
import io
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT
PUBLISH_PATH = REPO_ROOT / "scripts" / "publish_repo.py"


def _load(stem, path):
    """Load a script BY PATH under a bare stem.

    `spec_from_file_location` is the mandated mechanism and is explicitly NOT a
    frozen-core violation; the guard that scans for forbidden imports says so in
    its own docstring. Copied from the register module's loader.
    """
    if stem in sys.modules:
        return sys.modules[stem]
    spec = importlib.util.spec_from_file_location(stem, str(path))
    if spec is None or spec.loader is None:
        raise ImportError("could not build a spec for %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[stem] = module
    spec.loader.exec_module(module)
    return module


if not PUBLISH_PATH.is_file():
    # A published export deliberately leaves the publisher behind -- a script
    # that pushes repositories has no business travelling with an artifact, and
    # the toolkit manifest excludes scripts/ for that reason while still
    # shipping tools/tests/. Without this guard the module raises at IMPORT time
    # in every such export, which is a COLLECTION error rather than a failure,
    # and a collection error takes the rest of its file down with it.
    # The premise is asserted, not assumed: see the paired test at the end.
    pytest.skip("the publisher is not part of this tree, so nothing here applies",
                allow_module_level=True)

publish = _load("publish_repo_under_test", PUBLISH_PATH)


# ---------------------------------------------------------------------------
# Scratch manifests. NEVER the repository's own export tree.
# ---------------------------------------------------------------------------

AUTHOR = {
    "name": "publish-repo-test",
    "email": "publish-repo-test@example.invalid",
    "github_user": "publish-repo-test",
}

# `exclude_re.match(path)` is an EXCLUSION test, so "keep only X" is spelled as a
# negative lookahead: every path that is not X matches at zero width and is
# dropped, while X itself fails the lookahead, matches nothing, and survives.
KEEP_ONLY_CORE = r"^(?!tools/canonkit[.]py$)"

# `^` matches at zero width against every string, so everything is excluded.
KEEP_NOTHING = r"^"

SMOKE_TEST = (
    "def test_the_exported_suite_actually_runs():\n"
    "    assert 1 + 1 == 2\n"
)


def _scratch(tmp_path, exclude_pattern=KEEP_NOTHING, authored=None,
             rewrites=None, repo="exp", **extra):
    """Write a scratch manifest and return (path, parsed manifest, dest).

    `allow_dirty_working_tree` is set by default because these tests run while
    this repository's own tree is mid-edit, and the working-tree guard is about
    what a PUBLISH may ship, not about what a test may build. The guard's own
    two tests below turn it off deliberately.
    """
    manifest = {
        "repo": repo,
        "author": AUTHOR,
        "commit_message": "scratch export",
        "exclude_pattern": exclude_pattern,
        "rewrites": rewrites or [],
        "authored": authored if authored is not None else {},
        "export_root": str(tmp_path / "o"),
        "allow_dirty_working_tree": True,
    }
    manifest.update(extra)
    path = tmp_path / "m.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    dest = os.path.join(manifest["export_root"], manifest["repo"])
    return path, manifest, dest


def _authored(tmp_path, name, text):
    """Write an authored source file and return its ABSOLUTE path.

    `build_export` resolves an authored source as os.path.join(REPO_ROOT, src).
    On Windows an absolute second argument discards the first, so a temp path
    resolves to itself. That is not assumed -- the assertions below read the
    exported bytes back and compare them to this file's bytes.
    """
    p = tmp_path / "a" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return str(p)


def _smoke(tmp_path):
    """The one authored file that makes an export's own suite collectable."""
    return {"tools/tests/test_smoke.py": _authored(tmp_path, "s.py", SMOKE_TEST)}


def _git(args, cwd):
    """A git call with shell=False, returning the CHILD's own exit code."""
    return subprocess.run(["git"] + list(args), cwd=str(cwd),
                          capture_output=True, text=True, shell=False)


# The FULL key set `run_suite` returns. Declared once, asserted against the real
# function below, and used by every stub here.
#
# This literal exists because the first stub written in this module was shaped
# from what the TEST intended to read rather than from what the CALLER consumes,
# and the gate then measured the stub instead of the code. It was caught only
# because the caller subscripts the dict instead of reaching for a default: a
# `.get(..., 0)` there would have turned a missing key into a plausible zero and
# the test would have passed while proving nothing.
SUITE_RESULT_KEYS = {"code", "collected", "summary", "failed", "found",
                     "checked", "not_examined", "listed", "delta"}


def _suite_result(**overrides):
    """A stand-in for run_suite's return value, carrying its full key set."""
    result = {"code": 0, "collected": 0, "summary": "(stub)", "failed": [],
              "found": 0, "checked": 0, "not_examined": 0, "listed": 0,
              "delta": 0}
    unknown = set(overrides) - SUITE_RESULT_KEYS
    assert not unknown, "the stub was handed keys run_suite does not return: %r" % (
        sorted(unknown),)
    result.update(overrides)
    return result


# ---------------------------------------------------------------------------
# The argv-accepting main, and the in-process exit code
# ---------------------------------------------------------------------------

def test_main_takes_argv_and_returns_an_integer_exit_code(tmp_path):
    """Every other CLI here is `main(argv=None)`; this one read sys.argv.

    An in-process return value is the tool's own code with no pipe between it
    and the assertion, which is the whole reason this signature matters.
    """
    manifest, _m, _dest = _scratch(tmp_path, authored=_smoke(tmp_path))

    code = publish.main(["--manifest", str(manifest), "--dry-run",
                         "--python", sys.executable])

    assert isinstance(code, int), (
        "main() returned %r; a gate that cannot report an integer in process "
        "cannot be asserted on without a subprocess" % (code,))
    assert code == 0, (
        "a scratch export with one authored file and a passing suite should "
        "verify clean; main() returned %d" % code)


def test_a_missing_manifest_returns_non_zero_rather_than_raising(tmp_path):
    """A bad path is a refusal with a code, not a traceback.

    `--dry-run` is passed even though the manifest read happens first: this is a
    script that can push, and a test of its failure paths does not rely on the
    ordering of statements inside it staying the way it is today.
    """
    missing = tmp_path / "does-not-exist.json"

    code = publish.main(["--manifest", str(missing), "--dry-run"])

    assert code != 0, "a missing manifest reported success"
    assert code == publish.EXIT_DID_NOT_RUN, (
        "a manifest that could not be read is a DID-NOT-RUN (2), not a finding; "
        "got %d" % code)


def test_a_malformed_manifest_returns_non_zero_rather_than_raising(tmp_path):
    """Unparseable JSON is the same class of refusal as a missing file."""
    broken = tmp_path / "broken.json"
    broken.write_text("{ this is not json", encoding="utf-8")

    code = publish.main(["--manifest", str(broken), "--dry-run"])

    assert code == publish.EXIT_DID_NOT_RUN, (
        "malformed JSON should refuse as DID-NOT-RUN; got %d" % code)


# ---------------------------------------------------------------------------
# The export's file population -- counted, never assumed
# ---------------------------------------------------------------------------

def test_the_export_file_count_is_asserted_as_an_integer(tmp_path):
    """The counts the tool reports are checked against the tree on disk.

    Two numbers that must agree: what `build_export` says it wrote, and what a
    walk of the destination actually finds. A tool's own claim about its output
    is not evidence about its output.
    """
    authored = _smoke(tmp_path)
    _manifest, m, dest = _scratch(tmp_path, exclude_pattern=KEEP_ONLY_CORE,
                                  authored=authored)

    result = publish.build_export(m, dest)

    assert result["tracked"] == 1, (
        "the exclude pattern should have left exactly tools/canonkit.py; "
        "build_export reports %d tracked file(s)" % result["tracked"])
    assert result["authored"] == 1
    assert result["total"] == 2

    on_disk = sum(len(names) for _root, _dirs, names in os.walk(dest))
    assert on_disk == result["total"], (
        "build_export reports %d file(s); the destination holds %d"
        % (result["total"], on_disk))


def test_authored_files_win_over_the_tracked_copy(tmp_path):
    """The project rule is that authored files win, so prove BOTH directions.

    Asserting only that the export matches the authored source would also pass
    if the tracked copy had never been written at all. The second assertion is
    what makes the overwrite the thing being measured.
    """
    authored_core = _authored(tmp_path, "c.py", "AUTHORED_FOR_THE_EXPORT = True\n")
    authored = dict(_smoke(tmp_path))
    authored["tools/canonkit.py"] = authored_core

    _manifest, m, dest = _scratch(tmp_path, exclude_pattern=KEEP_ONLY_CORE,
                                  authored=authored)
    publish.build_export(m, dest)

    exported = Path(dest) / "tools" / "canonkit.py"
    assert exported.read_bytes() == Path(authored_core).read_bytes(), (
        "the authored file did not win")
    assert exported.read_bytes() != (REPO_ROOT / "tools" / "canonkit.py").read_bytes(), (
        "the export matches the TRACKED copy, so the authored file either never "
        "landed or the tracked copy was never written -- either way this test "
        "would have been vacuous")


def test_an_authored_file_that_replaces_a_tracked_one_is_counted_once(tmp_path):
    """Found by reconciling two of this tool's OWN counts against each other.

    A real dry run printed `leak-scan ... checked=168 of 168` and, three lines
    later, `commit: ... (169 file(s))`. The export holds 167 tracked survivors
    and 2 authored files, and ONE of the authored files replaces a tracked
    survivor rather than adding to it -- so the naive sum counted that file
    twice and the reported total overstated the published tree by one.

    A count that is PRESENT but WRONG is worse than a missing one: a wrong
    number reads as detail, while a missing one reads as a question.
    """
    replacement = _authored(tmp_path, "c.py", "AUTHORED_FOR_THE_EXPORT = True\n")
    authored = dict(_smoke(tmp_path))
    authored["tools/canonkit.py"] = replacement  # also a tracked survivor
    _manifest, m, dest = _scratch(tmp_path, exclude_pattern=KEEP_ONLY_CORE,
                                  authored=authored)

    result = publish.build_export(m, dest)

    assert result["tracked"] == 1
    assert result["authored"] == 2
    assert result["authored_replacements"] == 1, (
        "one authored file replaces a tracked survivor; the build reports %r"
        % (result.get("authored_replacements"),))

    on_disk = sum(len(names) for _root, _dirs, names in os.walk(dest))
    assert on_disk == 2, "expected canonkit.py and the smoke test, found %d" % on_disk
    assert result["total"] == on_disk, (
        "build_export reports a total of %d over an export holding %d file(s)"
        % (result["total"], on_disk))


def test_the_exclude_pattern_drops_a_non_zero_number_of_paths(tmp_path):
    """A filter that removed nothing is indistinguishable from no filter."""
    listed = [f for f in publish.run(["git", "ls-files"],
                                     publish.REPO_ROOT).stdout.splitlines() if f]
    kept = publish.tracked_files(re.compile(KEEP_ONLY_CORE))

    assert listed, "git ls-files returned nothing; the population is empty"
    assert kept == ["tools/canonkit.py"], (
        "expected exactly one survivor, got %r" % (kept,))

    dropped = len(listed) - len(kept)
    assert dropped > 0, (
        "the exclude pattern dropped 0 of %d listed path(s)" % len(listed))

    _manifest, m, dest = _scratch(tmp_path, exclude_pattern=KEEP_ONLY_CORE,
                                  authored=_smoke(tmp_path))
    publish.build_export(m, dest)

    victim = listed[0] if listed[0] != "tools/canonkit.py" else listed[1]
    assert not (Path(dest) / victim.replace("/", os.sep)).exists(), (
        "%s matched the exclude pattern and still reached the export" % victim)


# ---------------------------------------------------------------------------
# The tree an export is READ FROM. A manifest names it, or it is this one.
#
# Every path in the publisher resolved against this repository's own root, so
# the script could only ever publish ITSELF. A second repository -- an artifact
# that lives in its own work tree beside this one -- was not publishable by it
# at all, and nothing in the manifest schema said so.
#
# The `authored` half deliberately does NOT move. A file written FOR a published
# repository lives HERE, under the publish directory, which is the whole shape of
# the authored-not-filtered rule. Conflating the two roots would let the tree
# being exported supply the files that win over it.
# ---------------------------------------------------------------------------

# `exclude_re.match(path)` against this matches only the empty string, and the
# empty entry is already dropped before the filter -- so nothing is excluded.
KEEP_EVERYTHING = r"^$"


def _fixture_work_tree(tmp_path, names=("only-in-the-declared-source-tree.txt",
                                        "nested/second-file-declared-here.md")):
    """A REAL git work tree whose file names do not exist in this repository.

    The names are the discriminator. An assertion that the export contains
    `tools/canonkit.py` would pass whichever root the script read; an assertion
    that it contains a name which exists NOWHERE here cannot.
    """
    repo = tmp_path / "src"
    repo.mkdir()
    assert _git(["init", "-q", "."], repo).returncode == 0
    for name in names:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("content of %s\n" % name, encoding="utf-8")
    assert _git(["add"] + list(names), repo).returncode == 0
    assert _git(["-c", "user.name=t", "-c", "user.email=t@example.invalid",
                 "commit", "-q", "-m", "fixture"], repo).returncode == 0
    return repo, list(names)


def test_a_declared_source_root_exports_that_tree_and_not_this_one(tmp_path):
    """The property that makes a second repository publishable at all."""
    repo, names = _fixture_work_tree(tmp_path)
    for name in names:
        assert not (REPO_ROOT / name.replace("/", os.sep)).exists(), (
            "%s exists in this repository too, so finding it in the export "
            "would not tell the two roots apart" % name)

    _manifest, m, dest = _scratch(tmp_path, exclude_pattern=KEEP_EVERYTHING,
                                  authored=_smoke(tmp_path),
                                  source_root=str(repo))
    result = publish.build_export(m, dest)

    assert result["tracked"] == len(names), (
        "expected the fixture tree's %d tracked file(s), got %d -- `git "
        "ls-files` was run somewhere else"
        % (len(names), result["tracked"]))
    for name in names:
        assert (Path(dest) / name.replace("/", os.sep)).is_file(), (
            "%s is tracked in the declared source root and did not reach the "
            "export" % name)
    assert not (Path(dest) / "tools" / "canonkit.py").exists(), (
        "a file from THIS repository reached an export whose source root is "
        "elsewhere")


def test_no_declared_source_root_still_exports_this_repository(tmp_path):
    """The default path is unchanged; absence of the key means this root."""
    _manifest, m, dest = _scratch(tmp_path, exclude_pattern=KEEP_ONLY_CORE,
                                  authored=_smoke(tmp_path))

    assert "source_root" not in m, "the scratch manifest declared one after all"
    result = publish.build_export(m, dest)

    assert result["tracked"] == 1
    assert (Path(dest) / "tools" / "canonkit.py").is_file(), (
        "a manifest with no source root no longer exports this repository")


def test_a_source_root_that_is_not_a_work_tree_refuses_and_names_the_path(
        tmp_path, capsys):
    """Exporting nothing and calling it a publish is the 0/0 pass again.

    A directory that is not a work tree makes `git ls-files` list nothing, so
    without this refusal the run would build an empty export and the leak scan
    would be the only thing that noticed -- and it would say DID-NOT-RUN about
    the file count rather than about the root, which is the wrong diagnosis.
    """
    outsider = tmp_path / "not-a-work-tree"
    outsider.mkdir()
    (outsider / "a.txt").write_text("not tracked by anything\n", encoding="utf-8")
    manifest, _m, _dest = _scratch(tmp_path, exclude_pattern=KEEP_EVERYTHING,
                                   authored=_smoke(tmp_path),
                                   source_root=str(outsider))

    code = publish.main(["--manifest", str(manifest), "--dry-run",
                         "--python", sys.executable])
    err = capsys.readouterr().err

    assert code != 0, "a source root that is not a work tree reported success"
    assert code == publish.EXIT_DID_NOT_RUN, (
        "a root whose population cannot be listed is a DID-NOT-RUN (2); got %d"
        % code)
    assert os.path.abspath(str(outsider)) in err, (
        "the refusal did not name the resolved path, so a reader cannot tell "
        "WHICH root was rejected. stderr was: %r" % err)


def test_a_source_root_that_does_not_exist_refuses_rather_than_raising(tmp_path):
    """The same refusal, for the typo case rather than the wrong-kind case."""
    manifest, _m, _dest = _scratch(tmp_path, exclude_pattern=KEEP_EVERYTHING,
                                   authored=_smoke(tmp_path),
                                   source_root=str(tmp_path / "no-such-tree"))

    code = publish.main(["--manifest", str(manifest), "--dry-run",
                         "--python", sys.executable])

    assert code == publish.EXIT_DID_NOT_RUN, (
        "a missing source root returned %d rather than refusing" % code)


def test_authored_files_still_resolve_against_this_repository(tmp_path):
    """The two roots must not be conflated, and this is the discriminator.

    The authored source below is a path RELATIVE TO THIS REPOSITORY which does
    not exist in the declared source root at all. If `authored` had followed
    `source_root`, the build would refuse for a missing authored file; if it
    silently found something else, the byte comparison would fail.
    """
    repo, _names = _fixture_work_tree(tmp_path)
    authored = dict(_smoke(tmp_path))
    authored["tools/canonkit.py"] = "tools/canonkit.py"

    assert not (repo / "tools" / "canonkit.py").exists(), (
        "the fixture tree carries the authored source too, so this test could "
        "not tell the two roots apart")

    _manifest, m, dest = _scratch(tmp_path, exclude_pattern=KEEP_EVERYTHING,
                                  authored=authored, source_root=str(repo))
    publish.build_export(m, dest)

    exported = Path(dest) / "tools" / "canonkit.py"
    assert exported.read_bytes() == (REPO_ROOT / "tools" / "canonkit.py").read_bytes(), (
        "the authored file did not come from this repository")


def test_the_dirty_tree_refusal_follows_the_declared_source_root(tmp_path,
                                                                 monkeypatch):
    """The guard is about the tree being READ, not about the tree it lives in.

    The stub reports dirty for THIS repository and clean for anything else, so
    a run that still asked about this repository refuses and a run that asks
    about the declared root does not. The roots it was actually asked about are
    recorded and asserted, rather than inferred from the verdict.
    """
    repo, _names = _fixture_work_tree(tmp_path)
    seen = []

    def _stub(root):
        seen.append(os.path.abspath(root))
        return ([" M a-path-in-this-repository"]
                if os.path.abspath(root) == os.path.abspath(publish.REPO_ROOT)
                else [])

    monkeypatch.setattr(publish, "dirty_paths", _stub)
    manifest, _m, _dest = _scratch(tmp_path, exclude_pattern=KEEP_EVERYTHING,
                                   authored=_smoke(tmp_path),
                                   source_root=str(repo),
                                   allow_dirty_working_tree=False)

    code = publish.main(["--manifest", str(manifest), "--dry-run",
                         "--python", sys.executable])

    assert seen, "the working-tree guard was never consulted at all"
    assert seen == [os.path.abspath(str(repo))], (
        "the guard asked about %r; the declared source root is %r"
        % (seen, os.path.abspath(str(repo))))
    assert code == 0, (
        "the run refused (%d) over a CLEAN declared source root" % code)


def test_a_dirty_declared_source_root_refuses_and_prints_its_own_change(
        tmp_path, capsys):
    """The live control for the test above, with no stub anywhere.

    The uncommitted file's name exists only in the fixture tree, so seeing it in
    the printed porcelain lines proves WHICH tree the status came from. A bare
    refusal would not: this repository is routinely dirty while the suite runs.
    """
    repo, _names = _fixture_work_tree(tmp_path)
    victim = "uncommitted-only-in-the-declared-tree.txt"
    (repo / victim).write_text("not committed\n", encoding="utf-8")

    manifest, _m, _dest = _scratch(tmp_path, exclude_pattern=KEEP_EVERYTHING,
                                   authored=_smoke(tmp_path),
                                   source_root=str(repo),
                                   allow_dirty_working_tree=False)

    code = publish.main(["--manifest", str(manifest), "--dry-run",
                         "--python", sys.executable])
    printed = capsys.readouterr().out

    assert code == publish.EXIT_REFUSED, (
        "a dirty declared source root returned %d" % code)
    assert victim in printed, (
        "the refusal printed no porcelain line naming the declared tree's own "
        "uncommitted file, so the status may have come from elsewhere")


def test_the_toolkit_manifest_documents_the_source_root_key(tmp_path):
    """A manifest key with no note is a key the next reader guesses at."""
    manifest_path = REPO_ROOT / "scripts" / "publish" / "toolkit-publish.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert "_source_root_note" in manifest, (
        "the toolkit manifest documents every other key it carries and would "
        "leave this one unexplained")
    assert "source_root" not in manifest, (
        "the toolkit publishes THIS repository; declaring the key here would "
        "make the default path untested by the shipped manifest")


# ---------------------------------------------------------------------------
# --dry-run stops before anything irreversible
# ---------------------------------------------------------------------------

def test_dry_run_leaves_no_origin_remote_in_the_export(tmp_path):
    """The push path is `remote add` then `push --force-with-lease`.

    Asserting that no remote exists afterwards is the observable consequence of
    the dry run having stopped before the first of those two, and it does not
    depend on trusting a printed message.
    """
    manifest, _m, dest = _scratch(tmp_path, authored=_smoke(tmp_path))

    code = publish.main(["--manifest", str(manifest), "--dry-run",
                         "--python", sys.executable])

    assert code == 0, "the dry run refused; nothing downstream can be asserted"
    assert os.path.isdir(os.path.join(dest, ".git")), (
        "the dry run did not create a work tree, so the remote assertion below "
        "would pass for the wrong reason")

    remotes = _git(["remote"], dest)
    assert remotes.returncode == 0, remotes.stderr
    assert remotes.stdout.split() == [], (
        "a dry run configured remote(s): %r" % remotes.stdout.split())


def test_the_default_export_root_is_gitignored(tmp_path):
    """A test run may build an export only because that tree is never tracked."""
    probe = _git(["check-ignore", "-v", ".export/anything"], REPO_ROOT)

    assert probe.returncode == 0, (
        "the default export root is NOT ignored (git check-ignore exited %d); a "
        "publish run would leave tracked debris" % probe.returncode)
    assert ".gitignore" in probe.stdout, (
        "expected the ignore rule to come from .gitignore, got %r" % probe.stdout)


# ---------------------------------------------------------------------------
# The second run. Git writes loose objects READ-ONLY, and the script's own
# `git init` inside the export is what creates them -- so the first run arms
# the trap for every later one, and a dry run arms it as readily as a publish.
# ---------------------------------------------------------------------------

def test_a_real_read_only_file_denies_a_plain_unlink_on_this_filesystem(tmp_path):
    """The fixture the next two tests stand on, proven faithful before use.

    A simulated failure that never fires reads exactly like a pass. This asserts
    the read-only bit genuinely denies the unlink HERE, so a green result below
    measures the repair rather than a filesystem that never objected.
    """
    victim = tmp_path / "loose-object"
    victim.write_bytes(b"x")
    os.chmod(str(victim), stat.S_IREAD)
    try:
        with pytest.raises(PermissionError):
            os.unlink(str(victim))
    finally:
        os.chmod(str(victim), stat.S_IWRITE)


def _previous_export_with_read_only_objects(dest):
    """Leave behind what git leaves behind: loose objects with no write bit."""
    objects = os.path.join(dest, ".git", "objects", "02")
    os.makedirs(objects)
    victims = []
    for name in ("84bdd1f0070a654216d8bca2e88d0b7a6bbf6f", "c0ffee1"):
        path = os.path.join(objects, name)
        io.open(path, "w", encoding="utf-8").write("a loose object\n")
        os.chmod(path, stat.S_IREAD)
        victims.append(path)
    return victims


def test_the_export_rebuilds_over_a_previous_run_s_read_only_objects(tmp_path):
    """The measured defect: PermissionError [WinError 5] inside shutil.rmtree.

    It was raised BEFORE any work, so the traceback never mentioned the suite
    and a reader skimming for test failures would have misdiagnosed it.
    """
    _manifest, m, dest = _scratch(tmp_path, authored=_smoke(tmp_path))
    victims = _previous_export_with_read_only_objects(dest)

    try:
        result = publish.build_export(m, dest)
    finally:
        # Leave nothing undeletable behind if the rebuild refused part way.
        for path in victims:
            if os.path.exists(path):
                os.chmod(path, stat.S_IWRITE)

    assert result["readonly_retries"] >= len(victims), (
        "the rebuild reports %d read-only retry/retries over %d read-only "
        "file(s); the fixture was never exercised, so this test would pass on a "
        "machine where the defect cannot occur"
        % (result["readonly_retries"], len(victims)))
    for path in victims:
        assert not os.path.exists(path), "%s survived the rebuild" % path
    assert not os.path.isdir(os.path.join(dest, ".git")), (
        "the previous run's work tree survived the rebuild")


def test_two_consecutive_runs_against_one_export_root_both_complete(tmp_path):
    """The property a success criterion states and no test covered.

    The first run git-inits the export, which is what writes the read-only
    objects; the second is the one that had to delete them and could not.
    """
    manifest, _m, dest = _scratch(tmp_path, authored=_smoke(tmp_path))
    argv = ["--manifest", str(manifest), "--dry-run", "--python", sys.executable]

    assert publish.main(argv) == 0, "the first run refused"

    readonly = [p for p in (Path(dest) / ".git").rglob("*")
                if p.is_file() and not os.access(str(p), os.W_OK)]
    assert readonly, (
        "the first run left no read-only file under the export's .git, so the "
        "second run below would prove nothing about the defect being repaired")

    stale = Path(dest) / "only-after-the-first-run.txt"
    stale.write_text("debris\n", encoding="utf-8")

    assert publish.main(argv) == 0, "the second run refused"
    assert not stale.exists(), (
        "the export was not rebuilt from scratch: a file created after the "
        "first run survived the second")


def test_a_genuine_permission_problem_still_surfaces(tmp_path):
    """The retry is narrow on purpose.

    Clearing the write bit on the offending path and retrying THAT operation
    repairs the read-only case. Pre-walking the tree and chmod-ing everything
    would paper over a real permission failure instead of surfacing it, so the
    handler re-raises anything that is not a PermissionError.
    """
    retried = []
    retries_attempted = []

    with pytest.raises(OSError) as caught:
        publish.clear_readonly_and_retry(
            retries_attempted.append,
            str(tmp_path / "some-path"),
            OSError(9, "a failure that is not about a read-only bit"),
            retried)

    assert not isinstance(caught.value, PermissionError), (
        "the fixture did not inject the kind of failure this test is about")
    assert retries_attempted == [], (
        "the handler retried an operation it was supposed to re-raise, so a "
        "genuine permission problem would be papered over")
    assert retried == [], "a non-permission failure was counted as a repair"


# ---------------------------------------------------------------------------
# The leak scan states its population, or it has not scanned anything
# ---------------------------------------------------------------------------

def test_a_leak_scan_over_zero_files_refuses_rather_than_reporting_clean(tmp_path):
    """The 0/0 pass, in the one tool that imports no shared checking surface.

    An export with no files, an export nothing could read, and a needle set that
    matches nothing all produced the same three-letter verdict. The requirement
    this gate serves is verified by READING THE FILE LIST THAT WOULD SHIP, and
    an empty list cannot satisfy it.
    """
    manifest, _m, _dest = _scratch(tmp_path)  # excludes everything, authors nothing

    code = publish.main(["--manifest", str(manifest), "--dry-run",
                         "--python", sys.executable])

    assert code == publish.EXIT_DID_NOT_RUN, (
        "a scan over zero files returned %d; a check that examined no inputs is "
        "a DID-NOT-RUN and never a pass" % code)


def test_the_leak_scan_reports_its_population_as_separate_integers(tmp_path):
    """found and checked are different numbers, and one cannot stand for both."""
    authored = dict(_smoke(tmp_path))
    authored["docs/clean.md"] = _authored(tmp_path, "d.md", "nothing banned here\n")
    _manifest, m, dest = _scratch(tmp_path, authored=authored)
    publish.build_export(m, dest)

    scan = publish.leak_scan(dest)

    assert scan["found"] == 0
    assert scan["checked"] == 2, (
        "expected both authored files to be read, got checked=%d" % scan["checked"])
    # Re-keyed when the value and shape needles landed: the count is every
    # needle APPLIED, and the vocabulary list is no longer all of them.
    assert scan["needles"] == publish.needle_count(), (
        "the reported count is not the number of needles the scan applies")
    assert scan["needles"] > len(publish._LEAK_PARTS), (
        "the count covers only the vocabulary needles")
    assert scan["needles"] > 0, "a scan applying no needle cannot find anything"
    assert scan["checked"] + scan["not_examined"] == scan["listed"], (
        "the population does not close: checked=%d not-examined=%d listed=%d"
        % (scan["checked"], scan["not_examined"], scan["listed"]))


def test_the_population_prints_on_the_clean_branch(tmp_path, capsys):
    """A print guarded by the verdict makes the clean run silent.

    A silent run is indistinguishable from one that never happened, so the line
    has to carry its numbers on the branch where nothing was found too.
    """
    manifest, _m, _dest = _scratch(tmp_path, authored=_smoke(tmp_path))

    code = publish.main(["--manifest", str(manifest), "--dry-run",
                         "--python", sys.executable])
    printed = capsys.readouterr().out

    assert code == 0, printed
    line = [l for l in printed.splitlines() if "leak" in l]
    assert line, "no leak-scan line was printed at all"
    assert "found=0" in line[0], line[0]
    assert "checked=1" in line[0], line[0]
    assert "needles=" in line[0], line[0]


def test_the_population_prints_beside_a_hit_too(tmp_path, capsys):
    """The same three integers, on the branch a reader is most likely to skim."""
    banned = "Co-Authored" + "-By: somebody\n"
    authored = dict(_smoke(tmp_path))
    authored["docs/leaky.md"] = _authored(tmp_path, "l.md", banned)
    manifest, _m, _dest = _scratch(tmp_path, authored=authored)

    code = publish.main(["--manifest", str(manifest), "--dry-run",
                         "--python", sys.executable])
    printed = capsys.readouterr().out

    assert code == publish.EXIT_REFUSED, (
        "a banned token reached the export and the gate returned %d" % code)
    line = [l for l in printed.splitlines() if "leak" in l]
    assert line, "no leak-scan line was printed at all"
    assert "found=1" in line[0], line[0]
    assert "checked=2" in line[0], line[0]
    assert "needles=" in line[0], line[0]


# ---------------------------------------------------------------------------
# The real values are NEEDLES, keyed so they keep detecting
#
# Scrubbing the corpus fixes today. A needle is what makes a re-introduction
# DETECTABLE tomorrow rather than re-discovered by hand.
#
# TWO KINDS, and the distinction is the whole design. The archived canons are
# frozen and never edited, so a needle keyed to their DIGESTS keeps detecting
# forever. The live entries' digests were measured ALREADY STALE, and one moves
# again this phase, so a value needle keyed to them would stop detecting exactly
# when it mattered -- those are keyed by SHAPE instead, and the shape needle has
# to DISCRIMINATE: the corpus's own rows are recomputed from the files they name
# at scan time and are not hits, and any other digest beside a `sha256` key is.
# A needle that fired on the rows the corpus legitimately carries could never
# report CLEAN, which is a gate satisfied by the very defect it targets.
# ---------------------------------------------------------------------------

# Sixty-four hex characters that are obviously nobody's digest.
FOREIGN_DIGEST = ("dead" + "beef") * 8


def _example_sources():
    """The example documents the SHIPPED manifest authors, READ FROM IT.

    This was a hard-coded tuple of four filenames -- a second copy of a list
    the manifest already owns. Renaming those documents in the manifest left
    the copy behind, and nine tests in this module then refused with "the
    manifest names an authored file that does not exist": a failure about this
    fixture's own bookkeeping, wearing the shape of a failure about the export.
    Derived, it cannot drift, and the assertion below is what stops a derived
    list from silently becoming an empty one.
    """
    manifest = json.loads(
        (REPO_ROOT / "scripts" / "publish" / "toolkit-publish.json")
        .read_text(encoding="utf-8"))
    rows = {rel: src for rel, src in manifest["authored"].items()
            if rel.startswith("examples/")}
    assert len(rows) >= 4, (
        "the shipped manifest authors %d example document(s); the fingerprint "
        "tests below need the corpus's declared sources present, and a corpus "
        "whose sources are missing makes EVERY digest in it a hit" % len(rows))
    return rows


def _corpus_export(tmp_path, **extra):
    """A scratch export carrying the example corpus and its four sources."""
    authored = dict(_smoke(tmp_path))
    authored["tools/canon-bullets.json"] = (
        "scripts/publish/toolkit-publish/canon-bullets.json")
    authored.update(_example_sources())
    _manifest, m, dest = _scratch(tmp_path, authored=authored, **extra)
    publish.build_export(m, dest)
    return dest


def _plant(dest, rel, text):
    """Write a line into an exported file and return a remover."""
    path = Path(dest) / rel.replace("/", os.sep)
    original = path.read_text(encoding="utf-8") if path.exists() else None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")

    def remove():
        if original is None:
            path.unlink()
        else:
            path.write_text(original, encoding="utf-8", newline="\n")
    return remove


def _real_values():
    """The four real (bytes, sha256) pairs, read from the frozen baseline."""
    _corpus, rows = _real_corpus()
    return rows


def test_a_clean_export_of_the_example_corpus_is_not_a_hit(tmp_path):
    """The discriminating negative. A needle set that matches everything
    satisfies every positive test below and makes the gate useless."""
    dest = _corpus_export(tmp_path)

    scan = publish.leak_scan(dest)

    assert scan["checked"] == 6, (
        "expected the corpus, its four sources and the smoke test to be read, "
        "got checked=%d" % scan["checked"])
    assert scan["found"] == 0, (
        "a clean export of the example corpus reported %d hit(s): %r"
        % (scan["found"], scan["hits"][:5]))


def test_the_authored_rows_are_recomputed_at_scan_time_and_are_not_hits(tmp_path):
    """The trap this design exists to avoid, asserted as a live control.

    The corpus carries four digests beside `sha256` keys. A needle reading "any
    64-hex beside a sha256 key in an example corpus is a hit" would fire on all
    four and the scan could never report CLEAN.
    """
    dest = _corpus_export(tmp_path)
    corpus = json.loads((Path(dest) / "tools" / "canon-bullets.json")
                        .read_text(encoding="utf-8"))
    declared = [row["sha256"] for row in corpus["sources"]]

    assert len(declared) == 4 and len(set(declared)) == 4, (
        "the export's corpus does not carry four distinct digests, so a zero "
        "below would prove nothing about discrimination")

    scan = publish.leak_scan(dest)
    assert scan["found"] == 0, scan["hits"][:5]


def test_a_foreign_digest_beside_a_sha256_key_is_a_hit(tmp_path):
    """Plant, confirm the hit, remove, confirm clean."""
    dest = _corpus_export(tmp_path)
    corpus_rel = "tools/canon-bullets.json"
    path = Path(dest) / "tools" / "canon-bullets.json"
    original = path.read_text(encoding="utf-8")
    doc = json.loads(original)

    assert publish.leak_scan(dest)["found"] == 0, "the control was not clean"

    doc["sources"][0]["sha256"] = FOREIGN_DIGEST
    remove = _plant(dest, corpus_rel,
                    json.dumps(doc, indent=2, sort_keys=True,
                               ensure_ascii=False) + "\n")
    planted = publish.leak_scan(dest)
    remove()

    assert planted["found"] >= 1, (
        "a digest that is not the digest of the file its row names was not a "
        "hit, so the shape needle matches nothing")
    assert publish.leak_scan(dest)["found"] == 0, (
        "removing the planted value did not restore a clean verdict")


def test_a_real_live_entry_digest_in_an_authored_row_is_a_hit(tmp_path):
    """The exact re-introduction this needle exists for.

    The live entries' digests cannot be needled BY VALUE -- two of four were
    measured stale and one moves again -- so this is the proof that the shape
    needle catches them anyway.
    """
    dest = _corpus_export(tmp_path)
    live = [r for r in _real_values() if r["role"] == "live_collections"]
    assert len(live) == 2, "expected two live rows in the baseline"

    path = Path(dest) / "tools" / "canon-bullets.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["sources"][2]["sha256"] = live[0]["sha256"]
    remove = _plant(dest, "tools/canon-bullets.json",
                    json.dumps(doc, indent=2, sort_keys=True,
                               ensure_ascii=False) + "\n")
    planted = publish.leak_scan(dest)
    remove()

    assert planted["found"] >= 1, (
        "a real live-entry digest sitting in an authored row was not a hit")
    assert publish.leak_scan(dest)["found"] == 0


def test_re_introducing_an_archived_canon_digest_anywhere_is_a_hit(tmp_path):
    """BY VALUE, because the archived canons are frozen and never edited."""
    dest = _corpus_export(tmp_path)
    archived = [r for r in _real_values() if r["role"] == "frozen_canon"]
    assert len(archived) == 2

    for row in archived:
        remove = _plant(dest, "docs/notes.md",
                        "a note quoting %s\n" % row["sha256"])
        planted = publish.leak_scan(dest)
        remove()
        assert planted["found"] >= 1, (
            "an archived canon's digest reached the export and was not a hit")
        assert publish.leak_scan(dest)["found"] == 0, (
            "removing the planted digest did not restore a clean verdict")


def test_re_introducing_any_of_the_four_real_byte_counts_is_a_hit(tmp_path):
    """A byte count is half a fingerprint and is durable for all four rows."""
    dest = _corpus_export(tmp_path)

    for row in _real_values():
        remove = _plant(dest, "docs/notes.md",
                        "the source was %d bytes\n" % row["bytes"])
        planted = publish.leak_scan(dest)
        remove()
        assert planted["found"] >= 1, (
            "a real byte count reached the export and was not a hit")
        assert publish.leak_scan(dest)["found"] == 0


def test_the_census_count_and_record_filenames_are_hits(tmp_path):
    """Supplied BY THE MANIFEST, so a later phase adds one without a code edit."""
    corpus, _rows = _real_corpus()
    census = corpus["census"]
    manifest = json.loads(
        (REPO_ROOT / "scripts" / "publish" / "toolkit-publish.json")
        .read_text(encoding="utf-8"))
    extra = publish.manifest_needles(manifest)

    assert extra, "the toolkit manifest declares no needles"

    dest = _corpus_export(tmp_path)
    for planted_text in ("the walk censused %d files\n" % census["files_censused"],
                         "the record was %s\n" % census["before"],
                         "the record was %s\n" % census["after"]):
        remove = _plant(dest, "docs/notes.md", planted_text)
        hit = publish.leak_scan(dest, extra)
        clean = publish.leak_scan(dest)
        remove()
        assert hit["found"] >= 1, (
            "a real census value reached the export and the manifest's needles "
            "did not catch it")
        assert clean["found"] == 0, (
            "the same value was a hit WITHOUT the manifest's needles, so this "
            "test does not measure the manifest hook at all")
    assert publish.leak_scan(dest, extra)["found"] == 0


def test_a_manifest_can_add_a_needle_without_editing_the_script(tmp_path):
    """The hook itself, with a needle the script has never heard of."""
    dest = _corpus_export(tmp_path)
    invented = {"label": "invented", "parts": ["a-token-", "no-script-knows"]}
    extra = publish.manifest_needles({"leak_needles": [invented]})

    base = publish.leak_scan(dest)
    remove = _plant(dest, "docs/notes.md", "a-token-no-script-knows\n")
    without = publish.leak_scan(dest)
    with_needle = publish.leak_scan(dest, extra)
    remove()

    assert without["found"] == 0, "the script already matched the invented token"
    assert with_needle["found"] == 1, (
        "the manifest's needle did not fire; found=%d" % with_needle["found"])
    assert with_needle["needles"] == base["needles"] + 1, (
        "the applied-needle count did not rise with the manifest's needle: "
        "%d then %d" % (base["needles"], with_needle["needles"]))


def test_the_scan_reports_files_scanned_needles_applied_and_hits_found(
        tmp_path, capsys):
    """Three integers, on the line a reader skims, on every branch."""
    manifest, _m, _dest = _scratch(tmp_path, authored=_smoke(tmp_path))

    code = publish.main(["--manifest", str(manifest), "--dry-run",
                         "--python", sys.executable])
    printed = capsys.readouterr().out

    assert code == 0, printed
    line = [l for l in printed.splitlines() if "leak" in l]
    assert line, "no leak-scan line was printed at all"
    assert "found=0" in line[0], line[0]
    assert "checked=1" in line[0], line[0]
    match = re.search(r"needles=(\d+)", line[0])
    assert match, line[0]
    assert int(match.group(1)) > len(publish._LEAK_PARTS), (
        "the applied-needle count is %s, which is no more than the vocabulary "
        "needles alone -- the value and shape needles were not counted"
        % match.group(1))


def test_the_durable_value_needles_are_the_frozen_baselines_own_values():
    """The fragments are CHECKED against the file that records them.

    A hand-split literal is a value somebody typed. Comparing the assembled
    result to the baseline's own rows is what turns it back into a value
    somebody read.
    """
    rows = _real_values()
    assembled = set(publish.value_needle_values())

    archived = {r["sha256"] for r in rows if r["role"] == "frozen_canon"}
    counts = {str(r["bytes"]) for r in rows}

    assert archived <= assembled, (
        "%d archived digest(s) are not among the assembled value needles"
        % len(archived - assembled))
    assert counts <= assembled, (
        "%d real byte count(s) are not among the assembled value needles"
        % len(counts - assembled))
    live = {r["sha256"] for r in rows if r["role"] == "live_collections"}
    assert not (live & assembled), (
        "a LIVE entry's digest is needled by value; it was measured stale and "
        "moves again, so it must be covered by shape instead")


def test_the_manifest_needles_are_the_frozen_baselines_own_census_values():
    """The same guard for the values that live in the manifest."""
    corpus, _rows = _real_corpus()
    census = corpus["census"]
    manifest = json.loads(
        (REPO_ROOT / "scripts" / "publish" / "toolkit-publish.json")
        .read_text(encoding="utf-8"))
    values = {value for _label, value, _boundary
              in publish.manifest_needles(manifest)}

    assert str(census["files_censused"]) in values, (
        "the manifest's needles do not carry the real census file count")
    assert any(v in census["before"] and v in census["after"] for v in values), (
        "no manifest needle matches both real census record filenames")


def test_neither_the_script_nor_the_manifest_carries_a_contiguous_real_value():
    """Every needle is assembled at run time, or the gate is its own hit."""
    rows = _real_values()
    corpus, _r = _real_corpus()
    forbidden = ([r["sha256"] for r in rows]
                 + [str(r["bytes"]) for r in rows]
                 + [str(corpus["census"]["files_censused"]),
                    corpus["census"]["before"], corpus["census"]["after"]])

    assert len(forbidden) == 11, (
        "the probe carries %d value(s); a zero below is only as strong as the "
        "population it searched for" % len(forbidden))
    baseline = REAL_CORPUS.read_text(encoding="utf-8")
    assert all(value in baseline for value in forbidden), (
        "a value this probe searches for is absent from the record it was read "
        "out of, so the containment test itself is not working")

    for path in (REPO_ROOT / "scripts" / "publish_repo.py",
                 REPO_ROOT / "scripts" / "publish" / "toolkit-publish.json"):
        text = path.read_text(encoding="utf-8")
        hits = [i for i, value in enumerate(forbidden) if value in text]
        assert not hits, (
            "%s carries %d real value(s) as a contiguous literal (indices %r); "
            "assemble them from fragments" % (path.name, len(hits), hits))


def test_a_rewrite_may_be_assembled_from_fragments(tmp_path):
    """A rewrite's `from` side is sometimes exactly what a needle looks for.

    Writing it whole would make the manifest a hit for the scan it configures,
    and the gate would refuse over its own repair.

    Rewrites apply to the TRACKED files copied out of the source tree and not
    to authored files, which are written for the export and need no rewording.
    The fixture is therefore a tracked file in a declared source root.
    """
    repo, _names = _fixture_work_tree(tmp_path)
    (repo / "quote.md").write_text("an example naming a-secret-name\n",
                                   encoding="utf-8")
    assert _git(["add", "quote.md"], repo).returncode == 0
    assert _git(["-c", "user.name=t", "-c", "user.email=t@example.invalid",
                 "commit", "-q", "-m", "quote"], repo).returncode == 0

    _manifest, m, dest = _scratch(
        tmp_path, exclude_pattern=KEEP_EVERYTHING, authored=_smoke(tmp_path),
        source_root=str(repo),
        rewrites=[{"from_parts": ["a-secret", "-name"], "to": "a-neutral-name"}])

    result = publish.build_export(m, dest)

    assert result["reworded"] == 1, (
        "the build reworded %d file(s); the fragment-assembled rewrite did not "
        "fire" % result["reworded"])
    text = (Path(dest) / "quote.md").read_text(encoding="utf-8")
    assert "a-neutral-name" in text, (
        "the exported copy was not reworded: %r" % text)
    assert "a-secret-name" not in text


def test_the_shipped_toolkit_manifest_produces_a_clean_scan(tmp_path):
    """The property the whole plan exists for, asserted at suite time.

    Measured: the fingerprint needles found a real census record filename in
    the export on their first run, quoted as a worked example inside a README
    the census exclusion does not cover. A gate that only runs at publish time
    finds that three minutes into a publish; this finds it in seconds.
    """
    manifest = json.loads(
        (REPO_ROOT / "scripts" / "publish" / "toolkit-publish.json")
        .read_text(encoding="utf-8"))
    manifest["export_root"] = str(tmp_path / "o")
    dest = os.path.join(manifest["export_root"], manifest["repo"])

    built = publish.build_export(manifest, dest)
    scan = publish.leak_scan(dest, publish.manifest_needles(manifest))

    assert built["tracked"] > 100, (
        "the export holds %d tracked file(s); a clean verdict over a tiny "
        "population would prove nothing" % built["tracked"])
    assert scan["checked"] == built["total"], (
        "the scan read %d file(s) over an export of %d"
        % (scan["checked"], built["total"]))
    assert scan["needles"] > len(publish._LEAK_PARTS)
    assert scan["found"] == 0, (
        "the shipped manifest produces %d hit(s): %r"
        % (scan["found"], scan["hits"][:5]))


def test_a_hit_line_does_not_echo_the_value_it_matched(tmp_path):
    """The gate's own output must not become the leak surface.

    A hit prints the offending line. Printing a real digest into a capture file
    and a console transcript would re-publish the thing the needle caught.
    """
    dest = _corpus_export(tmp_path)
    archived = [r for r in _real_values() if r["role"] == "frozen_canon"][0]
    remove = _plant(dest, "docs/notes.md",
                    "a note quoting %s\n" % archived["sha256"])
    scan = publish.leak_scan(dest)
    remove()

    assert scan["found"] >= 1
    for hit in scan["hits"]:
        echoed = " ".join(str(part) for part in hit)
        assert archived["sha256"] not in echoed, (
            "the hit record echoes the digest it matched")


def test_the_scan_counts_what_it_could_not_read_and_says_why(tmp_path):
    """An excluded input with no count and no reason is an input silently dropped."""
    _manifest, m, dest = _scratch(tmp_path, authored=_smoke(tmp_path))
    publish.build_export(m, dest)
    # Bytes that are not valid UTF-8, so the scan cannot read them as text.
    io.open(os.path.join(dest, "blob.bin"), "wb").write(b"\xff\xfe\x00\x01")

    scan = publish.leak_scan(dest)

    assert scan["not_examined"] == 1, (
        "expected the undecodable file to be counted, got not-examined=%d"
        % scan["not_examined"])
    assert scan["reasons"], "the not-examined input was counted with no reason"
    assert scan["checked"] + scan["not_examined"] == scan["listed"]


# ---------------------------------------------------------------------------
# The suite gate reads a COLLECTED COUNT, not only a return code
# ---------------------------------------------------------------------------

def test_the_collected_count_is_read_from_pytest_s_own_output():
    """Verified against real output from this machine, not an invented format."""
    real = (
        "============================= test session starts ====================\n"
        "platform win32 -- Python 3.12.11, pytest-9.1.1\n"
        "collected 30 items\n"
        "\n"
        "tools/tests/test_mwlock.py ....                                 [100%]\n"
        "\n"
        "============================= 30 passed in 10.37s ====================\n"
    )
    assert publish.parse_collected(real) == 30

    quiet = "..............   [100%]\n30 passed in 14.78s\n"
    assert publish.parse_collected(quiet) is None, (
        "the quiet form carries NO collection line, which is why the child is "
        "not run with -q; reading a count out of it would be an invention")


def test_a_module_skipped_at_import_is_outside_the_collected_count():
    """Two of the child's own counts legitimately disagree. MEASURED here:

        collected 2 items / 1 skipped
        ======================== 2 passed, 1 skipped in 34.40s ==============

    A module skipped at IMPORT time is reported in the summary but was never
    collected, so the outcomes sum to MORE than the collection line. Deriving
    what ran by subtracting the skips FROM the collection line therefore
    under-counts by exactly the number of collection-time skips -- which is not
    hypothetical here, because the export skips this very module at import.

    The two numbers are printed side by side with their difference. A
    disagreement between two counts IS the finding, never a number to pick
    between.
    """
    text = (
        "collected 2 items / 1 skipped\n"
        "\n"
        "======================== 2 passed, 1 skipped in 34.40s =============\n"
    )

    assert publish.parse_collected(text) == 2
    population = publish.suite_population(text)

    assert population["checked"] == 2, (
        "expected the two tests that actually ran, got checked=%d"
        % population["checked"])
    assert population["not_examined"] == 1
    assert population["listed"] == 3
    assert population["collected"] == 2
    assert population["delta"] == 1, (
        "the difference between the summary total and the collection line must "
        "be reported, not reconciled away; got %r" % (population["delta"],))
    assert population["checked"] + population["not_examined"] == population["listed"]


def test_the_population_is_derived_from_what_ran_not_from_a_subtraction():
    """The ordinary case, where the two counts agree and the delta is zero."""
    text = (
        "collected 909 items\n"
        "============ 3 failed, 899 passed, 7 skipped in 202.24s ============\n"
    )

    population = publish.suite_population(text)

    assert population["found"] == 3
    assert population["checked"] == 902
    assert population["not_examined"] == 7
    assert population["listed"] == 909
    assert population["collected"] == 909
    assert population["delta"] == 0


def test_an_unreadable_collected_count_refuses_rather_than_passing(tmp_path,
                                                                   monkeypatch):
    """A population that could not be read is unknown, and unknown is not zero."""
    manifest, _m, _dest = _scratch(tmp_path, authored=_smoke(tmp_path))
    monkeypatch.setattr(publish, "run_suite", lambda *_a, **_k: _suite_result(
        collected=None, summary="(a summary with no collection line)"))

    code = publish.main(["--manifest", str(manifest), "--dry-run",
                         "--python", sys.executable])

    assert code == publish.EXIT_DID_NOT_RUN, (
        "an unreadable collected count returned %d" % code)


def test_a_narrowed_collection_refuses_despite_a_zero_return_code(tmp_path,
                                                                  monkeypatch):
    """The defect this closes: `returncode == 0` over a collection that shrank.

    A green run of three tests and a green run of eight hundred are the same
    integer, and the gate read only that integer.
    """
    manifest, _m, _dest = _scratch(tmp_path, authored=_smoke(tmp_path),
                                   suite_floor=845)
    monkeypatch.setattr(publish, "run_suite", lambda *_a, **_k: _suite_result(
        code=0, collected=3, summary="3 passed in 0.10s"))

    code = publish.main(["--manifest", str(manifest), "--dry-run",
                         "--python", sys.executable])

    assert code == publish.EXIT_REFUSED, (
        "a collection of 3 against a declared floor of 845 returned %d" % code)


def test_the_stubs_carry_the_same_keys_the_real_run_returns(tmp_path):
    """A stub is evidence only while its SHAPE matches the thing it replaces.

    Derived from the real function rather than from what these tests intend to
    read, because the consumer decides the schema and the test does not.
    """
    _manifest, m, dest = _scratch(tmp_path, authored=_smoke(tmp_path))
    publish.build_export(m, dest)

    real = publish.run_suite(dest, sys.executable)

    assert set(real) == SUITE_RESULT_KEYS, (
        "run_suite returns %r; this module's stubs declare %r. The difference "
        "IS the finding -- a stub missing a key the caller reads would make the "
        "gate measure the stub." % (sorted(real), sorted(SUITE_RESULT_KEYS)))
    assert real["collected"] == 1, (
        "the real run collected %r, so the key set above was read off an empty "
        "run and proves less than it appears to" % (real["collected"],))


def test_the_suite_path_defaults_to_this_repositorys_own_layout():
    """A manifest that says nothing gets the behaviour it had before the key.

    The default is what keeps this repository's own manifest from needing a new
    key, so it is pinned rather than left to be re-derived by a reader.
    """
    assert publish.resolve_suite_path({}) == "tools/tests"
    assert publish.DEFAULT_SUITE_PATH == "tools/tests"


def test_a_manifest_may_declare_where_its_own_tests_live(tmp_path):
    """The key exists because a second publishable tree keeps its suite
    elsewhere, and the gate ran a literal.

    This asserts the REAL run, not just the resolver: a resolver returning the
    right string while `run_suite` still ran a literal would satisfy a test of
    the resolver alone and change nothing about the gate.
    """
    suite = "checks_of_its_own"
    authored = {"%s/test_smoke.py" % suite: _authored(tmp_path, "s.py",
                                                      SMOKE_TEST)}
    _manifest, m, dest = _scratch(tmp_path, authored=authored,
                                  suite_path=suite)
    publish.build_export(m, dest)

    assert publish.resolve_suite_path(m) == suite

    result = publish.run_suite(dest, sys.executable, suite)

    assert result["collected"] == 1, (
        "the child collected %r at %r, so the declared path was not the one "
        "that ran" % (result["collected"], suite))
    assert result["code"] == 0, result["summary"]


def test_pytest_reports_a_MISSING_path_as_a_collection_of_zero(tmp_path):
    """The anti-rot pin under the refusal below. MEASURED, not assumed.

    The refusal exists because a wrong `suite_path` does NOT surface as a
    did-not-run on its own: pytest prints a collection line for a path it cannot
    find, so `parse_collected` reads 0 rather than None and the run falls
    through to the floor check, which then reports a MISSING DIRECTORY as a
    suite that narrowed. If pytest ever stopped emitting that line, the
    refusal's reasoning would be stale and this pin is what would say so.
    """
    _manifest, m, dest = _scratch(tmp_path, authored=_smoke(tmp_path))
    publish.build_export(m, dest)

    result = publish.run_suite(dest, sys.executable, "no/such/directory")

    assert result["collected"] == 0, (
        "pytest reported %r for a path that does not exist; the refusal below "
        "is written against `collected 0`, and unknown is not zero"
        % (result["collected"],))
    assert result["code"] != 0


def test_a_suite_path_absent_from_the_export_refuses_as_DID_NOT_RUN(tmp_path):
    """The discrimination, which is the whole point of the check.

    "the tests are not there" and "the tests narrowed" are different findings
    with different repairs, and before this they shared one sentence. The
    assertion is on the CODE, because both refusals are refusals and only the
    code tells them apart: a missing suite is a 2 (it could not look), a
    narrowed one is a 1 (it looked and found something).
    """
    manifest, _m, _dest = _scratch(tmp_path, authored=_smoke(tmp_path),
                                   suite_path="tests_that_are_not_there")

    code = publish.main(["--manifest", str(manifest), "--dry-run",
                         "--python", sys.executable])

    assert code == publish.EXIT_DID_NOT_RUN, (
        "a suite_path missing from the export returned %d; EXIT_REFUSED here "
        "would mean it was diagnosed as a narrowed collection" % code)


def test_the_gate_prints_the_collected_count_it_read(tmp_path, capsys):
    """Visible rather than inferred: the number is on the line, every run."""
    manifest, _m, _dest = _scratch(tmp_path, authored=_smoke(tmp_path))

    code = publish.main(["--manifest", str(manifest), "--dry-run",
                         "--python", sys.executable])
    printed = capsys.readouterr().out

    assert code == 0, printed
    line = [l for l in printed.splitlines() if "suite" in l]
    assert line, "no suite line was printed at all"
    assert "checked=1" in line[0], line[0]
    assert "of 1" in line[0], line[0]
    assert "floor=" in line[0], line[0]


# ---------------------------------------------------------------------------
# The export is read from the WORKING TREE, so a dirty tree is a refusal
# ---------------------------------------------------------------------------

def test_dirty_paths_really_reads_git(tmp_path):
    """A live control. A stub that always returned [] would satisfy the two
    tests below and would never refuse anything."""
    repo = tmp_path / "r"
    repo.mkdir()
    assert _git(["init", "-q", "."], repo).returncode == 0
    (repo / "f.txt").write_text("one\n", encoding="utf-8")
    assert _git(["add", "f.txt"], repo).returncode == 0
    assert _git(["-c", "user.name=t", "-c", "user.email=t@example.invalid",
                 "commit", "-q", "-m", "first"], repo).returncode == 0

    assert publish.dirty_paths(str(repo)) == [], (
        "a freshly committed tree reported as dirty")

    (repo / "f.txt").write_text("two\n", encoding="utf-8")
    dirty = publish.dirty_paths(str(repo))

    assert len(dirty) == 1, (
        "an edited tracked file produced %d porcelain line(s)" % len(dirty))


def test_a_dirty_working_tree_refuses(tmp_path, monkeypatch):
    """Measured: an export built from an edited-but-uncommitted module shipped
    the edit while HEAD still carried a stub, and the exported suite showed no
    failure for it. A published repository silently carried work absent from
    its own history."""
    manifest, _m, _dest = _scratch(tmp_path, authored=_smoke(tmp_path),
                                   allow_dirty_working_tree=False)
    monkeypatch.setattr(publish, "dirty_paths",
                        lambda _root: [" M tools/somewhere.py"])

    code = publish.main(["--manifest", str(manifest), "--dry-run",
                         "--python", sys.executable])

    assert code == publish.EXIT_REFUSED, (
        "a dirty source tree returned %d" % code)


def test_the_manifest_override_permits_a_dirty_working_tree(tmp_path, monkeypatch):
    """The override exists for the deliberate case and must be explicit."""
    manifest, _m, _dest = _scratch(tmp_path, authored=_smoke(tmp_path),
                                   allow_dirty_working_tree=True)
    monkeypatch.setattr(publish, "dirty_paths",
                        lambda _root: [" M tools/somewhere.py"])

    code = publish.main(["--manifest", str(manifest), "--dry-run",
                         "--python", sys.executable])

    assert code == 0, (
        "the declared override did not permit a dirty tree; got %d" % code)


def test_the_script_prints_the_unambiguous_spelling():
    """The naming decision, pinned where it can be broken by an edit.

    The banned verdict word reads as "deliberately and safely omitted", which is
    how a population of zero gets filed as a pass by a human reading a log. The
    four standalone tools that still print it do so because they call the shared
    reporting helper directly; this script imports no shared checking surface at
    all, so it is free to pick the unambiguous spelling and does.
    """
    source = PUBLISH_PATH.read_text(encoding="utf-8")
    live = [l for l in source.splitlines() if not l.lstrip().startswith("#")]
    body = "\n".join(live)

    assert "not-examined" in body, (
        "the script no longer prints the unambiguous spelling")

    banned = "skip" + "ped="
    assert banned not in body, (
        "the script prints the banned verdict word; the conventions forbid it "
        "outright in output a human reads")


# ---------------------------------------------------------------------------
# The authored example corpus describes the files it SHIPS, not the files it
# REPLACES.
#
# The corpus authored for the published repository kept the `bytes` and the
# `sha256` of four files that are not published and never will be -- so the
# export carried a verifiable FINGERPRINT of each of them. A fingerprint
# identifies a file even when its contents have been replaced, which is exactly
# what the replacement was for.
#
# Nothing in this section runs in an export. The module-level guard at the top
# stands the whole file down wherever the publisher is absent, and the published
# toolkit deliberately leaves the publisher behind -- so these assertions are
# free to read files that exist only here.
# ---------------------------------------------------------------------------

FIXTURE_DIR = REPO_ROOT / "scripts" / "publish" / "toolkit-publish"
FIXTURE_CORPUS = FIXTURE_DIR / "canon-bullets.json"
REAL_CORPUS = REPO_ROOT / "tools" / "canon-bullets.json"


def _fixture():
    return json.loads(FIXTURE_CORPUS.read_text(encoding="utf-8"))


def _fixture_text():
    return FIXTURE_CORPUS.read_text(encoding="utf-8")


def _real_corpus():
    """The FROZEN BASELINE. Read, never written -- and its population asserted.

    Its source rows are the only place the real files are NAMED, so the tests
    below derive the paths from it instead of carrying a private path as a
    literal in a file that is tracked.
    """
    corpus = json.loads(REAL_CORPUS.read_text(encoding="utf-8"))
    rows = [s for s in corpus.get("sources", [])
            if str(s.get("path", "")).startswith("..")]
    assert len(rows) == 4, (
        "the real corpus lists %d source row(s) pointing outside this "
        "repository; the differential below needs all four or it is comparing "
        "against a shorter list than it thinks" % len(rows))
    return corpus, rows


def _digest(path):
    payload = Path(path).read_bytes()
    return len(payload), hashlib.sha256(payload).hexdigest()


def test_every_example_source_row_describes_the_file_it_names():
    """`bytes` and `sha256` recomputed from the file each row's `path` names."""
    fixture = _fixture()
    rows = fixture["sources"]
    assert len(rows) == 4, "expected four source rows, got %d" % len(rows)

    checked = 0
    for row in rows:
        target = FIXTURE_DIR / str(row["path"]).replace("/", os.sep)
        assert target.is_file(), (
            "the corpus names %s and no such file ships beside it, so its "
            "`bytes` and `sha256` describe something nobody can see"
            % row["path"])
        size, digest = _digest(target)
        assert row["bytes"] == size, (
            "%s: the row claims %d byte(s), the file it names holds %d"
            % (row["path"], row["bytes"], size))
        assert row["sha256"] == digest, (
            "%s: the row's sha256 is not the digest of the file it names"
            % row["path"])
        checked += 1

    assert checked == 4, "checked %d of 4 rows" % checked


def test_the_example_source_paths_are_four_distinct_names():
    """The measured collapse: two names, four sources, different byte counts."""
    paths = [s["path"] for s in _fixture()["sources"]]

    assert len(paths) == 4
    assert len(set(paths)) == 4, (
        "four distinct sources rewrite onto %d name(s): %r"
        % (len(set(paths)), sorted(paths)))


def test_no_example_source_row_carries_a_real_private_fingerprint():
    """The differential. Asserting the numbers LOOK synthetic is not checkable.

    Both arms are measured: the pairs the frozen baseline RECORDS, and the pairs
    recomputed from the private files themselves. The second is what catches a
    row that was refreshed from the real file after the baseline was frozen.
    """
    _corpus, rows = _real_corpus()
    text = _fixture_text()
    fixture_pairs = {(s["bytes"], s["sha256"]) for s in _fixture()["sources"]}

    recorded = {(r["bytes"], r["sha256"]) for r in rows}
    assert len(recorded) == 4, "the baseline's four rows are not four distinct pairs"

    recomputed = set()
    for row in rows:
        # FINDING SITE 4, and it is the only one of the four whose mechanism is
        # legible on one line. Every row here is a `..`-relative path naming a
        # file BESIDE THE MAIN CHECKOUT. Resolved against `REPO_ROOT` -- the
        # WORKING checkout -- it becomes <main>/agent-worktrees/worktrees/information/...
        # inside an agent worktree, which is not a file, so the assertion below
        # fires and the differential never runs. The row's own anchor is the
        # main root; nothing about it was ever working-relative.
        target = conftest.MAIN_REPO_ROOT / str(row["path"]).replace("/", os.sep)
        assert target.is_file(), (
            "a source the frozen baseline names is not reachable at %s, so the "
            "recomputed arm of this differential would compare nothing"
            % target)
        recomputed.add(_digest(target))
    assert len(recomputed) == 4

    for kind, pairs in (("recorded by the baseline", recorded),
                        ("recomputed from the file", recomputed)):
        for size, digest in pairs:
            assert (size, digest) not in fixture_pairs, (
                "a (bytes, sha256) pair %s survives in the example corpus" % kind)
            assert str(size) not in text, (
                "a byte count %s appears in the example corpus text" % kind)
            assert digest not in text, (
                "a sha256 %s appears in the example corpus text" % kind)


def test_no_tracked_file_carrying_a_REAL_CLAIM_survives_into_the_export():
    """The guard that would have caught the leak that produced it.

    WHAT WAS MEASURED, by an earlier plan, by LISTING the built export rather than
    by re-reading the manifest's pattern: two tracked files carried a real
    private claim's text verbatim into the export --

        _records/corrections.md
        _records/corrections/<stamp>--example-cache-benchmark--corrections.md

    -- along with that claim's bullet id and the plan id that wrote it. Three
    of the things a published repository must never hold, in one file, and the
    export's leak scan reported CLEAN over all 174 of them.

    IT REPORTED CLEAN CORRECTLY. Its needles are internal VOCABULARY -- planning
    paths, agent references, a census file count. A measured claim about median
    latency contains no vocabulary of that kind, so the scan was answering a
    different question perfectly well. A check that cannot DISCRIMINATE between
    "no internal words" and "no real claims" is not a check for the second one.

    So this asks the other question, and asks it at the SOURCE rather than
    after a four-minute build: every tracked file whose bytes contain a real
    bullet's own text must be either DROPPED by the exclude pattern or REPLACED
    by an authored file. Both dispositions are recorded per file, so adding a
    new record that quotes a claim fails here, on the commit that adds it.
    """
    manifest = json.loads(
        (REPO_ROOT / "scripts" / "publish" / "toolkit-publish.json")
        .read_text(encoding="utf-8"))
    excluded = re.compile(manifest["exclude_pattern"])
    authored = set(manifest["authored"])

    corpus = json.loads(REAL_CORPUS.read_text(encoding="utf-8"))
    needles = {}
    for key, entry in corpus["bullets"].items():
        for field in ("text", "metric", "metric_basis", "backing"):
            value = str(entry.get(field) or "")
            # Long enough that a match is the CLAIM and not a shared phrase.
            if len(value) >= 60:
                needles["%s.%s" % (key, field)] = value
    assert len(needles) >= 100, (
        "derived only %d claim needle(s) from the corpus; a scan this thin "
        "would report a clean export it never really searched" % len(needles))

    tracked = [name for name in _git(["ls-files"], REPO_ROOT).stdout.splitlines()
               if name.strip()]
    assert len(tracked) >= 200, len(tracked)

    scanned = 0
    carriers = {}
    for name in tracked:
        path = REPO_ROOT / name.replace("/", os.sep)
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        found = sorted(label for label, needle in needles.items()
                       if needle in text)
        if found:
            carriers[name] = found

    survivors = {}
    for name, found in sorted(carriers.items()):
        if excluded.match(name) or name in authored:
            continue
        survivors[name] = found

    print("claim-carrying tracked files: %d of %d scanned; %d survive the "
          "export" % (len(carriers), scanned, len(survivors)))
    for name, found in sorted(carriers.items()):
        disposition = ("excluded" if excluded.match(name)
                       else "authored" if name in authored else "SURVIVES")
        print("    %-9s %-64s %d claim field(s)"
              % (disposition, name, len(found)))

    # The scan has to be able to find one, or its zero is a property of the walk.
    assert "tools/canon-bullets.json" in carriers, (
        "the corpus itself did not come back as a carrier, so this scan is "
        "not reading what it thinks it is reading")

    assert not survivors, (
        "%d tracked file(s) carry a real bullet's own text and are neither "
        "excluded nor replaced by an authored file, so a real private claim "
        "would ship: %s"
        % (len(survivors), json.dumps(survivors, indent=2, sort_keys=True)))


# THE TOOLKIT MANIFEST FIRST, because the artifacts inherit its rules and the
# comparison is against it. The artifacts follow in publication order.
PUBLISHED = ("toolkit-publish", "artifact-publish", "an earlier round-eslog",
             "engagement")

# Where each export keeps the vendored core. The toolkit keeps it under tools/;
# an artifact vendors it to its own root. Same bytes, different home, and the
# test has to know that.
CORE_SUBDIR = {"toolkit-publish": "tools"}


def _core_root(name, dest):
    """The directory inside one export that holds its vendored core.

    THREE ANSWERS, NOT TWO, once an export can be NESTED. The toolkit keeps the
    core under tools/. A standalone artifact vendors it to its own root, which
    is the export root. A nested artifact vendors it to its own root too -- but
    that root is now the destination prefix, and a lookup that stopped at the
    export root would find no .vendor.json there, drop that export out of the
    declared population, and compare the remaining ones happily. A set
    assertion that silently loses a member is the failure this whole test
    exists to catch, wearing the other hat.

    Derived from the manifest rather than tabulated, so adding a nested export
    does not require remembering to add a row here.
    """
    subdir = CORE_SUBDIR.get(name)
    if subdir is None:
        subdir = publish.resolve_dest_prefix(
            json.loads((REPO_ROOT / "scripts" / "publish" / ("%s.json" % name))
                       .read_text(encoding="utf-8")))
    return Path(dest) / subdir.replace("/", os.sep) if subdir else Path(dest)


def _declared_core(export_dir):
    """The core's python modules, DERIVED from an artifact's own .vendor.json.

    NOT ENUMERATED HERE, and the difference has already cost something. A
    hand-written list stops covering a check module the day one is added, and
    silently: this test carried `check_01 .. check_09` while the artifacts had
    been vendoring `check_16` as well, so the newest module in the core was the
    one module nothing compared. Reading the vendor manifest cannot drift,
    because it is the same file `vendor.py audit` reads.
    """
    data = json.loads((Path(export_dir) / ".vendor.json")
                      .read_text(encoding="utf-8"))
    return sorted(rel for rel in data["files"] if rel.endswith(".py"))


def test_every_published_repository_ships_a_BYTE_IDENTICAL_core(tmp_path):
    """The contract a reader can check in one command, over ALL THREE exports.

    Every published repository vendors the same frozen core and REWORDS it on
    the way out, so "the cores are identical" is a FUNCTION OF THE REWRITE RULES
    rather than a property of the source. The deferred record names this exact
    check as the one that would catch a drift and as having "no counterpart
    today"; this is the counterpart.

    It is why the artifact manifests INHERIT the toolkit's rules instead of
    copying them, and it is what would fail if anyone copied them back: a rule
    added to one side and not the others moves one core's bytes and not the
    rest, and nothing else in this suite would notice.

    IT COMPARED TWO EXPORTS AND NOW COMPARES THREE. A pairwise assertion is not
    a set assertion: with a third repository in the programme, two agreeing
    while the third drifts is exactly the failure this exists to catch, and the
    two-export form would have reported a clean pass over it.

    NO DIGEST IS QUOTED HERE. The exported core's hash moves whenever a rule is
    added -- it moved when five uppercase rules closed a phase-number leak, and
    again when fifty-one rules closed the identifier ruling -- so a test
    asserting a literal would be asserting its own output and would go stale
    silently. The assertion is EQUALITY ACROSS THE SET, which is the property
    that actually matters.
    """
    exports = {}
    for name in PUBLISHED:
        manifest = json.loads(
            (REPO_ROOT / "scripts" / "publish" / ("%s.json" % name))
            .read_text(encoding="utf-8"))
        dest = str(tmp_path / name)
        publish.build_export(manifest, dest)
        exports[name] = _core_root(name, dest)

    # The population is the artifacts' own declaration, and the artifacts must
    # agree about it before anything is compared. A comparison over a
    # population two sides describe differently is not a comparison.
    declared = {name: _declared_core(path) for name, path in exports.items()
                if (Path(path) / ".vendor.json").is_file()}
    # AND THE DECLARERS ARE COUNTED. `declared` being non-empty is satisfied by
    # ONE export; the byte comparison below then runs over a set of one and
    # passes without comparing anything across repositories. Every export that
    # is not the toolkit vendors the core, so the floor is the set minus one.
    assert len(declared) >= len(PUBLISHED) - 1, (
        "only %d of %d export(s) declare a vendored core, so at least one "
        "dropped out of the population silently: %s"
        % (len(declared), len(PUBLISHED), sorted(declared)))
    assert declared, (
        "no export carries a .vendor.json, so the core population is unknown. "
        "A clean verdict over an unknown population is not a pass")
    shapes = {name: tuple(files) for name, files in declared.items()}
    assert len(set(shapes.values())) == 1, (
        "the artifacts declare DIFFERENT vendored cores, so there is no single "
        "population to compare: %s"
        % json.dumps({k: list(v) for k, v in shapes.items()},
                     indent=2, sort_keys=True))
    core = list(next(iter(shapes.values())))
    assert len(core) >= 10, (
        "only %d core module(s) declared; the population floor exists so a "
        "vendor manifest that lost its file list cannot pass this by "
        "comparing nothing" % len(core))

    compared = 0
    for rel in core:
        digests = {}
        for name in PUBLISHED:
            path = Path(exports[name]) / rel.replace("/", os.sep)
            assert path.is_file(), "the %s export has no %s" % (name, rel)
            digests[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        assert len(set(digests.values())) == 1, (
            "%s differs across the exports (%s). The published repositories "
            "would ship different cores, and the byte-identical claim they "
            "make would be false. A rewrite rule was almost certainly added to "
            "one manifest and not the others -- the artifact manifests INHERIT "
            "the toolkit's set precisely so that cannot happen."
            % (rel, ", ".join("%s=%s" % (n, d[:12])
                              for n, d in sorted(digests.items()))))
        compared += 1

    assert compared == len(core), compared
    print("core files compared: %d, all byte-identical across %d export(s): %s"
          % (compared, len(PUBLISHED), ", ".join(PUBLISHED)))


def _claim_needles():
    """The same derivation the toolkit's claim guard uses, shared not re-written.

    One copy, so the two guards cannot drift into scanning for different things
    while both reporting clean.
    """
    corpus = json.loads(REAL_CORPUS.read_text(encoding="utf-8"))
    needles = {}
    for key, entry in corpus["bullets"].items():
        for field in ("text", "metric", "metric_basis", "backing"):
            value = str(entry.get(field) or "")
            if len(value) >= 60:
                needles["%s.%s" % (key, field)] = value
    return needles


# THE ONE INTENDED CARRIER, named rather than pattern-matched.
#
# The redis README's claim table quotes a real bullet's text VERBATIM, and the
# owner ruled that the whole table ships: the table carries the organization, the
# role, the engagement window, the bullet id, that text and the verdict, so the
# claim is presented to the reader in full rather than pointed at. An artifact
# repository that names the claim it backs is doing what it exists to do.
#
# THIS SET IS A CARVE-OUT, NOT A WIDENING, and the difference is the whole
# value of the guard. Widening it -- dropping the README from the scan, or
# raising the 60-character floor until nothing matched -- would disarm it for
# the carriers it exists to catch, which is how the leak that produced it got
# out: two records quoted a claim and the scan that ran over them was looking
# for internal vocabulary instead. One file, by name, with its reason.
INTENDED_CLAIM_CARRIER_WHY = (
    "the claim table, which ships by owner ruling: the bullet's text sits "
    "beside the organization, the role, the engagement window, the id and the "
    "verdict, so a reader can check the claim instead of taking it")

# BOTH MANIFESTS OVER THE ARTIFACT TREE, because there are two now and a guard
# run over one of them says nothing about the other. The second nests the same
# files under a destination prefix, so the carve-out and the corpus key are
# DERIVED from each manifest's own prefix rather than written twice -- a
# carve-out keyed to the wrong destination exempts a path that does not exist
# and reports the file it was written for as an unexplained survivor.
ARTIFACT_MANIFESTS = ("artifact-publish", "engagement")


def _claim_guard_case(name):
    """(manifest, intended-carrier map, corpus destination) for one export."""
    manifest = json.loads(
        (REPO_ROOT / "scripts" / "publish" / ("%s.json" % name))
        .read_text(encoding="utf-8"))
    prefix = publish.resolve_dest_prefix(manifest)
    carriers = {prefix + "README.md": INTENDED_CLAIM_CARRIER_WHY}
    return manifest, carriers, prefix + "canon-bullets.json"


def _shipping_sources(manifest):
    """(destination path -> source file) for everything the export will contain.

    THE POPULATION IS THE EXPORT'S, NOT THE SOURCE TREE'S, and the distinction
    is the whole reason this helper exists rather than a `git ls-files` loop.

    A first draft of the guard below walked the artifact's tracked files and
    classified each as excluded / authored / survivor. It reported clean, and it
    could not have done otherwise: README.md is DROPPED by the exclude pattern
    and supplied by an AUTHORED file instead, so the tracked copy -- the only one
    that walk could see -- never ships, while the authored copy, which is the
    one a reader actually gets, was not in the population at all. Both guards
    were blind to the same file for the same reason, and a carve-out written for
    it was dead code that exempted nothing.

    So the map is built the way `build_export` builds the export: tracked files
    that survive the exclusion, then authored files layered over them, winning
    on collision. Scanning the SOURCE bytes of each is the fail-closed
    direction -- a rewrite could only ever remove a claim, never add one.

    THE KEYS ARE DESTINATIONS, AND THE TRANSFORMS ARE THE SCRIPT'S OWN. Path
    rewrites and `dest_prefix` are applied here by CALLING publish_repo rather
    than by reimplementing them, so this map and the export cannot drift into
    disagreeing about where a file lands. It matters for the carve-out beside
    it: a carve-out keyed to a destination the export no longer uses exempts a
    path that does not exist -- a standing exemption with nothing under it --
    while the file it was written for is reported as an unexplained survivor.
    """
    source_root = Path(manifest["source_root"]) if manifest.get("source_root") \
        else REPO_ROOT
    excluded = re.compile(manifest["exclude_pattern"])
    prefix = publish.resolve_dest_prefix(manifest)
    path_rules = publish.manifest_path_rewrites(manifest)
    shipping = {}
    for name in _git(["ls-files"], source_root).stdout.splitlines():
        name = name.strip()
        if not name or excluded.match(name):
            continue
        out = publish.apply_dest_prefix(
            publish.apply_path_rewrites(name, path_rules), prefix)
        shipping[out] = source_root / name.replace("/", os.sep)
    for dest, src in manifest.get("authored", {}).items():
        shipping[publish.apply_dest_prefix(dest, prefix)] = \
            REPO_ROOT / src.replace("/", os.sep)
    # Root-authored pages belong to the repository rather than to the project,
    # so they do NOT take the prefix -- and they are in the population, because
    # they are files a reader gets and a claim could reach one of them.
    for dest, src in manifest.get("authored_root", {}).items():
        shipping[dest] = REPO_ROOT / src.replace("/", os.sep)
    return shipping


@pytest.mark.parametrize("manifest_name", ARTIFACT_MANIFESTS)
def test_nothing_the_ARTIFACT_export_SHIPS_carries_a_REAL_CLAIM_unintentionally(
        manifest_name):
    """The second published repository, which the first guard could not see.

    ITS SCOPE WAS MEASURED, NOT ASSUMED, TWICE. The toolkit's claim guard reads
    `toolkit-publish.json` and walks THIS repository's tracked files, so it
    never reached the redis artifact's work tree. Pointing a copy of it at that
    tree then reported clean for a second reason -- it walked tracked files, and
    the README that ships is an authored one. The population that matters is
    what the export CONTAINS, and that is what this walks.

    Measured: of the files the redis export ships, exactly two carry a real
    bullet's own text -- the authored README, which is the intended carrier
    named above, and the claim corpus, which is the SYNTHETIC one. The corpus
    being a carrier is itself the proof that the scan is reading something.
    """
    manifest, intended, corpus_key = _claim_guard_case(manifest_name)
    assert Path(manifest["source_root"]).is_dir(), manifest["source_root"]

    needles = _claim_needles()
    assert len(needles) >= 100, (
        "derived only %d claim needle(s); a scan this thin would report a "
        "clean export it never really searched" % len(needles))

    shipping = _shipping_sources(manifest)
    assert len(shipping) >= 150, (
        "the export ships %d file(s); a population that small is a property of "
        "the walk, not of the tree" % len(shipping))

    scanned = 0
    carriers = {}
    for dest, path in sorted(shipping.items()):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        found = sorted(label for label, needle in needles.items()
                       if needle in text)
        if found:
            carriers[dest] = found

    survivors = {d: f for d, f in carriers.items() if d not in intended}

    print("%s -- SHIPPING files scanned: %d of %d; claim carriers %d; "
          "survivors %d" % (manifest_name, scanned, len(shipping),
                            len(carriers), len(survivors)))
    for dest, found in sorted(carriers.items()):
        print("    %-9s %-52s %d claim field(s)"
              % ("INTENDED" if dest in intended else "SURVIVES",
                 dest, len(found)))

    # THE SHIPPED CORPUS MUST NOT BE THE REAL ONE. Asserted here as well as by
    # digest elsewhere, because this guard reads the same bytes and a corpus
    # carrying 195 claim fields would be the loudest possible finding.
    corpus = shipping.get(corpus_key)
    assert corpus is not None, (
        "the export ships no claim corpus at %s; the destinations it does "
        "ship start %s" % (corpus_key, sorted(shipping)[:5]))
    assert len(carriers.get(corpus_key, [])) < 100, (
        "the export's claim corpus carries %d real claim fields, so it is the "
        "OWNER'S CORPUS rather than the synthetic one"
        % len(carriers.get(corpus_key, [])))

    assert not survivors, (
        "%d file(s) the export SHIPS carry a real bullet's own text and are not "
        "a named intended carrier: %s"
        % (len(survivors), json.dumps(survivors, indent=2, sort_keys=True)))


@pytest.mark.parametrize("manifest_name", ARTIFACT_MANIFESTS)
def test_the_artifact_claim_guard_FIRES_without_its_carve_out(manifest_name):
    """A guard whose negative was never observed is a guard nobody has tested.

    The first version of the guard above passed with the carve-out AND with it
    removed, because the file it exempted was already invisible to the walk.
    That is indistinguishable from a working guard when you only ever run it in
    the passing direction. This runs it in the other one.
    """
    manifest, intended, corpus_key = _claim_guard_case(manifest_name)
    needles = _claim_needles()
    shipping = _shipping_sources(manifest)

    carriers = set()
    for dest, path in shipping.items():
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if any(needle in text for needle in needles.values()):
            carriers.add(dest)

    without = carriers - {corpus_key}
    with_carve = without - set(intended)

    print("%s -- carriers without the carve-out: %s"
          % (manifest_name, sorted(without)))
    print("%s -- carriers with    the carve-out: %s"
          % (manifest_name, sorted(with_carve)))

    assert without, (
        "with the carve-out removed the guard still finds nothing, so it is "
        "not watching the file it claims to exempt")
    assert not with_carve, sorted(with_carve)


@pytest.mark.parametrize("manifest_name", ARTIFACT_MANIFESTS)
def test_every_intended_claim_carrier_really_does_carry_one(manifest_name):
    """A carve-out that has stopped applying is a hole nobody is watching.

    Two ways it can stop applying, and both are checked here. The README could
    be reworded so it no longer quotes the bullet -- then the entry sits in the
    set forever, exempting a file for a reason that has ceased to be true, and
    the next file to take that name inherits the exemption silently. Or the
    export could MOVE the file, which is exactly what a destination prefix
    does: the carve-out then names a path nothing ships, exempts nothing, and
    the real carrier is reported as a survivor.

    So the carve-out is resolved THROUGH THE SHIPPING MAP rather than against
    the source tree. That asks the same question the guard asks, which is the
    only way the two can agree about what a name means.
    """
    manifest, intended, _corpus = _claim_guard_case(manifest_name)
    shipping = _shipping_sources(manifest)
    needles = _claim_needles()

    for name, why in intended.items():
        path = shipping.get(name)
        assert path is not None, (
            "%s is carved out of the claim guard but the export ships nothing "
            "at that destination, so the exemption covers a path that does not "
            "exist" % name)
        assert path.is_file(), "%s is carved out but %s does not exist" % (
            name, path)
        text = path.read_text(encoding="utf-8")
        found = sorted(label for label, needle in needles.items()
                       if needle in text)
        assert found, (
            "%s is carved out of the claim guard for this reason -- %s -- but "
            "no longer carries any real claim text. Remove the carve-out "
            "rather than leaving a standing exemption with nothing under it"
            % (name, why))
        print("INTENDED carrier %s still carries %d claim field(s): %s"
              % (name, len(found), found))


def test_no_example_source_row_carries_a_real_read_at_timestamp():
    """a design rule names `bytes` and `sha256`; `read_at` was identical 4 of 4 too."""
    _corpus, rows = _real_corpus()
    text = _fixture_text()

    stamps = {r["read_at"] for r in rows}
    assert len(stamps) == 4, "the baseline's four read_at values are not distinct"
    for stamp in stamps:
        assert stamp not in text, (
            "a read_at value from the frozen baseline survives in the example "
            "corpus")


def test_the_census_block_is_synthetic_including_its_count():
    """The manifest EXCLUDES the census records because they list every path
    under a directory that is not published -- and the authored replacement
    shipped that walk's exact file count, defeating the exclusion its own note
    explains. The count is read from the baseline here, never retyped."""
    corpus, _rows = _real_corpus()
    real_census = corpus["census"]
    fixture = _fixture()
    text = _fixture_text()

    assert str(real_census["files_censused"]) not in text, (
        "the real census file count survives in the example corpus")
    for key in ("before", "after"):
        assert real_census[key] not in text, (
            "a real census record filename survives in the example corpus")
        assert fixture["census"][key] != real_census[key]
    assert fixture["census"]["files_censused"] != real_census["files_censused"]


def _derive_counts(fixture):
    """The snapshot tool's OWN derivation, applied to the fixture's bullets.

    Copied in shape from the generator rather than invented here, so a fixture
    whose `counts` block was carried over from somewhere else fails instead of
    being re-blessed by a second, more forgiving formula.
    """
    bullets = fixture["bullets"]
    needle = fixture["needles"]["not_yet_run"]
    per_canon = {}
    for key in bullets:
        per_canon[key.split(":", 1)[0]] = per_canon.get(key.split(":", 1)[0], 0) + 1
    with_needle = sorted(
        key for key, b in bullets.items()
        if needle in "\n".join(str(b.get(f) or "") for f in
                               ("text", "metric", "metric_basis", "backing")))
    ids = {}
    for key in bullets:
        ids.setdefault(key.split(":", 1)[1], []).append(key)
    collisions = sorted(i for i, keys in ids.items() if len(keys) > 1)
    return {
        "sources": len(fixture["sources"]),
        "bullets_total": len(bullets),
        "per_canon": per_canon,
        "with_metric_basis": sum(1 for b in bullets.values()
                                 if (b.get("metric_basis") or "").strip()),
        "with_not_yet_run": len(with_needle),
        "not_yet_run_exceptions": sorted(set(bullets) - set(with_needle)),
        "id_collisions": len(collisions),
        "id_collisions_list": collisions,
        "build_path_slugs": sum(len(v) for v in fixture["build_paths"].values()),
    }


def test_the_counts_block_is_derived_from_the_fixture_s_own_bullets():
    """A copied count is a claim about somebody else's corpus.

    `with_not_yet_run` is the one that cannot be hand-waved: the shipped block
    said 48 of 49 over bullets not one of which carried the marker, so the
    number was a fact about the real snapshot and nothing else.
    """
    fixture = _fixture()
    derived = _derive_counts(fixture)

    for key, value in derived.items():
        assert fixture["counts"][key] == value, (
            "counts[%r] is %r; derived from the fixture's own bullets it is %r"
            % (key, fixture["counts"].get(key), value))

    for key, value in fixture["expected"].items():
        assert fixture["counts"][key] == value, (
            "expected[%r] is %r and counts[%r] is %r -- a committed literal "
            "that disagrees with the derivation has stopped checking"
            % (key, value, key, fixture["counts"].get(key)))


def test_the_counts_exception_list_names_the_fixture_s_own_bullet():
    """The exception is a member of this corpus, not a citation of another."""
    fixture = _fixture()
    exceptions = fixture["counts"]["not_yet_run_exceptions"]

    assert len(exceptions) == 1, (
        "expected exactly one bullet without the pending marker, got %r"
        % (exceptions,))
    assert exceptions[0] in fixture["bullets"], (
        "%r is named as an exception and is not a bullet in this corpus"
        % exceptions[0])


def test_the_example_corpus_carries_no_programme_vocabulary():
    """Assembled from fragments so this module is not its own hit."""
    text = _fixture_text().lower()
    banned = ["build" + " path", "canon" + "-backing", "gs" + "d",
              "pha" + "se ", "pl" + "an 0"]

    live_control = "build" + " path"
    assert live_control in "an example example project description".lower(), (
        "the assembled needle does not match a string that obviously carries "
        "it, so a zero below would prove nothing")

    hits = [n for n in banned if n in text]
    assert not hits, (
        "the example corpus carries %d forbidden token(s): %r" % (len(hits), hits))


def test_the_example_corpus_still_satisfies_the_claim_corpus_schema():
    """A replacement, not a deletion. The checks that read it must still read it."""
    fixture = _fixture()
    compound = re.compile(r"^[a-z0-9-]+:P\d+-B\d+$")

    assert fixture["schema"] == "canon-bullets/1"
    assert fixture["schema_version"] == 1
    assert len(fixture["bullets"]) == 49

    bad = sorted(k for k in fixture["bullets"] if not compound.match(k))
    assert not bad, "%d bullet key(s) are not canon-qualified: %r" % (len(bad), bad)

    required = ("backing", "canon", "id", "metric", "metric_basis", "project",
                "text")
    for key, record in fixture["bullets"].items():
        missing = [f for f in required if f not in record]
        assert not missing, "%s is missing %r" % (key, missing)
        assert record["canon"] == key.split(":", 1)[0]
        assert record["id"] == key.split(":", 1)[1]


def test_the_manifest_ships_every_example_file_the_corpus_names():
    """A corpus naming files the export does not carry re-creates the defect.

    The scan recomputes each row's digest from the file the row names, so a row
    whose file never reached the export has no declared value and becomes a hit.
    """
    manifest = json.loads(
        (REPO_ROOT / "scripts" / "publish" / "toolkit-publish.json")
        .read_text(encoding="utf-8"))
    authored = manifest["authored"]

    for row in _fixture()["sources"]:
        rel = str(row["path"])
        assert rel in authored, (
            "the corpus names %s and the manifest does not ship it" % rel)
        src = REPO_ROOT / authored[rel].replace("/", os.sep)
        assert src.is_file(), (
            "the manifest maps %s to %s, which does not exist"
            % (rel, authored[rel]))
        # Against the ROW, not against the path the row names. Comparing the
        # manifest's source to the corpus-relative path would be the same file
        # twice and would hold whatever either one contained.
        assert _digest(src) == (row["bytes"], row["sha256"]), (
            "the manifest ships a file at %s whose digest is not the one the "
            "corpus row declares" % rel)


# ---------------------------------------------------------------------------
# This module must not be a hit for the scan it tests
# ---------------------------------------------------------------------------

def test_this_module_is_not_itself_a_hit_for_the_scan_it_tests():
    """A guard that scans source must not match its own documentation.

    The live control matters as much as the zero: a needle assembled the same
    way the script assembles its own must MATCH, or a clean result here would be
    a broken search rather than a measurement.
    """
    live_control = "Co-Authored" + "-By"
    assert publish.LEAK.search(live_control), (
        "the scan did not match an assembled banned token, so a zero below "
        "would prove nothing about this file")

    text = io.open(__file__, encoding="utf-8").read()
    hits = [(i, line.strip()[:90])
            for i, line in enumerate(text.splitlines(), 1)
            if publish.LEAK.search(line)]

    assert not hits, (
        "this module is a tracked file and travels into every export, so a "
        "forbidden literal here would make the leak scan refuse a real "
        "publish. Hits: %r" % (hits,))


def test_the_module_level_guard_matches_what_the_toolkit_export_actually_does():
    """Both premises of the guard at the top of this file, pinned.

    The guard exists because the toolkit export ships this module while
    excluding the publisher it tests. If either half of that ever changes the
    guard becomes wrong in one direction or dead in the other, and a check
    nobody can trip is worse than no check.
    """
    manifest_path = REPO_ROOT / "scripts" / "publish" / "toolkit-publish.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    exclude = re.compile(manifest["exclude_pattern"])

    assert exclude.match("scripts/publish_repo.py"), (
        "the toolkit export no longer excludes the publisher, so the guard at "
        "the top of this module now suppresses tests that could have run")
    assert not exclude.match("tools/tests/test_publish_repo.py"), (
        "this module is no longer exported, so the guard is dead code -- delete "
        "it rather than leaving a branch nothing can reach")

    source = io.open(__file__, encoding="utf-8").read()
    assert "allow_module_level=True" in source, (
        "the module-level guard is gone; this module would raise at import "
        "time in every export that omits the publisher, which is a collection "
        "error and not a test failure")


# ---------------------------------------------------------------------------
# THE TWO REWRITE KINDS THE NEUTRALISATION NEEDED
# ---------------------------------------------------------------------------


def test_a_regex_rewrite_rewords_the_exported_copy(tmp_path):
    """A literal rule can only delete the token it names, and a citation is not
    a token. ``, `a design rule's shape` and `an earlier plan` are three sentence
    shapes around one class of identifier, and neutralising the identifier
    alone leaves `()` and `'s shape` behind."""
    repo, _names = _fixture_work_tree(tmp_path)
    (repo / "doc.md").write_text(
        "a sentence (XY-18) and another XY-19's shape\n", encoding="utf-8")
    assert _git(["add", "doc.md"], repo).returncode == 0
    assert _git(["-c", "user.name=t", "-c", "user.email=t@example.invalid",
                 "commit", "-q", "-m", "doc"], repo).returncode == 0

    _manifest, m, dest = _scratch(
        tmp_path, exclude_pattern=KEEP_EVERYTHING, authored=_smoke(tmp_path),
        source_root=str(repo),
        rewrites=[{"pattern": r"[ \t]*\(XY-\d{2}\)", "to": ""},
                  {"pattern": r"\bXY-\d{2}'s\b", "to": "a rule's"}])

    result = publish.build_export(m, dest)

    assert result["reworded"] == 1, (
        "the build reworded %d file(s); the regex rewrite did not fire"
        % result["reworded"])
    text = (Path(dest) / "doc.md").read_text(encoding="utf-8")
    assert text == "a sentence and another a rule's shape\n", repr(text)


def test_a_path_rewrite_renames_the_destination_and_leaves_the_source(tmp_path):
    """A content rewrite cannot reach a filename, and a filename is where the
    last copy of a private name survives a repair reported as complete."""
    repo, _names = _fixture_work_tree(tmp_path)
    secret = repo / "a-private-name" / "note.md"
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text("body\n", encoding="utf-8")
    assert _git(["add", "a-private-name/note.md"], repo).returncode == 0
    assert _git(["-c", "user.name=t", "-c", "user.email=t@example.invalid",
                 "commit", "-q", "-m", "p"], repo).returncode == 0

    _manifest, m, dest = _scratch(
        tmp_path, exclude_pattern=KEEP_EVERYTHING, authored=_smoke(tmp_path),
        source_root=str(repo),
        path_rewrites=[{"from": "a-private-name", "to": "a-neutral-name"}])

    result = publish.build_export(m, dest)

    assert result["renamed"] == 1, (
        "the build renamed %d path(s)" % result["renamed"])
    assert (Path(dest) / "a-neutral-name" / "note.md").is_file(), (
        "the renamed destination is not there: %s"
        % sorted(p.name for p in Path(dest).iterdir()))
    assert not (Path(dest) / "a-private-name").exists(), (
        "the original path survives in the export, so the rename added a copy "
        "rather than moving one")
    assert secret.is_file(), "the SOURCE tree was modified; only the copy moves"


def test_the_exec_bit_restore_follows_a_path_rewrite(tmp_path):
    """A gate that stops checking when an unrelated rule moves its subject.

    The executable bit does not survive the copy -- `core.filemode` is false on
    this machine, so git records every freshly added file as 100644 and the
    export shipped a fail-closed hook that git SKIPS WITHOUT SAYING SO. The
    restore loop looks the file up in the export BY ITS SOURCE NAME. A path
    rewrite would make that lookup miss, the branch fall through, and the bit
    quietly not be restored -- and the run would print exactly what a clean run
    prints, because the loop only reports what it found.
    """
    repo, _names = _fixture_work_tree(tmp_path)
    hook = repo / "hooks-old" / "gate.sh"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    assert _git(["add", "hooks-old/gate.sh"], repo).returncode == 0
    assert _git(["update-index", "--chmod=+x", "--", "hooks-old/gate.sh"],
                repo).returncode == 0
    assert _git(["-c", "user.name=t", "-c", "user.email=t@example.invalid",
                 "commit", "-q", "-m", "hook"], repo).returncode == 0
    # The premise, asserted rather than assumed: git really does record 100755
    # here, or this test proves nothing in either direction.
    modes = _git(["ls-files", "-s"], repo).stdout
    assert "100755" in modes, (
        "the fixture's hook is not recorded executable, so the restore this "
        "test exercises has nothing to restore:\n%s" % modes)

    manifest, m, dest = _scratch(
        tmp_path, exclude_pattern=KEEP_EVERYTHING, authored=_smoke(tmp_path),
        source_root=str(repo),
        path_rewrites=[{"from": "hooks-old", "to": "hooks-new"}])

    code = publish.main(["--manifest", str(manifest), "--dry-run",
                         "--python", sys.executable])
    assert code == 0, "the scratch publish returned %d" % code

    exported = _git(["ls-files", "-s"], Path(dest)).stdout
    rows = [line for line in exported.splitlines()
            if line.endswith("hooks-new/gate.sh")]
    assert rows, (
        "the renamed hook is not in the export's index at all:\n%s" % exported)
    assert rows[0].startswith("100755"), (
        "the exec bit was not restored on the RENAMED path, so the restore "
        "silently stopped finding its subject: %r" % rows[0])


def test_the_remote_url_is_built_from_the_repository_name_alone():
    """The pure half, pinned separately from the run that uses it."""
    author = {"github_user": "a-user", "name": "n", "email": "e@example.invalid"}
    assert publish.remote_url(author, "a-repo") == (
        "https://github.com/a-user/a-repo.git")


def test_the_push_url_survives_the_exec_bit_loop(tmp_path, capsys):
    """THE REGRESSION PIN for a real, measured publish failure.

    The exec-bit loop bound `name` -- the same local the push URL was
    interpolated from two hundred lines above. After the loop it held the last
    executable file's path, so the owner's approved publish tried to reach
    `github.com/<user>/.githooks/pre-push.git` and git answered
    `remote: Not Found`. Every gate before the push was green.

    TWO PROPERTIES MAKE THIS PIN ABLE TO DISCRIMINATE, and without either one
    it would pass against the bug:

      1. THE FIXTURE CARRIES A 100755 FILE and the run is asserted to have
         RESTORED it. If the loop never executes, the shadowed variable is
         never overwritten, the URL is right by accident, and a green result
         means nothing at all.
      2. THE URL IS READ OUT OF THE RUN'S OWN OUTPUT. It used to be built
         AFTER the `--dry-run` return, so no dry run could reach it -- six
         green ones did not. The construction now happens before that return
         and is printed, which is what lets a pin see it without a network
         call.
    """
    repo, _names = _fixture_work_tree(tmp_path)
    hook = repo / "hooks" / "gate.sh"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    assert _git(["add", "hooks/gate.sh"], repo).returncode == 0
    assert _git(["update-index", "--chmod=+x", "--", "hooks/gate.sh"],
                repo).returncode == 0
    assert _git(["-c", "user.name=t", "-c", "user.email=t@example.invalid",
                 "commit", "-q", "-m", "hook"], repo).returncode == 0
    assert "100755" in _git(["ls-files", "-s"], repo).stdout, (
        "the fixture has no executable file, so the loop under test would "
        "never run and this pin could not tell the bug from the fix")

    manifest, m, _dest = _scratch(
        tmp_path, exclude_pattern=KEEP_EVERYTHING, authored=_smoke(tmp_path),
        source_root=str(repo), repo="a-repository-name")

    code = publish.main(["--manifest", str(manifest), "--dry-run",
                         "--python", sys.executable])
    out = capsys.readouterr().out
    assert code == 0, out

    assert "exec-bit" in out and "RESTORED" in out, (
        "the exec-bit restore did not run, so the loop that shadowed the "
        "repository name never executed and this assertion proves nothing:\n%s"
        % out)

    announced = [l for l in out.splitlines() if "would push ->" in l]
    assert len(announced) == 1, (
        "expected exactly one push target in the output, got %d:\n%s"
        % (len(announced), out))
    url = announced[0].split("would push ->", 1)[1].strip()

    assert url == publish.remote_url(m["author"], m["repo"]), (
        "the push target is %r, which is not the URL for repository %r"
        % (url, m["repo"]))
    assert url.endswith("/%s.git" % m["repo"]), url
    assert "gate.sh" not in url and "hooks" not in url, (
        "the push target carries a FILE PATH from the exec-bit loop: %r" % url)


# ---------------------------------------------------------------------------
# WHAT A PUBLISHED REPOSITORY MAY NOT SAY
# ---------------------------------------------------------------------------
#
# The leak scan above answers "does internal VOCABULARY reach the export". It
# answers that correctly and it is not the only question. Measured on a built
# export while that scan reported `CLEAN found=0 checked=171 of 171`:
#
#     decision ids        826 occurrences in 104 of 171 files
#     plan ids            271 in 61
#     requirement ids     104 in 45
#     stage ids            62 in a union of 28
#     organization slugs      495 in 53, plus 6 PATHS
#     job titles            9 in 7   -- including a shipped CLI's --help text
#     engagement windows    9 in 8   -- two of them real, seven one digit away
#
# None of that is vocabulary, so none of it was a hit. A check that cannot
# DISCRIMINATE between "no internal words" and "no unresolvable identifiers"
# is not a check for the second one.
#
# EVERY NEEDLE BELOW IS DERIVED FROM DATA OR ASSEMBLED FROM FRAGMENTS, and
# neither is a style choice.
#
#   DERIVED, for the slugs and the bullet ids: they are read out of the real
#   expected set at run time, so the guard cannot go stale when the data moves
#   and this file carries no copy of them.
#
#   ASSEMBLED, for the vocabulary. A literal would make this module a carrier
#   for its own scan -- and worse, the export's own rewrite rules would REWRITE
#   THE NEEDLE. The rule that neutralises the role word matches inside a
#   pattern string that merely MENTIONS it, so an exported copy of this file
#   would carry a needle looking for something nobody writes. A check that
#   stops checking the moment its own file is processed is exactly the failure
#   this module exists to catch, one level up.


def _frag(*parts):
    """Join fragments at run time, so no forbidden literal sits in this file."""
    return "".join(parts)


def _month_alternation():
    """The three-letter month names, from the standard library rather than
    typed. A window needle keyed to a list somebody retyped is a needle with a
    typo waiting in it."""
    return "(?:" + "|".join(calendar.month_abbr[1:]) + ")"


def _neutralisation_classes():
    """(label, [compiled needle]) for every class a published tree may not carry.

    CHECK IDS ARE DELIBERATELY ABSENT from this list, and the reason is the
    test the rule itself states: a reader outside this programme cannot resolve
    an identifier unless something SHIPPED defines it, and the shipped README
    carries a table of every check id while the shipped tool prints them. 1,179
    occurrences in 97 files, resolvable, and therefore not a finding. Bare
    bullet ids are absent for the same reason -- the shipped example corpus
    defines every one of them, with its text -- while the QUALIFIED form is
    present here, because its prefix is an organization slug and no shipped file
    defines that.
    """
    expected = json.loads(
        (REPO_ROOT / "tools" / "manifest.json").read_text(encoding="utf-8"))
    rows = expected["slugs"]
    canons = sorted({r["canon"] for r in rows if r.get("canon")})
    qualified = sorted({b for r in rows
                        for b in list(r.get("bullets") or [])
                        + list(r.get("backs_bullets") or [])})
    # The needle set is only as strong as what it was derived FROM.
    assert len(canons) >= 2, (
        "derived %d canon slug(s) from the expected set; a slug needle this "
        "thin would report a clean export it never really searched" % len(canons))
    assert len(qualified) >= 40, (
        "derived only %d qualified bullet id(s)" % len(qualified))

    # The first hyphen-segment of a canon slug is the organization's NAME, which
    # survives inside a LONGER token that the whole-slug needle cannot see.
    # Measured: one example-project slug begins with an organization's name, in
    # four files and in a register the export's own checker cross-reads.
    stems = sorted({c.split("-")[0] for c in canons})

    account = os.path.basename(os.path.expanduser("~"))
    assert account and len(account) >= 3, (
        "could not derive this machine's account name, so its needle would "
        "match everything or nothing: %r" % account)

    month = _month_alternation()
    role = _frag("Engi", "neer ", "Int", "ern")

    # LETTER BOUNDARIES, NOT WORD BOUNDARIES, and the difference is a measured
    # blind spot rather than a style choice. `\b` counts `_` as part of a word,
    # so a needle built on it cannot see an employment word embedded in an
    # identifier -- `the_real_<word>_record`, `<WORD>_PREFIX`, `<word>_index` --
    # and a rewrite rule built the same way cannot remove one. This guard and
    # the rules shared that shape, so it passed over exactly what they missed.
    def words(*stems_):
        return [re.compile(r"(?<![A-Za-z])" + s + r"s?(?![A-Za-z])", re.I)
                for s in stems_]

    return [
        ("organization-slug", [re.compile(re.escape(c)) for c in canons]),
        ("organization-stem", [re.compile(r"\b" + re.escape(s) + r"\w*")
                           for s in stems]),
        ("qualified-bullet-id", [re.compile(re.escape(q)) for q in qualified]),
        ("decision-id", [re.compile(r"\bD-\d{2}\b")]),
        # The lookarounds are what tell a plan id from an ISO DATE: a record
        # stamped 2026-01-01 carries the characters of a plan id and is not
        # one. Measured: 67 of a previously reported 338 were dates.
        ("plan-id", [re.compile(r"(?<![-.\d\w])(?:0[12])-\d{2}(?![-\d])")]),
        ("requirement-id", [re.compile(r"\b(?:TOOL|PUB|BACK|CLOSE|ART)-\d+\b"),
                            re.compile(r"\bR-\d{2}(?:-\d{2})?\b")]),
        ("phase-or-wave", [re.compile(r"\b[Pp]hases? \d+\b"),
                           re.compile(r"\b[Ww]aves? \d+\b")]),
        ("job-title", [re.compile(r"\b(?:AI |Data Science )?" + role + r"\b")]),
        # A SHAPE, not four values: two of the nine windows measured were real
        # and seven were one digit away from real, which is worse, because a
        # near-miss reads as genuine and cannot be recognised as invented.
        ("engagement-window", [re.compile(
            month + r"\s+20\d\d\s*[-–]\s*" + month + r"\s+20\d\d")]),
        ("employment-word", words(_frag("int", "ern"),
                                  _frag("example role", "ship"),
                                  _frag("place", "ment"),
                                  _frag("employ", "er"),
                                  _frag("care", "er"),
                                  _frag("res", "ume"))),
        ("programme-word", words(_frag("work", "stream"),
                                 _frag("build ", "path"),
                                 _frag("port", "folio"))),
        ("account-name", [re.compile(re.escape(account), re.I)]),
    ]


def _count_over(texts, rels, pats):
    """(occurrences, carrying files, carrying paths) for one class."""
    occurrences = 0
    files = set()
    for rel, text in texts.items():
        hits = sum(len(p.findall(text)) for p in pats)
        if hits:
            occurrences += hits
            files.add(rel)
    paths = {rel for rel in rels if any(p.search(rel) for p in pats)}
    return occurrences, files, paths


# Stated in the source rather than only in a run's output, because a zero is a
# property of the needle until the list of what it cannot reach is written
# down. Each entry was probed separately rather than reasoned about.
UNREACHABLE_BY_THESE_NEEDLES = (
    "a slug split across a line, or one carried inside a longer token -- the "
    "organization-stem class exists for exactly that and was added after the "
    "whole-slug needle reported a smaller population than a fragment needle",
    "an employment word joined to other LETTERS with no separator between -- "
    "`<word>wise`, `non<word>` -- which a letter boundary cannot split from an "
    "ordinary word without also matching `internal` and `international`",
    "an identifier in a FILENAME rather than in contents -- counted separately "
    "as a path population, on the same needles",
    "a byte sequence in a file that does not decode as UTF-8 -- counted, "
    "asserted to be empty on this build rather than merely unreported",
    "anything on disk but NOT tracked, which a push would not carry anyway",
    "semantic disclosure with no literal: the structural fact that one example "
    "canon has six projects and twenty claims survives any renaming, and no "
    "string needle can see it",
)


def test_no_forbidden_identifier_or_employment_value_reaches_the_export(tmp_path):
    """The export carries no identifier a stranger cannot resolve, and says
    nothing about employment -- asserted as a BEFORE/AFTER over ONE population.

    A bare "zero hits" here would be worth very little. The same needles are
    therefore run over the SOURCE text of the very same files, before the
    manifest's rules touch them, and every class is required to have carriers
    there. That turns each row into a delta on one population rather than an
    absolute over an unknown one, and it is what makes the zero a property of
    the exported tree instead of a property of a dead needle.
    """
    manifest = json.loads(
        (REPO_ROOT / "scripts" / "publish" / "toolkit-publish.json")
        .read_text(encoding="utf-8"))
    manifest["export_root"] = str(tmp_path / "o")
    dest = os.path.join(manifest["export_root"], manifest["repo"])

    built = publish.build_export(manifest, dest)

    # ---- the AFTER population: the bytes that would actually ship ----------
    rels = []
    for root, _dirs, names in os.walk(dest):
        if ".git" in root.split(os.sep):
            continue
        for n in names:
            rels.append(os.path.relpath(os.path.join(root, n), dest)
                        .replace(os.sep, "/"))
    rels.sort()
    after = {}
    undecodable = []
    for rel in rels:
        try:
            after[rel] = io.open(os.path.join(dest, rel.replace("/", os.sep)),
                                 encoding="utf-8").read()
        except (UnicodeDecodeError, OSError) as exc:
            undecodable.append((rel, type(exc).__name__))

    assert len(rels) == built["total"], (
        "walked %d file(s) over an export the builder reports as %d"
        % (len(rels), built["total"]))
    assert not undecodable, (
        "%d exported file(s) could not be read as text, so this scan has not "
        "examined them: %r" % (len(undecodable), undecodable))
    assert len(after) > 100, (
        "read %d file(s); a clean verdict over a population this small would "
        "prove nothing" % len(after))

    # ---- the BEFORE population: the SAME files, unrewritten ---------------
    exclude = re.compile(manifest["exclude_pattern"])
    before = {}
    tracked = [n for n in _git(["ls-files"], REPO_ROOT).stdout.splitlines()
               if n.strip() and not exclude.match(n)]
    for name in tracked:
        path = REPO_ROOT / name.replace("/", os.sep)
        if not path.is_file():
            continue
        try:
            before[name] = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

    classes = _neutralisation_classes()
    print("neutralisation  before=%d file(s) after=%d file(s) undecodable=0  "
          "classes=%d" % (len(before), len(after), len(classes)))

    dead = []
    surviving = {}
    for label, pats in classes:
        was, was_files, was_paths = _count_over(before, sorted(before), pats)
        now, now_files, now_paths = _count_over(after, rels, pats)
        print("  %-20s occ %5d -> %-5d  files %3d -> %-3d  paths %2d -> %d"
              % (label, was, now, len(was_files), len(now_files),
                 len(was_paths), len(now_paths)))
        # The control. A class with nothing to find BEFORE proves nothing
        # AFTER -- that is a needle that stopped matching, wearing a pass.
        if not was and not was_paths:
            dead.append(label)
        if now or now_paths:
            surviving[label] = {
                "occurrences": now,
                "files": sorted(now_files)[:10],
                "paths": sorted(now_paths)[:10],
            }

    print("  what these needles could NOT have matched:")
    for line in UNREACHABLE_BY_THESE_NEEDLES:
        print("    - %s" % line)

    assert not dead, (
        "%d needle class(es) found NOTHING in the unrewritten source, so their "
        "zero in the export is a property of the needle rather than of the "
        "tree: %s" % (len(dead), dead))
    assert not surviving, (
        "%d class(es) still reach the export:\n%s"
        % (len(surviving), json.dumps(surviving, indent=2, sort_keys=True)))


_WHITESPACE = re.compile(r"\s+")


def test_no_exported_file_documents_this_repository_s_core_digest(tmp_path):
    """A published tree must not quote a hash that is not the hash beside it.

    THE EXPORTED FROZEN CORE IS REWORDED. It carries identifier citations and
    an upstream project's name in its own docstrings, so the rules neutralise
    it like any other file and the published `tools/canonkit.py` hashes
    differently from this repository's. That is deliberate. What is NOT
    acceptable is a shipped file that QUOTES this repository's digest beside
    it: nothing goes red, because it is prose in a docstring and a digest is
    not an identifier class, and the repository's whole pitch is that its
    numbers are checkable by the reader.

    THE NEEDLE MUST SURVIVE LINE WRAPPING, and that is the entire point of
    this test rather than a detail of it. The defect that produced it shipped
    past a probe which searched for the sixty-four characters IN ONE PIECE and
    reported zero carriers -- while a docstring carried the digest split
    across two lines. Measured at the time: whole-digest needle 0 carriers,
    whitespace-stripped needle 1. A guard that reproduces the blind spot which
    hid the defect is not a guard, so the wrap-tolerance is asserted below
    against a deliberately wrapped control before the tree is searched at all.

    The digest is DERIVED by hashing the core at run time and never written
    here, so this file is not a carrier for its own scan and the needle cannot
    go stale when the core legitimately changes.
    """
    core = REPO_ROOT / "tools" / "canonkit.py"
    assert core.is_file(), "the frozen core is not where this expects it: %s" % core
    source_digest = hashlib.sha256(core.read_bytes()).hexdigest()
    assert len(source_digest) == 64

    # CONTROL ONE: the blind spot, reproduced and then closed. A digest broken
    # over two lines the way a wrapped docstring breaks it is invisible to the
    # whole-value needle and visible to this one. If these two assertions ever
    # disagree, the needle has stopped being wrap-tolerant and every zero it
    # reports below is worthless.
    wrapped = source_digest[:43] + "\n    " + source_digest[43:]
    assert source_digest not in wrapped, (
        "the control is not actually wrapped, so it proves nothing about "
        "wrapping")
    assert source_digest in _WHITESPACE.sub("", wrapped), (
        "the whitespace-stripped needle cannot see a wrapped digest, which is "
        "the exact blind spot this test exists to close")

    manifest = json.loads(
        (REPO_ROOT / "scripts" / "publish" / "toolkit-publish.json")
        .read_text(encoding="utf-8"))
    manifest["export_root"] = str(tmp_path / "o")
    dest = os.path.join(manifest["export_root"], manifest["repo"])
    built = publish.build_export(manifest, dest)

    rels = []
    for root, _dirs, names in os.walk(dest):
        if ".git" in root.split(os.sep):
            continue
        for n in names:
            rels.append(os.path.relpath(os.path.join(root, n), dest)
                        .replace(os.sep, "/"))
    rels.sort()
    assert len(rels) == built["total"], (
        "walked %d file(s) over an export the builder reports as %d"
        % (len(rels), built["total"]))

    carriers = []
    read = 0
    unreadable = []
    for rel in rels:
        try:
            text = io.open(os.path.join(dest, rel.replace("/", os.sep)),
                           encoding="utf-8").read()
        except (UnicodeDecodeError, OSError) as exc:
            unreadable.append((rel, type(exc).__name__))
            continue
        read += 1
        if source_digest in _WHITESPACE.sub("", text):
            carriers.append(rel)

    exported_core = os.path.join(dest, "tools", "canonkit.py")
    exported_digest = hashlib.sha256(
        io.open(exported_core, "rb").read()).hexdigest()

    # CONTROL TWO: the same needle over the UNREWRITTEN source tree, which
    # documents this digest legitimately and must come back as a carrier.
    source_carriers = []
    for name in _git(["ls-files"], REPO_ROOT).stdout.splitlines():
        if not name.strip():
            continue
        path = REPO_ROOT / name.replace("/", os.sep)
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if source_digest in _WHITESPACE.sub("", text):
            source_carriers.append(name)

    print("core-digest  source=%s exported=%s differ=%s"
          % (source_digest[:16], exported_digest[:16],
             source_digest != exported_digest))
    print("core-digest  export read=%d of %d unreadable=%d  carriers=%d %s"
          % (read, len(rels), len(unreadable), len(carriers), carriers))
    print("core-digest  source carriers (the control)=%d"
          % len(source_carriers))

    assert not unreadable, (
        "%d exported file(s) could not be read, so this scan has not examined "
        "them: %r" % (len(unreadable), unreadable))
    assert source_carriers, (
        "the unrewritten source carries this digest NOWHERE, so the zero "
        "below is a property of the needle rather than of the export")
    assert not carriers, (
        "%d exported file(s) quote this repository's core digest while the "
        "exported core hashes %s: %s"
        % (len(carriers), exported_digest[:16], carriers))


# ---------------------------------------------------------------------------
# `dest_prefix` -- nesting a whole export under one destination directory
#
# THE MECHANISM EXISTS BECAUSE A PATH REWRITE CANNOT DO IT, and that is a
# property of `str.replace` rather than an omission. `apply_path_rewrites` is a
# SUBSTRING replace over (from, to) pairs, so there is no `from` value that
# means "the beginning of the path": the empty string inserts the replacement
# between every character, and any non-empty value matches wherever it occurs
# rather than only at position zero. Nesting one project under
# `<company>/<project>/` therefore needs an ANCHORED key of its own.
#
# THE AUTHORED MAP IS THE HALF THAT MATTERS, and it is the half a test written
# from the tracked-file side would miss. An authored file exists to REPLACE a
# tracked one -- that is how the owner's real claim corpus is swapped for a
# synthetic one. If the prefix reaches the tracked copy and not the authored
# replacement, the replacement lands at the export ROOT, the tracked original
# SURVIVES under the prefix, and the export ships the very file the authoring
# rule exists to keep out. Nothing goes red: both files are present, the counts
# still add up, and the export looks complete.
# ---------------------------------------------------------------------------

# A body that exists nowhere in this repository, for the authored half.
PREFIX_AUTHORED_MARK = "authored-body-that-must-win\n"


def _smoke_under(tmp_path):
    """The authored smoke test, declared at its PRE-prefix destination.

    An `authored` key names a path inside the exported PROJECT, so the manifest
    spells `tools/tests/test_smoke.py` and the prefix decides where it lands.
    """
    return {"tools/tests/test_smoke.py": _authored(tmp_path, "s.py", SMOKE_TEST)}


def _prefixed_tree(tmp_path, extra=None):
    """A work tree plus a scratch manifest that nests it under two directories.

    The prefix is spelled the way the shipped manifest spells it -- company
    directory, then project directory -- because a single-segment prefix would
    satisfy assertions that a two-segment one fails on a platform that joins
    with a backslash.
    """
    repo, names = _fixture_work_tree(tmp_path)
    kwargs = {"exclude_pattern": KEEP_EVERYTHING,
              "source_root": str(repo),
              "dest_prefix": "company-x/project-y/"}
    kwargs.update(extra or {})
    manifest, m, dest = _scratch(tmp_path, **kwargs)
    return repo, names, manifest, m, dest


def test_a_dest_prefix_nests_every_tracked_file_under_it(tmp_path):
    """The whole export moves down two directories, and nothing stays behind.

    Both halves are asserted. A prefix that COPIED rather than MOVED would
    satisfy the first assertion on its own, and an export carrying both copies
    is exactly the shape that ships a file the authoring rule meant to replace.
    """
    _repo, names, _manifest, m, dest = _prefixed_tree(
        tmp_path, {"authored": _smoke_under(tmp_path)})

    result = publish.build_export(m, dest)

    for name in names:
        moved = Path(dest) / "company-x" / "project-y" / name.replace("/", os.sep)
        assert moved.is_file(), (
            "%s did not land under the prefix; the export holds %s"
            % (name, sorted(str(p.relative_to(dest)).replace(os.sep, "/")
                            for p in Path(dest).rglob("*") if p.is_file())))
        assert not (Path(dest) / name.replace("/", os.sep)).exists(), (
            "%s is ALSO at the export root, so the prefix copied rather than "
            "moved and the export ships two of everything" % name)

    assert result["prefixed"] == len(names) + 1, (
        "the build reports %d prefixed path(s) over %d tracked file(s) plus "
        "one authored" % (result["prefixed"], len(names)))
    # The prefix is not a rename. Counting it as one would make `renamed`
    # unreadable -- every file moves under a prefix, so a path rule that fired
    # and one that did not would print the same number.
    assert result["renamed"] == 0, (
        "the prefix was counted as a path RENAME (%d); the two are different "
        "facts and one cannot stand in for the other" % result["renamed"])


def test_the_dest_prefix_reaches_the_AUTHORED_map_too(tmp_path):
    """THE DEFECT THIS KEY WAS ADDED FOR, run in the direction that fails.

    An authored file that replaces a tracked one must land ON the tracked copy
    after the prefix has moved it. Without the prefix on the authored side the
    replacement lands at the export root, the tracked original survives under
    the prefix, and the export ships BOTH -- with the original, which is the
    file the authoring rule exists to keep out, in the place a reader looks.

    The COUNT is asserted as well as the bytes, because `authored_replacements`
    is what a later reader will trust: a replacement that missed its target is
    counted as a NEW file, and zero replacements over one authored file is the
    number that says so.
    """
    repo, names = _fixture_work_tree(tmp_path)
    target = names[0]
    (repo / target).write_text("the ORIGINAL body, which must not ship\n",
                               encoding="utf-8")
    assert _git(["add", target], repo).returncode == 0
    assert _git(["-c", "user.name=t", "-c", "user.email=t@example.invalid",
                 "commit", "-q", "-m", "original"], repo).returncode == 0

    authored = {target: _authored(tmp_path, "replacement.txt",
                                  PREFIX_AUTHORED_MARK)}
    authored.update(_smoke_under(tmp_path))
    _manifest, m, dest = _scratch(
        tmp_path, exclude_pattern=KEEP_EVERYTHING, source_root=str(repo),
        dest_prefix="company-x/project-y/", authored=authored)

    result = publish.build_export(m, dest)

    landed = Path(dest) / "company-x" / "project-y" / target.replace("/", os.sep)
    assert landed.is_file(), (
        "the authored file is not under the prefix at all; the export holds %s"
        % sorted(str(p.relative_to(dest)).replace(os.sep, "/")
                 for p in Path(dest).rglob("*") if p.is_file()))
    assert landed.read_text(encoding="utf-8") == PREFIX_AUTHORED_MARK, (
        "the file under the prefix is the TRACKED original, so the authored "
        "replacement landed somewhere else: %r"
        % landed.read_text(encoding="utf-8"))
    assert not (Path(dest) / target.replace("/", os.sep)).exists(), (
        "the authored file ALSO sits at the export root, unprefixed")
    assert result["authored_replacements"] == 1, (
        "the build reports %d replacement(s); an authored file that misses the "
        "tracked copy it was written to replace is counted as a NEW file, and "
        "that is exactly what this number is for"
        % result["authored_replacements"])


def test_authored_root_files_land_at_the_export_ROOT_beside_the_prefix(tmp_path):
    """The repository's own pages, which belong ABOVE every project.

    Two authored maps rather than one, because they answer different
    questions. `authored` names a file inside the exported PROJECT and follows
    the project wherever the prefix puts it -- that is what makes a replacement
    land on its target. `authored_root` names a file belonging to the
    REPOSITORY -- its front page, a directory page for one company -- and is
    written at the export root whatever the prefix is. One map cannot express
    both, and an escape character inside a key would make the destination of
    every entry something a reader has to decode.
    """
    root_files = {
        "README.md": _authored(tmp_path, "root.md", "# the repository\n"),
        "company-x/README.md": _authored(tmp_path, "co.md", "# one company\n"),
    }
    _repo, _names, _manifest, m, dest = _prefixed_tree(
        tmp_path, {"authored": _smoke_under(tmp_path),
                   "authored_root": root_files})

    result = publish.build_export(m, dest)

    assert (Path(dest) / "README.md").read_text(encoding="utf-8") == \
        "# the repository\n"
    assert (Path(dest) / "company-x" / "README.md").read_text(
        encoding="utf-8") == "# one company\n"
    assert not (Path(dest) / "company-x" / "project-y" / "README.md").exists(), (
        "a root-authored file was pushed down under the prefix, which is the "
        "one thing this second map exists to prevent")
    assert result["authored_root"] == 2, (
        "the build reports %d root-authored file(s) over 2 declared"
        % result["authored_root"])
    # The two maps are counted separately, and the total counts both.
    assert result["authored"] == 1, result["authored"]
    assert result["total"] == (result["tracked"] + result["authored"]
                               + result["authored_root"]
                               - result["authored_replacements"]), result


def test_a_dest_prefix_is_applied_AFTER_the_path_rewrites(tmp_path):
    """Order is load-bearing in BOTH directions, and each is a separate failure.

    A path rewrite still has to fire on the source path, so the rewritten name
    is what sits under the prefix. And the PREFIX must not be rewritten -- the
    directory names in it are the organization and the project a reader is meant to
    see, and the shared rule set neutralises exactly those strings in a path.
    Applying the prefix last is what makes both true at once; applying it first
    would hand the neutralising rules their own destination directory.
    """
    repo, _names = _fixture_work_tree(tmp_path)
    secret = repo / "a-private-name" / "note.md"
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text("body\n", encoding="utf-8")
    assert _git(["add", "a-private-name/note.md"], repo).returncode == 0
    assert _git(["-c", "user.name=t", "-c", "user.email=t@example.invalid",
                 "commit", "-q", "-m", "p"], repo).returncode == 0

    _manifest, m, dest = _scratch(
        tmp_path, exclude_pattern=KEEP_EVERYTHING, source_root=str(repo),
        authored=_smoke_under(tmp_path),
        # The prefix deliberately CONTAINS the string the rule neutralises.
        dest_prefix="a-private-name/project-y/",
        path_rewrites=[{"from": "a-private-name", "to": "a-neutral-name"}])

    result = publish.build_export(m, dest)

    landed = (Path(dest) / "a-private-name" / "project-y"
              / "a-neutral-name" / "note.md")
    assert landed.is_file(), (
        "expected the REWRITTEN path under the UNREWRITTEN prefix; the export "
        "holds %s" % sorted(str(p.relative_to(dest)).replace(os.sep, "/")
                            for p in Path(dest).rglob("*") if p.is_file()))
    assert result["renamed"] == 1, (
        "the path rule reports %d rename(s), so it stopped firing once a "
        "prefix was in front of it" % result["renamed"])


def test_the_exec_bit_restore_follows_the_dest_prefix(tmp_path):
    """The third site, and the one that fails SILENTLY.

    The restore loop looks a tracked file up in the export by its transformed
    name. Miss the lookup and the branch falls through, the bit is not
    restored, and the run prints exactly what a clean run prints -- the loop
    only ever reports what it FOUND. The same reasoning as the path-rewrite
    case beside it; a second transform is a second way to miss.
    """
    repo, _names = _fixture_work_tree(tmp_path)
    hook = repo / "hooks" / "gate.sh"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    assert _git(["add", "hooks/gate.sh"], repo).returncode == 0
    assert _git(["update-index", "--chmod=+x", "--", "hooks/gate.sh"],
                repo).returncode == 0
    assert _git(["-c", "user.name=t", "-c", "user.email=t@example.invalid",
                 "commit", "-q", "-m", "hook"], repo).returncode == 0
    modes = _git(["ls-files", "-s"], repo).stdout
    assert "100755" in modes, (
        "the fixture's hook is not recorded executable, so there is nothing "
        "to restore and this test would pass over a broken restore:\n%s" % modes)

    manifest, _m, dest = _scratch(
        tmp_path, exclude_pattern=KEEP_EVERYTHING, source_root=str(repo),
        dest_prefix="company-x/project-y/",
        authored=_smoke_under(tmp_path),
        suite_path="company-x/project-y/tools/tests")

    code = publish.main(["--manifest", str(manifest), "--dry-run",
                         "--python", sys.executable])
    assert code == 0, "the scratch publish returned %d" % code

    exported = _git(["ls-files", "-s"], Path(dest)).stdout
    rows = [line for line in exported.splitlines()
            if line.endswith("company-x/project-y/hooks/gate.sh")]
    assert rows, (
        "the prefixed hook is not in the export's index at all:\n%s" % exported)
    assert rows[0].startswith("100755"), (
        "the exec bit was not restored on the PREFIXED path, so the restore "
        "silently stopped finding its subject: %r" % rows[0])


def test_no_dest_prefix_leaves_every_path_exactly_where_it_was(tmp_path):
    """The control. Three manifests in this repository declare no prefix, and a
    default that quietly moved their files would be the loudest possible
    regression -- so the absent case is pinned rather than assumed."""
    repo, names = _fixture_work_tree(tmp_path)
    _manifest, m, dest = _scratch(
        tmp_path, exclude_pattern=KEEP_EVERYTHING, source_root=str(repo),
        authored=_smoke(tmp_path))

    result = publish.build_export(m, dest)

    for name in names:
        assert (Path(dest) / name.replace("/", os.sep)).is_file(), name
    assert result["prefixed"] == 0, result["prefixed"]
    assert result["authored_root"] == 0, result["authored_root"]


@pytest.mark.parametrize("value,why", [
    ("../escape/", "climbs out of the export directory"),
    ("company/../../escape/", "climbs out after descending"),
    ("/absolute/", "is absolute, and os.path.join would discard the export"),
    ("C:/absolute/", "is a drive-absolute path"),
])
def test_a_dest_prefix_that_escapes_the_export_is_refused(tmp_path, value, why):
    """A prefix is joined onto the export root, so a value that climbs out of
    it writes the export somewhere nobody is looking -- and on this platform an
    absolute second argument to os.path.join DISCARDS the first, which turns a
    typo into a write at the filesystem root. Refused before anything is
    copied, because the failure it prevents is a WRITE.

    The drive-letter case is checked with an explicit pattern rather than with
    os.path.isabs, so the refusal does not depend on which platform the test
    happens to run on."""
    repo, _names = _fixture_work_tree(tmp_path)
    _manifest, m, dest = _scratch(
        tmp_path, exclude_pattern=KEEP_EVERYTHING, source_root=str(repo),
        dest_prefix=value, authored=_smoke(tmp_path))

    with pytest.raises(SystemExit) as caught:
        publish.build_export(m, dest)
    assert caught.value.code == publish.EXIT_DID_NOT_RUN, (
        "a prefix that %s was refused with code %r rather than a did-not-run"
        % (why, caught.value.code))


def test_a_dest_prefix_is_normalised_so_a_missing_slash_is_not_a_new_name(
        tmp_path):
    """`a/b` and `a/b/` are the same destination, and a manifest that omits the
    trailing slash must not produce `a/bREADME.md`. Spelled as a test because
    the concatenation IS the implementation and a missing separator is silent:
    the file is written, just under a name nobody will look for."""
    repo, names = _fixture_work_tree(tmp_path)
    _manifest, m, dest = _scratch(
        tmp_path, exclude_pattern=KEEP_EVERYTHING, source_root=str(repo),
        dest_prefix="company-x/project-y",
        authored=_smoke_under(tmp_path))

    publish.build_export(m, dest)

    for name in names:
        assert (Path(dest) / "company-x" / "project-y"
                / name.replace("/", os.sep)).is_file(), (
            "%s is not under the normalised prefix; the export holds %s"
            % (name, sorted(str(p.relative_to(dest)).replace(os.sep, "/")
                            for p in Path(dest).rglob("*") if p.is_file())))


# ---------------------------------------------------------------------------
# The shipped `engagement` manifest -- one repository, company then project
# ---------------------------------------------------------------------------

ENGAGEMENT_PREFIX = "example-beta/example-cache-benchmark/"

ENGAGEMENT_ROOT_PAGES = ("README.md", "example-alpha/README.md",
                          "example-beta/README.md")


def _manifest_named(name):
    return json.loads(
        (REPO_ROOT / "scripts" / "publish" / ("%s.json" % name))
        .read_text(encoding="utf-8"))


def test_the_engagement_project_folder_carries_the_identity_its_records_were_derived_under():
    """The project FOLDER'S NAME is data, not decoration, and this pins it.

    The artifact's derive step takes its identity from the directory it runs
    in -- `slug = slug or os.path.basename(os.path.abspath(str(root)))` -- and
    its suite re-derives over the REAL tree on purpose, trusting the committed
    record to come back byte-identical "by construction". That construction
    holds only while the folder is named what the record says. Nested under
    any other name, the shipped suite rewrites the committed record with the
    new name and then fails its own byte-identity check: measured 2026-09-23 on
    the first dry run of this manifest, 1 failed and 49 passed, with the
    export's results/figures.json left modified. Docker Compose names its
    containers after the same folder, so the captured run evidence would also
    stop matching a reader's own reproduction.

    Read from the source's committed record rather than typed here, so a
    renamed artifact moves this pin with it.
    """
    m = _manifest_named("engagement")
    source = Path(m["source_root"])
    record = source / "results" / "figures.json"
    if not record.is_file():
        pytest.skip("the source artifact is not checked out at %s" % source)
    identity = json.loads(record.read_text(encoding="utf-8"))["artifact"]
    leaf = m["dest_prefix"].rstrip("/").split("/")[-1]
    assert leaf == identity, (
        "the project folder is %r but the committed record was derived as %r, "
        "so the shipped suite would rewrite that record and fail its own "
        "re-derivation check" % (leaf, identity))


def test_the_engagement_manifest_nests_its_project_under_its_company():
    """The shape, read from the manifest rather than from a plan.

    Asserted structurally as well as by building, because a build failure would
    report the same defect five minutes later and less clearly.
    """
    m = _manifest_named("engagement")
    assert m["repo"] == "engagement", m["repo"]
    assert m["dest_prefix"] == ENGAGEMENT_PREFIX, m.get("dest_prefix")
    # The suite lives inside the project, so its declared path carries the
    # prefix. `dest_prefix` deliberately does NOT reach `suite_path`: that key
    # is already written in EXPORT terms, and auto-prefixing it would stop a
    # manifest ever naming a suite outside the project. A manifest that forgets
    # the prefix here gets the gate's own DID-NOT-RUN with the path in it.
    assert m["suite_path"] == ENGAGEMENT_PREFIX + "tests", m.get("suite_path")
    assert m["suite_floor"] == 50, m.get("suite_floor")
    assert m["inherit_rewrites_from"] == "scripts/publish/toolkit-publish.json"
    assert sorted(m["authored_root"]) == sorted(ENGAGEMENT_ROOT_PAGES), \
        sorted(m["authored_root"])
    named = sorted(m["authored_root"].items()) + sorted(m["authored"].items())
    for rel, src in named:
        assert (REPO_ROOT / src.replace("/", os.sep)).is_file(), (
            "%s names an authored source that does not exist: %s" % (rel, src))
    print("engagement authored: %d root page(s), %d project file(s)"
          % (len(m["authored_root"]), len(m["authored"])))


def test_the_two_manifests_over_ONE_source_tree_apply_the_SAME_own_rules():
    """Two manifests export the same work tree, so their tree-specific rules
    must not drift -- and inheritance cannot express that, because it is one
    level deep on purpose and both already inherit the shared set.

    So the duplication is real and this is what makes it safe. A rule added to
    one side and not the other changes what one export says about the same
    bytes, and nothing else here would notice: both exports would still build,
    both would still scan clean, and only the wording would differ.
    """
    redis = _manifest_named("artifact-publish")
    joint = _manifest_named("engagement")
    assert redis["source_root"] == joint["source_root"], (
        "the two manifests no longer read the same tree, so this pin is "
        "comparing rules over different sources: %s vs %s"
        % (redis["source_root"], joint["source_root"]))
    for key in ("rewrites", "rewrite_exempt_paths", "exclude_pattern",
                "suite_floor"):
        assert redis.get(key) == joint.get(key), (
            "`%s` differs between the two manifests over the same tree. One "
            "was edited and the other was not:\nredis=%s\njoint=%s"
            % (key, json.dumps(redis.get(key), indent=2, sort_keys=True),
               json.dumps(joint.get(key), indent=2, sort_keys=True)))
    # The one key that is REQUIRED to differ, asserted so the pin above cannot
    # be satisfied by the two files simply being the same file.
    assert redis.get("dest_prefix") in (None, ""), redis.get("dest_prefix")
    assert joint["dest_prefix"] == ENGAGEMENT_PREFIX
    assert redis["suite_path"] == "tests"
    assert joint["suite_path"] == ENGAGEMENT_PREFIX + "tests"


def test_the_engagement_export_puts_the_company_pages_above_the_project(
        tmp_path):
    """The tree a reader actually gets, WALKED rather than described.

    THE POPULATION IS PRINTED AND RECONCILED. A structural assertion over an
    export nobody counted cannot tell a correct tree from an empty one.
    """
    m = _manifest_named("engagement")
    dest = str(tmp_path / "engagement")
    result = publish.build_export(m, dest)

    rels = sorted(str(p.relative_to(dest)).replace(os.sep, "/")
                  for p in Path(dest).rglob("*") if p.is_file())
    under = [r for r in rels if r.startswith(ENGAGEMENT_PREFIX)]
    print("engagement export: %d file(s), %d under the project, %d at the root"
          % (len(rels), len(under), len(rels) - len(under)))
    assert len(rels) == result["total"], (
        "walked %d file(s) over an export the builder reports as %d"
        % (len(rels), result["total"]))
    assert len(rels) > 150, (
        "the export holds %d file(s); a structural check over a population "
        "that small is a property of the walk, not of the tree" % len(rels))

    for page in ENGAGEMENT_ROOT_PAGES:
        assert page in rels, "%s is not at the export root: %s" % (page, rels[:20])

    stranded = [r for r in rels
                if r not in ENGAGEMENT_ROOT_PAGES
                and not r.startswith(ENGAGEMENT_PREFIX)]
    assert not stranded, (
        "%d file(s) sit outside both the project and the three company pages: "
        "%s" % (len(stranded), stranded[:20]))

    # The project's README is the artifact's own, carrying the opening the
    # owner ratified. Named by a fragment so this file is not a hit for the
    # organization needles it asserts on.
    project_readme = (Path(dest) / ENGAGEMENT_PREFIX.replace("/", os.sep)
                      / "README.md")
    assert project_readme.is_file(), "the project ships no README"
    assert _frag("SAUD", "CONSULT") in project_readme.read_text(
        encoding="utf-8"), "the project README lost its organization sentence"


def test_the_engagement_export_replaces_the_claim_corpus_UNDER_the_prefix(
        tmp_path):
    """The authored-map half, asserted on the SHIPPED manifest and not only on
    a fixture.

    The artifact's root carries a byte copy of the owner's real approved-claim
    list, because its vendored checker resolves against it; the manifest swaps
    in a synthetic corpus. If the prefix did not reach the authored map, the
    synthetic copy would land at the export root and the REAL one would ship
    under the project -- which is the file a reader opens.
    """
    m = _manifest_named("engagement")
    dest = str(tmp_path / "engagement")
    publish.build_export(m, dest)

    shipped = (Path(dest) / ENGAGEMENT_PREFIX.replace("/", os.sep)
               / "canon-bullets.json")
    assert shipped.is_file(), "the project ships no claim corpus"
    authored_src = REPO_ROOT / m["authored"]["canon-bullets.json"].replace(
        "/", os.sep)
    assert shipped.read_bytes() == authored_src.read_bytes(), (
        "the corpus under the project is not the authored synthetic one")
    assert not (Path(dest) / "canon-bullets.json").exists(), (
        "a copy of the claim corpus is stranded at the export root")
