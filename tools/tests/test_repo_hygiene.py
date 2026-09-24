"""Repository hygiene: the floor every later an earlier round plan stands on.

Each test here asserts a property that, if it silently stopped holding, would
make a LATER result wrong rather than make this suite red. They are therefore
written to discriminate: every one of them states its population and refuses to
pass over an empty one.
"""

import ast
import subprocess
import sys
from pathlib import Path

from tools import census_live_store, vendor
from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT


# ---------------------------------------------------------------------------
# The vendored set -- DECLARED IN tools/vendor.py SINCE AN EARLIER PLAN.
#
# These files are run BY PATH and copied BY BYTES. They are never importable
# modules of the `tools` package. The list is the DECLARATION; the counts beside
# it are committed literals acting as tripwires on the derivation's own input
# (the design rule pattern: derive by filtering, never type the answer -- and assert the
# derivation against a literal, because a purely derived count silently stops
# checking when its input shrinks).
#
# an earlier round held its own copy of the tuple because tools/vendor.py did not exist.
# It does now, and it is the module that COPIES these files, so it is where the
# list belongs: two copies of one declaration is two things to drop a name from.
# ---------------------------------------------------------------------------

VENDORED_SET = vendor.VENDORED_SET

# How many paths the declaration names. A tripwire on the DECLARATION quietly
# shrinking -- without it, an emptied list would make every derived count
# trivially agree with zero. vendor.py asserts this at IMPORT time; asserting it
# again here is not redundant, because this test is what a reader runs.
VENDORED_SET_DECLARED = vendor.VENDORED_SET_COUNT

# How many of those paths exist on disk right now. an earlier round created none of them;
# an earlier plan raises this ONE PER COMMIT as it creates each file, and later plans
# raise it again. A file appearing without this literal moving is the finding.
#
# An earlier summary says "an earlier plan must raise VENDORED_SET_PRESENT from 0 to 2 in the
# same commit that creates tools/canonkit.py and tools/checks/__init__.py". Those
# two files are created by two DIFFERENT tasks of an earlier plan and therefore two
# different commits, so the literal moves 0 -> 1 -> 2, one step in each commit
# that creates one file. The property the tripwire protects -- that no vendored
# file ever appears without this number moving in the same commit -- is stronger
# this way, not weaker: a single 0 -> 2 jump would have been correct at the end
# and WRONG at the intervening commit.
#
# 2 -> 3 in an earlier plan's RED commit, the one that creates tools/render.py. The
# literal moves in the commit that creates the file, as the message below
# instructs, so the tripwire is never satisfied by a file that arrived silently.
#
# 3 -> 4 in an earlier plan's RED commit, the one that creates tools/conformance.py.
# That is the last name in the declaration, so the derived count and the DECLARED
# count agree from here on and any future disagreement is a file that vanished.
VENDORED_SET_PRESENT = 5

# The per-check modules, which arrive one at a time across an earlier plan .. an earlier plan.
#
# 0 -> 1 in an earlier plan's RED commit, the one that creates tools/checks/check_01.py.
# The literal moves in the commit that CREATES the file, exactly as the failure
# message below instructs, so the tripwire is never satisfied by a module that
# arrived silently. The remaining eight arrive one per plan across an earlier plan .. an earlier plan;
# an earlier plan asserts the glob and the declared universe have converged on 9.
#
# 1 -> 2 in an earlier plan's CHECK-03 RED commit, the one that creates
# tools/checks/check_03.py. Same rule: the literal moves in the commit that
# creates the file, never in a later one that notices it.
#
# 2 -> 9 in an earlier plan, and the DELAY IS THE FINDING RATHER THAN THE FIX. The
# protocol above -- each plan bumps this integer in the commit that creates its
# module -- held for an earlier plan and an earlier plan and then broke, where plans
# an earlier plan, an earlier plan and an earlier plan ran in PARALLEL and added seven modules between them.
# Three concurrent plans cannot each increment one shared integer, so none of
# them did, and the tripwire fired at the merge exactly as designed: `derived 9
# check module(s) ... committed literal says 2`. It caught the gap it exists to
# catch; what it could not do was tell the wave partition beforehand.
#
# The partition's pre-flight asked "do any two plans declare the same file?" and
# passed cleanly over 37 files with zero pairwise overlap. It cannot answer "does
# any plan need a file that NOBODY declares?", and the second question is the one
# that bit. Recorded here because the next parallel wave that adds modules will
# meet it again: either a wave-closing plan owns the bump (this one did), or the
# partition must give exactly one plan in the wave the file.
#
# From here the glob and the declared universe have CONVERGED: ten modules on
# disk, ten ids in tools/checks/__init__.py's DECLARED_CHECK_IDS. Ten is the
# MODULE count. The CHECKER count is TWELVE -- CHECK-10 and CHECK-11 are runner
# properties of tools/conformance.py and will never match this glob. The two
# numbers are asserted separately in a companion test module, and neither
# may stand in for the other.
#
# The tenth module is check_20.py, and the count moved because a MODULE landed
# rather than because this literal was raised to match a glob. That direction is
# the whole reason the literal exists.
#
# THIS IS THE ON-DISK COUNT AND IT IS NOT THE VENDORED COUNT. check_20.py reads
# the owner's live collections entries, so tools/vendor.py declares it as
# deliberately not vendored and an artifact carries NINE. Three numbers now, all
# derivable and none standing in for another: ten on disk, nine shipped, one
# excluded with its reason. tools/tests/test_vendoring.py asserts the arithmetic
# closes.
VENDORED_CHECK_GLOB = "tools/checks/check_*.py"
VENDORED_CHECK_GLOB_PRESENT = 11


