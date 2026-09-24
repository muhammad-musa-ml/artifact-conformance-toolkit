"""build_register -- the register is GENERATED, and it refuses to overwrite an edit.

a project requirement. The inherited register header literally said *"Figures here are copied
from that artifact's own results/RESULTS.md"*. two earlier findings overturn that, and the
reason is the whole point of this program: **that copy is the last hop where a
human retypes a number.** Every figure in the register below is read out of an
artifact's own `results/figures.json` at generation time. The only hand-written
thing is the SIMILARITY JUDGMENT, it lives in `register-fragments/<slug>.md`,
and it is numeral-free.

a design rule -- REFUSE, PRINT THE DIFF, WRITE NOTHING
-----------------------------------------------
The shared pattern note supplies the cautionary evidence from a shipped regenerator that
took the other route (`application_export.py:510-570`): partial knowledge plus a
`_carry_forward` clause, which silently rewrote a real score to `n/a` on every
run for an unknown period. a design rule's posture is stronger AND cheaper -- do not
reconcile, REFUSE. Two implementation details are what make that real rather
than nominal:

  1. The check runs BEFORE `atomic_write_text` is called. A trailer-checked
     refusal that happens after the write is not a refusal.
  2. The test asserts the on-disk BYTES are unchanged by hashing the file either
     side, rather than believing this module's own claim about what it did.

WHY THE TRAILER CARRIES **TWO** HASHES
----------------------------------------
    inputs-sha256   the manifest, every figures.json, every fragment
    body-sha256     the register's own text, above the trailer

Only the second can detect a hand edit, and the distinction is not academic: a
hand edit changes the BODY and leaves every generation INPUT untouched. A guard
keyed on the inputs hash alone would therefore compare EQUAL after an edit and
regenerate straight over it -- a check that passes while checking nothing, which
is the precise shape this phase has hit five times.

The inputs hash earns its place separately: it answers "would regenerating
change anything?" without regenerating, and it is what makes the register's
provenance auditable from the file itself.

a design rule -- THE NUMERAL LINT RUNS **BOTH** RULES
----------------------------------------------
`canonkit.classify_numerals` is called with the artifact's figure VALUES, so:

  * the SHAPE allow-list (bullet ids, ISO dates, `{{figures.*}}` key references,
    versions, ports) is the primary rule, and
  * the VALUE check fails on any `figures.json` value appearing outside a key
    reference.

Neither alone is sufficient. Deny-by-value alone misses a hand-typed number that
happens not to match a figure -- exactly an earlier finding's back-solving failure. Shape alone
misses a real figure value wearing an allowed shape. a design rule and a design rule share ONE
allow-list, in the core, because two implementations would drift.

a design rule -- EXCLUSIONS ARE REASONS, NOT SILENCE
---------------------------------------------
A scanned-but-not-backing slug carries `register_row: false` PLUS a
`no_row_reason`, and this tool prints `excluded: N (reasons recorded)` followed
by each reason VERBATIM. `register_row: false` with an empty reason is a hard
failure: a silent exclusion is indistinguishable from a slug someone forgot.

a design rule -- TRACKED HERE, MIRRORED BESIDE THE ARTIFACTS
-----------------------------------------------------
    tracked   <working checkout>/backing-artifacts.md
    mirror    <artifacts root>/backing-artifacts.md

Two anchors, two different rules, and getting them the same way round by
accident is easy because in an ordinary checkout they look related:

  * The TRACKED register is output that gets committed, so it is anchored to
    `working_repo_root()` -- the checkout that produced it. `census_live_store`
    records the measured cost of getting this wrong: 1.4 MB written into the
    MAIN checkout from inside a worktree, in a tree nobody was watching.
  * The MIRROR's location is defined by the ARTIFACTS, not by the checkout, so
    it is anchored to `main_repo_root()/..`. Anchoring it to the working root
    would put it in `agent-worktrees/worktrees/backing-artifacts.md` when run from an
    agent worktree -- which is the same defect wearing the opposite hat.

The artifacts SCAN ROOT is `main_repo_root()/..` for exactly this reason.
`tools/tests/conftest.py` derives its own `SCAN_ROOT` as `REPO_ROOT / ".."`,
which is correct in an ordinary checkout and resolves to
`<repo>/agent-worktrees/worktrees` inside an agent worktree -- measured at 2 directories
holding 0 manifest slugs, against 25 directories holding 2 under the main root.
A register generated over that population would look entirely fine.

EXIT CODES -- the canonkit contract
    0  generated over a non-empty artifact population, expected == found
    1  a finding: a shortfall, a bad fragment, or a REFUSED regeneration
    2  could NOT look: zero artifacts carrying results/figures.json
"""

