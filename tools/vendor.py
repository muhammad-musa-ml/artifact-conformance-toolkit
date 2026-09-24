"""Copy-and-assert vendoring, and `core current N of M`.

WHAT VENDORING IS HERE, AND WHAT IT IS NOT.
a design rule fixes the mechanism: COPY THE FILE AND ASSERT ITS sha256. No submodule, no
wheel, no package index. An artifact that needs a submodule fetch or an install
from a repository the reader does not have is a CLAIM again, not an artifact --
and an earlier round re-runs every one of them from a clean checkout.

WHY THIS MODULE LOADS THE FROZEN CORE BY PATH.
a design rule keeps the core OUT of the `tools` package. This module is repo-side
tooling, so it loads the core the same way an artifact's sibling import does:
by path, under a bare module name. It deliberately loads it under a name of its
own (`frozen_core`) rather than the core's artifact-side name, so that nothing
here can be mistaken for -- or later become -- a package import of it.

THREE COMPARISONS, KEPT DISTINCT, BECAUSE COLLAPSING THEM IS THE FAILURE.
`audit()` never asks one question where three are needed. A check that cannot
DISCRIMINATE between these is not a check:

    copy bytes  vs  the artifact's OWN recorded sha  -> MISMATCH = TAMPERING
    recorded sha vs this repository's CURRENT sha    -> STALE
    the recorded file present at all                 -> ABSENT

a design rule is pinned-at-build with drift REPORTED, not blocking: each artifact records
the core sha it was built against, and only a MISMATCH with its own record is
tampering. Always-current would turn every core edit into a re-vendor sweep over
up to fourteen artifacts and, for T2 figures, a re-verify costing real dollars
and GPU hours.

a design rule then says a stale core FAILS ITS OWN CHECK and the run CONTINUES, with the
artifact's overall exit non-zero. That is not in tension with a design rule once the two
checks are separate, which is the point of separating them: VENDOR-INTEGRITY
(tampering) PASSES on a stale-but-untouched copy -- staleness alone never reads
as tampering -- while VENDOR-CURRENT fails and is COUNTED. an earlier finding's stated goal is
that a stale core becomes a COUNT, never a surprise.

a design rule: the vendor record is written at the ARTIFACT ROOT, never under results/.
A checker output under results/ becomes an input to any hash over that tree and
shows up in git status, needing a permanent exclusion rule someone will forget.
"""

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VENDOR_RECORD_NAME = ".vendor.json"
VENDOR_SCHEMA = "canonkit/vendor/1"

# ---------------------------------------------------------------------------
# The declared vendored set
# ---------------------------------------------------------------------------
#
# Repo-relative SOURCE paths. The destination name inside an artifact is this
# path with its leading `tools/` removed, because an artifact has no `tools/`
# directory -- the core and the checker sit at its root, beside the scripts that
# import them.
#
# a design rule puts conformance.py in this list deliberately: a handed-over directory
# must SELF-CHECK with no access to this repository. Paired with a design rule, that is
# what makes the reader RE-RUN the checker rather than trust a stored verdict.
VENDORED_SET = (
    "tools/canonkit.py",         # the frozen core            (an earlier plan)
    "tools/conformance.py",      # the artifact's self-check  (an earlier plan)
    "tools/render.py",           # figure rendering           (an earlier plan)
    "tools/checks/__init__.py",  # the check-module contract  (an earlier plan)
    # THE CLAIM CORPUS, and it is DATA rather than code -- the only non-.py
    # member of this set. It ships because CHECK-09 resolves every bullet
    # reference against it, and without it that check REFUSED inside every
    # vendored artifact: a checker that cannot answer, shipped in each one,
    # reporting a refusal nobody reads as a defect (an earlier plan open item 8).
    #
    # It lands at the ARTIFACT ROOT, not under a tools/ subdirectory an artifact
    # does not have, because destination_name() strips the `tools/` prefix and
    # check_09.load_snapshot() reads CORE_ROOT/canon-bullets.json -- CORE_ROOT
    # being the directory ABOVE the checks package. The two agree by
    # construction; a test runs the vendored check to prove it rather than
    # reading this comment.
    "tools/canon-bullets.json",  # the claim corpus           (an earlier plan)
)