# The forbidden MODULE NAMES, built from FRAGMENTS rather than pasted literals.
# This module is itself inside the scanned population, so a pasted literal would
# make the test fail against its own source -- and the natural "fix" for that
# (excluding this file from the scan) would put a hole exactly where the guard
# is supposed to be.
_CORE = "canon" + "kit"
_PKG = "tools" + "."

FORBIDDEN_MODULES = (
    _CORE,
    _PKG + _CORE,
    _PKG + "conformance",
    _PKG + "render",
    _PKG + "checks",
)


def _vendored_paths():
    return {(REPO_ROOT / rel).resolve() for rel in VENDORED_SET}


def _repo_side_modules():
    """Every .py file under tools/ that is NOT part of the vendored set."""
    vendored = _vendored_paths()
    checks_dir = (REPO_ROOT / "tools" / "checks").resolve()
    found = []
    for path in sorted((REPO_ROOT / "tools").rglob("*.py")):
        resolved = path.resolve()
        if resolved in vendored:
            continue
        if checks_dir == resolved.parent or checks_dir in resolved.parents:
            continue
        found.append(path)
    return found


def _forbidden(name):
    """True when `name` is a forbidden module or a submodule of one."""
    if not isinstance(name, str):
        return False
    return any(name == mod or name.startswith(mod + ".")
               for mod in FORBIDDEN_MODULES)


# The two function names that turn a STRING into an import. Nothing else does,
# and in particular importlib.util.spec_from_file_location does NOT: that is the
# path-based load a design rule REQUIRES, and tools/vendor.py performs it.
_DYNAMIC_IMPORT_CALLS = ("import_module", "__import__")


