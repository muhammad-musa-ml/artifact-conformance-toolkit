"""canon_snapshot -- read the canons under a census, commit the bullets verbatim.

a design rule (HARD) fixes the MECHANISM: direct read of the canon JSON, wrapped in a
census snapshot before and a diff after, BOTH committed as the proof the
read-only store was untouched. a design rule fixes the OUTPUT: a verbatim snapshot of
every bullet, committed into this repository, so CHECK-09 is answerable offline
from a clean checkout.

THE ORDER IS THE PROOF, AND IT IS NOT REARRANGEABLE
---------------------------------------------------
    1. census snapshot  (before)
    2. THE READ         -- every source opened "rb", nothing opened for writing
    3. census snapshot  (after)
    4. diff             -- a NON-EMPTY diff is a failure and exits non-zero
    5. write tools/canon-bullets.json

Taking the "before" snapshot after the read, or skipping the diff because the
tool "obviously" does not write, would leave an assertion where a design rule asks for a
measurement.

WHY ensure_ascii=False HERE AND NOWHERE ELSE
--------------------------------------------
canonkit.atomic_write_json defaults to ensure_ascii=True because everything the
frozen core writes is ASCII by contract. This file deliberately passes
False: it stores VERBATIM canon text, and escaping it would destroy the
verbatim-ness that is the entire point of the snapshot. Two different settings
for two different files, each correct for what it writes. The core's own module
docstring names this file as the exception.

WHY THE COUNTS CARRY A COMMITTED LITERAL BESIDE THEM
-----------------------------------------------------
a design rule's shape, applied to the canon. A purely derived count silently stops
checking when its input shrinks -- expected falls to match found. The EXPECTED_*
constants below are the tripwire on the derivation's own input: if a canon is
re-archived with one bullet fewer, this tool FAILS instead of quietly publishing
48 as though it had always been 48.

The literals came from a measurement, not from a document. The research note
records the same figures, but a written record states what was true THEN; every
number below was re-derived by running this file.
"""

