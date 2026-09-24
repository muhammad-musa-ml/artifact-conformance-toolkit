"""CHECK-20 -- a built slug that left its collections entry uncorrected.

    python check_20.py <artifact> [--manifest FILE] [--live-store DIR]
                                  [--records-dir DIR] [--report FILE]
                                  [--min-population N]

the project requirements document states the check verbatim: "Fails when a slug the manifest marks
`built` has left its collections entry uncorrected -- every bullet id the manifest
maps to that slug must carry either a recorded correction or a recorded
confirmation, its designed-not-yet-measured marker must be gone, and the phase
record must carry the before/after rows. Exit 2 on a zero population."

THE ONE CHECK THAT LOOKS OUTSIDE THE ARTIFACT, AND WHY IT HAS TO
-----------------------------------------------------------------
Every other checker asks whether an artifact is well formed. This one asks
whether the artifact's existence CHANGED ANYTHING. Without it an example project can
run end to end, satisfy all eleven other checkers, take its register row, and
leave the collections entry exactly as it was -- every light green, the entire
deliverable skipped. That state is invisible from inside the artifact by
construction, because nothing inside it records what the claim used to say.

So this check reads three things that live outside the directory under test:

    the expected set     which slugs are built, and which claims they map to
    the live entries     whether each claimed row still carries its marker
    the records          whether a measurement was recorded, with before/after

THE ARTIFACT NEVER SUPPLIES THEM. All three are resolved from the command line,
from the runner's context, or from this repository -- never from inside the
directory being judged. A checker the thing being checked can point at its own
evidence is not a checker, and that sentence is already written down in this
programme about the `status` field one file over.

THE POPULATION IS THE BUILT SLUGS. THE OBLIGATIONS ARE A SECOND NUMBER.
-------------------------------------------------------------------------
The requirement's failure condition names a SLUG -- "a slug the manifest marks
built has left its collections entry uncorrected" -- so the verdict rests on the
built slugs, and ZERO BUILT SLUGS IS THE REFUSAL: saying "no built path has left
its entry uncorrected" over no built paths at all is a true sentence and not a
result.

The OBLIGATIONS those slugs carry are counted separately and printed beside the
first number, never folded into it. The two answer different questions and this
programme has measured, twice, what happens when one number stands in for
another: a run that examined two slugs carrying no claims and a run that
examined two slugs' claims are different runs, and only the printed pair can
tell them apart. A built slug that maps to no claim is LISTED by name in
`slugs_without_obligation`, because an input excluded without being counted is
an input that was silently dropped.

BOTH MAPPING FIELDS COUNT, AND THE SECOND IS THE LIVE CASE
------------------------------------------------------------
The expected set splits the mapping deliberately: `bullets` is the set a build
path is responsible for backing, `backs_bullets` is what an ALREADY-EXISTING
artifact is cited as backing. Reading only the first would make this check blind
to precisely the slug in the committed expected set that is already `built` AND
already cited -- a confident zero produced by the scope of the needle rather
than by the state of the world. The union is the obligation set, and the report
prints which field each obligation arrived through.

FOUR FINDING KINDS, AND WHY EACH IS SEPARATE FROM THE OTHERS
--------------------------------------------------------------
    no-correction     the records name no verdict for this claim. Silence is
                      not a result: "the measurement agreed" is a FINDING about
                      the world and has to be stated, never inferred from a row
                      nobody touched.
    no-before-after   a record names a verdict and does not say what moved. A
                      later reader cannot tell a corrected figure from an
                      unchanged one, which is the whole content of the record.
    marker-present    the live row still carries its not-yet-measured marker.
                      Independent of the record on purpose: a check that stopped
                      at the record would pass a claim that is recorded as
                      measured and still disclosed as designed.
    missing-row       the live entry carries no row with that id at all. Its
                      marker is gone trivially, because there is nothing to
                      carry one -- so a check that asked only "is the marker
                      gone" would report the absence as a correction. This kind
                      SUPPRESSES `marker-present` for the same id, because a
                      marker cannot be evaluated on a row that is not there;
                      it does not suppress `no-correction`, which is a separate
                      and separately true fact.

THE MARKER NEEDLE IS READ, NEVER RE-DECLARED
----------------------------------------------
`tools/check_canon_backing.py` owns the marker and the reason its needle stops
where it does: the canon wording INTERPOLATES an example project id, so a longer,
more specific-looking literal matches one canon's rows and none of the other's
-- it halves the population and reports no error. A second copy of that needle
here would be a second thing to keep true, so the needle is imported from that
module by path and this file declares none of its own. When that module is not
reachable -- a vendored copy inside an artifact has no tools/ directory -- the
check REFUSES with code 2 and says so, rather than falling back to a literal
nobody reconciled.

EXIT CODES (canonkit's contract, a design rule)
    0  every obligation of every built slug is recorded, corrected and unmarked
    1  at least one finding above. The check DID look.
    2  it could not look: no expected set, no reachable marker definition, an
       unreadable live entry, zero built slugs, or a population below the
       effective floor.

VENDORING. Enumerated into the vendored set by tools/vendor.py's check-module
glob. A VENDORED COPY CANNOT REACH the expected set, the marker definition or
the live entries -- an artifact has none of them -- so a vendored run refuses
with code 2 and names what was missing, rather than inventing any of the three.
Run BY PATH under a bare module name, never as a dotted package module. Stdlib
only, ASCII only.
"""

