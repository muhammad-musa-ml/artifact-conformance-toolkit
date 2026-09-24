"""Generate an artifact directory: a git work tree carrying the whole kit.

    python -m tools.new_artifact <slug> --into <parent-directory>

THE ORDER OF OPERATIONS IS THE WHOLE POINT OF THIS MODULE, so it is stated here,
restated beside the code that performs it, and asserted from git afterwards:

    1. REFUSE, before anything is written. The slug shape, the destination, the
       case-collision check and the path-length ceiling are all decided while
       the destination is still untouched, so a refusal leaves NOTHING behind.
    2. git init.
    3. Write `.gitattributes` and commit it ALONE, as the root commit.
    4. git config core.longpaths true, in the NEW repository.
    5. Copy the rest of the kit.
    6. Vendor the frozen core.
    7. Commit everything else.
    8. Print the report, with every number it can report.

WHY STEP 3 IS NOT MERGED INTO STEP 7, even though the same files end up tracked
either way. Git applies `.gitattributes` when a blob ENTERS the index. A file
committed before the end-of-line rule is in force keeps whatever line endings it
was written with, permanently, until someone renormalizes. Since the frozen core
is authored in one repository and hashed in this one, that difference makes a
digest fail to reproduce after a clone for a reason having nothing to do with
the file's content -- and the artifact then looks tampered with when it is not.
Committing everything in one go would reproduce that exact defect inside the
artifact built to demonstrate the fix. The generator asserts afterwards, from
`git log --diff-filter=A` and `git show --name-only`, that the root commit
touched exactly one path.

WHY GIT FACTS COME FROM GIT. "the file exists" and "git tracks the file" are
different claims and only the second survives a clean checkout, which is the
claim the artifact contract actually makes. Every git fact below is read with
`git rev-parse`, `git ls-files`, `git log` or `git show` through subprocess, and
never inferred from the filesystem.

WHY THE RUN-CHAIN FILES ARE COPIED BY BYTES WITH NO SUBSTITUTION. They are
executable Python. Running a name substitution across a source file is how a
generator silently corrupts one, and the corruption would be discovered at
measurement time rather than here. Only the two prose skeletons are substituted;
everything else is a byte copy, and the four run-chain members are additionally
sha256-compared against their source after landing.

WHAT THIS DELIBERATELY DOES NOT DO. It does not substitute a figure or a date.
Those belong to a machine-emitted results record and are written into the
README's regions by the renderer. A generator that stamped today's date into a
README would defeat the check that compares that date against a measurement's
recorded start time -- the two would agree by construction and the check would
be unable to fail.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

from tools import vendor

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Verified NOT set on this machine, so it is set per generated repository rather
# than assumed. The ceiling below is the artifact gate's own limit, repeated
# here because a tree that cannot be checked out is a refusal at GENERATION
# time, not a discovery three plans later.
MAX_PATH_CHARS = 240

# Lowercase, starts alphanumeric, hyphens only. No underscore and no uppercase:
# the artifact directory name becomes a path on a case-insensitive filesystem
# here and a case-sensitive one inside a Linux container, and a slug that
# differs only by case between two references is indistinguishable from a typo.
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# a project requirement's nine names. Transcribed from the requirement, never globbed from the
# template directory: a globbed expectation deletes itself in the same motion
# that deletes the file, so it can never report a missing one.
TOOL_04_REQUIRED = (
    "README.md",
    "LICENSE",
    ".gitattributes",
    "requirements.txt",
    "gate.py",
    "verify.py",
    "provenance.py",
    "finalize.py",
    "docker-compose.yml",
)
TOOL_04_REQUIRED_COUNT = 9

if len(TOOL_04_REQUIRED) != TOOL_04_REQUIRED_COUNT:
    raise RuntimeError(
        "TOOL_04_REQUIRED names %d file(s) but the committed literal says %d. "
        "Update BOTH in the same commit."
        % (len(TOOL_04_REQUIRED), TOOL_04_REQUIRED_COUNT))

# The four that arrive from the run-chain plan, sha256-compared after the copy.
RUN_CHAIN_MEMBERS = ("gate.py", "verify.py", "provenance.py", "finalize.py")

# The files whose text is substituted AND whose destination differs from their
# template name. Everything else is a byte copy landing at the artifact root.
#
# The third member arrived with CHECK-16. It carries one substitution, the slug,
# and NO DATE -- `reviewed_on` ships EMPTY on purpose, which is what makes an
# unedited copy a finding rather than a pass. The docstring on substitutions()
# states the general rule this follows: a date stamped in at generation time
# would agree with everything by construction, leaving the check that reads it
# unable to fail.
SUBSTITUTED = {
    "README-SKELETON.md": "README.md",
    "RESULTS-SKELETON.md": "results/RESULTS.md",
    "RETRACTIONS-SKELETON.json": "results/retractions.json",
}

FIRST_COMMIT_PATH = ".gitattributes"

# Never copied into an artifact: caches and the tooling repository's own noise.
KIT_EXCLUDED_DIRS = ("__pycache__", ".pytest_cache", ".git")


class Refusal(Exception):
    """A precondition makes generating unsafe or meaningless. Nothing was written.

    Distinct from a failure on purpose. A refusal means the generator COULD NOT
    LOOK; it never means it looked and found a problem. Callers map this to the
    did-not-run exit code so the two stay distinguishable in a script.
    """


@dataclass
class GenerateReport:
    """Everything the run can report, with the counts kept SEPARATE.

    `files_written` and `files_tracked` answer different questions and are
    allowed to disagree: the artifact's own .gitignore excludes some paths on
    purpose. Collapsing them into one number would hide exactly the case worth
    seeing -- a file written but never tracked, which a clean checkout would not
    have at all.
    """

    slug: str = ""
    artifact_dir: str = ""
    kit_source: str = ""
    files_written: int = 0
    files_tracked: int = 0
    longest_path: int = 0
    vendored_count: int = 0
    vendor_missing: list = field(default_factory=list)
    first_commit: str = ""
    second_commit: str = ""
    written: list = field(default_factory=list)
    tracked: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pure predicates. Separated from the side effects so they can be tested on
# inputs this filesystem cannot hold -- which is the only way two of them can be
# exercised at all.
# ---------------------------------------------------------------------------


def case_only_collisions(paths):
    """Pairs of paths that differ ONLY by case, as sorted groups.

    NTFS will not hold `results/x` and `Results/x` at once, so this condition
    cannot be reproduced on the machine that must catch it. It arrives from a
    tree checked out on a case-sensitive filesystem and copied here, where the
    two silently merge into one and a file is lost without an error. Running the
    check over the prospective path LIST rather than over the filesystem is what
    lets it fire at all.
    """
    buckets = {}
    for path in paths:
        buckets.setdefault(path.lower(), []).append(path)
    return sorted(sorted(group) for group in buckets.values() if len(group) > 1)


def longest_path_length(paths):
    """The longest ABSOLUTE path length, or 0 for an empty list.

    ABSOLUTE, because the limit this feeds is a limit on absolute paths.
    Measuring the relative form under-reports by the whole length of the leading
    directories -- it would report a comfortable number for a tree whose real
    paths sit at the ceiling, which is to say it could not detect the condition
    it exists to detect.
    """
    return max((len(str(path)) for path in paths), default=0)


def kit_files(templates_root):
    """(absolute source, artifact-relative destination) for every kit file.

    Sorted, so the written order is stable and two runs produce the same report.
    """
    templates_root = os.path.abspath(str(templates_root))
    found = []
    for base, dirnames, filenames in os.walk(templates_root):
        dirnames[:] = [d for d in dirnames if d not in KIT_EXCLUDED_DIRS]
        for name in filenames:
            source = os.path.join(base, name)
            relative = os.path.relpath(source, templates_root)
            relative = relative.replace(chr(92), "/")
            destination = SUBSTITUTED.get(relative, relative)
            found.append((source, destination))
    return sorted(found, key=lambda pair: pair[1])


def substitutions(slug, canon=None, project=None, bullets=None, gpu_required=False,
                  organization=None, role=None, engagement_dates=None,
                  collections_entry=None):
    """The NAME-ONLY substitution table.

    No figure and no date appears here, and none may be added. A date stamped in
    at generation time would agree with a measurement's recorded start time by
    construction, leaving the check that compares them unable to fail.
    (`{{figures.dated_at}}` in the reproduction paragraph is a RENDERED figure
    reference, written by `render.py` from `figures.json` -- not a substitution,
    and that distinction is a design rule.)

    `project` is the EXAMPLE PROJECT id (`P1`, `BP-2`). The token keeps its name so
    artifacts generated before the 2026-09-16 relabel still substitute; the
    skeleton's LABEL is `Example project`, because this work is never presented as a
    personal project.
    """
    return {
        "{{artifact.slug}}": slug,
        "{{artifact.title}}": slug,
        "{{artifact.canon}}": canon or "TODO: name the canon this artifact backs",
        "{{artifact.project}}": project or "TODO: name the example project (P1, BP-2)",
        "{{artifact.bullet_ids}}": (", ".join(bullets) if bullets
                                    else "TODO: name the bullet id"),
        "{{artifact.gpu_required}}": "yes" if gpu_required else "no",
        "{{artifact.organization}}": organization or "TODO: name the organization",
        "{{artifact.role}}": role or "TODO: name the role, e.g. Example Role One",
        "{{artifact.engagement_dates}}": (
            engagement_dates or "TODO: the engagement window, e.g. Month YYYY - Month YYYY"),
        "{{artifact.collections_entry}}": (
            collections_entry
            or "TODO: collections/everything-<field>/<slug>/raw.json"),
    }


def apply_substitutions(text, table):
    for needle, value in table.items():
        text = text.replace(needle, value)
    return text


# ---------------------------------------------------------------------------
# git, through subprocess, always
# ---------------------------------------------------------------------------


def _git(args, cwd, identity=None, check=True):
    argv = ["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath="]
    if identity:
        argv += ["-c", "user.name=%s" % identity[0],
                 "-c", "user.email=%s" % identity[1]]
    argv += list(args)
    completed = subprocess.run(
        argv, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
        errors="replace", shell=False)
    if check and completed.returncode != 0:
        raise Refusal(
            "git %s failed in %s (exit %d): %s"
            % (" ".join(args), cwd, completed.returncode,
               (completed.stderr or completed.stdout).strip()))
    return completed.stdout


def _read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def _write_bytes(path, payload):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    # newline translation is impossible in binary mode, which is the point: a
    # text-mode round trip re-translates line endings on Windows and reproduces
    # the measured failure this whole ordering exists to prevent.
    with open(path, "wb") as handle:
        handle.write(payload)


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


def generate(slug, dest_root, *, canon=None, project=None, bullets=None,
             gpu_required=False, source_root=None, identity=None, stream=None,
             organization=None, role=None, engagement_dates=None,
             collections_entry=None):
    """Create `<dest_root>/<slug>` as a git work tree carrying the whole kit.

    Raises:
        Refusal: on any precondition failure. Nothing has been written when it
            is raised from the refusal block, which is the first thing that runs.
    """
    stream = stream or sys.stdout
    root = os.path.abspath(str(source_root)) if source_root else REPO_ROOT
    templates_root = os.path.join(root, "templates")
    core = vendor.load_core(root)

    # -- 1. REFUSE FIRST -----------------------------------------------------
    if not isinstance(slug, str) or not SLUG_RE.match(slug):
        raise Refusal(
            "slug %r does not match %s. Use lowercase letters, digits and "
            "hyphens, starting with a letter or digit."
            % (slug, SLUG_RE.pattern))

    if not os.path.isdir(templates_root):
        raise Refusal(
            "no kit at %s. Run this from the tooling repository, or pass "
            "source_root=<repo>." % templates_root)

    artifact_dir = os.path.abspath(os.path.join(str(dest_root), slug))
    if os.path.exists(artifact_dir) and os.listdir(artifact_dir):
        raise Refusal(
            "%s already exists and is not empty. Generating into it would mix a "
            "new kit with whatever is there. Move or delete it first, or choose "
            "another slug: rmdir /s %s" % (artifact_dir, artifact_dir))

    kit = kit_files(templates_root)
    if not kit:
        raise Refusal(
            "the kit at %s holds zero files. Generating from an empty kit would "
            "produce an artifact that passes every later check over nothing."
            % templates_root)

    destinations = [destination for _, destination in kit]
    prospective = [os.path.join(artifact_dir, destination.replace("/", os.sep))
                   for destination in destinations]
    longest = longest_path_length(prospective)

    # PRINTED WHETHER OR NOT IT REFUSES. A ceiling reported only on failure
    # tells a reader nothing about how close a passing tree came to it.
    print("longest path = %d character(s), limit %d"
          % (longest, MAX_PATH_CHARS), file=stream)

    if longest >= MAX_PATH_CHARS:
        raise Refusal(
            "the longest path this would create is %d character(s), at or over "
            "the %d limit. Generate into a shorter parent directory."
            % (longest, MAX_PATH_CHARS))

    collisions = case_only_collisions(destinations)
    if collisions:
        raise Refusal(
            "the kit holds %d path group(s) differing only by case, which merge "
            "into one file here and stay separate in a Linux container: %s"
            % (len(collisions), collisions))

    report = GenerateReport(slug=slug, artifact_dir=artifact_dir,
                            kit_source=templates_root, longest_path=longest)

    # -- 2. git init ---------------------------------------------------------
    os.makedirs(artifact_dir, exist_ok=True)
    _git(["init", "-q", "-b", "main"], artifact_dir, identity)

    # -- 3. .gitattributes, COMMITTED ALONE, as the root commit --------------
    attributes_source = os.path.join(templates_root, FIRST_COMMIT_PATH)
    if not os.path.isfile(attributes_source):
        raise Refusal(
            "the kit has no %s, so the end-of-line rule could not be put in "
            "force before anything is hashed." % FIRST_COMMIT_PATH)
    _write_bytes(os.path.join(artifact_dir, FIRST_COMMIT_PATH),
                 _read_bytes(attributes_source))
    report.written.append(FIRST_COMMIT_PATH)
    _git(["add", "--", FIRST_COMMIT_PATH], artifact_dir, identity)
    _git(["commit", "-q", "-m",
          "chore: .gitattributes before anything is hashed"],
         artifact_dir, identity)

    # ASSERTED FROM HISTORY, not from the fact that the file is now present.
    added_in = _git(["log", "--diff-filter=A", "--format=%H", "--reverse", "--",
                     FIRST_COMMIT_PATH], artifact_dir, identity).split()
    if not added_in:
        raise Refusal("%s was written but never added in any commit"
                      % FIRST_COMMIT_PATH)
    report.first_commit = added_in[0]
    touched = _git(["show", "--pretty=format:", "--name-only",
                    report.first_commit], artifact_dir, identity).split()
    if touched != [FIRST_COMMIT_PATH]:
        raise Refusal(
            "the root commit touched %d path(s) rather than exactly %s: %s"
            % (len(touched), FIRST_COMMIT_PATH, touched))

    # -- 4. core.longpaths, in the NEW repository ----------------------------
    _git(["config", "core.longpaths", "true"], artifact_dir, identity)

    # -- 5. the rest of the kit ---------------------------------------------
    table = substitutions(slug, canon, project, bullets, gpu_required,
                          organization=organization, role=role,
                          engagement_dates=engagement_dates,
                          collections_entry=collections_entry)
    for source, destination in kit:
        if destination == FIRST_COMMIT_PATH:
            continue
        target = os.path.join(artifact_dir, destination.replace("/", os.sep))
        relative = os.path.relpath(source, templates_root).replace(chr(92), "/")
        if relative in SUBSTITUTED:
            text = _read_bytes(source).decode("ascii")
            payload = apply_substitutions(text, table).encode("ascii")
        else:
            payload = _read_bytes(source)
        _write_bytes(target, payload)
        report.written.append(destination)

    # The four run-chain members are byte-compared AFTER landing, so a partial
    # copy is a failure here rather than a smaller file discovered later.
    for name in RUN_CHAIN_MEMBERS:
        source = os.path.join(templates_root, name)
        landed = os.path.join(artifact_dir, name)
        if not os.path.isfile(source):
            continue
        if core.sha256_file(source) != core.sha256_file(landed):
            raise Refusal(
                "%s landed with a different sha256 than its source. A byte copy "
                "that changes the bytes is the end-of-line failure this ordering "
                "exists to prevent." % name)

    # -- 6. vendor the frozen core ------------------------------------------
    vendor_report = vendor.vendor_into(artifact_dir, source_root=root, core=core)
    report.vendored_count = len(vendor_report.copied)
    report.vendor_missing = list(vendor_report.missing_sources)
    report.written.extend(vendor_report.copied)
    report.written.append(vendor.VENDOR_RECORD_NAME)

    # -- 7. everything else, in a second commit ------------------------------
    _git(["add", "-A", "--", "."], artifact_dir, identity)
    if _git(["status", "--porcelain"], artifact_dir, identity).strip():
        _git(["commit", "-q", "-m",
              "chore: the artifact kit, the vendored core and an empty results record"],
             artifact_dir, identity)
    report.second_commit = _git(["rev-parse", "HEAD"], artifact_dir,
                                identity).strip()

    # -- 8. the report, with every number it can report ----------------------
    report.tracked = sorted(_git(["ls-files"], artifact_dir, identity).split())
    report.files_tracked = len(report.tracked)
    report.files_written = len(report.written)

    print("artifact      %s" % artifact_dir, file=stream)
    print("kit source    %s" % templates_root, file=stream)
    print("files written %d" % report.files_written, file=stream)
    print("files tracked %d" % report.files_tracked, file=stream)
    print("vendored      %d file(s), %d declared source(s) absent: %s"
          % (report.vendored_count, len(report.vendor_missing),
             report.vendor_missing or "none"), file=stream)
    print("first commit  %s (%s alone)"
          % (report.first_commit[:12], FIRST_COMMIT_PATH), file=stream)
    print("second commit %s" % report.second_commit[:12], file=stream)

    missing = [name for name in TOOL_04_REQUIRED if name not in report.tracked]
    print("a project requirement       %d of %d required file(s) tracked%s"
          % (len(TOOL_04_REQUIRED) - len(missing), len(TOOL_04_REQUIRED),
             "" if not missing else "; MISSING %s" % missing), file=stream)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="new_artifact",
        description="Generate an artifact directory as its own git work tree.")
    parser.add_argument("slug", help="lowercase directory name, e.g. alpha-artifact-1")
    parser.add_argument("--into", default=None,
                        help="parent directory (default: the sibling of this repo)")
    parser.add_argument("--canon", default=None)
    # `--example project` is the name from 2026-09-16; `--project` stays as a
    # deprecated alias so a command written before the relabel still runs.
    parser.add_argument("--example project", "--project", default=None,
                        dest="project",
                        help="the example project id this artifact backs, e.g. P1 or BP-2")
    parser.add_argument("--organization", default=None,
                        help="the organization named in the README opening")
    parser.add_argument("--role", default=None,
                        help="the role, e.g. 'Example Role One'")
    parser.add_argument("--engagement-dates", default=None,
                        dest="engagement_dates",
                        help="the engagement window, e.g. 'Month YYYY - Month YYYY'")
    parser.add_argument("--collections-entry", default=None,
                        dest="collections_entry",
                        help="collections/everything-<field>/<slug>/raw.json")
    parser.add_argument("--bullet", action="append", dest="bullets", default=None)
    parser.add_argument("--gpu-required", action="store_true")
    parser.add_argument("--source-root", default=None,
                        help="tooling repository root (default: this one)")
    args = parser.parse_args(list(argv) if argv is not None else None)

    core = vendor.load_core(args.source_root)
    dest_root = args.into or os.path.dirname(REPO_ROOT)
    try:
        generate(args.slug, dest_root, canon=args.canon, project=args.project,
                 bullets=args.bullets, gpu_required=args.gpu_required,
                 source_root=args.source_root, organization=args.organization,
                 role=args.role, engagement_dates=args.engagement_dates,
                 collections_entry=args.collections_entry)
    except Refusal as refusal:
        # Exit 2 means COULD NOT LOOK, and it is deliberately not the same code
        # as a finding. A script that collapses them loses the distinction
        # between "this artifact has a problem" and "no artifact was made".
        print("%s %s" % (core.REFUSAL_PREFIX, refusal), file=sys.stderr)
        return core.EXIT_DID_NOT_RUN
    return core.EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
