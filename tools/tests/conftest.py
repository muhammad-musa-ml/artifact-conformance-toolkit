"""Shared fixtures and repo-level constants consumed by every later an earlier round plan.

Declared because later waves build on this contract rather than
re-deriving it. Four helpers and one constant:

    tmp_artifact(tmp_path, **overrides) -> Path
    committed_tree(tmp_path, src) -> Path
    broken_fixture(name) -> Path
    run_cli(argv, cwd) -> CliResult
    SCAN_ROOT: Path

They are plain module-level functions rather than pytest fixture factories so a
caller can invoke them with the exact signatures above, from a test module or
from a helper, with no indirection. Import them as:

    from tools.tests import conftest
    art = conftest.tmp_artifact(tmp_path)
"""

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from tools import census_live_store

__all__ = [
    "SCAN_ROOT",
    "SCAN_ROOT_RELATIVE",
    "SCAN_DEPTH",
    "REPO_ROOT",
    "MAIN_REPO_ROOT",
    "BROKEN_FIXTURES_DIR",
    "CliResult",
    "tmp_artifact",
    "committed_tree",
    "broken_fixture",
    "run_cli",
]

# tools/tests/conftest.py -> tools/tests -> tools -> <repo root>
REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# SCAN_ROOT -- the directory conformance.py enumerates artifacts in.
#
# Declared HERE,, rather than in tools/manifest.json, because the design rule
# assertion that fixtures/broken-artifacts/ is never scanned is load-bearing from
# the moment the fixture tree is committed, and the manifest does not exist until
# an earlier round. an earlier plan writes the same value into the manifest's declared scan root
# and asserts the two RESOLVE EQUAL. This constant is therefore the earlier round half of
# ONE assertion, not a second source of truth. If the two ever disagree, THAT is
# the finding -- never a value to pick between.
#
# Expressed RELATIVE to the repository root and resolved, so no absolute home path
# is baked into a tracked file. It resolves to <home>/Research/, the directory that
# holds every artifact slug, the read-only live data dir, and ~22 unrelated trees
# (which is the measured reason a design rule reports extras with a count and exits 0
# instead of failing).
#
# a recorded defect's DURABLE FIX: the relative rule is applied to the MAIN repository root,
# never to `REPO_ROOT`.
#
# WHAT WAS MEASURED. `REPO_ROOT / ".."` is correct in the main checkout, where it
# resolves to <home>/Research/ and the design rule guard runs over 25 directories.
# Inside an agent worktree REPO_ROOT is <repo>/agent-worktrees/worktrees/agent-<id>, so
# the same expression resolves to <repo>/agent-worktrees/worktrees and the guard runs
# over 2 to 4 directories -- the sibling worktrees of that wave. Every agent in
# every parallel wave (4, 5 and 8) therefore measured the wrong population, and
# an earlier plan's guard reported it GREEN because its vacuity check only fires at 0
# and 2 is not 0. A count that is PRESENT but WRONG reads as detail, where a
# missing one would have read as a question.
#
# (an earlier plan partly hardened this: test_conformance.py's
# test_the_fixture_tree_is_never_enumerated_by_the_runner carries an explicit
# `>= 10` floor and FAILS LOUDLY at 4. The deferred-items record written at wave
# 4 still described the old silent-pass behaviour and was propagated into four
# an earlier round briefs, predicting one pre-existing failure where there were two. Read
# the code, not the record.)
#
# THE FIX ALREADY EXISTED IN THE TREE. an earlier plan hit the same anchor problem
# while writing the census -- it first recorded `../../../../information`, a
# worktree-relative path resolving to nothing once merged -- and split the notion
# in two: working_repo_root() (where I am) versus main_repo_root() (the real
# repository root, whether or not I am in a worktree). tools/conformance.py
# already derives its scan root that way, and an earlier plan deliberately did not patch
# this file because conftest.py was outside its declared files_modified.
#
# The property that matters is that the SAME population is enumerated from inside
# an agent as from the main checkout. Anchoring on main_repo_root() is what makes
# that true; anchoring on REPO_ROOT is what made it false.
SCAN_ROOT_RELATIVE = ".."
MAIN_REPO_ROOT = Path(census_live_store.main_repo_root()).resolve()
SCAN_ROOT = (MAIN_REPO_ROOT / SCAN_ROOT_RELATIVE).resolve()

