"""The mutation harness: break the chain on purpose and name the guard that caught it.

    python -m tools.mutate --tree <artifact> [--only M-01] [--report FILE]

a success criterion requires that changing one per-item record makes verify.py FAIL, run on a
COMMITTED tree and never on a dirty one. a design rule adds the half that makes it a check
rather than a ritual: the run FAILS both when a mutant is caught by NOTHING and
when it is caught by a DIFFERENT guard than the one its catalogue entry names.
"Caught by some guard" is the check-that-cannot-discriminate shape -- it keeps
reporting success while the named guard has quietly stopped working.

THE TWO RULES BELOW ARE PLATFORM-LEVEL, NOT STYLISTIC.

  1. THE DIRTY-TREE REFUSAL. Never mutate a file with uncommitted changes. The
     status is read on the TARGET tree, not on this repository, because a check
     keyed to the harness's own checkout answers the same way for every target
     and therefore discriminates nothing.

  2. NEVER RESTORE FROM GIT. A restore from HEAD silently destroys uncommitted
     work; and used to revert a mutant it can make the thing under test the
     RESTORED IMPLEMENTATION rather than the mutation -- so the verdict is wrong
     in the direction that flatters it. This harness snapshots the bytes before
     editing, restores from the SNAPSHOT, and VERIFIES the restored bytes hash
     back to the recorded pre-mutation digest. A restore that does not verify is
     not a restore.

     TWO TELLS THAT YOU HAVE HIT IT, recorded so the next reader recognises the
     failure instead of re-deriving it:
         * a mutation that PASSES when it should fail;
         * a diff that shrank without anyone editing anything.

     Measured precedent, an earlier plan: HEAD there held the RED *stub*, so a git
     restore would have replaced the implementation with the blind version and
     made every later verdict flattering rather than merely wrong.

A CRASH IS NOT A KILL, AND THIS IS THE HIGHEST-LEVERAGE DISTINCTION HERE.
When a mutant makes a module unimportable, every probe exits non-zero. A harness
that reads only the exit code then calls the mutant killed -- by a stack trace,
not by a guard -- and the kill rate becomes fiction. Every probe is classified
three ways: FIRED (a guard's own predicate matched), SILENT (it ran and found
nothing) or ERRORED (it crashed, or could not look). Only FIRED counts, and the
four numbers -- attempted, killed, survived, errored -- are printed separately
because one rate cannot make an unrun probe visible.

EVERY PROBE IN THE DECLARED SET RUNS, ALWAYS. A loop that stops at the first
firing guard has learned that SOMETHING caught the mutant and nothing about
WHICH -- and "caught by another guard" is only observable when the guards that
were not named are run too.

WHY THE PROBE SET IS PER-MUTANT DATA RATHER THAN "ALL GUARDS".
Most guards are read-only: verify.py, render.py in its default reporting mode
 and conformance.py look without writing. `derive:refuse` does not -- on
success derive.py REWRITES results/figures.json, which would overwrite a mutant
mid-probe and destroy the very thing being measured. That is measured rather
than assumed (test_derive_rewrites_figures_json_which_is_why_it_is_scoped). So
each entry declares the probes actually run, the count is PRINTED beside the
verdict, and "caught by nothing" means "caught by none of the N probes run"
with N stated -- a bounded claim instead of an unbounded one.

EXIT CODES (the canonkit contract, a design rule):
    0  every mutant was killed by a guard named in its own entry
    1  at least one mutant survived, was misattributed, or errored
    2  REFUSED: the tree was dirty, a target was missing, or the catalogue was
       empty. A mutation run over zero mutants is a DID-NOT-RUN, never a pass.
"""

import argparse
import fnmatch
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid

_HERE = os.path.dirname(os.path.abspath(__file__))

__all__ = [
    "MutationError", "Snapshot", "Guard", "Probe", "MutationResult",
    "CampaignResult", "GUARDS", "OPERATIONS",
    "snapshot", "restore", "assert_committed", "apply_operation",
    "resolve_target", "mutate", "load_catalogue", "run_catalogue", "main",
]