import argparse
import difflib
import hashlib
import importlib.util
import json
import os
import tempfile
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)

SCHEMA = "register/1"
SCHEMA_VERSION = 1

REGISTER_NAME = "backing-artifacts.md"
FIGURES_RELATIVE = os.path.join("results", "figures.json")

TRAILER_MARKER = "<!-- build_register trailer -- do not edit -->"
INPUTS_PREFIX = "<!-- inputs-sha256: "
BODY_PREFIX = "<!-- body-sha256: "
SUFFIX = " -->"


class RegisterError(Exception):
    """The register cannot be generated honestly, or must not be overwritten."""


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
census = _load_module("live_store_census", "census_live_store.py")


def working_repo_root():
    """The checkout this file runs from. The TRACKED register's anchor."""
    return _REPO_ROOT


def default_artifacts_root():
    """`<home>/Research/` -- the directory holding every artifact slug.

    Anchored to main_repo_root() so it resolves to the SAME directory from an
    ordinary checkout and from an agent worktree. See the module docstring.
    """
    return os.path.abspath(os.path.join(census.main_repo_root(), os.pardir))


def default_register_path():
    return os.path.join(working_repo_root(), REGISTER_NAME)


def default_mirror_path(artifacts_root=None):
    """The mirror for a scan of `artifacts_root`, INSIDE that root.

    It used to take no argument and resolve through `default_artifacts_root()`,
    which is anchored to the repository and ignores whatever root the caller is
    actually scanning. A caller scanning one tree therefore published into
    another -- and because the only caller that omits `--mirror` is the round
    trip, which scans a pytest temp directory, the tree it published into was
    the owner's real `<home>/Research/backing-artifacts.md`. That file is
    outside every git repository and versioned by nothing, so the damage was
    silent, and three sessions measured it before anyone traced it.

    Passing no root preserves the old meaning for callers that genuinely mean
    the default root.
    """
    root = artifacts_root if artifacts_root is not None else default_artifacts_root()
    return os.path.join(os.path.abspath(str(root)), REGISTER_NAME)


def _within(child, parent):
    """True when `child` is `parent` or sits under it, BY RESOLUTION.

    Never by string prefix: the conventions document section 8 rule 8 -- a
    repository-relative anchor resolves differently inside a worktree, and a
    prefix comparison is defeated by a single parent hop (`<root>/../<root>`).
    """
    try:
        child = os.path.realpath(str(child))
        parent = os.path.realpath(str(parent))
    except OSError:
        return False
    if child == parent:
        return True
    return child.startswith(parent + os.sep)