# conformance.py enumerates the IMMEDIATE children of SCAN_ROOT and classifies each
# one. It does not walk. This depth is the whole mechanism by which a design rule holds, and
# it is stated as a number so a test can assert against it rather than restate it.
#
# READ THIS BEFORE CHANGING EITHER CONSTANT. This repository lives INSIDE SCAN_ROOT
# (at <home>/Research/artifact-conformance-toolkit), so fixtures/broken-artifacts/ IS a
# descendant of SCAN_ROOT by naive path containment. A test written as
# "assert not fixture_tree.is_relative_to(SCAN_ROOT)" can therefore never pass, and
# making it pass by shrinking SCAN_ROOT would break the reconciliation an earlier plan
# performs against the manifest, which must declare the real scan root. The
# property a design rule actually requires is that the fixture tree is never ENUMERATED as
# an artifact -- which holds because enumeration stops at depth 1 and the fixture
# tree sits at depth 3. test_broken_fixture_tree_is_outside_the_scan_root asserts
# that, not the containment.
SCAN_DEPTH = 1

# a design rule's committed tree of deliberately broken mini-artifacts.
BROKEN_FIXTURES_DIR = REPO_ROOT / "fixtures" / "broken-artifacts"

# Git identity and configuration forced on every temp repository, so a test never
# depends on (or is broken by) the developer's global git config.
_GIT_ENV_FLAGS = [
    "-c", "user.name=artifact-conformance-toolkit tests",
    "-c", "user.email=tests@example.invalid",
    "-c", "commit.gpgsign=false",
    "-c", "core.hooksPath=",
]

# The one normative line a design rule requires. Mirrored into every temp repository.
GITATTRIBUTES_LINE = "* text=auto eol=lf"


# ---------------------------------------------------------------------------
# run_cli
# ---------------------------------------------------------------------------

@dataclass
class CliResult:
    """The outcome of running a tool as a subprocess.

    `exit_code` is the CHILD process's own return code.
    """

    exit_code: int
    stdout: str
    stderr: str
    report: Optional[dict] = None
    argv: list = field(default_factory=list)
    cwd: Optional[Path] = None
    log_path: Optional[Path] = None

    def __str__(self):
        return "CliResult(exit_code=%d, argv=%r, log=%s)" % (
            self.exit_code, self.argv, self.log_path)


def run_cli(argv, cwd, log_dir=None, timeout=300, env=None):
    """Run a tool as a subprocess and return its REAL exit code.

    This exists so the piped-exit-code trap is structurally impossible in this
    suite. A shell pipeline reports the LAST stage's status, so
    `conformance.py | tail` prints EXIT=0 with failures present. Two properties
    prevent that here, and they are stated precisely rather than as "no pipes":

      * `shell=False` always (argv is a list, never a string), so no shell
        pipeline is ever constructed and no stage can mask the child's status.
      * the returned `exit_code` is `CompletedProcess.returncode`, the child's
        own status. `capture_output=True` does attach an OS pipe to the child's
        stdout, but that is a capture channel, not a pipeline stage, and it does
        not participate in the exit status at all.

    Both streams are also written to files under `log_dir`, so the evidence
    outlives the test process and can be pasted into a summary.

    Args:
        argv: list of command tokens. Never a shell string.
        cwd: working directory for the child.
        log_dir: where stdout.txt / stderr.txt are written. A fresh temp dir by
            default.
        timeout: seconds before the child is killed.
        env: full environment mapping for the child, or None to inherit.

    Returns:
        CliResult. `report` is the parsed JSON of the file named after a
        `--report` flag in argv, or None when the flag is absent or the file
        was not written.
    """
    argv = [str(token) for token in argv]
    cwd = Path(cwd)
    if log_dir is None:
        log_dir = Path(tempfile.mkdtemp(prefix="cbb-cli-"))
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    completed = subprocess.run(
        argv,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
        shell=False,
    )

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    (log_dir / "stdout.txt").write_text(stdout, encoding="utf-8")
    (log_dir / "stderr.txt").write_text(stderr, encoding="utf-8")

    report = None
    if "--report" in argv:
        index = argv.index("--report")
        if index + 1 < len(argv):
            candidate = Path(argv[index + 1])
            if not candidate.is_absolute():
                candidate = cwd / candidate
            if candidate.is_file():
                report = json.loads(candidate.read_text(encoding="utf-8"))

    return CliResult(
        exit_code=completed.returncode,
        stdout=stdout,
        stderr=stderr,
        report=report,
        argv=argv,
        cwd=cwd,
        log_path=log_dir,
    )