# THE COMMITTED LITERAL, asserted against the derivation at import time.
# This is a design rule's derive-and-assert shape applied to the vendored set. A purely
# derived count silently stops checking when a name is dropped, because expected
# falls to match found: an emptied tuple would make every derived count agree
# with zero and every audit pass over nothing. The shared pattern note records that the
# shipped provenance.py has the DERIVE half (`SOURCES` filtered by existence)
# and lacks exactly this assertion.
VENDORED_SET_COUNT = 5

if len(VENDORED_SET) != VENDORED_SET_COUNT:
    raise RuntimeError(
        "VENDORED_SET names %d path(s) but the committed literal "
        "VENDORED_SET_COUNT says %d. Update BOTH in the same commit."
        % (len(VENDORED_SET), VENDORED_SET_COUNT))

# The per-check modules arrive one plan at a time across an earlier plan .. an earlier plan, so their
# population is NOT knowable at declaration time and cannot carry a literal. They
# are enumerated and COUNTED SEPARATELY, and both numbers are printed -- a glob
# folded silently into a declared count is how a declared count stops meaning
# anything.
VENDORED_CHECK_GLOB_DIR = "tools/checks"
VENDORED_CHECK_PREFIX = "check_"

# CHECK MODULES THAT ARE DELIBERATELY NOT VENDORED, each with its reason.
#
# This is an EXCLUSION from a glob, so it is declared, counted and NAMED in the
# report rather than filtered silently -- an excluded input nobody counts is an
# input that was dropped.
#
# check_20.py is the only member and the reason is the framing rule, not
# convenience. It reads the owner's live collections entries: it knows where that
# private record lives, what its rows are keyed by and what its not-yet-measured
# disclosure says. A vendored artifact is a directory that may be handed to
# someone outside this programme, and shipping that module inside one would put
# the private record's shape into a repository whose whole point is that it can
# be read by a stranger.
#
# It is also not an ARTIFACT property. Every other check asks whether the
# directory it is pointed at is well formed. CHECK-20 asks whether the
# PROGRAMME corrected a claim, which is a question about two files that live
# nowhere near an artifact -- so a vendored copy could never answer it anyway,
# and would refuse on the marker definition it cannot reach.
NOT_VENDORED_CHECKS = {
    "check_20.py": (
        "CHECK-20 reads the live collections entries, so vendoring it would ship "
        "the shape of a private record inside a directory meant to be handed to "
        "a stranger -- and it asks a PROGRAMME question a vendored copy could "
        "not answer in any case."
    ),
}


def _repo_root(source_root=None):
    return os.path.abspath(str(source_root)) if source_root else REPO_ROOT