def _refuse_throwaway_publish(artifacts_root, mirror_path):
    """A scan of a THROWAWAY tree may not publish a mirror outside that tree.

    The rule is deliberately narrower than "refuse every temp root". The round
    trip legitimately scans a pytest temp directory and writes its mirror INSIDE
    it; what is forbidden is a throwaway scan reaching a path outside the tree it
    scanned, which is the exact shape of the defect this guard was written for.

    Refusing every temp root would also be a guard that cannot tell its two arms
    apart -- satisfied by refusing everything -- and
    test_the_guard_discriminates_and_does_not_refuse_everything exists to stop
    that.
    """
    if not _within(artifacts_root, tempfile.gettempdir()):
        return None
    if _within(mirror_path, artifacts_root):
        return None
    return (
        "DID-NOT-RUN: %s a scan rooted at %s resolves inside the system "
        "temporary directory, and its mirror would be written to %s, which is "
        "OUTSIDE that root. A throwaway tree may not publish a register to a "
        "real location: the mirror lives outside every git repository and is "
        "versioned by nothing, so an accidental overwrite is silent and "
        "unrecoverable. Nothing was written. REPAIR: pass --mirror pointing "
        "inside the root you are scanning, or scan the real artifacts root if "
        "you meant to publish."
        % (core.REFUSAL_PREFIX, os.path.realpath(str(artifacts_root)),
           os.path.realpath(str(mirror_path))))


def default_fragments_dir():
    return os.path.join(working_repo_root(), "register-fragments")


def default_manifest_path():
    return os.path.join(_HERE, "manifest.json")


# ---------------------------------------------------------------------------
# The trailer
# ---------------------------------------------------------------------------

def body_sha256(text):
    """sha256 of everything ABOVE the trailer, as bytes.

    Encoded explicitly rather than hashing the str, so the digest does not
    depend on the platform's default encoding -- the same reason
    canonkit.sha256_file reads bytes and never decoded text.
    """
    body, _ = split_body_and_trailer(text)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def split_body_and_trailer(text):
    """Return (body, trailer_text). trailer_text is "" when absent."""
    index = text.find(TRAILER_MARKER)
    if index < 0:
        return text, ""
    return text[:index], text[index:]


def read_trailer(text):
    """Parse the trailer. Returns a dict, or None when there is not one.

    Returns None rather than guessing on a malformed trailer: a trailer this
    tool cannot read is treated as an edit, which is the safe direction -- it
    refuses rather than overwriting.
    """
    _, trailer = split_body_and_trailer(text)
    if not trailer:
        return None
    found = {}
    for line in trailer.split("\n"):
        line = line.strip()
        for key, prefix in (("inputs_sha256", INPUTS_PREFIX),
                            ("body_sha256", BODY_PREFIX)):
            if line.startswith(prefix) and line.endswith(SUFFIX):
                found[key] = line[len(prefix):-len(SUFFIX)].strip()
    if "inputs_sha256" not in found or "body_sha256" not in found:
        return None
    return found


def _render_trailer(inputs_hash, body_hash):
    return "\n".join([
        TRAILER_MARKER,
        "%s%s%s" % (INPUTS_PREFIX, inputs_hash, SUFFIX),
        "%s%s%s" % (BODY_PREFIX, body_hash, SUFFIX),
        "",
    ])


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def load_manifest(path):
    path = str(path)
    if not os.path.isfile(path):
        raise RegisterError("no manifest at %s" % path)
    with open(path, "r", encoding="utf-8", newline="") as handle:
        raw = handle.read()
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise RegisterError("%s is not valid JSON: %s" % (path, exc))
    if not isinstance(payload.get("slugs"), list) or not payload["slugs"]:
        raise RegisterError(
            "%s carries no slugs. A register generated from an empty expected "
            "set would report a 0/0 pass." % path)
    return payload, raw


def _expected_count(manifest, path):
    """The COMMITTED literal, never the derived count.

    a design rule's shape: the derivation is asserted against a committed literal,
    because a purely derived count silently stops checking when a slug is
    dropped -- expected falls to match found.
    """
    counts = manifest.get("counts") or {}
    expected = counts.get("register_rows_expected")
    if not isinstance(expected, int):
        raise RegisterError(
            "%s carries no counts.register_rows_expected. That literal is the "
            "tripwire on the derivation's own input; without it `expected N, "
            "found M` is two derived numbers agreeing with each other." % path)
    derived = len([s for s in manifest["slugs"] if s.get("register_row")])
    if derived != expected:
        raise RegisterError(
            "%s: counts.register_rows_expected is %d but %d slug(s) carry "
            "register_row: true. THAT disagreement is the finding, never a "
            "value to pick between." % (path, expected, derived))
    return expected


