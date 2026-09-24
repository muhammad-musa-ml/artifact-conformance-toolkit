"""census_live_store -- the read-only boundary's PROOF, not its promise.

a design rule (HARD) says the canons are read by direct read of the canon JSON "wrapped in
a census_live_store.py snapshot before and a diff after, both committed as proof
the read-only store was untouched". The operative word is COMMITTED. A tool that
reads the store and then announces "I did not write anything" has produced an
assertion, and an assertion is the thing this program exists to replace with a
measurement. The evidence is the PAIR plus the diff, both on disk, re-runnable by
a reader who does not trust this file.

WHY A ZERO-FILE SNAPSHOT IS REFUSED (exit 2)
--------------------------------------------
A census over zero files diffs EMPTY against anything. It would report the store
untouched while having looked at nothing -- the 0/0 pass wearing a different hat,
and the single failure mode this whole phase is organised against. So snapshot()
prints its population line and then REFUSES rather than returning a record that
would launder an unrun check as a proof. diff() refuses the same way on a
zero-file input, because a hand-edited or truncated record reaches it by a door
snapshot() does not guard.

WHAT IS RECORDED, AND WHAT IS NOT
---------------------------------
Per file: the relative path, the byte size and the sha256 of the BYTES. Never the
content. an earlier step in an earlier plan's threat register turns on this: these records are
committed, so a key-shaped literal must never be able to enter one. Paths, sizes
and hashes cannot carry one.

The root is stored RELATIVE to this repository when it can be (`../information`),
so no absolute home path is baked into a tracked file -- the same rule
tools/tests/conftest.py applies to SCAN_ROOT, and for the same reason.

THE SCOPE IS PART OF THE RECORD
-------------------------------
A narrower census is a WEAKER proof, and a reader must be able to see which was
taken without re-running anything. `scope` is therefore a required field, printed
in the population line and carried in the JSON. A proof whose strength cannot be
read off the artifact is not a proof.

EXIT CODES -- the canonkit contract
    0  the census ran over a non-empty population and the diff was empty
    1  the diff found a change: the store was NOT untouched
    2  could not look: zero files, missing input, mismatched scope
"""

import argparse
import importlib.util
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)

SCHEMA = "census/1"
SCHEMA_VERSION = 1

# The four finding kinds diff() can name. Declared as a tuple so a test can
# assert the set rather than restate it, and so a new kind cannot be added
# without the test noticing.
FINDING_KINDS = ("added", "removed", "resized", "rehashed",
                 "became_unreadable", "became_readable", "scope_mismatch",
                 "allow_listed_path_absent")

# The two kinds an ALLOW-LISTED path can produce. Deliberately NOT in
# FINDING_KINDS: an authorised change is not a finding, and keeping it out of
# that tuple is what stops an aggregate counting it as one.
#
# Why this exists at all. Until 2026-09-16 the boundary was "the live store
# never changes", and the census proved it by failing on ANY diff. Correcting
# the two live collections entries then became this program's deliverable, so a
# census that fails on any change would fail on the program's own output. The
# proof NARROWS rather than disappearing: an allow-listed path may change,
# everything else still may not, and the allow-list is printed and recorded so a
# reader can see which proof was taken.
EXPECTED_KINDS = ("expected_change", "expected_change_absent")

# An allow-list forgives an EDIT and nothing else. A correction rewrites an
# entry in place; deleting it, or conjuring one, is not a correction -- and an
# allow-list that forgave `removed` would forgive exactly the damage worth
# catching.
_ALLOWABLE_KINDS = ("resized", "rehashed")


