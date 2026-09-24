"""assemble_records -- fragments in, ONE counted and hashed file out.

THE PROBLEM THIS SOLVES
-----------------------
A fragment written but never assembled is INVISIBLE. Nothing raises, no count
moves, and the assembled file a reader trusts is simply missing a record. That
is why the header carries the fragment COUNT and a sha256 over the fragment set:
those two numbers are the entire mechanism by which "written but never
assembled" becomes detectable rather than silent.

Parallelization is ON and its granularity is `fine`, so record-writing plans run
concurrently. A plan that appends to an assembled file DIRECTLY loses the other
agent's write with no error at all -- so assembled files are GENERATED-ONLY,
`build` writes them atomically under a blocking `mwlock`, and `lint` re-runs
`build` in memory and byte-compares, which is what makes a direct append
detectable instead of silently winning.

a design rule -- SUPERSESSION IS EXCLUSION PLUS A COUNT, NEVER DELETION
---------------------------------------------------------------
A fragment carrying `supersedes: <id>` removes that id's BODY from the assembled
output and adds it to the `superseded` count. The superseded file stays on disk
and its id is still NAMED in the output, so a reader can tell a retracted record
from one that was never written. This is the same LIVE-vs-FROZEN classification
earlier rounds apply to retractions and superseded wording -- one rule for the
whole program rather than two. a shared pattern states the shipped model's reason
in one line: *discarding the run that disagrees is how a benchmark lies.*

A `supersedes:` pointing at an id that does not exist FAILS, with the id named.
A dangling pointer means either the target was deleted (which a design rule forbids) or
the id was mistyped, and both make the `superseded` count a lie.

FRAGMENT NAMING -- WHY A TIMESTAMP AND NOT A PLAN NUMBER
---------------------------------------------------------
    _records/<kind>/YYYY-MM-DD-HHMMSS--<slug>--<kind>.md

Ordering is by the timestamp prefix, NEVER by plan number. Five inherited waves
hold 2-3 record-writing plans each and five paths are order-free, so the plan
number stops being chronological the moment the roadmap reorders. The plan id is
therefore a FIELD in the front matter, not part of the name.

WHERE THE ASSEMBLED FILE GOES, AND WHY IT IS NOT IN THE SCANNED DIRECTORY
-------------------------------------------------------------------------
    fragments -> _records/<kind>/*.md        (the scanned population)
    assembled -> _records/<kind>.md          (BESIDE the directory)

An aggregate placed inside the directory it aggregates is either re-assembled
into itself or silently excluded by whatever pattern skips it -- and the second
reads as working. Keeping it one level up makes the two populations disjoint by
construction rather than by a filter someone has to remember.

Files inside the fragment directory that do not match the fragment pattern are
IGNORED, COUNTED and NAMED -- `_records/census/README.md` already exists in this
repository, so this is a live case. A scan that does not print what it skipped
cannot be audited.

ENCODING -- WHICH RULE APPLIES HERE, STATED RATHER THAN LEFT TO INFERENCE
--------------------------------------------------------------------------
`canonkit.atomic_write_text` defaults to ASCII because a design rule makes the frozen core
and everything it writes ASCII by contract. That is NOT the rule for this file.
Record fragments are prose that may legitimately quote verbatim canon text --
BP-1's canon is bilingual Arabic/English -- which is the same reason
`tools/canon-bullets.json` is written with `ensure_ascii=False`. Assembled
records are therefore UTF-8 with `ensure_ascii=False`, and the ASCII contract
stays where it belongs, on the core.

The WRITE goes through `canonkit.atomic_write_text` rather than a local copy:
per-writer `pid+uuid` tmp name in the SAME directory, flush, fsync, `os.replace`,
`finally` cleanup, and `newline=""` so no line ending is translated on the way
out. Duplicating that here would put a second copy of the one function whose
whole purpose is preventing drift.

EXIT CODES -- the canonkit contract
    0  the run covered a non-empty fragment population and did what it says
    1  a finding: the assembled file does not match the fragments
    2  could NOT look: zero fragments
"""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)