def _read_figures(artifacts_root, slug):
    """Read and VALIDATE one artifact's figures.json. None when absent."""
    path = os.path.join(str(artifacts_root), slug, FIGURES_RELATIVE)
    if not os.path.isfile(path):
        return None, None
    with open(path, "r", encoding="utf-8", newline="") as handle:
        raw = handle.read()
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise RegisterError("%s is not valid JSON: %s" % (path, exc))
    violations = core.validate_figures(payload)
    if violations:
        raise RegisterError(
            "%s is not a valid figures record (%d violation(s)):\n  %s"
            % (path, len(violations), "\n  ".join(violations)))
    return payload, raw


def leakable_values(payload):
    """Every number in a figures record a fragment could retype.

    NOT just `value`. A POPULATION is equally back-solvable and equally a
    measurement: "the denominator was 500" retypes a measured number exactly as
    surely as quoting the p95 does, and an earlier finding's recorded failure was deriving a
    NUMERATOR from a percentage and typing it into a sentence. Restricting the
    leak set to `value` would have left the denominator half of that open.
    """
    values = []
    for entry in (payload.get("figures") or {}).values():
        if not isinstance(entry, dict):
            continue
        for key in ("value", "population"):
            if key in entry:
                values.append(entry[key])
    return values


def lint_fragment(name, text, figure_values):
    """a design rule, BOTH rules. Returns a list of located violation strings."""
    report = core.classify_numerals(text, figure_values)
    violations = []
    for hit in report.hits:
        if hit.kind == core.KIND_UNCLASSIFIED:
            violations.append(
                "%s line %d col %d: bare numeral %r is not a bullet id, an ISO "
                "date, a version, a port or a {{figures.*}} key reference. A "
                "fragment carries the JUDGMENT; the numbers are generated."
                % (name, hit.line, hit.col, hit.token))
    for leak in report.leaks:
        violations.append(
            "%s line %d col %d: %r is a VALUE from this artifact's figures.json, "
            "typed outside a key reference. Write {{figures.<id>}} instead -- a "
            "retyped value is the one hop this register exists to remove."
            % (name, leak.line, leak.col, leak.token))
    return violations


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _figure_rows(payload):
    figures = payload.get("figures") or {}
    rows = []
    for key in sorted(figures):
        entry = figures[key]
        rows.append({
            "id": key,
            "value": entry.get("value"),
            "unit": entry.get("unit"),
            "population": entry.get("population"),
            "population_label": entry.get("population_label"),
            "canon_bullet": entry.get("canon_bullet"),
            "canon_value": entry.get("canon_value"),
            "similar": entry.get("similar"),
        })
    return rows