# ---------------------------------------------------------------------------
# tmp_artifact
# ---------------------------------------------------------------------------

_DEFAULT_README = """# demo-artifact

artifact:limits:begin
Measured on one laptop with one RTX 4050. Nothing here was run on managed cloud.
artifact:limits:end

artifact:figures:begin
Median latency 12.5 ms over 500 replayed requests, measured 2026-09-15.
artifact:figures:end

## What this does not show

This is a hermetic test fixture. It measures nothing and no number in it was
produced by running anything.

Dated: 2026-09-15
"""

_DEFAULT_FIGURES = {
    "schema_version": 1,
    "slug": "demo-artifact",
    "dated_at": "2026-09-15",
    "figures": [
        {
            "id": "median_latency_ms",
            "value": 12.5,
            "population": 500,
            "population_label": "replayed requests",
        }
    ],
}

_DEFAULT_GATE = {
    "schema_version": 1,
    "slug": "demo-artifact",
    "ok": True,
    "passed": True,
    "dated_at": "2026-09-15T00:00:00Z",
    "started_at": "2026-09-15T00:00:00Z",
    "failed_ids": [],
    "fallback_wording": "",
    "run_token": "0" * 64,
}

# The retraction declaration CHECK-16 reads. An artifact that withdrew nothing
# still declares that it withdrew nothing, and the declaration's ABSENCE is a
# did-not-run rather than a pass -- so the minimal artifact carries a dated,
# empty one, and a caller wanting the absent case passes `retractions=None`
# exactly as it does for any other file here.
_DEFAULT_RETRACTIONS = {
    "schema": "canonkit/retractions/1",
    "schema_version": "canonkit/1",
    "reviewed_on": "2026-09-15",
    "retracted": [],
}

# Override keyword -> path inside the artifact. Keywords must be Python
# identifiers, so the mapping is explicit rather than derived from the paths.
_ARTIFACT_FILES = {
    "readme": "README.md",
    "figures": "results/figures.json",
    "gate": "results/gate.json",
    "retractions": "results/retractions.json",
}


def tmp_artifact(tmp_path, **overrides):
    """Build a minimal, hermetic artifact directory under `tmp_path`.

    Deliberately minimal: three files, enough for a checker to have something
    to read and something to refuse. an earlier plan, an earlier plan, an earlier plan and an earlier plan own the
    real schemas and extend this shape; nothing here should be read as the
    contract.

    Keyword overrides, one per file:

        readme=...       README.md
        figures=...      results/figures.json
        gate=...         results/gate.json
        retractions=...  results/retractions.json

    A str value replaces the file's text. A dict value is written as JSON. A
    value of None DELETES the file, which is how a caller constructs the
    zero-input and one-known-bad fixtures a design rule requires without touching the
    committed tree.

    `slug=` renames the directory (default "demo-artifact").

    Raises:
        TypeError: on an unknown keyword, naming the ones that are accepted --
            a typo must be a findable error, never a silently ignored override.
    """
    slug = overrides.pop("slug", "demo-artifact")
    unknown = sorted(set(overrides) - set(_ARTIFACT_FILES))
    if unknown:
        raise TypeError(
            "tmp_artifact() got unknown override(s) %s; accepted overrides are %s"
            % (unknown, sorted(_ARTIFACT_FILES) + ["slug"])
        )

    root = Path(tmp_path) / slug
    (root / "results").mkdir(parents=True, exist_ok=True)

    defaults = {
        "readme": _DEFAULT_README,
        "figures": _DEFAULT_FIGURES,
        "gate": _DEFAULT_GATE,
        "retractions": _DEFAULT_RETRACTIONS,
    }

    for key, relative in _ARTIFACT_FILES.items():
        target = root / relative
        value = overrides[key] if key in overrides else defaults[key]
        if value is None:
            if target.exists():
                target.unlink()
            continue
        if isinstance(value, (dict, list)):
            text = json.dumps(value, indent=2, sort_keys=True) + "\n"
        else:
            text = str(value)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")

    return root