import argparse
import importlib.util
import json
import os
import sys

CHECK_ID = "CHECK-20"

# a design rule: the POPULATION floor, declared per-check IN CODE, overridable on the
# command line, and the EFFECTIVE value is what prints as `floor=`. One built
# slug is the smallest population over which this check means anything.
DEFAULT_FLOOR = 1

SCHEMA = "canonkit/check-20/1"

HERE = os.path.dirname(os.path.abspath(__file__))

# `tools/` in this repository, `<artifact>/` in a vendored copy. ONE expression
# for both layouts: the checks package always sits one directory below the core.
CORE_ROOT = os.path.dirname(HERE)

# The repository root in this repository; the ARTIFACTS root in a vendored copy.
SOURCE_ROOT = os.path.dirname(CORE_ROOT)

MANIFEST_RELATIVE = os.path.join("tools", "manifest.json")
BACKING_MODULE_RELATIVE = "check_canon_backing.py"
# The module that OWNS the fragment-name predicate. Loaded by path for the same
# reason the marker needle is: there must be only one copy of it.
ASSEMBLER_MODULE_RELATIVE = "assemble_records.py"
RECORDS_RELATIVE = os.path.join("_records", "corrections")

# The live store sits BESIDE this repository, never inside it. Declared relative
# to the source root for the reason every path in this programme is: a tracked
# file must not bake in a home directory.
LIVE_STORE_RELATIVE = os.path.join("..", "information")

STATUS_BUILT = "built"

# The record's shape. Four line prefixes, parsed in order; `bullet:` opens a
# block and everything until the next `bullet:` belongs to it.
RECORD_GLOB_SUFFIX = ".md"
KEY_BULLET = "bullet:"
KEY_VERDICT = "verdict:"
KEY_BEFORE = "before:"
KEY_AFTER = "after:"

# What a verdict may say. A measurement either moved the figure or agreed with
# it, and BOTH are results. An unrecognised word is not silently accepted:
# a record saying something this check does not understand is a record nobody
# reconciled, and reading it as a pass would make the vocabulary unbounded.
VERDICTS = ("corrected", "confirmed")

FINDING_NO_CORRECTION = "no-correction"
FINDING_NO_BEFORE_AFTER = "no-before-after"
FINDING_MARKER_PRESENT = "marker-present"
FINDING_MISSING_ROW = "missing-row"

FINDING_PREFIX = "backing"

MAX_LISTED_FINDINGS = 20


class CheckRefusal(Exception):
    """The check could not look. Carries the note printed beside code 2."""