def render(rows, excluded, expected, found, scan_root, dated_at):
    lines = []
    lines.append("# Backing artifacts register")
    lines.append("")
    lines.append("GENERATED by `tools/build_register.py`. **Do not edit.** Every")
    lines.append("figure below is read from that artifact's own")
    lines.append("`results/figures.json` at generation time; only the similarity")
    lines.append("judgment is hand-written, and it lives in")
    lines.append("`register-fragments/<slug>.md`. A hand edit here makes the next")
    lines.append("regeneration REFUSE rather than overwrite it.")
    lines.append("")
    lines.append("- scanned: `%s`" % scan_root)
    lines.append("- expected %d, found %d" % (expected, found))
    lines.append("- excluded: %d (reasons recorded)" % len(excluded))
    lines.append("- generated: %s" % dated_at)
    lines.append("")

    if excluded:
        lines.append("## Excluded slugs")
        lines.append("")
        lines.append("| slug | reason |")
        lines.append("| ---- | ------ |")
        for item in excluded:
            lines.append("| `%s` | %s |" % (item["slug"], item["reason"]))
        lines.append("")

    for row in rows:
        lines.append("## %s" % row["slug"])
        lines.append("")
        lines.append("- status: %s" % row["status"])
        lines.append("- canon: %s / %s" % (row["canon"], row["project"]))
        lines.append("- figures source: `%s`" % row["figures_path"])
        lines.append("- dated_at: %s" % row["dated_at"])
        lines.append("")
        lines.append("| figure | measured | population | canon bullet | "
                     "canon value | similar |")
        lines.append("| ------ | -------- | ---------- | ------------ | "
                     "----------- | ------- |")
        for figure in row["figures"]:
            lines.append("| `%s` | %s %s | %s %s | `%s` | %s | %s |" % (
                figure["id"], figure["value"], figure["unit"],
                figure["population"], figure["population_label"],
                figure["canon_bullet"], figure["canon_value"],
                figure["similar"]))
        lines.append("")
        lines.append("### Similarity judgment")
        lines.append("")
        if row["fragment"] is None:
            lines.append("MISSING: no `register-fragments/%s.md`. The verdict is "
                         "the OWNER's reading and cannot be generated."
                         % row["slug"])
        else:
            lines.append(row["fragment"].strip())
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def build(artifacts_root=None, fragments_dir=None, manifest_path=None,
          register_path=None, mirror_path=None, allow_shortfall=False,
          dated_at=None):
    """Generate the register. Returns the result dict.

    Raises:
        RegisterError: on zero artifacts, an invalid input, a bad fragment, or a
            trailer mismatch. Nothing is written on ANY of those paths.
    """
    artifacts_root = os.path.abspath(str(artifacts_root or default_artifacts_root()))
    fragments_dir = os.path.abspath(str(fragments_dir or default_fragments_dir()))
    manifest_path = os.path.abspath(str(manifest_path or default_manifest_path()))
    register_path = os.path.abspath(str(register_path or default_register_path()))
    mirror_path = os.path.abspath(str(
        mirror_path or default_mirror_path(artifacts_root)))

    refusal = _refuse_throwaway_publish(artifacts_root, mirror_path)
    if refusal is not None:
        raise RegisterError(refusal)

    manifest, manifest_raw = load_manifest(manifest_path)
    expected = _expected_count(manifest, manifest_path)

    digest = hashlib.sha256()
    digest.update(manifest_raw.encode("utf-8"))

    excluded = []
    for entry in manifest["slugs"]:
        if entry.get("register_row"):
            continue
        reason = (entry.get("no_row_reason") or "").strip()
        if not reason:
            raise RegisterError(
                "manifest slug %r carries register_row: false with no "
                "no_row_reason. A silent exclusion is indistinguishable "
                "from a slug somebody forgot." % entry.get("slug"))
        excluded.append({"slug": entry.get("slug"), "reason": reason})
    excluded.sort(key=lambda item: item["slug"])

    rows = []
    missing_figures = []
    missing_fragments = []
    violations = []

    for entry in sorted(manifest["slugs"], key=lambda item: item["slug"]):
        if not entry.get("register_row"):
            continue
        slug = entry["slug"]
        payload, raw = _read_figures(artifacts_root, slug)
        if payload is None:
            missing_figures.append(slug)
            continue
        digest.update(slug.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(raw.encode("utf-8"))

        fragment_path = os.path.join(fragments_dir, "%s.md" % slug)
        fragment_text = None
        if os.path.isfile(fragment_path):
            with open(fragment_path, "r", encoding="utf-8", newline="") as handle:
                fragment_text = handle.read()
            digest.update(fragment_text.encode("utf-8"))
            violations.extend(lint_fragment("%s.md" % slug, fragment_text,
                                            leakable_values(payload)))
        else:
            missing_fragments.append(slug)

        rows.append({
            "slug": slug,
            "status": entry.get("status", "unknown"),
            "canon": entry.get("canon", "unknown"),
            "project": entry.get("project", "unknown"),
            "figures_path": os.path.join(slug, FIGURES_RELATIVE).replace(os.sep, "/"),
            "dated_at": payload.get("dated_at", "unknown"),
            "figures": _figure_rows(payload),
            "fragment": fragment_text,
        })

    found = len(rows)

    if found == 0:
        raise RegisterError(
            "DID-NOT-RUN: scanned %s and found 0 of %d expected artifact(s) "
            "carrying %s. Nothing was written. Missing: %s"
            % (artifacts_root, expected, FIGURES_RELATIVE,
               ", ".join(missing_figures) or "<none>"))

    if violations:
        raise RegisterError(
            "%d numeral-lint violation(s) in register-fragments/. A "
            "fragment carries the similarity JUDGMENT and is numeral-free:\n  %s"
            % (len(violations), "\n  ".join(violations)))

    # WHOLE stamp. `core.now_local()` returns a STRING, so the `[0]` this line
    # used to carry took the first CHARACTER of the year and every register
    # this tool ever wrote dated itself `2`. Nothing errored, the line still
    # rendered, and no exit code could see it -- it was found by reading the
    # register's own text rather than the verdict printed beside it.
    dated_at = dated_at or core.now_local()
    body = render(rows, excluded, expected, found, artifacts_root, dated_at)
    inputs_hash = digest.hexdigest()
    text = body + "\n" + _render_trailer(inputs_hash,
                                         hashlib.sha256(
                                             (body + "\n").encode("utf-8")
                                         ).hexdigest())

    # ---------------------------------------------------------------
    # a design rule. BEFORE any write. A refusal that happens after the atomic
    # write call is not a refusal.
    # ---------------------------------------------------------------
    _refuse_if_edited(register_path, text)
    _refuse_if_edited(mirror_path, text)

    core.atomic_write_text(register_path, text, encoding="utf-8",
                           ensure_ascii=False)
    core.atomic_write_text(mirror_path, text, encoding="utf-8",
                           ensure_ascii=False)

    result = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "scan_root": artifacts_root,
        "register": register_path,
        "mirror": mirror_path,
        "expected": expected,
        "found": found,
        "excluded": len(excluded),
        "excluded_slugs": [item["slug"] for item in excluded],
        "excluded_reasons": {item["slug"]: item["reason"] for item in excluded},
        "missing_figures": missing_figures,
        "missing_fragments": missing_fragments,
        "inputs_sha256": inputs_hash,
        "shortfall": found != expected,
    }
    if result["shortfall"] and not allow_shortfall:
        result["verdict"] = core.VERDICT_FAIL
    else:
        result["verdict"] = core.VERDICT_PASS
    return result