def load_core(source_root=None):
    """Load the frozen core BY PATH under a neutral module name.

    Never a package import: a design rule forbids it, tools/tests/test_repo_hygiene.py
    scans for it, and since an earlier plan the core itself raises on a dotted
    __name__.
    """
    path = os.path.join(_repo_root(source_root), "tools", "canonkit.py")
    spec = importlib.util.spec_from_file_location("frozen_core", path)
    if spec is None or spec.loader is None:
        raise ImportError("could not build an import spec for %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_modules(source_root=None):
    """Repo-relative paths of the per-check modules that are vendored right now.

    The declared exclusions are removed HERE and reported by
    `excluded_check_modules()`, so the two populations -- what ships and what
    deliberately does not -- are both derivable and neither is a silent filter.
    """
    return [relative for relative in _all_check_modules(source_root)
            if os.path.basename(relative) not in NOT_VENDORED_CHECKS]


def _all_check_modules(source_root=None):
    """Every per-check module on disk, before the declared exclusions."""
    root = _repo_root(source_root)
    directory = os.path.join(root, VENDORED_CHECK_GLOB_DIR)
    if not os.path.isdir(directory):
        return []
    return sorted(
        VENDORED_CHECK_GLOB_DIR + "/" + name
        for name in os.listdir(directory)
        if name.startswith(VENDORED_CHECK_PREFIX) and name.endswith(".py")
    )


def excluded_check_modules(source_root=None):
    """[(relative path, reason)] for every check module deliberately not vendored.

    Derived from what is ON DISK rather than from the declaration, so a reason
    left behind for a module that no longer exists cannot read as an exclusion
    that still happens.
    """
    return [(relative, NOT_VENDORED_CHECKS[os.path.basename(relative)])
            for relative in _all_check_modules(source_root)
            if os.path.basename(relative) in NOT_VENDORED_CHECKS]


def resolve_vendored_set(source_root=None):
    """The declared set plus the enumerated check modules, as repo-relative paths."""
    return list(VENDORED_SET) + check_modules(source_root)


def destination_name(source_relative):
    """`tools/checks/__init__.py` -> `checks/__init__.py`. An artifact has no tools/."""
    prefix = "tools/"
    return (source_relative[len(prefix):] if source_relative.startswith(prefix)
            else source_relative)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


@dataclass
class VendorReport:
    """What vendor_into() did, with every number it could report."""

    artifact_dir: str = ""
    copied: list = field(default_factory=list)
    missing_sources: list = field(default_factory=list)
    declared: int = 0
    files: dict = field(default_factory=dict)
    bundle_sha256: str = ""
    record_path: str = ""

    @property
    def count(self):
        return len(self.copied)


@dataclass
class FileVerdict:
    """One vendored file's three comparisons, kept apart."""

    name: str
    status: str                 # OK | MISMATCH | ABSENT | UNRECORDED
    stale: bool = False
    recorded_sha: str = ""
    actual_sha: str = ""
    repo_sha: str = ""


@dataclass
class ArtifactVerdict:
    artifact_dir: str = ""
    files: list = field(default_factory=list)
    integrity_code: int = 0
    current_code: int = 0
    error: str = ""
    # THE OTHER HALF OF THE GLOB, read from the ARTIFACT'S OWN RECORD rather
    # than from this repository's current tree. `files` is what shipped;
    # `excluded` is what deliberately did not, and an audit that prints the
    # first without the second reports `checked=14 of 14` over a population it
    # silently narrowed by one. An excluded input nobody counts is an input
    # that was dropped -- and this module's own docstring promises the record
    # answers "is a check missing here because it was excluded, or because the
    # vendoring broke?", which only holds if the audit reads it out.
    #
    # Derived from the record, not from `excluded_check_modules()`, because the
    # question an audit answers is about THIS artifact as it was built. A
    # repository that later drops or adds an exclusion must not silently
    # rewrite what an already-vendored copy is understood to contain.
    excluded: list = field(default_factory=list)

    @property
    def tampered(self):
        return [f for f in self.files if f.status in ("MISMATCH", "UNRECORDED")]

    @property
    def absent(self):
        return [f for f in self.files if f.status == "ABSENT"]

    @property
    def stale(self):
        return [f for f in self.files if f.stale]

    @property
    def current(self):
        return (not self.stale and not self.tampered and not self.absent
                and not self.error and bool(self.files))


@dataclass
class AuditReport:
    audited: int = 0
    current: int = 0
    artifacts: list = field(default_factory=list)
    code: int = 0

    @property
    def summary(self):
        return "core current %d of %d" % (self.current, self.audited)


# ---------------------------------------------------------------------------
# vendor_into
# ---------------------------------------------------------------------------


def _read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def _write_bytes(path, payload):
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(payload)


def _source_head(source_root):
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=source_root, capture_output=True,
        text=True, encoding="utf-8", errors="replace", shell=False)
    return completed.stdout.strip() if completed.returncode == 0 else None


def bundle_sha256(core, files):
    """sha256 over the sorted `name sha` list. One number for the whole set."""
    payload = "\n".join("%s %s" % (name, files[name]) for name in sorted(files))
    return core.sha256_bytes(payload.encode("ascii"))