def load_core():
    """Load the frozen core BY PATH, as a sibling. Never a dotted import."""
    path = os.path.join(CORE_ROOT, "canonkit.py")
    spec = importlib.util.spec_from_file_location("frozen_core", path)
    if spec is None or spec.loader is None:
        raise ImportError("could not build an import spec for %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_contract():
    """The check-module contract (CheckResult, CheckContext).

    PREFERS AN ALREADY-LOADED COPY, for the reason check_03.py records: a runner
    that loaded the package holds one class object, and loading __init__.py by
    path a second time would mint a SECOND CheckResult class that the runner
    would reject as foreign despite being structurally identical.
    """
    target = os.path.realpath(os.path.join(HERE, "__init__.py"))
    for module in list(sys.modules.values()):
        origin = getattr(module, "__file__", None)
        if not origin or not hasattr(module, "CheckResult"):
            continue
        try:
            if os.path.realpath(origin) == target:
                return module
        except (OSError, ValueError):
            continue
    spec = importlib.util.spec_from_file_location("check_contract", target)
    if spec is None or spec.loader is None:
        raise ImportError("could not build an import spec for %s" % target)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_backing():
    """The module that OWNS the marker needle and the entry layout.

    Loaded by path under a bare stem, never as a dotted package module. A
    vendored copy has no tools/ directory, so this raises CheckRefusal there
    rather than falling back to a re-declared needle -- the whole point of
    reading it from one place is that there is only one place.
    """
    path = os.path.join(CORE_ROOT, BACKING_MODULE_RELATIVE)
    if not os.path.isfile(path):
        raise CheckRefusal(
            "the marker definition is not reachable at %s, so this check has no "
            "way to tell a disclosed figure from a measured one. Re-declaring "
            "the needle here would be a second copy of a literal whose exact "
            "length is the thing that makes it match both canons. REPAIR: run "
            "from the tooling repository." % path)
    spec = importlib.util.spec_from_file_location(
        "canon_backing_for_check_20", path)
    if spec is None or spec.loader is None:
        raise CheckRefusal("could not build an import spec for %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_assembler():
    """The module that OWNS the record-fragment name predicate.

    Same contract as :func:`load_backing`, for the same reason: re-declaring
    `FRAGMENT_RE` here would be a second copy of the one predicate that decides
    whether a file in a records directory is a RECORD or is documentation, and
    a drift between the two copies is invisible from a green run.
    """
    path = os.path.join(CORE_ROOT, ASSEMBLER_MODULE_RELATIVE)
    if not os.path.isfile(path):
        raise CheckRefusal(
            "the record-fragment name predicate is not reachable at %s, so this "
            "check cannot tell a record from a README. Selecting on the `.md` "
            "suffix instead is the measured defect this loader exists to "
            "prevent: the corrections README's worked example names a real "
            "claim, and reading it satisfied this check with no record on disk. "
            "REPAIR: run from the tooling repository." % path)
    spec = importlib.util.spec_from_file_location(
        "assemble_records_for_check_20", path)
    if spec is None or spec.loader is None:
        raise CheckRefusal("could not build an import spec for %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Reading the three inputs
# ---------------------------------------------------------------------------


def default_manifest_path():
    return os.path.join(SOURCE_ROOT, MANIFEST_RELATIVE)


def default_live_store():
    return os.path.join(SOURCE_ROOT, LIVE_STORE_RELATIVE)


def default_records_dir():
    return os.path.join(SOURCE_ROOT, RECORDS_RELATIVE)


def read_manifest(path):
    """The expected set. Raises CheckRefusal -- every refusal is a code 2."""
    path = str(path)
    if not os.path.isfile(path):
        raise CheckRefusal(
            "no expected set at %s, so there is nothing that says which slugs "
            "are built or which claims they map to. A vendored copy inside an "
            "artifact cannot reach one -- an artifact has no tools/ directory. "
            "REPAIR: pass --manifest, or run from the tooling repository."
            % path)
    try:
        with open(path, "r", encoding="utf-8", newline="") as handle:
            payload = json.loads(handle.read())
    except (OSError, ValueError) as error:
        raise CheckRefusal("%s could not be read as JSON: %s" % (path, error))
    if not isinstance(payload, dict) or not isinstance(payload.get("slugs"), list):
        raise CheckRefusal(
            "%s carries no slugs[]. An expected set with no members produces a "
            "comparison in which everything agrees and nothing was checked."
            % path)
    return payload


def built_entries(manifest):
    """Every slug the expected set marks built, with its obligation set.

    The obligation set is the UNION of both mapping fields, each obligation
    tagged with the field it arrived through so the report can say so.
    """
    out = []
    for slug in manifest.get("slugs") or []:
        if not isinstance(slug, dict) or not slug.get("slug"):
            continue
        if str(slug.get("status") or "") != STATUS_BUILT:
            continue
        obligations = {}
        for field in ("bullets", "backs_bullets"):
            for bullet in slug.get(field) or []:
                if isinstance(bullet, str) and bullet:
                    obligations.setdefault(bullet, field)
        out.append({
            "slug": str(slug["slug"]),
            "canon": slug.get("canon"),
            "obligations": obligations,
        })
    return sorted(out, key=lambda item: item["slug"])


def read_live_rows(live_store, backing):
    """{canon: {row_id: row_text}} for both live entries.

    BOTH entries are read, always. Reading one of two and reporting the result
    would make a missing entry indistinguishable from an entry with nothing to
    correct, which is a smaller population with no error attached to it.
    """
    rows = {}
    for spec in backing.LIVE_ENTRIES:
        path = os.path.join(str(live_store),
                            spec["relative"].replace("/", os.sep))
        if not os.path.isfile(path):
            raise CheckRefusal(
                "no live collections entry at %s. An entry that cannot be read is "
                "not an entry with nothing to correct, and treating it as one "
                "would shrink this check's reach with no error anywhere. "
                "REPAIR: pass --live-store pointing at the directory that holds "
                "both entries." % path)
        try:
            with open(path, "rb") as handle:
                entry = json.loads(handle.read().decode("utf-8"))
        except (OSError, ValueError, UnicodeDecodeError) as error:
            raise CheckRefusal("%s could not be read: %s" % (path, error))
        canon = spec["canon"]
        rows[canon] = {}
        for key, text in backing.live_metric_rows(entry, canon):
            rows[canon][key.split(":", 1)[1]] = text
    return rows


def parse_record(text):
    """Every block in one record fragment, as {bullet: {verdict, before, after}}.

    A `bullet:` line OPENS a block; the three other keys attach to the open
    block. A key appearing before any `bullet:` belongs to nothing and is
    ignored rather than attached to the next block, because attaching it would
    silently satisfy a condition for a claim the record never named.
    """
    blocks = {}
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith(KEY_BULLET):
            current = line[len(KEY_BULLET):].strip()
            blocks.setdefault(current, {"verdict": "", "before": "", "after": ""})
            continue
        if current is None:
            continue
        for key, field in ((KEY_VERDICT, "verdict"), (KEY_BEFORE, "before"),
                           (KEY_AFTER, "after")):
            if line.startswith(key):
                blocks[current][field] = line[len(key):].strip()
                break
    return blocks


def read_records(records_dir, ignored=None):
    """{bullet_id: block} across every fragment in `records_dir`.

    A missing directory is an EMPTY record set rather than a refusal: "nothing
    has been recorded yet" is the programme's true state today and is exactly
    what this check is supposed to report as a finding, not as an inability to
    look. An UNREADABLE directory is different and does refuse.

    ONLY FRAGMENTS ARE READ, and this is the whole point rather than a detail.
    Selecting on the `.md` suffix read `_records/corrections/README.md`, whose
    worked example is a fenced block spelling out the real claim id:

        bullet: example-beta:P5-B3
        verdict: corrected
        before: <the row exactly as the entry carried it, marker and all>

    `parse_record` cannot see a fence, so the documentation that explains the
    format SATISFIED the check that reads it -- measured 2026-09-20: with the
    live marker cleared and NO fragment on disk, this check reported
    `PASS found=0`, and the same run against an empty directory reported
    `FAIL found=1 no-correction`. A green run could not show the difference,
    because the block it wanted was supplied by the wrong file.

    The predicate is `assemble_records.FRAGMENT_RE`, loaded by path so there is
    exactly one copy of it, and it is STRUCTURAL rather than a blacklist for the
    reason that module already states: "everything except README.md" needs
    editing every time someone drops a new non-fragment beside the records.
    Ignored names are COUNTED and NAMED through `ignored`, because a scan that
    does not say what it skipped cannot be audited.
    """
    blocks = {}
    root = str(records_dir)
    if not os.path.isdir(root):
        return blocks
    fragment_re = load_assembler().FRAGMENT_RE
    try:
        listing = sorted(name for name in os.listdir(root)
                         if name.endswith(RECORD_GLOB_SUFFIX))
    except OSError as error:
        raise CheckRefusal("%s could not be listed: %s" % (root, error))
    names = [name for name in listing if fragment_re.match(name)]
    if ignored is not None:
        ignored.extend(name for name in listing if not fragment_re.match(name))
    for name in names:
        path = os.path.join(root, name)
        try:
            with open(path, "r", encoding="utf-8", newline="") as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError) as error:
            raise CheckRefusal("%s could not be read: %s" % (path, error))
        for bullet, block in parse_record(text).items():
            # A later fragment supersedes an earlier one for the same claim, in
            # the timestamp order the filenames already sort by.
            blocks[bullet] = dict(block, source=name)
    return blocks


# ---------------------------------------------------------------------------
# THE DETECTION. Isolated in one function so the RED commit stubs exactly this
# and the GREEN commit replaces exactly this.
# ---------------------------------------------------------------------------


def _finding(kind, slug, bullet, detail):
    return {
        "kind": kind,
        "id": "%s:%s:%s" % (FINDING_PREFIX, kind, bullet),
        "slug": slug,
        "bullet": bullet,
        "detail": detail,
    }


def backing_findings(entries, live_rows, blocks, marker):
    """Every way a built slug can have left its entry uncorrected.

    Takes only values -- no filesystem, no module loading -- so what it decides
    is entirely a function of what it is handed.
    """
    findings = []
    for entry in entries:
        slug = entry["slug"]
        for bullet in sorted(entry["obligations"]):
            canon, _, row_id = bullet.partition(":")
            row = (live_rows.get(canon) or {}).get(row_id)
            block = blocks.get(bullet)

            if block is None:
                findings.append(_finding(
                    FINDING_NO_CORRECTION, slug, bullet,
                    "the records name no verdict for this claim. A measurement "
                    "that agreed is a RESULT and has to be stated; an untouched "
                    "row says only that nobody looked."))
            elif block.get("verdict") not in VERDICTS:
                findings.append(_finding(
                    FINDING_NO_CORRECTION, slug, bullet,
                    "the record for this claim carries verdict %r, which is not "
                    "one of %s. A word this check does not understand is a "
                    "record nobody reconciled."
                    % (block.get("verdict", ""), list(VERDICTS))))
            elif not block.get("before") or not block.get("after"):
                findings.append(_finding(
                    FINDING_NO_BEFORE_AFTER, slug, bullet,
                    "the record names a verdict and does not say what moved. "
                    "Without the before and after rows a reader cannot tell a "
                    "corrected figure from an unchanged one, which is the whole "
                    "content of the record."))

            if row is None:
                findings.append(_finding(
                    FINDING_MISSING_ROW, slug, bullet,
                    "the live entry carries no row with this id. Its marker is "
                    "gone only because there is nothing to carry one, so a "
                    "check that asked whether the marker had gone would read "
                    "the absence as a correction."))
                continue
            if marker in row:
                findings.append(_finding(
                    FINDING_MARKER_PRESENT, slug, bullet,
                    "the live row still carries its not-yet-measured marker, so "
                    "the entry still discloses this figure as designed however "
                    "the records describe it."))
    return findings


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


def waiver_ids(waivers):
    """The finding ids an owner-authored waiver suppresses for THIS check."""
    ids = set()
    for waiver in waivers or []:
        if not isinstance(waiver, dict):
            continue
        check = waiver.get("check") or waiver.get("check_id")
        if check != CHECK_ID:
            continue
        for key in ("finding_id", "id"):
            value = waiver.get(key)
            if isinstance(value, str) and value:
                ids.add(value)
    return ids


def run(artifact, ctx=None, manifest_path=None, live_store=None,
        records_dir=None):
    """Measure. Returns a CheckResult. DOES NOT PRINT -- the caller prints."""
    core = load_core()
    contract = load_contract()
    ctx = ctx if ctx is not None else contract.CheckContext()
    floor = ctx.floor_for(CHECK_ID, DEFAULT_FLOOR)
    artifact = os.path.abspath(str(artifact))

    # THE RUNNER'S OWN COPY WINS WHEN IT HAS ONE, exactly as check_05 resolves
    # it: conformance.py reads the expected set once and hands it to every check
    # through CheckContext(manifest=...), and re-reading it from disk here would
    # give this check a SECOND source of truth that can disagree with the one
    # the runner printed its scan root from. An explicit --manifest still wins
    # over both, because a caller naming a file means it.
    explicit = manifest_path is not None
    supplied = getattr(ctx, "manifest", None)
    usable_supplied = (isinstance(supplied, dict)
                       and isinstance(supplied.get("slugs"), list)
                       and bool(supplied["slugs"]))

    if explicit:
        manifest_name = os.path.abspath(str(manifest_path))
    elif usable_supplied:
        manifest_name = "the expected set supplied by the runner"
    else:
        manifest_name = default_manifest_path()

    # The other two are read by NAME off the context when a runner supplies
    # them, which the contract invites: a check module reads what it needs by
    # name and never assumes the context's field set is closed.
    store = (live_store if live_store is not None
             else getattr(ctx, "live_store", "") or default_live_store())
    store = os.path.abspath(str(store))
    record_root = (records_dir if records_dir is not None
                   else getattr(ctx, "records_dir", "") or default_records_dir())
    record_root = os.path.abspath(str(record_root))

    def refused(note, detail=None):
        # EVERY refusal names the two out-of-artifact inputs it WOULD have read.
        #
        # This is a safety property, not decoration. These two paths are the only
        # way any check in this repository reaches outside the directory under
        # test, and one of them is the owner's live private record; the runner
        # pins them to a fixture for tests, and `test_the_runner_pins_check_20_
        # away_from_the_real_private_record` proves the pin held by reading them
        # off this line. Printing them only on the paths that produce a VERDICT
        # would mean the pin is unobservable exactly when the check declined to
        # look -- and "it refused" is not evidence about which store it refused
        # against. an earlier plan added refusals that fire before any verdict, which
        # is what made this reachable.
        note = ("%s | live-store=%s records=%s"
                % (note, store.replace(chr(92), "/"),
                   record_root.replace(chr(92), "/")))
        result = contract.CheckResult(
            check_id=CHECK_ID, code=core.EXIT_DID_NOT_RUN, found=0, checked=0,
            floor=floor, waived=0, note=note)
        base = {
            "artifact": artifact, "manifest": manifest_name,
            "live_store": store, "records_dir": record_root,
            "built_slugs": 0, "obligations": 0,
            "slugs_without_obligation": [], "findings": [],
        }
        base.update(detail or {})
        result.detail = base
        return result

    try:
        backing = load_backing()
        if explicit or not usable_supplied:
            manifest = read_manifest(manifest_name)
        else:
            manifest = supplied
    except CheckRefusal as refusal:
        return refused(str(refusal))

    # THE PROGRAMME-WIDE VIEW. Computed in full and kept, because the verdict
    # narrows and the COUNTS do not: a narrower scope that hides the wider fact
    # is the population line lying by omission. These feed the note and the
    # structured detail a project requirement and a project requirement read at closeout, which is the
    # right reader for a programme-level obligation. Ruling: the scope decision.
    entries = built_entries(manifest)
    without = sorted(entry["slug"] for entry in entries
                     if not entry["obligations"])
    obligations = sum(len(entry["obligations"]) for entry in entries)

    # The 0/0 refusal, BEFORE the floor is consulted. "No built path has left
    # its entry uncorrected" is a TRUE sentence over zero built paths and it is
    # not a result, and no --min-population value may talk this check into
    # calling it one.
    if not entries:
        return refused(
            "the expected set marks nothing as built, so there is no path that "
            "could have left an entry uncorrected. A verdict over that "
            "population is a true sentence about nothing. REPAIR: an expected "
            "set with at least one built slug -- a field only the owner and the "
            "plan set may write.")

    # a design rule plus the scope ruling: THIS CHECK ANSWERS FOR THE ARTIFACT
    # IT WAS HANDED.
    #
    # Measured before this change and committed at _records/pre-fix/: pointed at
    # redis and at es-log, this module printed the SAME line byte for byte,
    # including the trailing slug name, and printed it from a pytest temp
    # directory too. A check whose output does not depend on its input has not
    # examined its input.
    #
    # The slug comes from the runner when there is one, and there is not always
    # one -- main() below builds a CheckContext with no artifact_slug, which is
    # how the CLI, every test in test_check_20.py and a vendored copy inside an
    # artifact all invoke this. An empty context falls back to the directory's
    # own basename, the derivation conformance.py::self_module_check uses.
    slug_under_test = (getattr(ctx, "artifact_slug", "") or "").strip()
    if not slug_under_test:
        slug_under_test = os.path.basename(artifact.rstrip("/" + chr(92)))

    programme = {
        "built_slugs": len(entries),
        "obligations": obligations,
        "slugs_without_obligation": without,
        "slug_under_test": slug_under_test,
    }

    mine = [entry for entry in entries if entry["slug"] == slug_under_test]
    if not mine:
        return refused(
            "`%s` is not a slug this expected set marks BUILT, so it owes no "
            "correction and there is nothing here for this check to judge. A "
            "verdict would be a statement about a path that has not run. The "
            "programme-level figures are recorded in this result's detail "
            "rather than thrown away: %d built slug(s) carrying %d obligation(s)"
            ". REPAIR: point the check at a built artifact, or -- if this path "
            "really has run -- an owner or plan sets its status to `built`."
            % (slug_under_test, len(entries), obligations),
            programme)

    # A BUILT slug that owes nothing is NOT a pass. It is the 0/0 trap wearing
    # this check's clothes: "every obligation of this artifact is corrected" is
    # a true sentence over no obligations. It stays countable in `without`
    # above, so it is a stated fact rather than a silent absence.
    under_obligation = [entry for entry in mine if entry["obligations"]]
    if not under_obligation:
        return refused(
            "`%s` is marked built and carries NO obligation -- neither "
            "`bullets` nor `backs_bullets` names a claim for it -- so there is "
            "nothing whose correction could be checked. Reporting a pass here "
            "would be a verdict over zero. REPAIR: record what this path backs, "
            "or accept that it backs nothing, which the runner's applicability "
            "mechanism states rather than this module passing over it."
            % slug_under_test,
            programme)

    ignored_records = []
    try:
        live_rows = read_live_rows(store, backing) if under_obligation else {}
        blocks = (read_records(record_root, ignored=ignored_records)
                  if under_obligation else {})
    except CheckRefusal as refusal:
        return refused(str(refusal),
                       {"built_slugs": len(entries), "obligations": obligations,
                        "slugs_without_obligation": without})

    # SCOPED: only this artifact's own obligations are judged. Every finding
    # this check emits is about a bullet a specific slug owes, so unlike
    # CHECK-05 there is no kind that becomes unreachable when scoped -- each
    # built slug's run reports its own, and every obligation still has exactly
    # one run that reports it.
    findings = backing_findings(under_obligation, live_rows, blocks,
                                backing.LIVE_MARKER)

    # `missing-row` suppresses `marker-present` for the same claim: a marker
    # cannot be evaluated on a row that is not there. It does NOT suppress
    # `no-correction`, which is separately true and separately repairable.
    missing = {finding["bullet"] for finding in findings
               if finding["kind"] == FINDING_MISSING_ROW}
    findings = [finding for finding in findings
                if not (finding["kind"] == FINDING_MARKER_PRESENT
                        and finding["bullet"] in missing)]

    waived_ids = waiver_ids(getattr(ctx, "waivers", None))
    kept = [finding for finding in findings if finding["id"] not in waived_ids]
    waived = len(findings) - len(kept)

    checked = len(under_obligation)
    found = len(kept)
    if checked == 0 or checked < floor:
        code = core.EXIT_DID_NOT_RUN
    elif found:
        code = core.EXIT_FINDING
    else:
        code = core.EXIT_PASS

    # BOTH populations, as separate numbers: this artifact's obligations -- the
    # one the verdict rests on -- and the programme's built-slug count, so the
    # narrower scope cannot hide the wider fact. `built slugs` and `obligations`
    # keep their published spellings; test_the_note_prints_both_populations
    # matches on them.
    mine_obligations = sum(len(entry["obligations"]) for entry in mine)
    note = ("artifact %s: %d obligation(s), %d finding(s) | built slugs %d, of "
            "which %d under obligation | obligations %d | live-store=%s records=%s"
            % (slug_under_test, mine_obligations, found,
               len(entries), len([e for e in entries if e["obligations"]]),
               obligations,
               store.replace(chr(92), "/"), record_root.replace(chr(92), "/")))
    if without:
        note += (" | %d built slug(s) map to no claim: %s"
                 % (len(without), ", ".join(without)))
    # Named, not merely counted. A non-fragment sitting in the records directory
    # is exactly how this check was silently satisfied before 2026-09-20, so the
    # population line says which files were not read as records.
    note += (" | records read=%d ignored=%d%s"
             % (len(blocks), len(ignored_records),
                (": " + ", ".join(sorted(ignored_records)))
                if ignored_records else ""))

    result = contract.CheckResult(
        check_id=CHECK_ID, code=code, found=found, checked=checked, floor=floor,
        waived=waived, not_examined=len(without), note=note,
        finding_ids=sorted({finding["id"] for finding in kept}))
    result.detail = {
        "artifact": artifact,
        "manifest": manifest_name,
        "live_store": store,
        "records_dir": record_root,
        "built_slugs": len(entries),
        "obligations": obligations,
        "slugs_without_obligation": without,
        "slug_under_test": slug_under_test,
        "artifact_obligations": mine_obligations,
        "findings": kept,
    }
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_report(result, core):
    """The structured record, over stable fields only."""
    detail = getattr(result, "detail", {}) or {}
    return {
        "schema": SCHEMA,
        "schema_version": core.SCHEMA_VERSION,
        "check_id": result.check_id,
        "code": result.code,
        "found": result.found,
        "checked": result.checked,
        "listed": result.listed,
        "not_examined": result.not_examined,
        "floor": result.floor,
        "waived": result.waived,
        "finding_ids": list(result.finding_ids),
        "note": result.note,
        "manifest": detail.get("manifest", ""),
        "live_store": detail.get("live_store", ""),
        "records_dir": detail.get("records_dir", ""),
        "built_slugs": detail.get("built_slugs", 0),
        # PROGRAMME-wide, and it keeps that meaning: existing readers match on
        # it. The artifact's own count is a SEPARATE field rather than a
        # redefinition, because silently narrowing a published number is how a
        # reader ends up comparing two different populations without knowing it.
        "obligations": detail.get("obligations", 0),
        "artifact_obligations": detail.get("artifact_obligations", 0),
        "slug_under_test": detail.get("slug_under_test", ""),
        "slugs_without_obligation": list(
            detail.get("slugs_without_obligation", [])),
        "findings": detail.get("findings", []),
        "artifact": detail.get("artifact", ""),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="check_20",
        description="CHECK-20: fails when a slug the expected set marks built "
                    "has left its collections entry uncorrected.")
    parser.add_argument("artifact", nargs="?", default=".",
                        help="the artifact directory (default: the current one)")
    parser.add_argument("--manifest", default=None,
                        help="the expected set. Default: tools/manifest.json "
                             "beside this module's core.")
    parser.add_argument("--live-store", default=None,
                        help="the directory holding the collections entries. "
                             "Default: the store beside this repository.")
    parser.add_argument("--records-dir", default=None,
                        help="the directory holding the correction records. "
                             "Default: _records/corrections at the source root.")
    parser.add_argument("--report", default=None,
                        help="write the structured report here. A file "
                             "rather than a stream a caller has to capture: a "
                             "command joined to another process reports the "
                             "other process's exit status.")
    parser.add_argument("--min-population", type=int, default=None,
                        help="override the effective POPULATION floor. "
                             "The OVERRIDDEN value is what prints as floor=. It "
                             "cannot produce a pass over a population of zero.")
    args = parser.parse_args(argv)

    core = load_core()
    contract = load_contract()

    overrides = {}
    if args.min_population is not None:
        overrides[CHECK_ID] = args.min_population
    ctx = contract.CheckContext(floor_overrides=overrides)

    result = run(args.artifact, ctx, manifest_path=args.manifest,
                 live_store=args.live_store, records_dir=args.records_dir)

    core.report(CHECK_ID, result.code == core.EXIT_PASS, result.found,
                result.checked, result.floor, waived=result.waived,
                note=result.note, not_examined=result.not_examined, listed=result.listed)

    if result.checked and result.checked < result.floor:
        print("  DEMOTED to DID-NOT-RUN: population %d is below the effective "
              "floor %d." % (result.checked, result.floor))

    detail = getattr(result, "detail", {}) or {}
    for slug in detail.get("slugs_without_obligation", []):
        print("  maps to no claim    %s" % slug)
    for finding in detail.get("findings", [])[:MAX_LISTED_FINDINGS]:
        print("  %-18s %s: %s" % (finding["kind"], finding["bullet"],
                                  finding["detail"]))
    extra = len(detail.get("findings", [])) - MAX_LISTED_FINDINGS
    if extra > 0:
        print("  ... and %d more" % extra)

    if result.code == core.EXIT_DID_NOT_RUN and not result.checked:
        sys.stderr.write("%s %s\n" % (core.REFUSAL_PREFIX, result.note))
        sys.stderr.flush()

    if args.report:
        core.atomic_write_json(args.report, build_report(result, core))

    return result.code


if __name__ == "__main__":
    sys.exit(main())