def _load_core():
    """Load the frozen core BY PATH under a neutral name.

    Never a package import: a design rule forbids it, test_repo_hygiene.py scans every
    repo-side module for one, and the core itself raises on a dotted __name__.
    """
    path = os.path.join(_HERE, "canonkit.py")
    spec = importlib.util.spec_from_file_location("frozen_core", path)
    if spec is None or spec.loader is None:
        raise ImportError("could not build an import spec for %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = _load_core()

EXIT_PASS = core.EXIT_PASS
EXIT_FINDING = core.EXIT_FINDING
EXIT_DID_NOT_RUN = core.EXIT_DID_NOT_RUN

SCHEMA = "canonkit/mutants"

# What a crashed probe looks like. A guard's own refusal carries REFUSING: on
# stderr and is NOT a crash; an unhandled exception carries this header and is.
_TRACEBACK = "Traceback (most recent call last)"

# The git flags every subprocess carries, so a developer's global config can
# neither break nor silently satisfy a status read.
_GIT_FLAGS = ["-c", "core.hooksPath="]


class MutationError(Exception):
    """A fault in the HARNESS or in a catalogue entry -- never a guard verdict."""


# ---------------------------------------------------------------------------
# The byte snapshot
# ---------------------------------------------------------------------------


class Snapshot(object):
    """The bytes of one file before it was touched, and their sha256."""

    def __init__(self, path, data, sha256):
        self.path = str(path)
        self.data = data
        self.sha256 = sha256

    def __repr__(self):
        return "Snapshot(path=%r, bytes=%d, sha256=%s)" % (
            self.path, len(self.data), self.sha256[:12])


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def atomic_write_bytes(path, payload):
    """Write bytes atomically with NO translation of any kind.

    The binary counterpart of canonkit.atomic_write_text, whose `newline=""` is
    the line that matters most in that file. There is no text layer here at all,
    so a mutation cannot introduce a line-ending change that a later reader would
    mistake for the mutation's own effect.

    Same directory for the temp file, because os.replace is atomic within a
    volume and is not atomic across one; pid + uuid in its name so two writers
    aiming at one target cannot truncate each other; the `finally` unlink so a
    raise mid-stream leaves no stale .tmp for a later glob to count.
    """
    path = str(path)
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    tmp = "%s.%d.%s.tmp" % (path, os.getpid(), uuid.uuid4().hex)
    try:
        with open(tmp, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def snapshot(path):
    """Capture `path`'s bytes BEFORE anything edits them.

    Refuses a missing target rather than creating one: a mutation applied to a
    file the harness invented measures the harness, not the artifact.
    """
    path = str(path)
    if not os.path.isfile(path):
        core.die(EXIT_DID_NOT_RUN,
                 "%s no file at %s, so there is nothing to snapshot and nothing "
                 "to mutate. The harness will not create it -- a mutation "
                 "applied to a file the harness invented measures the harness.\n"
                 "  REPAIR: point --tree at an artifact that carries this path, "
                 "or fix the mutant's `target` pattern."
                 % (core.REFUSAL_PREFIX, path))
    with open(path, "rb") as handle:
        data = handle.read()
    return Snapshot(path, data, sha256_bytes(data))


def restore(snap):
    """Put the SNAPSHOT bytes back and VERIFY they hash to the recorded digest.

    Returns the verified digest. Raises MutationError when the bytes on disk
    after the write do not hash back -- an unverified restore is an assumption
    every later verdict would silently rest on.
    """
    atomic_write_bytes(snap.path, snap.data)
    with open(snap.path, "rb") as handle:
        after = sha256_bytes(handle.read())
    if after != snap.sha256:
        raise MutationError(
            "restore(%s): the restored bytes hash to %s but the pre-mutation "
            "snapshot recorded sha256 %s. The file on disk is NOT what was "
            "captured, so nothing measured after this point can be trusted."
            % (snap.path, after[:16], snap.sha256[:16]))
    return after


# ---------------------------------------------------------------------------
# The dirty-tree refusal (a design rule)
# ---------------------------------------------------------------------------


def _git(tree, *args):
    return subprocess.run(
        ["git"] + _GIT_FLAGS + list(args),
        cwd=str(tree), capture_output=True, text=True,
        encoding="utf-8", errors="replace", shell=False)


def assert_committed(tree):
    """REFUSE with exit 2 when the TARGET tree has any uncommitted change.

    Read on the target, never on this repository. a success criterion states it directly: run
    on a committed tree, never on a dirty one. The repair instruction is part of
    the refusal because a refusal that does not say what to do is one the
    operator learns to work around.
    """
    tree = str(tree)
    if not os.path.isdir(tree):
        core.die(EXIT_DID_NOT_RUN,
                 "%s --tree %s is not a directory.\n"
                 "  REPAIR: pass the root of the artifact to mutate."
                 % (core.REFUSAL_PREFIX, tree))

    status = _git(tree, "status", "--porcelain")
    if status.returncode != 0:
        core.die(EXIT_DID_NOT_RUN,
                 "%s `git status` failed in %s (exit %d): %s\n"
                 "  REPAIR: the mutation harness requires a git work tree, "
                 "because the committed state is what a restore is checked "
                 "against. Run `git init` and commit the artifact first."
                 % (core.REFUSAL_PREFIX, tree, status.returncode,
                    status.stderr.strip() or "<no stderr>"))

    lines = [line for line in status.stdout.splitlines() if line.strip()]
    if lines:
        core.die(EXIT_DID_NOT_RUN,
                 "%s %s has %d uncommitted change(s):\n%s\n"
                 "  Mutating a file with uncommitted changes makes the verdict "
                 "wrong in the direction that flatters it: the bytes restored "
                 "afterwards may be your own work rather than the mutant, and "
                 "the thing measured may have been the reverted implementation.\n"
                 "  REPAIR: commit the tree (or move the work aside with a "
                 "unique-tagged stash), then re-run."
                 % (core.REFUSAL_PREFIX, tree, len(lines),
                    "\n".join("    " + line for line in lines[:20])))


# ---------------------------------------------------------------------------
# Probes -- one subprocess, its REAL exit code, and a crash/verdict split
# ---------------------------------------------------------------------------


class Probe(object):
    """One guard command's run. `exit_code` is the CHILD's own status.

    Never a pipeline: argv is a list and shell=False always, so no stage can
    mask the child's status the way `cmd | tail` does.
    """

    def __init__(self, guard_id, argv, exit_code, stdout, stderr, report=None):
        self.guard_id = guard_id
        self.argv = argv
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.report = report
        self.outcome = "silent"
        self.evidence = ""

    @property
    def command(self):
        return " ".join(str(token) for token in self.argv)

    def crashed(self):
        """True when the process died rather than reaching a verdict.

        A guard's own refusal prints REFUSING: and exits deliberately; an
        unhandled exception prints a traceback. Only the second is a crash, and
        a crash may never be credited to a guard.
        """
        return _TRACEBACK in (self.stderr or "")


def _run_probe(guard_id, argv, cwd):
    argv = [str(token) for token in argv]
    completed = subprocess.run(
        argv, cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace", shell=False)
    report = None
    if "--report" in argv:
        index = argv.index("--report")
        if index + 1 < len(argv):
            candidate = argv[index + 1]
            if os.path.isfile(candidate):
                with open(candidate, "rb") as handle:
                    try:
                        report = json.loads(handle.read().decode("utf-8"))
                    except ValueError:
                        report = None
    return Probe(guard_id, argv, completed.returncode,
                 completed.stdout or "", completed.stderr or "", report)


# ---------------------------------------------------------------------------
# Guards -- an id, the command that exercises it, and what FIRING looks like
# ---------------------------------------------------------------------------


class Guard(object):
    """One named guard. `fired(probe)` returns (bool, evidence)."""

    def __init__(self, guard_id, build, fired, note=""):
        self.guard_id = guard_id
        self.build = build
        self.fired = fired
        self.note = note

    def __repr__(self):
        return "Guard(%r)" % self.guard_id


def _artifact_script(tree, name, *args):
    return [sys.executable, os.path.join(str(tree), name)] + [str(a) for a in args]


def _verify_argv(tree, workdir):
    return _artifact_script(tree, "verify.py", "--root", tree, "--tier", "derive")


def _render_argv(tree, workdir):
    return _artifact_script(tree, "render.py", tree)


def _derive_argv(tree, workdir):
    return _artifact_script(tree, "derive.py", "--root", tree,
                            "--specs", os.path.join(str(tree), "figure-specs.json"))


def _conformance_argv(tree, workdir):
    """DETERMINISTIC report path, so every check-backed guard shares ONE run.

    A uuid here would make each guard's argv unique, the run cache would miss,
    and the report would say conformance.py ran once per check -- which is a
    false statement about what the harness did, in the field whose whole job is
    saying what it ran.
    """
    report = os.path.join(str(workdir), "conformance.json")
    return _artifact_script(tree, "conformance.py", tree, "--report", report)


_TOKEN_MARKER = "gate_token mismatch"
_PROBLEM_PREFIX = "[verify]   "


def _verify_problem_lines(probe):
    return [line for line in probe.stdout.splitlines()
            if line.startswith(_PROBLEM_PREFIX)]


def _fired_verify_token(probe):
    """The token half of verify.py, distinguished by MESSAGE, not by exit code.

    verify:chain and verify:token are one command. Attributing by exit code
    alone would make them indistinguishable, which is precisely the resolution
    a design rule requires -- so each reads the finding it owns.
    """
    hits = [line for line in _verify_problem_lines(probe) if _TOKEN_MARKER in line]
    return (probe.exit_code != 0 and bool(hits), hits[0].strip() if hits else "")


def _fired_verify_chain(probe):
    hits = [line for line in _verify_problem_lines(probe)
            if _TOKEN_MARKER not in line]
    return (probe.exit_code != 0 and bool(hits), hits[0].strip() if hits else "")


def _fired_render_drift(probe):
    """render.py reporting DRIFT (exit 1) or REFUSING (exit 2). Never argparse.

    a design rule makes reporting the default, so exit 1 means the tool looked and the
    bytes differ. Exit 2 is the success criterion refusal -- a figure with no population
    cannot be rendered at all -- but argparse uses 2 for an unknown flag too, so
    the refusal prefix is required rather than the code alone. A guard credited
    for a typo in the harness would be the purest form of a fictional kill.
    """
    if probe.exit_code == EXIT_PASS:
        return (False, "")
    if probe.exit_code == EXIT_DID_NOT_RUN:
        if core.REFUSAL_PREFIX not in (probe.stderr or ""):
            raise MutationError(
                "render.py exited %d with no %s on stderr, which is argparse's "
                "code for an unknown flag rather than a verdict: %s"
                % (probe.exit_code, core.REFUSAL_PREFIX,
                   _first_line(probe.stderr) or "<no stderr>"))
        return (True, _first_line(probe.stderr))
    return (True, _first_line(probe.stdout) or _first_line(probe.stderr))


def _fired_derive_refusal(probe):
    """derive.py REFUSING at authorship time -- exit 2 with the refusal prefix.

    Exit 2 alone is not enough: argparse uses the same code for an unknown flag,
    which would credit the guard for a typo in the harness.
    """
    refused = (probe.exit_code == EXIT_DID_NOT_RUN
               and core.REFUSAL_PREFIX in (probe.stderr or ""))
    if not refused:
        return (False, "")
    for line in probe.stderr.splitlines():
        if core.REFUSAL_PREFIX in line:
            return (True, line.strip()[:200])
    return (True, "")


def _fired_check(check_id):
    """A named conformance check's own row -- attribution by id, not by exit.

    An ABSENT row raises: the check does not exist in this artifact, so the
    probe could not look. Reporting that as "did not fire" would manufacture a
    false survivor, which is the 0/0 pass wearing a mutation harness's clothes.
    """

    def fired(probe):
        rows = (probe.report or {}).get("checks") or []
        for row in rows:
            if row.get("check_id") == check_id:
                return (row.get("code") != EXIT_PASS,
                        "%s verdict=%s found=%s checked=%s"
                        % (check_id, row.get("verdict"), row.get("found"),
                           row.get("checked")))
        raise MutationError(
            "%s is not among the %d check row(s) this artifact's conformance.py "
            "reported (%s). The probe could not look, so it has no verdict to "
            "give -- naming it as an owning guard here would file an absence as "
            "a finding."
            % (check_id, len(rows),
               ", ".join(sorted(str(r.get("check_id")) for r in rows)) or "none"))

    return fired


GUARDS = {
    "verify:chain": Guard(
        "verify:chain", _verify_argv, _fired_verify_chain,
        "verify.py re-walks per-item records -> count(predicate) -> rendered"),
    "verify:token": Guard(
        "verify:token", _verify_argv, _fired_verify_token,
        "figures.json's gate_token against the gate that authorised them"),
    "render:check": Guard(
        "render:check", _render_argv, _fired_render_drift,
        "render.py in its default reporting mode byte-compares"),
    "derive:refuse": Guard(
        "derive:refuse", _derive_argv, _fired_derive_refusal,
        "derive.py refuses at AUTHORSHIP; it REWRITES figures.json on success"),
    "CHECK-01": Guard(
        "CHECK-01", _conformance_argv, _fired_check("CHECK-01"),
        "a figure that appears without its population"),
    "CHECK-03": Guard(
        "CHECK-03", _conformance_argv, _fired_check("CHECK-03"),
        "an unedited template copy must not pass"),
}

# Guards that WRITE into the artifact on success. Never in a default probe set:
# one of them would overwrite the mutant mid-run.
MUTATING_GUARDS = ("derive:refuse",)

DEFAULT_PROBES = tuple(g for g in GUARDS if g not in MUTATING_GUARDS)


# ---------------------------------------------------------------------------
# Operations -- bytes in, bytes out, and never a silent no-op
# ---------------------------------------------------------------------------


def _text(data, mutant):
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise MutationError(
            "%s: %s is not valid UTF-8, so a text operation cannot address it"
            % (mutant.get("id"), mutant.get("target")))


def _json_roundtrip(data, mutant):
    """Decode, and PROVE the serializer reproduces the file byte for byte.

    Without this the structural edit below could reformat the whole document and
    every byte difference afterwards would be unattributable -- a mutation whose
    effect cannot be isolated proves nothing about the guard it was meant to
    trip.
    """
    obj = json.loads(_text(data, mutant))
    rendered = (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode("ascii")
    if rendered != data:
        raise MutationError(
            "%s: %s is not canonkit-serialized (indent=2, sort_keys, trailing "
            "newline), so a structural edit would change bytes the mutation did "
            "not intend. Use a text operation for this target."
            % (mutant.get("id"), mutant.get("target")))
    return obj


def _dump_json(obj):
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode("ascii")


def _walk(obj, path, mutant):
    """Follow a key path, resolving a `*` element to the first key in sort order."""
    node = obj
    walked = []
    for key in path[:-1]:
        if key == "*":
            if not isinstance(node, dict) or not node:
                raise MutationError(
                    "%s: `*` at %r has no keys to resolve"
                    % (mutant.get("id"), walked))
            key = sorted(node)[0]
        if not isinstance(node, dict) or key not in node:
            raise MutationError(
                "%s: no %r under %r in %s"
                % (mutant.get("id"), key, walked, mutant.get("target")))
        walked.append(key)
        node = node[key]
    last = path[-1]
    if last == "*":
        if not isinstance(node, dict) or not node:
            raise MutationError("%s: `*` leaf has no keys" % mutant.get("id"))
        last = sorted(node)[0]
    return node, last, walked + [last]


def _op_replace_once(data, mutant):
    """Replace a declared literal, requiring EXACTLY one occurrence.

    an earlier plan's measured lesson: its first mutant swapped a pathspec that the
    invariant did not depend on, changed nothing, and PASSED. A mutation that
    does not occur is an error, never a survivor and never a kill.
    """
    needle = mutant["find"].encode("utf-8")
    replacement = mutant["replace"].encode("utf-8")
    count = data.count(needle)
    if count != 1:
        raise MutationError(
            "%s: `find` matched %d occurrence(s) of %r in %s; exactly 1 is "
            "required. %s"
            % (mutant.get("id"), count, mutant["find"], mutant.get("target"),
               "A mutation that changes nothing proves nothing about any guard."
               if count == 0 else
               "An ambiguous mutation cannot be attributed to one change."))
    return data.replace(needle, replacement)


def _op_flip_bool(data, mutant):
    """Flip one boolean field in a per-item record. a success criterion's headline change.

    The field defaults to the FIRST boolean in sort order rather than a
    hard-coded name, so the same entry addresses a real artifact whose predicate
    is called something else. Which field was flipped is returned to the caller
    through the mutant dict so the run can print it rather than imply it.
    """
    obj = _json_roundtrip(data, mutant)
    if not isinstance(obj, dict):
        raise MutationError("%s: %s is not a JSON object"
                            % (mutant.get("id"), mutant.get("target")))
    field = mutant.get("field")
    if not field:
        booleans = [key for key in sorted(obj) if isinstance(obj[key], bool)]
        if not booleans:
            raise MutationError(
                "%s: %s holds no boolean field to flip (keys: %s)"
                % (mutant.get("id"), mutant.get("target"), sorted(obj)))
        field = booleans[0]
    if field not in obj or not isinstance(obj[field], bool):
        raise MutationError("%s: %r is not a boolean in %s"
                            % (mutant.get("id"), field, mutant.get("target")))
    obj[field] = not obj[field]
    mutant["_resolved_field"] = field
    return _dump_json(obj)


def _op_drop_key(data, mutant):
    obj = _json_roundtrip(data, mutant)
    node, last, walked = _walk(obj, mutant["path"], mutant)
    if not isinstance(node, dict) or last not in node:
        raise MutationError("%s: nothing to drop at %r"
                            % (mutant.get("id"), walked))
    del node[last]
    mutant["_resolved_field"] = ".".join(walked)
    return _dump_json(obj)


def _op_mangle_string(data, mutant):
    """Change ONE character of a string value, preserving its length.

    Length-preserving on purpose: a truncated token and a wrong token are
    different claims, and only the second is the thing the guard exists to catch.
    """
    obj = _json_roundtrip(data, mutant)
    node, last, walked = _walk(obj, mutant["path"], mutant)
    value = node.get(last) if isinstance(node, dict) else None
    if not isinstance(value, str) or not value:
        raise MutationError("%s: %r is not a non-empty string in %s"
                            % (mutant.get("id"), walked, mutant.get("target")))
    first = value[0]
    node[last] = ("b" if first != "b" else "c") + value[1:]
    mutant["_resolved_field"] = ".".join(walked)
    return _dump_json(obj)


_HOLE_RE = re.compile(
    r"(<!--artifact:key:[A-Za-z0-9_.]+-->)([^<]+)(<!--/artifact:key-->)")


def _op_mangle_hole(data, mutant):
    """Alter a RENDERED figure in a document without touching figures.json.

    The hand edit render.py's byte-compare exists to catch. Length-preserving,
    and it refuses when no rendered hole exists -- on an unrendered document this
    mutation would silently do nothing and the guard would look falsifiable when
    it had not been exercised at all.
    """
    text = _text(data, mutant)
    wanted = mutant.get("key")
    match = None
    seen = []
    for candidate in _HOLE_RE.finditer(text):
        key = candidate.group(1)[len("<!--artifact:key:"):-len("-->")]
        seen.append(key)
        if wanted is None or key == wanted:
            match = candidate
            break
    if match is None:
        raise MutationError(
            "%s: %s carries no rendered hole%s, so there is no rendered figure "
            "to alter. Either render.py never ran or the document is not the one "
            "this mutant addresses. Holes present (%d): %s"
            % (mutant.get("id"), mutant.get("target"),
               " for key %r" % wanted if wanted else "",
               len(seen), sorted(set(seen)) or "none"))
    value = match.group(2)
    digits = [i for i, ch in enumerate(value) if ch.isdigit()]
    if not digits:
        raise MutationError("%s: the rendered hole %r holds no digit to alter"
                            % (mutant.get("id"), value))
    index = digits[0]
    replacement = "9" if value[index] != "9" else "8"
    altered = value[:index] + replacement + value[index + 1:]
    mutant["_resolved_field"] = "%s: %s -> %s" % (
        match.group(1)[len("<!--artifact:key:"):-len("-->")],
        value.strip(), altered.strip())
    return (text[:match.start(2)] + altered + text[match.end(2):]).encode("utf-8")


def _region_re(name):
    return re.compile(
        r"(<!--\s*artifact:%s:begin\s*-->\n)(.*?)(<!--\s*artifact:%s:end\s*-->)"
        % (re.escape(name), re.escape(name)), re.S)


def _op_replace_region(data, mutant):
    """Put a declared body back into a paired region -- the addressing mechanism.

    Keyed on the region anchor, never on heading text: CHECK-03 records that two
    artifacts shipped two DIFFERENT limitations headings, so a mutation keyed on
    either literal would address one artifact and miss the other.
    """
    text = _text(data, mutant)
    pattern = _region_re(mutant["region"])
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise MutationError(
            "%s: region %r matched %d time(s) in %s; exactly 1 is required"
            % (mutant.get("id"), mutant["region"], len(matches),
               mutant.get("target")))
    body = mutant["body"]
    match = matches[0]
    if match.group(2) == body:
        raise MutationError(
            "%s: region %r already holds the declared body, so this mutation "
            "would change nothing and prove nothing."
            % (mutant.get("id"), mutant["region"]))
    mutant["_resolved_field"] = "artifact:%s" % mutant["region"]
    return (text[:match.start(2)] + body + text[match.end(2):]).encode("utf-8")


OPERATIONS = {
    "replace_once": _op_replace_once,
    "flip_bool": _op_flip_bool,
    "drop_key": _op_drop_key,
    "mangle_string": _op_mangle_string,
    "mangle_rendered_hole": _op_mangle_hole,
    "replace_region_body": _op_replace_region,
}


def apply_operation(snap, mutant):
    """Return the MUTATED bytes. Pure: nothing is written here."""
    name = mutant.get("operation")
    if name not in OPERATIONS:
        raise MutationError(
            "%s: unknown operation %r. Known operations: %s"
            % (mutant.get("id"), name, sorted(OPERATIONS)))
    mutated = OPERATIONS[name](snap.data, mutant)
    if mutated == snap.data:
        raise MutationError(
            "%s: operation %r produced 0 occurrence(s) of change in %s. A "
            "mutant that changes nothing proves nothing about any guard."
            % (mutant.get("id"), name, mutant.get("target")))
    return mutated


# ---------------------------------------------------------------------------
# Target resolution
# ---------------------------------------------------------------------------


def resolve_target(tree, pattern):
    """Resolve a repo-relative pattern to ONE path, refusing zero matches.

    A glob keeps an entry portable across artifacts whose per-item record ids
    differ. The RESOLVED path is what the run prints -- a pattern is not a fact
    about any artifact, and zero matches is a DID-NOT-RUN rather than a pass.
    """
    parts = str(pattern).replace(chr(92), "/").split("/")
    current = [str(tree)]
    for part in parts:
        nxt = []
        for base in current:
            if not any(ch in part for ch in "*?["):
                nxt.append(os.path.join(base, part))
                continue
            if not os.path.isdir(base):
                continue
            nxt.extend(os.path.join(base, name)
                       for name in sorted(os.listdir(base))
                       if fnmatch.fnmatch(name, part))
        current = nxt
    existing = [path for path in current if os.path.exists(path)]
    if not existing:
        return os.path.join(str(tree), *parts)
    return sorted(existing)[0]


# ---------------------------------------------------------------------------
# One mutant, start to finish
# ---------------------------------------------------------------------------


class MutationResult(object):
    """Everything one mutant produced. Four outcomes, never one rate."""

    def __init__(self, mutant_id, target, owning_guard, probes, restored_sha256,
                 applied_bytes=0, resolved_field=""):
        self.mutant_id = mutant_id
        self.target = target
        self.owning_guard = list(owning_guard)
        self.probes = list(probes)
        self.restored_sha256 = restored_sha256
        self.applied_bytes = applied_bytes
        self.resolved_field = resolved_field

    @property
    def fired(self):
        return [p.guard_id for p in self.probes if p.outcome == "fired"]

    @property
    def errored(self):
        return [p.guard_id for p in self.probes if p.outcome == "errored"]

    @property
    def killed(self):
        return bool(self.fired)

    @property
    def attributed(self):
        """Every guard that fired is named, and at least one named guard fired.

        Both halves, because a design rule fails in BOTH directions. An extra guard
        firing is a finding about the CATALOGUE -- where guards legitimately
        overlap the entry names them all, which is a data change rather than a
        relaxed rule.
        """
        if not self.fired:
            return False
        return set(self.fired) <= set(self.owning_guard)

    @property
    def exit_of_owning(self):
        for probe in self.probes:
            if probe.outcome == "fired" and probe.guard_id in self.owning_guard:
                return probe.exit_code
        return None

    def verdict(self):
        if self.errored and not self.fired:
            return "ERRORED"
        if not self.killed:
            return "SURVIVED"
        if not self.attributed:
            return "MISATTRIBUTED"
        return "KILLED"


def mutate(tree, mutant, guards=None, stream=None, workdir=None):
    """Apply ONE mutant to a COMMITTED tree, run its probes, ALWAYS restore.

    The restore is in a `finally`, so a failure anywhere between the edit and the
    verdict still puts the snapshot bytes back and still verifies them. An
    interrupted mutation run that leaves a mutant on disk is how a mutant escapes
    into a commit.
    """
    stream = stream if stream is not None else sys.stdout
    guards = GUARDS if guards is None else guards
    tree = str(tree)
    mutant_id = mutant.get("id", "<unnamed>")

    assert_committed(tree)

    # REFUSE BEFORE YOU MEASURE. The entry is validated before a
    # single byte is read, so a malformed entry cannot leave a snapshot taken,
    # a file edited, or a probe half-run behind it.
    probe_ids = list(mutant.get("probes") or DEFAULT_PROBES)
    unknown = [g for g in probe_ids + list(mutant.get("owning_guard") or [])
               if g not in guards]
    if unknown:
        core.die(EXIT_DID_NOT_RUN,
                 "%s %s names unknown guard(s) %s. Known guards: %s\n"
                 "  REPAIR: name a guard that exists, or add it to GUARDS."
                 % (core.REFUSAL_PREFIX, mutant_id, sorted(set(unknown)),
                    sorted(guards)))
    unprobed = sorted(set(mutant.get("owning_guard") or []) - set(probe_ids))
    if unprobed:
        core.die(EXIT_DID_NOT_RUN,
                 "%s %s names owning guard(s) %s that are not in its probe set "
                 "%s. A guard that is never run cannot be shown to catch "
                 "anything.\n  REPAIR: add them to the entry's `probes`."
                 % (core.REFUSAL_PREFIX, mutant_id, unprobed, probe_ids))

    target = resolve_target(tree, mutant["target"])
    snap = snapshot(target)

    relative = os.path.relpath(target, tree).replace(chr(92), "/")
    stream.write("[mutate] %s target   %s\n" % (mutant_id, relative))
    stream.write("[mutate] %s sha256   %s (pre-mutation)\n"
                 % (mutant_id, snap.sha256))

    if workdir is None:
        workdir = tempfile.mkdtemp(prefix="cbb-mutate-")
    os.makedirs(workdir, exist_ok=True)

    probes = []
    try:
        mutated = apply_operation(snap, mutant)
        atomic_write_bytes(target, mutated)
        if mutant.get("_resolved_field"):
            stream.write("[mutate] %s changed  %s\n"
                         % (mutant_id, mutant["_resolved_field"]))

        # EVERY probe in the declared set runs. Stopping at the first firing
        # guard answers THAT something caught it and never WHICH.
        cache = {}
        for guard_id in probe_ids:
            guard = guards[guard_id]
            argv = guard.build(tree, workdir)
            key = tuple(str(token) for token in argv)
            if key in cache:
                base = cache[key]
                probe = Probe(guard_id, base.argv, base.exit_code, base.stdout,
                              base.stderr, base.report)
            else:
                probe = _run_probe(guard_id, argv, workdir)
                cache[key] = probe

            if probe.crashed():
                probe.outcome = "errored"
                probe.evidence = "crashed: %s" % _first_line(probe.stderr)
            else:
                try:
                    did_fire, evidence = guard.fired(probe)
                except MutationError as failure:
                    probe.outcome = "errored"
                    probe.evidence = str(failure)
                else:
                    probe.outcome = "fired" if did_fire else "silent"
                    probe.evidence = evidence

            probes.append(probe)
            stream.write("[mutate] %s command  %s\n" % (mutant_id, probe.command))
            stream.write("[mutate] %s exit     %d\n" % (mutant_id, probe.exit_code))
            stream.write("[mutate] %s guard    %s %s%s\n"
                         % (mutant_id, guard_id, probe.outcome.upper(),
                            (" -- " + probe.evidence) if probe.evidence else ""))
    finally:
        restored = restore(snap)

    result = MutationResult(mutant_id, relative,
                            mutant.get("owning_guard") or [], probes, restored,
                            len(snap.data), mutant.get("_resolved_field", ""))
    stream.write("[mutate] %s restored %s (verified)\n" % (mutant_id, restored))
    stream.write("[mutate] %s verdict  %s  probes=%d fired=%s expected=%s\n"
                 % (mutant_id, result.verdict(), len(probes),
                    result.fired or "none", result.owning_guard))
    return result


def _first_line(text):
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()[:200]
    return ""


# ---------------------------------------------------------------------------
# The catalogue
# ---------------------------------------------------------------------------


def load_catalogue(path=None):
    """Read tools/mutants.json. An EMPTY catalogue is a refusal, never a pass.

    A mutation suite over zero mutants is the 0/0 pass in its most flattering
    form: nothing fails, so everything looks proven.
    """
    path = str(path or os.path.join(_HERE, "mutants.json"))
    if not os.path.isfile(path):
        core.die(EXIT_DID_NOT_RUN,
                 "%s no catalogue at %s.\n"
                 "  REPAIR: pass --catalogue, or create the file."
                 % (core.REFUSAL_PREFIX, path))
    with open(path, "rb") as handle:
        record = json.loads(handle.read().decode("utf-8"))
    mutants = record.get("mutants") or []
    if not mutants:
        core.die(EXIT_DID_NOT_RUN,
                 "%s the catalogue at %s holds 0 mutants. A mutation run over "
                 "zero mutants is a DID-NOT-RUN, never a pass -- nothing fails, "
                 "so everything looks proven.\n"
                 "  REPAIR: add at least one entry, each naming the guard it "
                 "exists to trip."
                 % (core.REFUSAL_PREFIX, path))
    missing = [m.get("id", "<unnamed>") for m in mutants if not m.get("why")]
    if missing:
        core.die(EXIT_DID_NOT_RUN,
                 "%s %d catalogue entr(ies) carry no `why`: %s. An entry that "
                 "does not state the flattering error it closes is a mutation "
                 "nobody can evaluate.\n  REPAIR: write one."
                 % (core.REFUSAL_PREFIX, len(missing), missing))
    return record


class CampaignResult(object):
    """The four numbers. One rate cannot make an unrun probe visible."""

    def __init__(self, results):
        self.results = list(results)

    @property
    def attempted(self):
        return len(self.results)

    @property
    def killed(self):
        return [r for r in self.results if r.verdict() == "KILLED"]

    @property
    def survived(self):
        return [r for r in self.results if r.verdict() == "SURVIVED"]

    @property
    def misattributed(self):
        return [r for r in self.results if r.verdict() == "MISATTRIBUTED"]

    @property
    def errored(self):
        return [r for r in self.results if r.verdict() == "ERRORED"]

    @property
    def ok(self):
        return self.attempted > 0 and len(self.killed) == self.attempted


def run_catalogue(tree, catalogue, stream=None, only=None, guards=None,
                  workdir=None):
    """Run EVERY entry, then report. Never stop at the first survivor.

    A loop that stops at the first failure has learned about one mutant, not
    about the catalogue -- and "the catalogue is proven" is a claim about the
    whole set.
    """
    stream = stream if stream is not None else sys.stdout
    mutants = catalogue.get("mutants") or []
    if only:
        mutants = [m for m in mutants if m.get("id") in set(only)]
        if not mutants:
            core.die(EXIT_DID_NOT_RUN,
                     "%s --only %s matched 0 of %d catalogue entr(ies).\n"
                     "  REPAIR: name an id that exists."
                     % (core.REFUSAL_PREFIX, sorted(only),
                        len(catalogue.get("mutants") or [])))

    stream.write("[mutate] catalogue %d mutant(s) to attempt\n" % len(mutants))
    results = []
    for mutant in mutants:
        results.append(mutate(tree, dict(mutant), guards=guards, stream=stream,
                              workdir=workdir))
    return CampaignResult(results)


def print_campaign(campaign, stream):
    """Four numbers, printed separately, on every branch."""
    stream.write(
        "[mutate] attempted=%d killed=%d survived=%d misattributed=%d errored=%d\n"
        % (campaign.attempted, len(campaign.killed), len(campaign.survived),
           len(campaign.misattributed), len(campaign.errored)))
    for result in campaign.results:
        stream.write("  [%-13s] %-6s %-34s fired=%s expected=%s\n"
                     % (result.verdict(), result.mutant_id, result.target,
                        result.fired or "none", result.owning_guard))
    core.report("MUTATION", campaign.ok,
                campaign.attempted - len(campaign.killed),
                campaign.attempted, 1,
                note="killed %d of %d" % (len(campaign.killed),
                                          campaign.attempted))


def main(argv=None, stream=None):
    parser = argparse.ArgumentParser(
        description="Break the chain on purpose and name the guard that caught it.")
    parser.add_argument("--tree", required=True,
                        help="the artifact work tree to mutate (must be committed)")
    parser.add_argument("--catalogue", default=None)
    parser.add_argument("--only", action="append", default=None)
    parser.add_argument("--report", default=None)
    args = parser.parse_args(argv)
    stream = stream if stream is not None else sys.stdout

    catalogue = load_catalogue(args.catalogue)
    campaign = run_catalogue(args.tree, catalogue, stream=stream, only=args.only)
    print_campaign(campaign, stream)

    if args.report:
        core.atomic_write_json(args.report, {
            "schema": SCHEMA + "/report",
            "schema_version": core.SCHEMA_VERSION,
            "attempted": campaign.attempted,
            "killed": len(campaign.killed),
            "survived": len(campaign.survived),
            "misattributed": len(campaign.misattributed),
            "errored": len(campaign.errored),
            "mutants": [{
                "id": r.mutant_id,
                "target": r.target,
                "verdict": r.verdict(),
                "fired": r.fired,
                "owning_guard": r.owning_guard,
                "probes": [{"guard": p.guard_id, "exit": p.exit_code,
                            "outcome": p.outcome, "evidence": p.evidence}
                           for p in r.probes],
            } for r in campaign.results],
        })

    return EXIT_PASS if campaign.ok else EXIT_FINDING


if __name__ == "__main__":
    sys.exit(main())