def _refuse_if_edited(path, replacement):
    """Refuse when `path` is not the file this tool last wrote. Writes nothing.

    TWO checks, and the second was MEASURED as necessary rather than added for
    completeness. The body-hash check alone passed happily on a register with
    text APPENDED AFTER THE TRAILER -- the body was untouched, so its hash
    matched, and the next build would have silently discarded the appended
    lines. An append is the single most likely way someone edits a generated
    file, so a guard blind to it is blind to the common case.

    The fix is to require that the on-disk text is EXACTLY body + trailer, with
    nothing after it. That subsumes the body check, but both are kept because
    they answer differently and an operator needs to know which happened.
    """
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8", newline="") as handle:
        on_disk = handle.read()

    trailer = read_trailer(on_disk)
    if trailer is None:
        raise RegisterError(
            "REFUSING to overwrite %s: it carries no readable build_register "
            "trailer, so this tool cannot tell it apart from a hand-written "
            "file. Nothing was written. Move it aside and re-run if it really "
            "is stale generated output." % path)

    body, _ = split_body_and_trailer(on_disk)
    actual = body_sha256(on_disk)
    expected_tail = _render_trailer(trailer["inputs_sha256"],
                                    trailer["body_sha256"])

    if actual == trailer["body_sha256"] and on_disk == body + expected_tail:
        return

    if actual != trailer["body_sha256"]:
        what = ("its body no longer hashes to the value its own trailer records"
                "\n  recorded body-sha256 %s\n  actual   body-sha256 %s"
                % (trailer["body_sha256"], actual))
    else:
        what = ("its body is intact but something was APPENDED AFTER THE "
                "TRAILER, which the body hash alone cannot see")

    diff = "\n".join(difflib.unified_diff(
        replacement.splitlines(), on_disk.splitlines(),
        fromfile="what this tool would generate",
        tofile="what is on disk (%s)" % os.path.basename(path),
        lineterm=""))
    raise RegisterError(
        "REFUSING to regenerate %s: it has been edited since it was generated "
        "-- %s.\n"
        "NOTHING WAS WRITTEN. The register is GENERATED; if this edit is right, "
        "the artifact's results/figures.json or its register-fragment is what "
        "should change.\n%s" % (path, what, diff))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="build_register",
        description="Generate the backing-artifacts register from the artifacts "
                    "themselves. It is never hand-edited and never "
                    "copied into.")
    parser.add_argument("--artifacts-root", default=None)
    parser.add_argument("--fragments-dir", default=None)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--register", default=None)
    parser.add_argument("--mirror", default=None)
    parser.add_argument("--report", default=None)
    parser.add_argument("--allow-shortfall", action="store_true",
                        help="report expected != found without failing; for a "
                             "program still mid-build")
    args = parser.parse_args(list(argv) if argv is not None else None)

    scan_root = os.path.abspath(str(args.artifacts_root
                                    or default_artifacts_root()))
    try:
        result = build(artifacts_root=args.artifacts_root,
                       fragments_dir=args.fragments_dir,
                       manifest_path=args.manifest,
                       register_path=args.register,
                       mirror_path=args.mirror,
                       allow_shortfall=args.allow_shortfall)
    except RegisterError as exc:
        message = str(exc)
        code = (core.EXIT_DID_NOT_RUN if message.startswith("DID-NOT-RUN")
                else core.EXIT_FINDING)
        sys.stdout.write("scanned %s\n" % scan_root)
        sys.stdout.write("%s\n" % message)
        if args.report:
            core.atomic_write_json(
                args.report,
                {"schema": SCHEMA, "schema_version": SCHEMA_VERSION,
                 "scan_root": scan_root, "error": message, "exit_code": code},
                ensure_ascii=False)
        return code

    sys.stdout.write("scanned %s\n" % result["scan_root"])
    sys.stdout.write("expected %d, found %d\n"
                     % (result["expected"], result["found"]))
    sys.stdout.write("excluded: %d (reasons recorded)\n" % result["excluded"])
    for slug in result["excluded_slugs"]:
        sys.stdout.write("  %s: %s\n" % (slug, result["excluded_reasons"][slug]))
    if result["missing_figures"]:
        sys.stdout.write("missing figures.json (%d): %s\n"
                         % (len(result["missing_figures"]),
                            ", ".join(result["missing_figures"])))
    if result["missing_fragments"]:
        sys.stdout.write("missing register-fragment (%d): %s\n"
                         % (len(result["missing_fragments"]),
                            ", ".join(result["missing_fragments"])))
    sys.stdout.write("inputs-sha256 %s\n" % result["inputs_sha256"])
    sys.stdout.write("wrote %s\n" % result["register"])
    sys.stdout.write("wrote %s\n" % result["mirror"])

    if args.report:
        core.atomic_write_json(args.report, result, ensure_ascii=False)

    if result["missing_fragments"]:
        return core.EXIT_FINDING
    if result["shortfall"] and not args.allow_shortfall:
        return core.EXIT_FINDING
    return core.EXIT_PASS


if __name__ == "__main__":
    raise SystemExit(main())