def vendor_into(artifact_dir, source_root=None, core=None):
    """Copy the vendored set into `artifact_dir` and write its vendor record.

    THE COPY IS BY BYTES, NEVER TEXT MODE. A text-mode read/write round trip
    re-translates line endings on Windows and reproduces the measured arm-A
    failure: byte-identical content hashing two ways, so a project requirement's assertion
    fails for a reason unrelated to the core's content and the artifact looks
    tampered with when it is not.

    A declared file absent from the SOURCE repository is recorded in
    `missing_sources` rather than raising: conformance.py and render.py arrive
    in later plans, and an audit compares an artifact against its OWN record,
    so a file that was never vendored is not a missing one.

    Raises:
        RuntimeError: when zero files would be copied. Vendoring over an empty
            set writes a record asserting nothing, and every later audit of that
            artifact would then pass over zero files -- the 0/0 pass, arriving
            at build time instead of at check time.
    """
    core = core or load_core(source_root)
    root = _repo_root(source_root)
    artifact_dir = os.path.abspath(str(artifact_dir))

    report = VendorReport(artifact_dir=artifact_dir)
    declared = resolve_vendored_set(source_root)
    report.declared = len(declared)
    excluded = excluded_check_modules(source_root)

    for relative in declared:
        source = os.path.join(root, relative.replace("/", os.sep))
        if not os.path.isfile(source):
            report.missing_sources.append(relative)
            continue
        name = destination_name(relative)
        target = os.path.join(artifact_dir, name.replace("/", os.sep))
        payload = _read_bytes(source)
        _write_bytes(target, payload)
        digest = core.sha256_bytes(payload)
        report.files[name] = digest
        report.copied.append(name)

        landed = core.sha256_file(target)
        if landed != digest:
            raise RuntimeError(
                "the copy of %s landed with sha256 %s but its source hashes %s. "
                "A byte copy that changes the bytes is the CRLF failure a design rule and "
                "atomic_write_text's newline=\"\" both exist to prevent."
                % (name, landed, digest))

    if not report.copied:
        raise RuntimeError(
            "REFUSING: vendoring into %s would copy 0 of %d declared file(s). A "
            "record over an empty set asserts nothing, and every later audit of "
            "this artifact would pass over zero files."
            % (artifact_dir, report.declared))

    report.bundle_sha256 = bundle_sha256(core, report.files)
    record = {
        "schema": VENDOR_SCHEMA,
        "schema_version": core.SCHEMA_VERSION,
        "vendored_at": core.now_local(),
        "vendored_at_utc": core.now_utc(),
        "source_repo_head": _source_head(root),
        "declared": declared,
        "declared_count": report.declared,
        "declared_static_count": VENDORED_SET_COUNT,
        # The other side of the glob: what deliberately did NOT ship, with the
        # reason, so an artifact's own record answers "is a check missing here
        # because it was excluded, or because the vendoring broke?"
        "excluded_checks": [
            {"source": relative, "reason": reason} for relative, reason in excluded
        ],
        "excluded_check_count": len(excluded),
        "files": report.files,
        "missing_sources": report.missing_sources,
        "bundle_sha256": report.bundle_sha256,
    }
    report.record_path = os.path.join(artifact_dir, VENDOR_RECORD_NAME)
    core.atomic_write_json(report.record_path, record)
    return report


def read_vendor_record(artifact_dir):
    path = os.path.join(str(artifact_dir), VENDOR_RECORD_NAME)
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as handle:
        return json.loads(handle.read().decode("ascii"))


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------


def _repo_shas(core, source_root=None):
    root = _repo_root(source_root)
    shas = {}
    for relative in resolve_vendored_set(source_root):
        path = os.path.join(root, relative.replace("/", os.sep))
        if os.path.isfile(path):
            shas[destination_name(relative)] = core.sha256_file(path)
    return shas