def _load_core():
    """Load the frozen core BY PATH under a neutral name.

    Never a package import: a design rule forbids it, test_repo_hygiene.py scans every
    repo-side module for it, and the core itself raises on a dotted __name__.
    """
    path = os.path.join(_HERE, "canonkit.py")
    spec = importlib.util.spec_from_file_location("frozen_core", path)
    if spec is None or spec.loader is None:
        raise ImportError("could not build an import spec for %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = _load_core()


def working_repo_root():
    """The root of the checkout THIS FILE IS RUNNING FROM. Where OUTPUT goes.

    The counterpart to main_repo_root(), and the distinction is not academic --
    it was MEASURED the hard way. main_repo_root() was introduced so the
    recorded root would be portable, and was then reused to anchor the census
    tool's OUTPUT directory. That wrote two 730 KB census records into the MAIN
    checkout from inside a worktree: files nobody asked for, in a tree nobody
    was watching, which the next commit in that checkout would have swept up.

    The rule the two functions encode:

        READ anchor  -> main_repo_root().   The live store sits BESIDE the main
                        checkout, and a worktree is nested INSIDE it, so only
                        the main root resolves `../information` correctly.
        WRITE anchor -> working_repo_root(). Output belongs to the checkout that
                        produced it, always.

    Getting these the same way round by accident is easy, because in an ordinary
    checkout they are the SAME directory and nothing distinguishes them.
    """
    return _REPO_ROOT


def main_repo_root():
    """The MAIN checkout's root, even when this runs from a git worktree.

    MEASURED, not anticipated. The first full-tree census taken for an earlier plan
    ran inside agent-worktrees/worktrees/agent-<id>/ and recorded its root as
    `../../../../information` -- four levels, counted from the WORKTREE. That
    string is correct exactly once: in the worktree that produced it. Merged to
    main and read from the ordinary checkout it resolves to a directory that
    does not exist, and the census record -- a committed proof whose whole value
    is being re-runnable by a reader who does not trust the tool -- silently
    stops being re-runnable.

    A worktree's `.git` is a FILE holding `gitdir: <main>/.git/worktrees/<name>`.
    Walking that back to <main> is what makes the recorded root portable. In an
    ordinary checkout `.git` is a directory and this returns the repo root
    unchanged, so the two cases produce the SAME string for the same tree --
    which is the property that matters.
    """
    marker = os.path.join(_REPO_ROOT, ".git")
    if not os.path.isfile(marker):
        return _REPO_ROOT
    try:
        with open(marker, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return _REPO_ROOT
    return resolve_worktree_main_root(_REPO_ROOT, text)


def resolve_worktree_main_root(repo_root, marker_text):
    """Pure half of main_repo_root(), so the worktree case is TESTABLE.

    Separated because the interesting branch only fires inside a real worktree,
    and a guard that can only be exercised by the environment that broke it is
    a guard nobody re-checks.

    Returns `repo_root` unchanged for any marker this does not understand --
    failing back to the observable value rather than to a guess.
    """
    text = (marker_text or "").strip()
    if not text.startswith("gitdir:"):
        return repo_root
    gitdir = text.split(":", 1)[1].strip()
    if not os.path.isabs(gitdir):
        gitdir = os.path.join(repo_root, gitdir)
    gitdir = os.path.abspath(gitdir)
    parts = gitdir.replace("\\", "/").rstrip("/").split("/")
    if len(parts) >= 3 and parts[-2] == "worktrees" and parts[-3] == ".git":
        return os.path.abspath(os.path.join(gitdir, os.pardir, os.pardir,
                                            os.pardir))
    return repo_root


def _root_ref(root):
    """Render `root` relative to the MAIN repository root when possible.

    Returns (reference_string, is_absolute). On Windows a relpath across drive
    letters raises ValueError; that is the one case where an absolute path is
    recorded, and the flag beside it says so rather than leaving a reader to
    infer it from the string's shape.
    """
    absolute = os.path.abspath(str(root))
    try:
        relative = os.path.relpath(absolute, main_repo_root())
    except ValueError:
        return absolute.replace(os.sep, "/"), True
    return relative.replace(os.sep, "/"), False


def snapshot(root, scope, label=None, quiet=False):
    """Record {path, bytes, sha256} for every file under `root`.

    Args:
        root: the directory to walk. Never written to, opened "rb" only.
        scope: a REQUIRED human sentence stating what this census covers. A
            narrower scope is a weaker proof; the record carries its own
            strength so a reader does not have to reconstruct it.
        label: short tag carried into the record and into generated filenames.
        quiet: suppress the population line (the caller prints its own).

    Returns:
        The snapshot dict.

    Raises:
        SystemExit(2): when `root` is not a directory, or when the walk would
            record ZERO files.
    """
    if not scope or not str(scope).strip():
        raise ValueError(
            "snapshot(): `scope` is required. A census record that does not "
            "state what it covered cannot be evaluated as a proof.")

    root_abs = os.path.abspath(str(root))
    if not os.path.isdir(root_abs):
        core.die(core.EXIT_DID_NOT_RUN,
                 "%s census root is not a directory: %s\n"
                 "  A census over a missing root would record zero files and "
                 "then diff empty against anything.\n"
                 "  REPAIR: pass an existing directory."
                 % (core.REFUSAL_PREFIX, root_abs))

    files = {}
    unreadable = {}
    for dirpath, dirnames, filenames in os.walk(root_abs, followlinks=False):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            relative = os.path.relpath(full, root_abs).replace(os.sep, "/")
            try:
                size = os.path.getsize(full)
                digest = core.sha256_file(full)
            except OSError as exc:
                # Counted and given a reason, never silently dropped. An
                # uncounted skip is how a population line stops being checkable.
                unreadable[relative] = type(exc).__name__
                continue
            files[relative] = {"bytes": size, "sha256": digest}

    reference, is_absolute = _root_ref(root_abs)
    record = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "label": label or "",
        "scope": str(scope).strip(),
        "root": reference,
        "root_is_absolute": is_absolute,
        "taken_at": core.now_local(),
        "taken_at_utc": core.now_utc(),
        "file_count": len(files),
        "unreadable_count": len(unreadable),
        "total_bytes": sum(entry["bytes"] for entry in files.values()),
        "files": files,
        "unreadable": unreadable,
    }

    # THE POPULATION LINE COMES FIRST, ON EVERY BRANCH -- including the branch
    # that is about to refuse. A refusal with no count beside it does not tell
    # the operator whether the root was empty or the walk was broken.
    if not quiet:
        core.report("CENSUS-SNAP", True, found=0, checked=len(files), floor=1,
                    not_examined=len(unreadable),
                    listed=len(files) + len(unreadable),
                    note="scope=%s root=%s" % (record["scope"], reference))

    # THE REFUSAL. The RED for this block is committed at the preceding commit,
    # and what it captured is worth restating: without it, snapshot() printed
    #     CENSUS-SNAP  DID-NOT-RUN found=0 checked=0 of 0 ...
    # and then exited 0. The line said one thing and the exit code said the
    # opposite, and the exit code is what a caller branches on. The record it
    # returned would then diff EMPTY against anything, reporting the read-only
    # store untouched on the strength of having looked at nothing.
    if not files:
        core.die(core.EXIT_DID_NOT_RUN,
                 "%s census of %s recorded 0 files (scope: %s).\n"
                 "  A census over zero files diffs EMPTY against anything, so "
                 "this record would report the\n"
                 "  store untouched while having looked at nothing. That is an "
                 "unrun check wearing a proof's\n"
                 "  clothes, and a design rule asks for a proof.\n"
                 "  REPAIR: point --root at the tree that actually holds the "
                 "files the read will open,\n"
                 "  then confirm the printed checked= count against what you "
                 "know the tree holds."
                 % (core.REFUSAL_PREFIX, reference, record["scope"]))

    return record


def _entry_findings(path, before_entry, after_entry):
    findings = []
    if before_entry["bytes"] != after_entry["bytes"]:
        findings.append({
            "kind": "resized", "path": path,
            "before": before_entry["bytes"], "after": after_entry["bytes"]})
    if before_entry["sha256"] != after_entry["sha256"]:
        findings.append({
            "kind": "rehashed", "path": path,
            "before": before_entry["sha256"], "after": after_entry["sha256"]})
    return findings


def diff(before, after):
    """Name every change between two snapshots. An empty list means UNCHANGED.

    A same-size different-hash edit is the case a size-only census would miss,
    so both are compared and both are named separately -- "resized" and
    "rehashed" are different evidence about what happened.

    This is the UNSCOPED form and its contract is unchanged: no path is
    forgiven. `diff_scoped` is the same walk with an allow-list.

    Raises:
        SystemExit(2): when either side records zero files. snapshot() cannot
            produce such a record, so one reaching here is hand-written or
            truncated, and diffing it would report "unchanged" over nothing.
    """
    findings, _expected = diff_scoped(before, after, allow_changed=())
    return findings


def diff_scoped(before, after, allow_changed=()):
    """`diff`, with an allow-list of paths a correction was authorised to change.

    Returns ``(findings, expected)``. An allow-listed path that was EDITED lands
    in ``expected`` as ``expected_change`` and is not a finding. Everything else
    behaves exactly as the unscoped diff does, including for allow-listed paths:

    * an allow-listed path that was ADDED or REMOVED is still a finding, because
      a correction rewrites a file that already exists;
    * an allow-listed path that did NOT change is reported as
      ``expected_change_absent``, so "the entry was corrected" and "the entry was
      never touched" cannot look the same to a caller;
    * an allow-listed path absent from BOTH snapshots is a finding
      (``allow_listed_path_absent``) -- a misspelt entry path would otherwise
      authorise nothing while the run still reported a clean scoped proof.

    Raises:
        SystemExit(2): as `diff` does, on a zero-file snapshot on either side.
    """
    for name, record in (("before", before), ("after", after)):
        if not isinstance(record, dict):
            core.die(core.EXIT_DID_NOT_RUN,
                     "%s the %s snapshot is not an object (got %s)."
                     % (core.REFUSAL_PREFIX, name, type(record).__name__))
        if not record.get("files"):
            core.die(core.EXIT_DID_NOT_RUN,
                     "%s the %s snapshot records 0 files.\n"
                     "  A census over zero files diffs EMPTY against anything "
                     "and would report the store untouched\n"
                     "  while having looked at nothing. That is an unrun check, "
                     "not a proof.\n"
                     "  REPAIR: re-run `census_live_store.py snapshot` against a "
                     "root that holds files."
                     % (core.REFUSAL_PREFIX, name))

    findings = []

    # A scope or root change means the two records describe DIFFERENT
    # populations. Comparing them would produce a diff whose emptiness says
    # nothing about the store.
    for key in ("root", "scope"):
        if before.get(key) != after.get(key):
            findings.append({
                "kind": "scope_mismatch", "path": key,
                "before": before.get(key), "after": after.get(key)})

    before_files = before["files"]
    after_files = after["files"]
    for path in sorted(set(after_files) - set(before_files)):
        findings.append({"kind": "added", "path": path,
                         "after": after_files[path]["sha256"]})
    for path in sorted(set(before_files) - set(after_files)):
        findings.append({"kind": "removed", "path": path,
                         "before": before_files[path]["sha256"]})
    for path in sorted(set(before_files) & set(after_files)):
        findings.extend(_entry_findings(path, before_files[path],
                                        after_files[path]))

    before_bad = set(before.get("unreadable") or {})
    after_bad = set(after.get("unreadable") or {})
    for path in sorted(after_bad - before_bad):
        findings.append({"kind": "became_unreadable", "path": path})
    for path in sorted(before_bad - after_bad):
        findings.append({"kind": "became_readable", "path": path})

    allowed = tuple(allow_changed or ())
    if not allowed:
        return findings, []

    allowed_set = set(allowed)
    kept = []
    # One entry per allow-listed PATH, not per finding. A size-changing edit
    # emits both `resized` and `rehashed` for the same file, and reporting that
    # as two expected changes would make `expected_count` a count of evidence
    # rather than a count of entries corrected -- which is the number a caller
    # compares against "how many entries did I authorise".
    by_path = {}
    # Paths that produced ANY finding, allowable or not. A path reported as
    # `added` or `removed` has already been accounted for; also calling it
    # `expected_change_absent` would report the same fact twice and let
    # --require-changed fire a second finding for one event.
    accounted = set()
    for finding in findings:
        accounted.add(finding["path"])
        if (finding["path"] in allowed_set
                and finding["kind"] in _ALLOWABLE_KINDS):
            entry = by_path.setdefault(finding["path"], {
                "kind": "expected_change",
                "path": finding["path"],
                "was": [],
            })
            entry["was"].append(finding["kind"])
            # Carry the first before/after seen so the record vouches for a
            # concrete transition rather than merely naming one.
            entry.setdefault("before", finding.get("before"))
            entry.setdefault("after", finding.get("after"))
            if finding["kind"] == "rehashed":
                entry["before"] = finding.get("before")
                entry["after"] = finding.get("after")
        else:
            kept.append(finding)

    known = set(before_files) | set(after_files) | before_bad | after_bad
    expected = []
    for path in allowed:
        if path not in known:
            kept.append({"kind": "allow_listed_path_absent", "path": path})
        elif path in by_path:
            expected.append(by_path[path])
        elif path not in accounted:
            expected.append({"kind": "expected_change_absent", "path": path})

    return kept, expected


def diff_population(before, after):
    """How many distinct paths the diff actually compared.

    Separated from diff() so a caller can print `checked=` without recomputing
    it, and so the number is derived from the same sets the comparison used
    rather than from one side of it.
    """
    return len(set(before.get("files") or {}) | set(after.get("files") or {})
               | set(before.get("unreadable") or {})
               | set(after.get("unreadable") or {}))


def read_snapshot(path):
    """Load a snapshot record, refusing a missing or unparseable file with 2."""
    try:
        with open(str(path), "rb") as handle:
            payload = handle.read()
    except OSError as exc:
        core.die(core.EXIT_DID_NOT_RUN,
                 "%s cannot read snapshot %s (%s)."
                 % (core.REFUSAL_PREFIX, path, type(exc).__name__))
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        core.die(core.EXIT_DID_NOT_RUN,
                 "%s snapshot %s is not valid UTF-8 JSON (%s)."
                 % (core.REFUSAL_PREFIX, path, exc))


def snapshot_filename(label, side, when=None):
    """`YYYY-MM-DD-HHMMSS--<label>--<side>.json`, the design rule pair's naming."""
    if side not in ("before", "after"):
        raise ValueError("side must be 'before' or 'after', got %r" % (side,))
    stamp = when or core.now_local()
    # Local time, digits only: 2026-09-15T10:22:31.123456+03:00 -> 2026-09-15-102231
    date_part = stamp[:10]
    time_part = stamp[11:19].replace(":", "")
    return "%s-%s--%s--%s.json" % (date_part, time_part, label, side)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="census_live_store.py",
        description="Snapshot a read-only tree and diff two snapshots.")
    sub = parser.add_subparsers(dest="command")

    snap = sub.add_parser("snapshot", help="record a census of a tree")
    snap.add_argument("root")
    snap.add_argument("--out", required=True)
    snap.add_argument("--scope", required=True)
    snap.add_argument("--label", default="census")

    delta = sub.add_parser("diff", help="compare two committed snapshots")
    delta.add_argument("before")
    delta.add_argument("after")
    delta.add_argument("--report", default=None)
    delta.add_argument(
        "--allow-changed", action="append", default=[], dest="allow_changed",
        metavar="PATH",
        help="a census-relative path a correction was authorised to EDIT; "
             "repeatable. An addition or a deletion of it is still a finding.")
    delta.add_argument(
        "--require-changed", action="store_true",
        help="fail when an allow-listed path did NOT change -- the flag a build "
             "phase uses, because a run that authorised a correction and did not "
             "make one has not done the work.")

    args = parser.parse_args(argv)

    if args.command == "snapshot":
        record = snapshot(args.root, scope=args.scope, label=args.label)
        core.atomic_write_json(args.out, record, ensure_ascii=True)
        return core.EXIT_PASS

    if args.command == "diff":
        before = read_snapshot(args.before)
        after = read_snapshot(args.after)
        allow_changed = list(args.allow_changed or [])
        findings, expected = diff_scoped(before, after,
                                         allow_changed=allow_changed)
        absent = [e for e in expected if e["kind"] == "expected_change_absent"]
        if args.require_changed and absent:
            # Not folded into `findings` by diff_scoped, because whether an
            # unused authorisation is a failure is the CALLER's policy: a
            # pre-correction census legitimately has none.
            findings = findings + [
                dict(e, kind="expected_change_absent") for e in absent]
        checked = diff_population(before, after)
        # The allow-list SIZE prints on every branch. A narrowed proof that does
        # not say it was narrowed is the weaker proof presented as the stronger
        # one, which is the whole failure the population line exists to prevent.
        verdict = core.report(
            "CENSUS-DIFF", not findings, found=len(findings),
            checked=checked, floor=1,
            note="scope=%s allowed=%d expected=%d"
                 % (before.get("scope", "<none>"), len(allow_changed),
                    len(expected)))
        for finding in findings:
            print("  %-18s %s" % (finding["kind"], finding["path"]))
        for entry in expected:
            print("  %-18s %s" % (entry["kind"], entry["path"]))
        if args.report:
            core.atomic_write_json(args.report, {
                "schema": "census-diff/1",
                "schema_version": 1,
                "before": os.path.basename(str(args.before)),
                "after": os.path.basename(str(args.after)),
                "scope": before.get("scope"),
                "checked": checked,
                "found": len(findings),
                "findings": findings,
                "allow_changed": allow_changed,
                "require_changed": bool(args.require_changed),
                "expected_count": len(expected),
                "expected": expected,
            }, ensure_ascii=True)
        return core.code_for(verdict)

    parser.print_help()
    return core.EXIT_DID_NOT_RUN


if __name__ == "__main__":
    sys.exit(main())