# ---------------------------------------------------------------------------
# committed_tree
# ---------------------------------------------------------------------------

def committed_tree(tmp_path, src):
    """Copy `src` into `tmp_path`, git-init it, and commit `.gitattributes` FIRST.

    The commit ORDER mirrors a design rule: a sha256 computed over a file in the returned
    work tree matches one computed after a clone, because LF normalization was in
    force before any other blob entered the index. Committing everything in one
    go would reproduce the exact defect a design rule exists to prevent, inside the very
    fixture used to test for it.

    Required by a design rule's dirty-tree refusal and by a success criterion's "run on a committed tree,
    never on a dirty one".

    Returns:
        Path to the work-tree root.
    """
    src = Path(src)
    if not src.is_dir():
        raise FileNotFoundError("committed_tree(): src is not a directory: %s" % src)

    work = Path(tmp_path) / (src.name + "-committed")
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(src, work)

    def git(*args):
        return subprocess.run(
            ["git"] + _GIT_ENV_FLAGS + list(args),
            cwd=str(work),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            shell=False,
        )

    git("init", "-q", "-b", "main")

    attributes = work / ".gitattributes"
    if not attributes.exists():
        attributes.write_text(GITATTRIBUTES_LINE + "\n", encoding="ascii", newline="\n")
    git("add", "--", ".gitattributes")
    git("commit", "-q", "-m", "chore: .gitattributes before anything is hashed")

    git("add", "-A", "--", ".")
    status = git("status", "--porcelain")
    if status.stdout.strip():
        git("commit", "-q", "-m", "chore: the rest of the tree")

    return work


# ---------------------------------------------------------------------------
# broken_fixture
# ---------------------------------------------------------------------------

def broken_fixture(name):
    """Return the path to a subdirectory of fixtures/broken-artifacts/.

    Raises with the list of available names on a miss, so a typo in a test is a
    findable error rather than a silent skip. A skipped test that reads as a pass
    is the failure mode this guard exists to prevent.
    """
    if not BROKEN_FIXTURES_DIR.is_dir():
        raise FileNotFoundError(
            "broken_fixture(%r): the design rule fixture tree does not exist at %s"
            % (name, BROKEN_FIXTURES_DIR)
        )
    candidate = BROKEN_FIXTURES_DIR / name
    if not candidate.is_dir():
        available = sorted(
            entry.name for entry in BROKEN_FIXTURES_DIR.iterdir() if entry.is_dir()
        )
        raise FileNotFoundError(
            "broken_fixture(%r): no such fixture. Available (%d): %s"
            % (name, len(available), available or "<none>")
        )
    return candidate


# ---------------------------------------------------------------------------
# Thin pytest-fixture wrappers, so a test may also request these by name.
# The plain functions above remain the documented interface.
# ---------------------------------------------------------------------------

try:
    import pytest
except ImportError:  # pragma: no cover - pytest is always present when collecting
    pytest = None

if pytest is not None:

    @pytest.fixture
    def make_tmp_artifact():
        return tmp_artifact

    @pytest.fixture
    def make_committed_tree():
        return committed_tree

    @pytest.fixture
    def get_broken_fixture():
        return broken_fixture

    @pytest.fixture
    def cli_runner():
        return run_cli