def audit_one(artifact_dir, core, repo_shas):
    """Audit ONE artifact. Three comparisons, never collapsed into one."""
    verdict = ArtifactVerdict(artifact_dir=os.path.abspath(str(artifact_dir)))
    record = read_vendor_record(artifact_dir)
    if record is None:
        verdict.error = ("no %s at the artifact root -- nothing was ever vendored "
                         "here, or the record was removed" % VENDOR_RECORD_NAME)
        verdict.integrity_code = core.EXIT_DID_NOT_RUN
        verdict.current_code = core.EXIT_DID_NOT_RUN
        return verdict

    for entry in record.get("excluded_checks") or []:
        if isinstance(entry, dict):
            verdict.excluded.append((str(entry.get("source", "?")),
                                     str(entry.get("reason", ""))))

    recorded = record.get("files") or {}
    for name in sorted(recorded):
        path = os.path.join(str(artifact_dir), name.replace("/", os.sep))
        recorded_sha = recorded[name]
        repo_sha = repo_shas.get(name, "")
        if not os.path.isfile(path):
            verdict.files.append(FileVerdict(name, "ABSENT",
                                             recorded_sha=recorded_sha,
                                             repo_sha=repo_sha))
            continue
        actual = core.sha256_file(path)

        # COMPARISON 1 -- the copy against the artifact's OWN record. This and
        # only this is TAMPERING. It is deliberately blind to what this
        # repository currently holds, so a correctly pinned artifact never
        # reads as tampered with merely because the repository moved on.
        status = "OK" if actual == recorded_sha else "MISMATCH"

        # COMPARISON 2 -- the artifact's RECORD against this repository's
        # current sha. This is DRIFT. It is counted and it fails VENDOR-CURRENT
        #, and it never contributes to comparison 1: `stale` is a
        # separate field precisely so no caller can read one as the other. An
        # unknown repo_sha (the file is not in this repository at all) is not
        # drift -- there is nothing to be behind.
        stale = bool(repo_sha) and recorded_sha != repo_sha

        verdict.files.append(FileVerdict(name, status, stale=stale,
                                         recorded_sha=recorded_sha,
                                         actual_sha=actual, repo_sha=repo_sha))

    for name in sorted(repo_shas):
        path = os.path.join(str(artifact_dir), name.replace("/", os.sep))
        if name not in recorded and os.path.isfile(path):
            verdict.files.append(FileVerdict(
                name, "UNRECORDED", actual_sha=core.sha256_file(path),
                repo_sha=repo_shas[name]))

    tampered = verdict.tampered + verdict.absent
    checked = len(verdict.files)
    verdict.integrity_code = (
        core.EXIT_DID_NOT_RUN if checked == 0
        else (core.EXIT_FINDING if tampered else core.EXIT_PASS))
    verdict.current_code = (
        core.EXIT_DID_NOT_RUN if checked == 0
        else (core.EXIT_FINDING if verdict.stale else core.EXIT_PASS))
    return verdict


def audit(artifact_dirs, source_root=None, core=None, verbose=True):
    """Audit every artifact and print `core current N of M` with both numbers.

    An audit over ZERO artifacts is a DID-NOT-RUN with code 2. It is never
    reported as `core current 0 of 0` and a pass: a scan that enumerated nothing
    and a scan that found everything current render almost identically, and only
    one of them is evidence.
    """
    core = core or load_core(source_root)
    dirs = [str(d) for d in artifact_dirs]
    report = AuditReport(audited=len(dirs))
    repo_shas = _repo_shas(core, source_root)

    if not dirs:
        if verbose:
            core.report("VENDOR-AUDIT", False, 0, 0, 1,
                        note="no artifact directories were enumerated")
        report.code = core.EXIT_DID_NOT_RUN
        return report

    codes = []
    for artifact_dir in dirs:
        verdict = audit_one(artifact_dir, core, repo_shas)
        report.artifacts.append(verdict)
        codes.extend([verdict.integrity_code, verdict.current_code])
        if verdict.current:
            report.current += 1

        if verbose:
            label = os.path.basename(os.path.normpath(artifact_dir))
            if verdict.error:
                core.report("VENDOR-INTEGRITY", False, 0, 0, 1,
                            note="%s: %s" % (label, verdict.error))
                core.report("VENDOR-CURRENT", False, 0, 0, 1,
                            note="%s: %s" % (label, verdict.error))
            else:
                checked = len(verdict.files)
                broken = verdict.tampered + verdict.absent
                # EACH LINE PRINTS ITS OWN VOCABULARY. The integrity line names
                # the file's STATUS and the currency line says STALE, because a
                # file can be both and a shared formatter printed "STALE" beside
                # a MISMATCH -- re-conflating, in the report, the two things the
                # whole module exists to keep apart.
                core.report("VENDOR-INTEGRITY", not broken, len(broken), checked,
                            1, note="%s: %s" % (label, _status_detail(broken)
                                                or "clean"))
                core.report("VENDOR-CURRENT", not verdict.stale,
                            len(verdict.stale), checked, 1,
                            note="%s: %s" % (label, _stale_detail(verdict.stale)
                                             or "on this repository's current core"))
                _print_exclusions(label, verdict)

    report.code = core.aggregate(codes)
    if verbose:
        print(report.summary)
        print(core.summary_line(core.count_codes(codes)))
    return report