def _called_name(node):
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _forbidden_references(path):
    """Every LIVE reference to the vendored set in `path`. Prose is not a reference.

    RE-KEYED TWICE IN AN EARLIER PLAN, and each re-key closed a different way of
    being too loose. Recorded here because the shape recurred five times across
    this plan and the next person will write the same predicate again.

    FIRST DRAFT (from an earlier plan): `needle in line` over the raw text. It fired
    against a test DOCSTRING that QUOTED an earlier plan's own acceptance criterion
    while explaining why that criterion had to be re-keyed. an earlier plan had
    already found this shape in .githooks/pre-push and fixed it there by
    stripping `#` comments -- which does not help in Python, where a docstring
    is a string expression rather than a comment.

    SECOND DRAFT: AST import nodes, plus any whole-string literal equal to a
    forbidden module name or beginning with one plus a dot. `startswith("x.")`
    was meant to catch the submodule `tools.checks.check_01`. It also matched
    the FILENAME `canonkit.py`, which is a path, not a module -- 26 false
    findings across two files, every one of them a legitimate file reference in
    the module whose entire job is copying that file.

    THIS DRAFT is structural on both axes and matches only what actually
    imports:

      IMPORT NODES     ast.Import / ast.ImportFrom.
      DYNAMIC IMPORTS  a string argument to import_module() or __import__().
                       Those two calls, and only those two, turn a string into
                       an import. spec_from_file_location() is deliberately NOT
                       one of them: loading the core by path under a bare name
                       is the mechanism a design rule mandates, so flagging it would
                       have made the guard forbid the correct behaviour.
    """
    hits = []
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _forbidden(alias.name):
                    hits.append("%s:%d imports %r"
                                % (path.name, node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and _forbidden(node.module):
                hits.append("%s:%d imports from %r"
                            % (path.name, node.lineno, node.module))
        elif isinstance(node, ast.Call) and _called_name(node) in _DYNAMIC_IMPORT_CALLS:
            for arg in node.args:
                if (isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                        and _forbidden(arg.value.strip())):
                    hits.append("%s:%d imports %r dynamically via %s()"
                                % (path.name, node.lineno, arg.value.strip(),
                                   _called_name(node)))
    return hits


def test_frozen_core_is_never_imported():
    """a design rule's split is enforced by a test, not by a convention.

    The frozen core's whole job is being copied byte-identical into up to
    fourteen artifact repositories. Making it a package module invites importing
    it HERE while the artifacts import their vendored copy, and the two then
    drift in the one file whose purpose is preventing drift.

    Since an earlier plan the core ALSO refuses a dotted import from inside itself,
    so this is now the outer of two independent guards rather than the only one.
    """
    modules = _repo_side_modules()

    assert modules, (
        "scanned 0 repo-side modules under %s -- an empty population cannot "
        "prove anything, and `all(...)` over it would report PASS"
        % (REPO_ROOT / "tools")
    )

    hits = []
    for path in modules:
        hits.extend(
            "%s -> %s" % (path.relative_to(REPO_ROOT), hit)
            for hit in _forbidden_references(path)
        )

    assert not hits, (
        "scanned %d repo-side module(s); %d forbidden reference(s) found:\n%s"
        % (len(modules), len(hits), "\n".join(hits))
    )


def test_vendored_set_literal_matches_derived():
    """The derived on-disk count must agree with the committed literal."""
    assert VENDORED_SET_DECLARED > 0, "the declared vendored set may never be empty"
    assert len(VENDORED_SET) == VENDORED_SET_DECLARED, (
        "the vendored-set DECLARATION moved: declares %d path(s), literal says %d. "
        "Update VENDORED_SET_COUNT in tools/vendor.py in the same commit that "
        "changes the list." % (len(VENDORED_SET), VENDORED_SET_DECLARED)
    )

    present = sorted(
        rel for rel in VENDORED_SET if (REPO_ROOT / rel).is_file()
    )
    assert len(present) == VENDORED_SET_PRESENT, (
        "derived %d vendored-set file(s) on disk, committed literal says %d. "
        "Present: %s. A file appearing or vanishing without this literal moving "
        "is the finding -- raise VENDORED_SET_PRESENT in the plan that creates it."
        % (len(present), VENDORED_SET_PRESENT, present or "<none>")
    )

    check_modules = sorted(
        str(p.relative_to(REPO_ROOT)).replace("\\", "/")
        for p in REPO_ROOT.glob(VENDORED_CHECK_GLOB)
    )
    assert len(check_modules) == VENDORED_CHECK_GLOB_PRESENT, (
        "derived %d check module(s) matching %s, committed literal says %d. Found: %s"
        % (
            len(check_modules),
            VENDORED_CHECK_GLOB,
            VENDORED_CHECK_GLOB_PRESENT,
            check_modules or "<none>",
        )
    )


def test_lock_is_hash_pinned():
    """a design rule: every requirement carries at least one sha256 hash.

    `--require-hashes` refuses the WHOLE install if a single transitive pin
    lacks a hash, so this test is the tripwire on the lock being regenerated
    without `--generate-hashes`.
    """
    lock = REPO_ROOT / "requirements.txt"
    assert lock.is_file(), "no hash-pinned lock at %s" % lock

    hashes_per_requirement = {}
    order = []
    current = None
    for raw in lock.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw[0].isspace():
            if current is not None and "--hash=sha256:" in raw:
                hashes_per_requirement[current] += 1
            continue
        stripped = raw.strip()
        if stripped.startswith("-"):
            current = None
            continue
        name = stripped.split(";")[0].rstrip("\\").strip()
        current = name
        if current not in hashes_per_requirement:
            hashes_per_requirement[current] = 0
            order.append(current)
        if "--hash=sha256:" in raw:
            hashes_per_requirement[current] += 1

    assert order, (
        "parsed 0 requirement lines out of %s -- a lock with no requirements "
        "would pass a naive all() check while pinning nothing" % lock
    )

    unhashed = [name for name in order if hashes_per_requirement[name] < 1]
    assert not unhashed, (
        "parsed %d requirement(s); %d carry no --hash=sha256: continuation: %s"
        % (len(order), len(unhashed), unhashed)
    )


def test_broken_fixture_tree_is_outside_the_scan_root():
    """a design rule -> a design rule: conformance.py must never scan its own fixtures.

    NOTE ON THE PREDICATE, because the obvious one is wrong here. This
    repository lives INSIDE the scan root (<home>/Research/artifact-conformance-toolkit),
    so `fixtures/broken-artifacts/` IS a descendant of SCAN_ROOT by naive path
    containment and `assert not fixtures.is_relative_to(SCAN_ROOT)` could never
    pass. Shrinking SCAN_ROOT to make it pass would be inventing a constraint:
    the real scan root is where the artifact slugs live, and an earlier plan must be
    able to declare that same value in the manifest.

    The property a design rule actually requires is that no part of the fixture tree is
    ever ENUMERATED as an artifact. conformance.py enumerates the IMMEDIATE
    children of SCAN_ROOT (depth 1); the fixture tree sits at depth 3. That is
    what is asserted.
    """
    scan_root = conftest.SCAN_ROOT
    fixtures = conftest.BROKEN_FIXTURES_DIR.resolve()

    assert scan_root.is_dir(), "SCAN_ROOT does not exist: %s" % scan_root
    assert fixtures.is_dir(), "the design rule fixture tree does not exist: %s" % fixtures

    # FINDING SITE 3. This test MIXES ANCHORS by construction and cannot stop: the
    # scan root is the MAIN checkout's parent, while the fixture tree under
    # test is the WORKING checkout's, because the working tree is the thing
    # being checked. What it must not do is let a slipped anchor pass silently
    # -- every "is not among the enumerated" below holds vacuously over the two
    # or three sibling worktrees a working-anchored root would enumerate. So
    # the anchor is asserted, and the relative_to() call below is given a
    # premise instead of a ValueError.
    assert scan_root == (conftest.MAIN_REPO_ROOT / "..").resolve(), (
        "SCAN_ROOT %s is not the MAIN checkout's parent %s"
        % (scan_root, (conftest.MAIN_REPO_ROOT / "..").resolve()))
    assert fixtures.is_relative_to(scan_root), (
        "the fixture tree %s is not under the scan root %s at all, so this "
        "checkout sits outside the population the assertion is about"
        % (fixtures, scan_root))

    enumerated = sorted(
        child.resolve() for child in scan_root.iterdir() if child.is_dir()
    )
    assert enumerated, (
        "enumerated 0 directories under SCAN_ROOT %s -- an empty scan set makes "
        "every 'not in' assertion below vacuously true" % scan_root
    )

    assert fixtures not in enumerated, (
        "the fixture tree is itself one of the %d enumerated artifact candidates "
        "under %s" % (len(enumerated), scan_root)
    )

    broken_children = sorted(
        child.resolve() for child in fixtures.iterdir() if child.is_dir()
    )
    assert broken_children, (
        "the design rule fixture tree at %s holds 0 subdirectories -- an unseeded tree "
        "makes the per-child assertion below vacuous" % fixtures
    )
    for child in broken_children:
        assert child not in enumerated, (
            "%s is enumerated as an artifact candidate under %s" % (child, scan_root)
        )

    depth = len(fixtures.relative_to(scan_root).parts)
    assert depth > conftest.SCAN_DEPTH, (
        "the fixture tree sits at depth %d below SCAN_ROOT while the scan reaches "
        "depth %d -- it is within reach of the enumeration"
        % (depth, conftest.SCAN_DEPTH)
    )


def _check_ignore(relative_path):
    """Ask git whether it would ignore `relative_path`. Returns (exit_code, text).

    Exit 0 means at least one path IS ignored; exit 1 means none are.
    """
    completed = subprocess.run(
        ["git", "check-ignore", "-v", "--", relative_path],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    return completed.returncode, completed.stdout + completed.stderr


def test_fixture_results_are_committable():
    """Both directions, because one alone is satisfied by deleting the rule.

    `.gitignore`'s broad `results/` rule was VERIFIED to swallow
    `fixtures/broken-artifacts/**/results/*.json`, which would mean a design rule's tree
    is silently never committed and an earlier plan's audit counts a population that
    excludes it. A scoped negation admits that tree ONLY. Asserting just the
    admission would also pass if the `results/` rule were deleted outright,
    which is the door the rule exists to keep shut.
    """
    inside = "fixtures/broken-artifacts/broken-unpinned-dependency/results/probe.json"
    outside = (
        "results/probe.json",
        "some-artifact/results/probe.json",
    )

    code, text = _check_ignore(inside)
    assert code != 0, (
        "the design rule fixture tree is still ignored -- %s matched a rule:\n%s"
        % (inside, text.strip() or "<no output>")
    )

    for path in outside:
        code, text = _check_ignore(path)
        assert code == 0, (
            "the `results/` rule no longer ignores %s. A negation that admits "
            "everything would pass the first half of this test and defeat the "
            "rule entirely.\ngit check-ignore said: %s"
            % (path, text.strip() or "<no output>")
        )
        assert "results/" in text, (
            "%s is ignored, but not by the `results/` rule: %s" % (path, text.strip())
        )


HOOKS_DIRNAME = ".githooks"
HOOK_NAME = "pre-push"
HOOK_PATH = HOOKS_DIRNAME + "/" + HOOK_NAME
_FAIL_CLOSED_BEGIN = "FAIL-CLOSED-BRANCH: begin"
_FAIL_CLOSED_END = "FAIL-CLOSED-BRANCH: end"


def test_pre_push_hook_is_fail_closed():
    """a design rule + a project requirement + an owner decision: this hook IS the gate, so it must refuse, not wave through.

    The analog (the-upstream-project/.githooks/pre-commit) ends its no-interpreter
    branch with `exit 0` because that project has CI as the authoritative
    backstop. This repository has none -- a project requirement disqualifies hosted runners and
    an owner decision chose the local hook AS the gate. A fail-open hook here makes a design rule
    silently optional while still looking installed.
    """
    completed = subprocess.run(
        ["git", "ls-files", "--", HOOK_PATH],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    rows = [line for line in completed.stdout.splitlines() if line.strip()]
    # TRACKED, not merely present. The same distinction CHECK-07 makes: an
    # untracked hook is invisible to every other clone and to review.
    assert len(rows) == 1, (
        "expected exactly 1 tracked row for %s, got %d: %s"
        % (HOOK_PATH, len(rows), rows or "<none>")
    )

    # The RECORDED mode must be executable. git silently SKIPS a hook that is not
    # executable, so a 100644 hook is a gate that quietly never runs -- the same
    # fail-open this hook exists to prevent, arriving through the file mode
    # instead of through an exit code. `core.filemode` is false on this machine,
    # so the bit is not picked up from the filesystem and must be set explicitly
    # with `git update-index --chmod=+x`. The analog ships 100755.
    staged = subprocess.run(
        ["git", "ls-files", "-s", "--", HOOK_PATH],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    fields = staged.stdout.split()
    assert fields, "git ls-files -s returned nothing for %s" % HOOK_PATH
    assert fields[0] == "100755", (
        "%s is recorded as mode %s, not 100755. git skips a non-executable hook "
        "without saying so. Fix with: git update-index --chmod=+x %s"
        % (HOOK_PATH, fields[0], HOOK_PATH)
    )

    hook = REPO_ROOT / HOOK_PATH
    text = hook.read_text(encoding="utf-8")

    configured = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    # RE-KEYED by an earlier plan, and the split is between a property of the
    # REPOSITORY and a property of ONE CLONE OF IT.
    #
    # `core.hooksPath` lives in .git/config. It is NEVER pushed and never
    # cloned: the hook's own header says "run ONCE per clone" for exactly that
    # reason. So this assertion, as written, said "whoever is running this
    # suite has already activated the hook" -- true here, and false for every
    # reader who clones the published toolkit and runs pytest, which is a
    # repository refuting itself on the first command a reader types.
    #
    # What ships is the INSTALLED half: the hook is tracked, recorded 100755
    # (asserted above), fails closed (asserted below), and the repository
    # carries the activation command in a tracked file. What cannot ship is the
    # ACTIVATED half. Both are asserted; neither branch is a pass-by-absence,
    # and the branch that ran is PRINTED, because a verdict without its
    # population is the thing this project does not accept.
    activated = configured.returncode == 0 and configured.stdout.strip()
    print("pre-push gate: tracked=yes mode=100755 activated=%s"
          % ("yes" if activated else "no"))

    if not activated:
        instruction = "git config core.hooksPath " + HOOKS_DIRNAME
        carriers = sorted(
            path for path in (REPO_ROOT / HOOK_PATH, REPO_ROOT / "README.md")
            if path.is_file()
            and instruction in path.read_text(encoding="utf-8", errors="replace")
        )
        assert carriers, (
            "core.hooksPath is not set AND no tracked file carries the "
            "activation command %r, so this hook is inert with nothing telling "
            "a reader how to arm it" % instruction)
        # The hook's OWN BYTES are asserted on both paths. An early return that
        # took the fail-closed assertions with it would have traded one
        # untravelling assertion for three that travel perfectly well.
        _assert_the_hook_fails_closed(text)
        return
    # a recorded defect's DURABLE FIX: RESOLVE-equality, never string equality.
    #
    # WHAT WAS MEASURED, five times. Creating an automated agent worktree
    # rewrites core.hooksPath in the SHARED .git/config from `.githooks` to the
    # main checkout's ABSOLUTE `<repo>/.githooks`. The orchestrator read the
    # value immediately before and immediately after an earlier round worktree creation
    # and saw exactly that; earlier plans read the absolute form from
    # inside their own worktrees without being told what to expect; removing the
    # worktree does not revert it.
    #
    # WHY THE OLD ASSERTION WAS THE WRONG SHAPE. It pinned the literal string
    # `.githooks`, so it failed on SPELLING while the configured path still
    # resolved to this repository's tracked hooks and the hook was never inert.
    # A one-off `git config core.hooksPath .githooks` repair is a treadmill: it
    # was applied at the earlier round merge and undone within minutes of an earlier round
    # dispatching, then applied again and undone again. The
    # config value is not the fix; this assertion is.
    #
    # The property that matters is "the configured hooks path IS this
    # repository's tracked .githooks directory", and that is a question about
    # paths, so it is asked by resolving paths. Both states the guard exists to
    # catch are still rejected: UNSET (the returncode assertion above -- hook
    # tracked but inert) and POINTING ELSEWHERE (any resolution outside the
    # accepted set below). Same discipline an earlier plan applied to the scan-root
    # criterion, and the same one an earlier plan applied when it replaced a
    # `startswith("canonkit.")` text match -- which produced 26 confident false
    # findings by matching a FILENAME -- with an AST predicate.
    #
    # TWO ROOTS ARE ACCEPTED, and that is the point rather than a loophole. A
    # linked worktree SHARES .git/config with the main checkout, so from inside
    # an agent the configured value legitimately names the MAIN checkout's
    # .githooks while REPO_ROOT is the worktree's. Accepting only the working
    # root would reproduce a recorded defect with a different spelling; accepting only the main
    # root would fail in an ordinary clone that has never had a worktree. Both
    # are derived -- never typed -- and the resolution that matched is named in
    # the failure message so a reader can tell which one answered.
    configured_value = configured.stdout.strip()
    assert configured_value, (
        "core.hooksPath is set to the EMPTY string, so git looks for hooks in a "
        "directory that cannot exist and this hook is INERT. "
        "Repair with: git config core.hooksPath .githooks"
    )

    working_root = Path(census_live_store.working_repo_root()).resolve()
    main_root = Path(census_live_store.main_repo_root()).resolve()
    accepted = {working_root / HOOKS_DIRNAME, main_root / HOOKS_DIRNAME}

    resolved = Path(configured_value)
    if not resolved.is_absolute():
        resolved = working_root / resolved
    resolved = resolved.resolve()

    assert resolved in accepted, (
        "core.hooksPath is %r, which resolves to %s. That is not this "
        "repository's tracked hooks directory. Accepted resolutions (both "
        "derived, neither typed): working checkout %s; main checkout %s. A "
        "linked worktree shares .git/config with the main checkout, so the "
        "ABSOLUTE main-checkout spelling is correct from inside an agent and is "
        "accepted -- what is rejected is a path pointing somewhere else "
        "entirely, and (above) core.hooksPath being unset."
        % (configured_value, resolved, accepted and sorted(accepted)[0],
           sorted(accepted)[-1])
    )

    # The directory the configuration resolves to must actually hold this hook.
    # Without this, a value resolving to an accepted-but-EMPTY directory would
    # satisfy the assertion above while git found no pre-push hook to run --
    # which is the inert state again, arriving through the filesystem instead of
    # through the config.
    assert (resolved / HOOK_NAME).is_file(), (
        "core.hooksPath resolves to %s, which holds no %s. The hook is tracked "
        "but git has nothing to run there." % (resolved, HOOK_NAME)
    )

    _assert_the_hook_fails_closed(text)


def _assert_the_hook_fails_closed(text):
    """The hook's OWN BYTES: the interpreter probe and the refusing branch.

    Extracted by an earlier plan so both paths through
    test_pre_push_hook_is_fail_closed assert it. These three properties are
    readable from the tracked file and hold in every clone, activated or not,
    which is exactly why they must not sit behind the activation check.
    """
    # The interpreter-selection loop must probe with --version, not merely with
    # `command -v`. On Windows `command -v python3` finds the Microsoft Store
    # App-execution alias: a non-functional stub that is findable and unusable.
    start = text.find("for py in $candidates")
    assert start != -1, "the interpreter-selection loop was not found in the hook"
    stop = text.find("\ndone", start)
    assert stop != -1, "the interpreter-selection loop is unterminated"
    loop = text[start:stop]

    assert '"$py" --version' in loop, (
        "the interpreter-selection loop does not probe `--version`. A bare "
        "`command -v` check would select the Store alias stub."
    )
    if 'command -v "$py"' in loop:
        probe_at = loop.find('"$py" --version')
        assert probe_at != -1, (
            "`command -v` is the ONLY probe in the selection loop -- the "
            "--version confirmation was removed"
        )

    # a design rule's payload: the test suite, and not yet the self-check.
    assert "-m pytest tools/tests" in text, (
        "the hook does not run the test suite, which is a design rule's entire payload"
    )

    begin = text.find(_FAIL_CLOSED_BEGIN)
    end = text.find(_FAIL_CLOSED_END)
    assert begin != -1 and end > begin, (
        "the no-interpreter branch is not delimited by the FAIL-CLOSED-BRANCH "
        "markers, so this test cannot assert on it"
    )
    # Judge LIVE CODE, not prose. Comment lines are stripped before asserting,
    # and that is not a convenience -- it is the fix for a defect this test
    # caught on its first run. The hook's own comment explained the fail-closed
    # design by NAMING the permissive token, so the negative assertion below
    # matched the DOCUMENTATION of the rule instead of a violation of it. A
    # guard that can be disarmed by writing about it is not a guard.
    branch_code = "\n".join(
        line
        for line in text[begin:end].splitlines()
        if not line.strip().startswith("#")
    )

    assert "exit 1" in branch_code, (
        "the no-interpreter branch does not refuse. It must exit non-zero.\n%s"
        % branch_code
    )
    assert "exit 0" not in branch_code, (
        "the no-interpreter branch contains `exit 0` in LIVE CODE -- it fails "
        "OPEN, which is the analog's behaviour and is wrong here: there is no CI "
        "backstop, so an unrunnable gate must refuse.\n%s" % branch_code
    )


def test_run_cli_preserves_a_nonzero_exit_code(tmp_path):
    """The fixture that makes the piped-exit-code trap impossible in this suite.

    A shell pipeline reports its LAST stage's status, so `conformance.py | tail`
    prints EXIT=0 with failures present. The assertion below is on the EXACT
    code, not merely on non-zero: an implementation that lost the child's status
    to a pipe would return 0 here.
    """
    ok = conftest.run_cli([sys.executable, "-c", "print('fine')"], cwd=tmp_path)
    assert ok.exit_code == 0, "a clean child reported %d" % ok.exit_code
    assert "fine" in ok.stdout

    argv = [
        sys.executable,
        "-c",
        "import sys; print('boom', file=sys.stderr); sys.exit(7)",
    ]
    bad = conftest.run_cli(argv, cwd=tmp_path)
    assert bad.exit_code == 7, (
        "expected the child's own exit code 7, got %d -- a lost exit code is "
        "exactly the trap this fixture exists to prevent" % bad.exit_code
    )
    assert "boom" in bad.stderr
    assert bad.report is None

    log = Path(bad.log_path) / "stderr.txt"
    assert log.is_file(), "run_cli did not write the captured stderr to %s" % log
    assert "boom" in log.read_text(encoding="utf-8")