import argparse
import importlib.util
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load(stem, filename):
    path = os.path.join(_HERE, filename)
    spec = importlib.util.spec_from_file_location(stem, path)
    if spec is None or spec.loader is None:
        raise ImportError("could not build an import spec for %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = _load("frozen_core", "canonkit.py")
census = _load("census_live_store", "census_live_store.py")

SCHEMA = "canon-bullets/1"
SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# The sources. a project requirement is CLOSED; these four paths are the whole answer.
# ALL FOUR ARE READ-ONLY. Nothing in this repository ever writes under them.
#
# Stored RELATIVE to the live-store root so no absolute home path is baked into
# this tracked file.
# ---------------------------------------------------------------------------
LIVE_STORE_RELATIVE = os.path.join("..", "information")

SOURCES = (
    {"canon": "example-alpha", "role": "frozen_canon",
     "relative": "placeholders/_archive/example-alpha-canon-2026-09-07/canon.json"},
    {"canon": "example-beta", "role": "frozen_canon",
     "relative": "placeholders/_archive/example-beta-canon-2026-09-07/canon.json"},
    {"canon": "example-alpha", "role": "live_collections",
     "relative": "collections/collection-one/example-alpha/raw.json"},
    {"canon": "example-beta", "role": "live_collections",
     "relative": "collections/collection-two/example-beta/raw.json"},
)

CANON_SLUGS = ("example-alpha", "example-beta")

# ---------------------------------------------------------------------------
# THE COMMITTED LITERALS -- the tripwires on the derivation's own input.
# ---------------------------------------------------------------------------
EXPECTED_SOURCE_COUNT = 4
EXPECTED_BULLETS_TOTAL = 49
EXPECTED_PER_CANON = {"example-alpha": 20, "example-beta": 29}
EXPECTED_WITH_METRIC_BASIS = 49
EXPECTED_WITH_NOT_YET_RUN = 48
EXPECTED_ID_COLLISIONS = 17
EXPECTED_BUILD_PATH_SLUGS = 11
# A FLOOR, not an equality (loosened 2026-09-16). It was `==` until the boundary
# became scoped-write, and that equality would have failed the moment this
# program SUCCEEDED: a correction unions new `source_refs` and `evidence_quotes`
# into the live entry, so the quote count grows as artifacts land. An assertion
# that fires on the program's own output is not a guard, it is a tripwire across
# the exit.
#
# The constraint is not dropped, it is MOVED to the thing that genuinely must not
# change: every bullet id in the frozen canon must still be cited by the live
# entry (`_missing_quote_ids` below). That is strictly stronger than the count
# was -- a count of 20 could be satisfied by twenty quotes for nineteen bullets,
# and id coverage cannot.
EXPECTED_EVIDENCE_QUOTES = {"example-alpha": 20, "example-beta": 29}

# `<path> P1-B3: ...` -- how a live entry cites the bullet a quote came from.
QUOTE_ID_RE = re.compile(r"\b((?:BP-)?P\d+-B\d+)\s*:")

# The needle, at the length that actually matches. The longer literal
# `example project not yet run` misses ALL 20 alpha bullets, because alpha
# interpolates the project id (`example project P1 not yet run`). check_canon_backing
# refuses that override; the measurement behind the refusal is made here.
NOT_YET_RUN_NEEDLE = "not yet run"
LONG_NEEDLE = "example project not yet run"

# The slugs whose citation counts a project requirement's two exclusions depend on. Probed
# both document-scoped and bullet-scoped, because the two DISAGREE for
# example-search-benchmark and the disagreement is the finding.
PROBE_SLUGS = ("example-cache-benchmark", "example-search-benchmark",
               "alpha-substrate")

# `build_paths[i].artifact` is prose whose LEADING TOKEN is the slug, but the
# separator DIFFERS BETWEEN CANONS: alpha writes `slug: ...`, example-beta
# writes `slug - ...`. A parser keyed on one separator returns 6 or 5 instead of
# 11 and NOTHING ERRORS -- which is why the extraction asserts its own count.
SLUG_RE = re.compile(r"^([a-z0-9][a-z0-9-]*)\s*[:\-]\s")

BULLET_ID_RE = re.compile(r"^P(\d+)-B(\d+)$")
COMPOUND_KEY_RE = re.compile(r"^[a-z0-9-]+:P\d+-B\d+$")


# ---------------------------------------------------------------------------
# The READ. Binary only.
# ---------------------------------------------------------------------------

def read_json_bytes(path):
    """Open `path` in BINARY mode, hash the bytes, parse the decoded text.

    "rb" is not incidental. Reading as text would re-introduce the line-ending
    translation a design rule exists to prevent, and would make the recorded sha256
    differ from the one a reader computes. It is also the mode a test asserts:
    tools/tests/test_canon_bullets.py patches `open` and fails the run if any
    path under the live store is opened in a mode that could write.
    """
    with open(str(path), "rb") as handle:
        payload = handle.read()
    return payload, json.loads(payload.decode("utf-8"))


def _walk_strings(node, path="$"):
    """Yield (json_path, string) for every string anywhere under `node`.

    LOCATE rather than count. The research note measured the trap this exists to
    avoid: a document-scoped scan of example-beta's canon returns ONE hit for
    `example-search-benchmark`, and that hit is at $.consistency_notes[13],
    whose text says the artifact is "cited nowhere here" -- the canon's own
    words AFFIRMING the claim. A count alone inverts the finding; a location
    settles it.
    """
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for key in sorted(node):
            for item in _walk_strings(node[key], "%s.%s" % (path, key)):
                yield item
    elif isinstance(node, list):
        for index, value in enumerate(node):
            for item in _walk_strings(value, "%s[%d]" % (path, index)):
                yield item


def extract_build_path_slugs(canon):
    """Slug per example project, handling BOTH separators. Never a short list.

    Returns a list of {project, slug, artifact}. The caller asserts the count;
    this function reports what it found, including entries it could not parse,
    so a miss is visible rather than absent.
    """
    rows = []
    for entry in canon.get("build_paths") or []:
        artifact = entry.get("artifact") or ""
        match = SLUG_RE.match(artifact)
        rows.append({
            "project": entry.get("project") or entry.get("id") or "",
            "slug": match.group(1) if match else None,
            "artifact": artifact,
        })
    return rows


def collect_bullets(canon, canon_slug):
    """Every bullet in `$.projects[].bullets[]`, keyed `<canon>:<id>`.

    PERMISSIVE by design: two example-beta bullets (P4-B6, P5-B6) carry an extra
    `public: false` key, so a strict reader that rejects unknown keys fails on
    2 of 49. Unknown keys are carried through in `extra_keys` rather than
    rejected or silently dropped.
    """
    known = {"backing", "defense_note", "earliest_era", "fields", "id",
             "metric", "metric_basis", "skills", "text", "variants"}
    bullets = {}
    for project in canon.get("projects") or []:
        project_id = project.get("id") or ""
        for bullet in project.get("bullets") or []:
            bullet_id = bullet.get("id") or ""
            key = "%s:%s" % (canon_slug, bullet_id)
            match = BULLET_ID_RE.match(bullet_id)
            display_ref = None
            if canon_slug == "example-beta" and match:
                # NON-AUTHORITATIVE. ROADMAP and the project overview document call example-beta's
                # paths BP-1..BP-5 while the canon stores them as P1..P5, so
                # `BP-2` must resolve to example-beta:P2-B* and never to
                # example-alpha:P2-B*. The compound key stays the only address.
                display_ref = "BP-%s-B%s" % (match.group(1), match.group(2))
            bullets[key] = {
                "canon": canon_slug,
                "id": bullet_id,
                "project": project_id,
                "text": bullet.get("text"),
                "metric": bullet.get("metric"),
                "metric_basis": bullet.get("metric_basis"),
                "backing": bullet.get("backing"),
                "display_ref": display_ref,
                "extra_keys": sorted(set(bullet) - known),
            }
    return bullets


def _bullet_blob(bullet_obj):
    """Every string inside one raw bullet, joined. The BULLET-SCOPED surface."""
    return "\n".join(text for _, text in _walk_strings(bullet_obj))


def probe_slug_citations(canon, canon_slug, raw_text):
    """Document-scoped AND bullet-scoped counts for each probe slug.

    Both numbers are recorded because they DISAGREE, and the disagreement is
    what makes a project requirement's negative claim checkable rather than merely asserted.
    A single number here would have reported a false citation.
    """
    bullet_blobs = []
    for project in canon.get("projects") or []:
        for bullet in project.get("bullets") or []:
            bullet_blobs.append(_bullet_blob(bullet))
    joined_bullets = "\n".join(bullet_blobs)

    result = {}
    for slug in PROBE_SLUGS:
        locations = [path for path, text in _walk_strings(canon)
                     if slug in text]
        result[slug] = {
            "document": raw_text.count(slug),
            "bullets": joined_bullets.count(slug),
            "locations": locations,
            "bullet_population": len(bullet_blobs),
        }
    return result


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def _assert(condition, message):
    if not condition:
        core.die(core.EXIT_FINDING, "%s %s" % (core.REFUSAL_PREFIX, message))


def slug_count_message(found):
    """The `expected 11, found N` message, as a PURE function.

    Split out so a test can exercise the message on a deliberately mangled
    fixture without performing the whole live read. The wording is the
    load-bearing part: a parser keyed on one separator returns a SHORT LIST and
    nothing errors, so the count has to be stated as a disagreement rather than
    reported as a result.
    """
    return ("slug extraction expected %d, found %d. The separator differs "
            "between canons (`slug: ` vs `slug - `); a parser keyed on one "
            "returns a SHORT LIST and nothing errors."
            % (EXPECTED_BUILD_PATH_SLUGS, found))


def build_record(live_store, census_meta):
    """Read all four sources and assemble the canon-bullets record."""
    sources = []
    canons = {}
    raw_texts = {}

    for spec in SOURCES:
        path = os.path.join(live_store, spec["relative"].replace("/", os.sep))
        if not os.path.isfile(path):
            core.die(core.EXIT_DID_NOT_RUN,
                     "%s canon source missing: %s\n"
                     "  REPAIR: confirm the live store is at %s."
                     % (core.REFUSAL_PREFIX, path, live_store))
        payload, parsed = read_json_bytes(path)
        sources.append({
            "canon": spec["canon"],
            "role": spec["role"],
            "path": (LIVE_STORE_RELATIVE.replace(os.sep, "/") + "/"
                     + spec["relative"]),
            "sha256": core.sha256_bytes(payload),
            "bytes": len(payload),
            "read_at": core.now_local(),
        })
        if spec["role"] == "frozen_canon":
            canons[spec["canon"]] = parsed
            raw_texts[spec["canon"]] = payload.decode("utf-8")
        else:
            raw_texts[spec["canon"] + "::live"] = payload.decode("utf-8")
            canons.setdefault(spec["canon"] + "::live", parsed)

    _assert(len(sources) == EXPECTED_SOURCE_COUNT,
            "expected %d sources, read %d"
            % (EXPECTED_SOURCE_COUNT, len(sources)))

    bullets = {}
    per_canon = {}
    build_paths = {}
    slug_citations = {}
    evidence_quotes = {}

    for canon_slug in CANON_SLUGS:
        canon = canons[canon_slug]
        declared = canon.get("slug")
        _assert(declared == canon_slug,
                "canon at %s declares slug %r, expected %r -- the canon's own "
                "slug is the key every bullet is addressed by"
                % (canon_slug, declared, canon_slug))

        found = collect_bullets(canon, canon_slug)
        bullets.update(found)
        per_canon[canon_slug] = len(found)
        build_paths[canon_slug] = extract_build_path_slugs(canon)
        slug_citations[canon_slug] = probe_slug_citations(
            canon, canon_slug, raw_texts[canon_slug])

        live = canons[canon_slug + "::live"]
        quotes = live.get("evidence_quotes") or []
        evidence_quotes[canon_slug] = len(quotes)

    # ---- derived counts, each asserted against its committed literal --------
    total = len(bullets)
    _assert(total == EXPECTED_BULLETS_TOTAL,
            "derived %d bullets, committed literal says %d. A derived count "
            "that is allowed to fall to meet its input has stopped checking."
            % (total, EXPECTED_BULLETS_TOTAL))
    _assert(per_canon == EXPECTED_PER_CANON,
            "per-canon bullet counts %r != committed literal %r"
            % (per_canon, EXPECTED_PER_CANON))

    bad_keys = sorted(key for key in bullets if not COMPOUND_KEY_RE.match(key))
    _assert(not bad_keys,
            "%d bullet key(s) are not canon-qualified: %s"
            % (len(bad_keys), bad_keys))

    with_metric_basis = sum(1 for b in bullets.values()
                            if (b.get("metric_basis") or "").strip())
    _assert(with_metric_basis == EXPECTED_WITH_METRIC_BASIS,
            "derived %d bullets with metric_basis, literal says %d"
            % (with_metric_basis, EXPECTED_WITH_METRIC_BASIS))

    not_yet_run_ids = sorted(
        key for key, b in bullets.items()
        if NOT_YET_RUN_NEEDLE in "\n".join(
            str(b.get(field) or "")
            for field in ("text", "metric", "metric_basis", "backing")))
    _assert(len(not_yet_run_ids) == EXPECTED_WITH_NOT_YET_RUN,
            "derived %d bullets containing %r, literal says %d"
            % (len(not_yet_run_ids), NOT_YET_RUN_NEEDLE,
               EXPECTED_WITH_NOT_YET_RUN))

    ids_by_canon = {slug: {b["id"] for b in bullets.values()
                           if b["canon"] == slug}
                    for slug in CANON_SLUGS}
    collisions = sorted(ids_by_canon[CANON_SLUGS[0]]
                        & ids_by_canon[CANON_SLUGS[1]])
    _assert(len(collisions) == EXPECTED_ID_COLLISIONS,
            "derived %d colliding bullet ids, literal says %d: %s"
            % (len(collisions), EXPECTED_ID_COLLISIONS, collisions))

    all_slugs = [row["slug"] for rows in build_paths.values() for row in rows]
    parsed_slugs = [slug for slug in all_slugs if slug]
    _assert(len(parsed_slugs) == EXPECTED_BUILD_PATH_SLUGS,
            slug_count_message(len(parsed_slugs)))

    # A FLOOR. Growth is the program working: each correction unions new
    # provenance into the live entry. A DROP is still a finding, because a
    # correction never removes a bullet's grounding.
    for canon_slug in CANON_SLUGS:
        floor = EXPECTED_EVIDENCE_QUOTES[canon_slug]
        _assert(evidence_quotes[canon_slug] >= floor,
                "%s: evidence_quotes fell to %d, below the committed floor of "
                "%d -- growth is expected as artifacts land, a DROP means a "
                "bullet lost its grounding, which is exactly the detection a design rule "
                "exists to provide"
                % (canon_slug, evidence_quotes[canon_slug], floor))
        _assert(evidence_quotes[canon_slug] >= per_canon[canon_slug],
                "%s: evidence_quotes has %d entries but the canon has %d "
                "bullets -- fewer quotes than bullets means at least one bullet "
                "is uncited" % (canon_slug, evidence_quotes[canon_slug],
                                per_canon[canon_slug]))

    # The constraint the count used to stand in for, stated directly: every
    # frozen bullet id is still cited by the live entry. Strictly stronger than
    # the equality it replaces -- twenty quotes covering nineteen bullets
    # satisfied the count and does not satisfy this.
    for canon_slug in CANON_SLUGS:
        live = canons[canon_slug + "::live"]
        cited = set()
        for quote in (live.get("evidence_quotes") or []):
            cited.update(QUOTE_ID_RE.findall(str(quote)))
        expected_ids = {b["id"] for b in bullets.values()
                        if b["canon"] == canon_slug}
        missing = sorted(expected_ids - cited)
        _assert(not missing,
                "%s: %d of %d frozen bullet id(s) are no longer cited by the "
                "live entry's evidence_quotes: %s"
                % (canon_slug, len(missing), len(expected_ids), missing))

    # The exception the needle count implies, NAMED rather than left as a gap.
    missing_needle = sorted(set(bullets) - set(not_yet_run_ids))

    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "generated_at": core.now_local(),
        "generated_at_utc": core.now_utc(),
        "census": census_meta,
        "sources": sources,
        "build_paths": build_paths,
        "slug_citations": slug_citations,
        "bullets": bullets,
        "counts": {
            "sources": len(sources),
            "bullets_total": total,
            "per_canon": per_canon,
            "with_metric_basis": with_metric_basis,
            "with_not_yet_run": len(not_yet_run_ids),
            "not_yet_run_exceptions": missing_needle,
            "id_collisions": len(collisions),
            "id_collisions_list": collisions,
            "build_path_slugs": len(parsed_slugs),
            "evidence_quotes_per_canon": evidence_quotes,
        },
        "expected": {
            "sources": EXPECTED_SOURCE_COUNT,
            "bullets_total": EXPECTED_BULLETS_TOTAL,
            "per_canon": dict(EXPECTED_PER_CANON),
            "with_metric_basis": EXPECTED_WITH_METRIC_BASIS,
            "with_not_yet_run": EXPECTED_WITH_NOT_YET_RUN,
            "id_collisions": EXPECTED_ID_COLLISIONS,
            "build_path_slugs": EXPECTED_BUILD_PATH_SLUGS,
            "evidence_quotes_per_canon": dict(EXPECTED_EVIDENCE_QUOTES),
        },
        "needles": {
            "not_yet_run": NOT_YET_RUN_NEEDLE,
            "long_form_refused": LONG_NEEDLE,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="canon_snapshot.py",
        description="Read the canons under a committed census and snapshot "
                    "their bullets verbatim (the design rules).")
    parser.add_argument("--live-store", default=None,
                        help="root of the live store (this tool only READS it)")
    parser.add_argument("--out", default=None,
                        help="where canon-bullets.json is written")
    parser.add_argument("--records-dir", default=None,
                        help="where the census pair is written")
    parser.add_argument("--label", default="canon-read")
    args = parser.parse_args(argv)

    # TWO DIFFERENT ANCHORS, and mixing them up is a measured defect rather
    # than a hypothetical one. The live store sits BESIDE the main checkout and
    # a worktree is nested INSIDE it, so only main_repo_root() resolves
    # `../information`. Output, by contrast, belongs to the checkout that
    # produced it -- anchoring it to the main root wrote this plan's first
    # census pair into the wrong tree entirely.
    read_anchor = census.main_repo_root()
    write_anchor = census.working_repo_root()

    live_store = os.path.abspath(
        args.live_store or os.path.join(read_anchor, LIVE_STORE_RELATIVE))
    out_path = args.out or os.path.join(_HERE, "canon-bullets.json")
    records_dir = args.records_dir or os.path.join(write_anchor, "_records",
                                                   "census")

    # The wording changed on 2026-09-16 with the boundary: the store is no
    # longer read-only in the blanket sense, because correcting the two
    # collections entries is this program's deliverable. The SCOPE of the census
    # is unchanged -- still the full tree, still the strongest available -- and
    # a record taken under the old wording will now report a `scope_mismatch`
    # against one taken under the new, which is correct: the two describe
    # different regimes, and a diff that quietly spanned them would compare
    # populations gathered under different rules.
    scope = ("FULL TREE: every file under the live store, walked recursively. "
             "This READ writes nothing; the only authorised writes are "
             "corrections to the two collections entries, made through the "
             "the-upstream-project writer. The strongest census available; a "
             "narrower scope would be a weaker proof.")

    # 1. BEFORE
    before = census.snapshot(live_store, scope=scope,
                             label=args.label + "-before")

    # 2. THE READ -- binary only, nothing opened for writing under live_store.
    record = build_record(live_store, census_meta={})

    # 3. AFTER
    after = census.snapshot(live_store, scope=scope,
                            label=args.label + "-after")

    # 4. DIFF. A non-empty diff is a FAILURE.
    findings = census.diff(before, after)
    checked = census.diff_population(before, after)
    verdict = core.report("CENSUS-DIFF", not findings, found=len(findings),
                          checked=checked, floor=1,
                          note="the read-only store, either side of the read")
    for finding in findings:
        print("  %-18s %s" % (finding["kind"], finding["path"]))

    stamp = before["taken_at"]
    before_name = census.snapshot_filename(args.label, "before", when=stamp)
    after_name = census.snapshot_filename(args.label, "after", when=stamp)
    core.atomic_write_json(os.path.join(records_dir, before_name), before)
    core.atomic_write_json(os.path.join(records_dir, after_name), after)

    if findings:
        core.die(core.EXIT_FINDING,
                 "%s the live store CHANGED across the read window (%d "
                 "finding(s)).\n"
                 "  The snapshots are written to %s so the change is "
                 "inspectable; the bullet\n"
                 "  snapshot is NOT written, because a verbatim copy taken "
                 "across a mutation is not verbatim."
                 % (core.REFUSAL_PREFIX, len(findings), records_dir))

    # 5. WRITE. ensure_ascii=False: verbatim canon text is the point.
    record["census"] = {
        "before": before_name,
        "after": after_name,
        "scope": scope,
        "files_censused": before["file_count"],
        "findings": len(findings),
        "records_dir": "_records/census",
    }
    core.atomic_write_json(out_path, record, ensure_ascii=False)

    core.report("CANON-SNAP", True,
                found=record["counts"]["bullets_total"],
                checked=record["counts"]["bullets_total"], floor=1,
                note="bullets written to %s" % os.path.basename(out_path))
    return core.code_for(verdict)


if __name__ == "__main__":
    sys.exit(main())