def _status_detail(verdicts):
    """For the INTEGRITY line: name each file's own status, never its currency."""
    return ", ".join("%s %s" % (v.name, v.status) for v in verdicts)


def _stale_detail(verdicts):
    """For the CURRENCY line: these are stale by construction."""
    return ", ".join("%s STALE" % v.name for v in verdicts)


def _print_exclusions(label, verdict):
    """Count and NAME what deliberately did not ship, beside what did.

    Deliberately NOT a `core.report()` verdict line and deliberately NOT part of
    the aggregate. There is nothing here to pass or fail: an exclusion is a
    DECLARATION, and turning it into a fourth verdict would either invent a
    finding out of a decision already made or add a PASS that inflates the
    counts line without measuring anything. What the convention requires of a
    population is that every input NOT examined is counted and given a reason
    beside it, and that is what this prints.

    The count is printed on BOTH branches, including zero, because an audit
    that says nothing about exclusions and one over an artifact that declares
    none render identically otherwise -- and only one of those is a
    measurement.
    """
    if not verdict.excluded:
        print("vendor-exclusions %s: not-vendored=0 -- the record declares none"
              % label)
        return
    print("vendor-exclusions %s: not-vendored=%d, each NAMED with its reason"
          % (label, len(verdict.excluded)))
    for source, reason in verdict.excluded:
        print("  not-vendored  %s" % source)
        if reason:
            print("     reason: %s" % reason)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None):
    """Exit 0 clean, 1 a finding, 2 could not look, 3 a guard failure.

    Output is written to a file with --report rather than piped, because a
    command piped into tail returns the PIPE's status and a failing run then
    reports EXIT=0.
    """
    parser = argparse.ArgumentParser(prog="vendor", description=__doc__.split("\n")[0])
    parser.add_argument("action", choices=("vendor", "audit"))
    parser.add_argument("artifacts", nargs="*")
    parser.add_argument("--source-root", default=None)
    parser.add_argument("--report", default=None)
    args = parser.parse_args(argv)

    core = load_core(args.source_root)

    if args.action == "vendor":
        if not args.artifacts:
            core.die(core.EXIT_DID_NOT_RUN,
                     "%s vendor was given 0 artifact directories.\n"
                     "  REPAIR: name at least one, e.g. `vendor <home>/Research/<slug>`."
                     % core.REFUSAL_PREFIX)
        payload = []
        for artifact in args.artifacts:
            report = vendor_into(artifact, args.source_root, core)
            core.report("VENDOR-COPY", True, 0, report.count, 1,
                        not_examined=len(report.missing_sources),
                        listed=report.declared,
                        note="%s bundle=%s" % (report.artifact_dir,
                                               report.bundle_sha256[:12]))
            payload.append({"artifact": report.artifact_dir,
                            "copied": report.copied,
                            "missing_sources": report.missing_sources,
                            "bundle_sha256": report.bundle_sha256})
        if args.report:
            core.atomic_write_json(args.report, {
                "schema": VENDOR_SCHEMA, "schema_version": core.SCHEMA_VERSION,
                "action": "vendor", "results": payload})
        return core.EXIT_PASS

    report = audit(args.artifacts, args.source_root, core)
    if args.report:
        core.atomic_write_json(args.report, {
            "schema": VENDOR_SCHEMA,
            "schema_version": core.SCHEMA_VERSION,
            "action": "audit",
            "audited": report.audited,
            "current": report.current,
            "code": report.code,
            "artifacts": [
                {"artifact": v.artifact_dir, "error": v.error,
                 "integrity_code": v.integrity_code,
                 "current_code": v.current_code,
                 # Both halves of the glob, so a machine consumer can close the
                 # same identity a reader closes from the printed lines: what
                 # shipped, plus what deliberately did not, with its reason.
                 "excluded": [{"source": source, "reason": reason}
                              for source, reason in v.excluded],
                 "excluded_count": len(v.excluded),
                 "files": [{"name": f.name, "status": f.status, "stale": f.stale,
                            "recorded_sha": f.recorded_sha,
                            "actual_sha": f.actual_sha, "repo_sha": f.repo_sha}
                           for f in v.files]}
                for v in report.artifacts],
        })
    return report.code


if __name__ == "__main__":
    sys.exit(main())