SCHEMA = "records/1"
SCHEMA_VERSION = 1

# The fragment name, as a STRUCTURAL predicate rather than a blacklist of names
# to skip. "Everything except README.md" would need editing every time someone
# drops a new non-fragment beside the records; this needs editing never.
FRAGMENT_RE = re.compile(
    r"^(?P<stamp>\d{4}-\d{2}-\d{2}-\d{6})"
    r"--(?P<slug>[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"--(?P<kind>[A-Za-z0-9][A-Za-z0-9._-]*)\.md$")

REQUIRED_KEYS = ("id", "plan", "dated_at")
OPTIONAL_KEYS = ("supersedes",)

GENERATED_BANNER = (
    "GENERATED by tools/assemble_records.py. DO NOT EDIT and DO NOT APPEND.\n"
    "Edit a fragment in the directory named below and re-run `build`; a direct\n"
    "edit is detected by `lint` and would be lost by the next `build`.")


class AssembleError(Exception):
    """A fragment set that cannot be assembled honestly.

    Raised rather than returned so no caller can carry on with a count it did
    not earn. `main` turns it into a non-zero exit with the message intact.
    """


def _load_module(stem, filename):
    """Load a sibling BY PATH under a neutral name.

    Never a package import: a design rule forbids it, test_repo_hygiene.py scans every
    repo-side module for it, and the core itself raises on a dotted __name__.
    """
    path = os.path.join(_HERE, filename)
    spec = importlib.util.spec_from_file_location(stem, path)
    if spec is None or spec.loader is None:
        raise ImportError("could not build an import spec for %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = _load_module("frozen_core", "canonkit.py")
mwlock = _load_module("measurement_window_lock", "mwlock.py")


def working_repo_root():
    """The checkout this file runs from. Assembled records are OUTPUT."""
    return _REPO_ROOT


def default_records_root():
    return os.path.join(working_repo_root(), "_records")


def default_target(kind_dir):
    """The assembled file for `kind_dir`: its sibling, one level up.

    See the module docstring on why this is NOT inside `kind_dir`.
    """
    kind_dir = os.path.abspath(str(kind_dir))
    parent = os.path.dirname(kind_dir)
    return os.path.join(parent, os.path.basename(kind_dir) + ".md")


# ---------------------------------------------------------------------------
# Reading fragments
# ---------------------------------------------------------------------------

def parse_fragment(path):
    """Read one fragment. Raises AssembleError with the path named on any miss.

    Front matter is a `---` delimited block of `key: value` lines. Deliberately
    not YAML: a record format the program cannot parse without a dependency is a
    record format an artifact cannot re-read from a clean checkout.
    """
    path = str(path)
    name = os.path.basename(path)
    with open(path, "r", encoding="utf-8", newline="") as handle:
        raw = handle.read()

    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise AssembleError(
            "%s: no front matter. A fragment must open with a '---' block "
            "carrying %s." % (name, ", ".join(REQUIRED_KEYS)))

    fields = {}
    end = None
    for index in range(1, len(lines)):
        line = lines[index]
        if line.strip() == "---":
            end = index
            break
        if not line.strip():
            continue
        if ":" not in line:
            raise AssembleError(
                "%s: front matter line %d is not 'key: value': %r"
                % (name, index + 1, line))
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    if end is None:
        raise AssembleError("%s: front matter block is never closed with '---'"
                            % name)

    missing = [key for key in REQUIRED_KEYS if not fields.get(key)]
    if missing:
        raise AssembleError(
            "%s: front matter is missing required key(s): %s. Required: %s."
            % (name, ", ".join(missing), ", ".join(REQUIRED_KEYS)))

    unknown = sorted(set(fields) - set(REQUIRED_KEYS) - set(OPTIONAL_KEYS))
    if unknown:
        raise AssembleError(
            "%s: unknown front-matter key(s) %s. Accepted: %s. A typo'd key is "
            "silently ignored otherwise, and `supersedes` typo'd is a "
            "retraction that never happens."
            % (name, unknown, ", ".join(REQUIRED_KEYS + OPTIONAL_KEYS)))

    match = FRAGMENT_RE.match(name)
    body = "\n".join(lines[end + 1:]).strip("\n")
    return {
        "path": path,
        "name": name,
        "stamp": match.group("stamp"),
        "slug": match.group("slug"),
        "kind": match.group("kind"),
        "id": fields["id"],
        "plan": fields["plan"],
        "dated_at": fields["dated_at"],
        "supersedes": fields.get("supersedes") or None,
        "body": body,
        "sha256": core.sha256_bytes(raw.encode("utf-8")),
    }


def collect(kind_dir):
    """Enumerate `kind_dir`. Returns (fragments, ignored_names).

    Sorted by the TIMESTAMP prefix, then by name to break ties deterministically
    -- never by plan number. Both populations are returned so the caller can
    print what it skipped as well as what it read.
    """
    kind_dir = str(kind_dir)
    if not os.path.isdir(kind_dir):
        return [], []

    fragments = []
    ignored = []
    for name in sorted(os.listdir(kind_dir)):
        path = os.path.join(kind_dir, name)
        if not os.path.isfile(path):
            continue
        if FRAGMENT_RE.match(name):
            fragments.append(parse_fragment(path))
        else:
            ignored.append(name)

    fragments.sort(key=lambda item: (item["stamp"], item["name"]))
    return fragments, ignored


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _fragments_sha256(fragments):
    """sha256 over the sorted (name, content-hash) list.

    Both halves matter and for different reasons: the CONTENT hash moves when a
    fragment is edited, the NAME moves when one is added, removed or renamed.
    Hashing only the concatenated bodies would miss a rename; hashing only the
    names would miss an edit.
    """
    digest = hashlib.sha256()
    for item in sorted(fragments, key=lambda entry: entry["name"]):
        digest.update(item["name"].encode("utf-8"))
        digest.update(b"\x00")
        digest.update(item["sha256"].encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def render(kind, fragments, superseded_ids):
    """Build the assembled text. Pure -- so `lint` can compare without writing."""
    live = [item for item in fragments if item["id"] not in superseded_ids]
    frozen = [item for item in fragments if item["id"] in superseded_ids]

    lines = []
    lines.append("# Records: %s" % kind)
    lines.append("")
    lines.append(GENERATED_BANNER)
    lines.append("")
    lines.append("assembled %d, superseded %d, total %d"
                 % (len(live), len(frozen), len(fragments)))
    lines.append("")
    lines.append("fragments-sha256: %s" % _fragments_sha256(fragments))
    lines.append("")

    if frozen:
        lines.append("## Superseded (excluded from the body, kept on disk)")
        lines.append("")
        for item in frozen:
            replaced_by = [other["id"] for other in fragments
                           if other["supersedes"] == item["id"]]
            lines.append("- `%s` (%s) superseded by %s"
                         % (item["id"], item["name"],
                            ", ".join("`%s`" % ident for ident in replaced_by)))
        lines.append("")

    for item in live:
        lines.append("## %s" % item["id"])
        lines.append("")
        lines.append("- fragment: `%s`" % item["name"])
        lines.append("- plan: %s" % item["plan"])
        lines.append("- dated_at: %s" % item["dated_at"])
        if item["supersedes"]:
            lines.append("- supersedes: `%s`" % item["supersedes"])
        lines.append("")
        if item["body"]:
            lines.append(item["body"])
            lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def _superseded_ids(fragments):
    """Resolve `supersedes:` pointers. Raises on a dangling or duplicate id."""
    by_id = {}
    for item in fragments:
        if item["id"] in by_id:
            raise AssembleError(
                "duplicate fragment id %r in %s and %s. An id is the handle a "
                "`supersedes:` points at, so two fragments sharing one makes "
                "every retraction ambiguous."
                % (item["id"], by_id[item["id"]]["name"], item["name"]))
        by_id[item["id"]] = item

    superseded = set()
    for item in fragments:
        target = item["supersedes"]
        if target is None:
            continue
        if target not in by_id:
            raise AssembleError(
                "%s declares `supersedes: %s` but no fragment carries that id. "
                "Either the superseded fragment was DELETED -- which a design rule "
                "forbids, it must be kept and counted -- or the id is mistyped. "
                "Known ids (%d): %s"
                % (item["name"], target, len(by_id),
                   ", ".join(sorted(by_id)) or "<none>"))
        if target == item["id"]:
            raise AssembleError(
                "%s supersedes itself (%s)" % (item["name"], target))
        superseded.add(target)
    return superseded


# ---------------------------------------------------------------------------
# build / lint
# ---------------------------------------------------------------------------

def _prepare(kind_dir):
    """The half `build` and `lint` share, so they cannot drift apart.

    `lint` byte-comparing against a DIFFERENT rendering than `build` writes
    would be a check of two implementations agreeing, not of the file matching
    its fragments.
    """
    kind_dir = os.path.abspath(str(kind_dir))
    kind = os.path.basename(kind_dir)
    fragments, ignored = collect(kind_dir)
    if not fragments:
        return kind_dir, kind, [], ignored, None, None
    superseded = _superseded_ids(fragments)
    return (kind_dir, kind, fragments, ignored, superseded,
            render(kind, fragments, superseded))


def build(kind_dir, target=None, timeout=mwlock.DEFAULT_TIMEOUT):
    """Assemble `kind_dir` into one file. Returns the result dict.

    Raises:
        AssembleError: on zero fragments, or any fragment the set cannot be
            assembled honestly from. Zero is a REFUSAL rather than an empty
            file: an empty assembled file reported as success would make the
            next `lint` compare clean, and the missing fragments would never
            surface.
    """
    kind_dir, kind, fragments, ignored, superseded, text = _prepare(kind_dir)
    if not fragments:
        raise AssembleError(
            "DID-NOT-RUN: 0 fragments matched %s in %s (ignored %d: %s). "
            "Nothing was written -- an empty assembled file reported as a "
            "success is how a missing record stays missing."
            % (FRAGMENT_RE.pattern, kind_dir, len(ignored),
               ", ".join(ignored) or "<none>"))

    target = os.path.abspath(str(target or default_target(kind_dir)))

    # The lock is held around the REPLACE, not merely around the render: two
    # agents rendering concurrently is harmless, two replacing is not.
    with mwlock.held(mwlock.lock_path_for(target), timeout=timeout):
        core.atomic_write_text(target, text, encoding="utf-8",
                               ensure_ascii=False)

    live = len(fragments) - len(superseded)
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "scan_root": kind_dir,
        "target": target,
        "assembled": live,
        "superseded": len(superseded),
        "total": len(fragments),
        "ignored": len(ignored),
        "ignored_names": list(ignored),
        "fragments_sha256": _fragments_sha256(fragments),
        "superseded_ids": sorted(superseded),
    }


def lint(kind_dir, target=None):
    """Re-render in memory and byte-compare. Returns (verdict, result, diff).

    verdict is "match" | "differs" | "missing" | "empty".

    This is the half that makes a DIRECT APPEND detectable. A plan that appends
    to the assembled file rather than adding a fragment loses the next agent's
    write silently; here it becomes a non-zero exit and a printed diff.
    """
    kind_dir, kind, fragments, ignored, superseded, text = _prepare(kind_dir)
    target = os.path.abspath(str(target or default_target(kind_dir)))
    result = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "scan_root": kind_dir,
        "target": target,
        "assembled": (len(fragments) - len(superseded)) if fragments else 0,
        "superseded": len(superseded) if fragments else 0,
        "total": len(fragments),
        "ignored": len(ignored),
        "ignored_names": list(ignored),
        "fragments_sha256": _fragments_sha256(fragments) if fragments else None,
    }
    if not fragments:
        return "empty", result, []

    if not os.path.isfile(target):
        return "missing", result, []

    with open(target, "r", encoding="utf-8", newline="") as handle:
        on_disk = handle.read()
    if on_disk == text:
        return "match", result, []

    import difflib
    diff = list(difflib.unified_diff(
        text.splitlines(), on_disk.splitlines(),
        fromfile="expected (rebuilt from %d fragments)" % len(fragments),
        tofile="on disk (%s)" % os.path.basename(target), lineterm=""))
    return "differs", result, diff


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _write_report(path, payload):
    if not path:
        return
    core.atomic_write_json(path, payload, ensure_ascii=False)


def _print_population(result, ignored_names):
    sys.stdout.write("scanned %s\n" % result["scan_root"])
    sys.stdout.write("assembled %d, superseded %d, total %d\n"
                     % (result["assembled"], result["superseded"],
                        result["total"]))
    sys.stdout.write("ignored %d%s\n"
                     % (len(ignored_names),
                        (": " + ", ".join(ignored_names)) if ignored_names
                        else ""))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="assemble_records",
        description="Assemble record fragments into one counted, hashed file "
                    ". Assembled files are GENERATED-ONLY.")
    parser.add_argument("command", choices=("build", "lint"))
    parser.add_argument("--dir", required=True,
                        help="the fragment directory, e.g. _records/judgment")
    parser.add_argument("--target", default=None,
                        help="the assembled file (default: the directory's "
                             "sibling, one level up)")
    parser.add_argument("--report", default=None,
                        help="write a structured report here")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "build":
        try:
            result = build(args.dir, target=args.target)
        except AssembleError as exc:
            message = str(exc)
            code = (core.EXIT_DID_NOT_RUN if message.startswith("DID-NOT-RUN")
                    else core.EXIT_FINDING)
            sys.stdout.write("%s\n" % message)
            _write_report(args.report,
                          {"schema": SCHEMA, "schema_version": SCHEMA_VERSION,
                           "scan_root": os.path.abspath(str(args.dir)),
                           "error": message, "exit_code": code})
            return code
        _print_population(result, result["ignored_names"])
        sys.stdout.write("fragments-sha256 %s\n" % result["fragments_sha256"])
        sys.stdout.write("wrote %s\n" % result["target"])
        _write_report(args.report, result)
        return core.EXIT_PASS

    try:
        verdict, result, diff = lint(args.dir, target=args.target)
    except AssembleError as exc:
        sys.stdout.write("%s\n" % exc)
        _write_report(args.report,
                      {"schema": SCHEMA, "schema_version": SCHEMA_VERSION,
                       "scan_root": os.path.abspath(str(args.dir)),
                       "error": str(exc), "exit_code": core.EXIT_FINDING})
        return core.EXIT_FINDING

    result["verdict"] = verdict
    _print_population(result, result["ignored_names"])

    if verdict == "empty":
        sys.stdout.write(
            "DID-NOT-RUN: 0 fragments in %s -- nothing to compare against\n"
            % result["scan_root"])
        _write_report(args.report, result)
        return core.EXIT_DID_NOT_RUN

    if verdict == "missing":
        sys.stdout.write(
            "FINDING: %d fragment(s) exist but %s was never assembled. This is "
            "the written-but-never-assembled case a project requirement exists to detect. "
            "Run: python tools/assemble_records.py build --dir %s\n"
            % (result["total"], result["target"], result["scan_root"]))
        _write_report(args.report, result)
        return core.EXIT_FINDING

    if verdict == "differs":
        sys.stdout.write(
            "FINDING: %s does not match its %d fragment(s). An assembled file "
            "is GENERATED-ONLY; a direct edit or append is lost by the next "
            "build and loses a concurrent agent's write meanwhile.\n"
            % (result["target"], result["total"]))
        for line in diff:
            sys.stdout.write("%s\n" % line)
        _write_report(args.report, result)
        return core.EXIT_FINDING

    sys.stdout.write("match: %s is exactly its %d fragment(s)\n"
                     % (result["target"], result["total"]))
    _write_report(args.report, result)
    return core.EXIT_PASS


if __name__ == "__main__":
    raise SystemExit(main())
