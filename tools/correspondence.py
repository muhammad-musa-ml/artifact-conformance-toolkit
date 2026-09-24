"""correspondence -- what each example project is, what it corresponds to, and its state.

THE QUESTION THIS ANSWERS, at any moment and without reading a plan:

    for every example project -- which example project is it, which collections entry and
    which rows does it correspond to, how many of those rows are still unbacked,
    and what exactly do I run when it lands?

WHY IT DERIVES AND STORES NOTHING
---------------------------------
Every fact it prints already exists somewhere authoritative, so it JOINS rather
than records:

    tools/manifest.json   slug -> canon, example project, its bullet ids, status
    the live entry        company, role, dates, kind -- read from the entry
                          itself, because the entry IS the record of the
                          engagement and a second copy here would be a second
                          thing to keep true
    the live entry        the marker on each row -> how many are still unbacked

A stored map would go stale the first time a correction landed and nobody
re-ran the generator. This cannot: there is no copy to fall out of date.

WHAT IT DELIBERATELY DOES NOT SAY
---------------------------------
Nothing it prints, and nothing it instructs anyone to write, describes the work
as built by an agent or by this programme. The entries record the owner's own
engagement work. This repository is the record-keeping around a reproduction of
that work, and the two must not be confused in a private record -- so the
correction command it prints carries a `--note` about the MEASUREMENT, never
about who or what performed the rebuild.

EXIT CODES -- the canonkit contract
    0  the map was printed over a non-empty population
    2  could NOT look: no manifest, no entry, or an empty population
"""

import argparse
import importlib.util
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

CHECK_ID = "CORRESPONDENCE"


def _load(stem, filename):
    path = os.path.join(_HERE, filename)
    spec = importlib.util.spec_from_file_location(stem, path)
    if spec is None or spec.loader is None:
        raise ImportError("could not build an import spec for %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(stem, module)
    spec.loader.exec_module(module)
    return module


core = _load("frozen_core", "canonkit.py")
backing = _load("check_canon_backing_for_correspondence", "check_canon_backing.py")

# The entry fields this reads. Declared so a reader can see the whole surface,
# and asserted per entry -- a `.get()` on a shape nobody enumerated answers every
# question with None and makes an absent field indistinguishable from an empty
# one.
ENTRY_FIELDS = ("company", "role", "dates", "kind", "detail")

# What an entry must still be. The framing rule is not a style note: these are
# engagement, and a `kind` that drifted to something else would be the record
# saying otherwise.
REQUIRED_KIND = "experience"


def read_manifest(path=None):
    path = path or os.path.join(_HERE, "manifest.json")
    if not os.path.isfile(str(path)):
        core.die(core.EXIT_DID_NOT_RUN,
                 "%s no manifest at %s." % (core.REFUSAL_PREFIX, path))
    with open(str(path), "rb") as handle:
        payload = json.loads(handle.read().decode("utf-8"))
    slugs = payload.get("slugs")
    if not isinstance(slugs, list) or not slugs:
        core.die(core.EXIT_DID_NOT_RUN,
                 "%s the manifest holds 0 slugs, so there is nothing to map.\n"
                 "  A map over an empty population describes everything and "
                 "checks nothing." % core.REFUSAL_PREFIX)
    return payload


def read_entries(live_store):
    """{canon: entry} for both live entries, with the read surface asserted."""
    entries = {}
    for spec in backing.LIVE_ENTRIES:
        entry = backing.read_live_entry(live_store, spec)
        missing = [name for name in ENTRY_FIELDS if name not in entry]
        if missing:
            core.die(core.EXIT_DID_NOT_RUN,
                     "%s %s is missing %d of the %d field(s) this map reads: "
                     "%s.\n  Reading a shape nobody enumerated turns an absent "
                     "field into an empty one."
                     % (core.REFUSAL_PREFIX, spec["relative"], len(missing),
                        len(ENTRY_FIELDS), missing))
        entries[spec["canon"]] = entry
    return entries


def marker_state(entry, canon):
    """{bullet_id: marker_kind or None} for one entry's metric rows."""
    state = {}
    for key, text in backing.live_metric_rows(entry, canon):
        row_id = key.split(":", 1)[1]
        if backing.LIVE_MARKER not in text:
            state[row_id] = None
            continue
        state[row_id] = next(
            (name for name, needle in backing.LIVE_MARKER_KINDS
             if needle in text), "unclassified")
    return state


def obligations_of(slug):
    """{canon:bullet -> the field it arrived through}, over BOTH mapping fields.

    a design rule. The expected set splits the mapping deliberately: `bullets` is what a
    path is RESPONSIBLE for backing, `backs_bullets` is what an already-existing
    artifact is CITED as backing. Reading only the first makes this map blind to
    precisely the slug that is already `built` AND already cited -- a confident
    zero produced by the scope of the field read rather than by the state of the
    world, and a disagreement with `tools/checks/check_20.py`, which reads both.
    Two tools disagreeing about what a path answers for makes a gate's verdict
    depend on which field a reader happened to open.

    The shape is copied from `check_20.py::built_entries` rather than
    re-invented, including `setdefault`, which keeps the FIRST field a claim
    arrived through so a row can say which relationship reached it.
    """
    found = {}
    for field in ("bullets", "backs_bullets"):
        for key in slug.get(field) or []:
            if isinstance(key, str) and key:
                found.setdefault(key, field)
    return found


def distinct_keys(rows):
    """Every `canon:bullet` key any row claims, counted ONCE.

    THE DENOMINATOR IS DISTINCT, NOT A SUM, and this is the whole reason the
    function exists. Two slugs legitimately name one claim -- measured, exactly
    one does: `example-beta:P5-B3`, owned by `beta-artifact-5` through
    `bullets` and cited by `example-cache-benchmark` through
    `backs_bullets`. Summing per-row lengths would report 50 obligations where
    the programme has 49, and that denominator is what the project technology-stack document section 9
    quotes and what the marker countdown is measured against. A double-CLAIM is
    legitimate; a double-COUNT inflates the scoreboard.
    """
    seen = set()
    for row in rows:
        seen.update(row.get("keys") or [])
    return seen


def _double_claimed_keys(rows):
    """Every key more than one path names. Named, never just counted."""
    seen, twice = set(), set()
    for row in rows:
        for key in row.get("keys") or []:
            if key in seen:
                twice.add(key)
            seen.add(key)
    return twice


def distinct_unbacked(rows):
    """The same, over the keys a row found still carrying a marker."""
    seen = set()
    for row in rows:
        seen.update(row.get("unbacked_keys") or [])
    return seen


def build_map(manifest, entries, live_store):
    """One row per example project, joined. Never stored."""
    states = {canon: marker_state(entry, canon)
              for canon, entry in entries.items()}
    paths = []
    for slug in manifest["slugs"]:
        canon = slug.get("canon")
        if not canon:
            # The shared substrate and the legacy scan-only directory back no
            # bullet. They are LISTED rather than dropped, because a path
            # silently absent from a map reads as a path that does not exist.
            paths.append({
                "slug": slug.get("slug"),
                "canon": None, "example project": None,
                "status": slug.get("status"),
                "backs_no_bullet": True,
                "bullet_ids": [], "keys": [], "unbacked_keys": [],
                "fields": {}, "unbacked": 0, "kinds": {},
                "entry": None, "organization": None, "role": None, "dates": None,
            })
            continue
        entry = entries.get(canon) or {}
        spec = next(s for s in backing.LIVE_ENTRIES if s["canon"] == canon)
        obligations = obligations_of(slug)
        keys = sorted(obligations)
        ids = [key.split(":", 1)[1] for key in keys]
        state = states.get(canon, {})
        kinds = {}
        unbacked_keys = []
        for key in keys:
            row_id = key.split(":", 1)[1]
            kind = state.get(row_id, "MISSING-ROW")
            if kind is not None:
                unbacked_keys.append(key)
                kinds[kind] = kinds.get(kind, 0) + 1
        paths.append({
            "slug": slug.get("slug"),
            "canon": canon,
            "example project": slug.get("project"),
            "status": slug.get("status"),
            "backs_no_bullet": not keys,
            "bullet_ids": ids,
            "keys": keys,
            "unbacked_keys": unbacked_keys,
            # Which RELATIONSHIP reached each claim. The two fields are not the
            # same thing and a row that showed only the id could not say so.
            "fields": {key.split(":", 1)[1]: obligations[key] for key in keys},
            "unbacked": len(unbacked_keys),
            "kinds": kinds,
            "entry": spec["relative"],
            "field": spec["relative"].split("/")[1].replace("everything-", ""),
            "collections_slug": canon,
            "organization": entry.get("company"),
            "role": entry.get("role"),
            "dates": entry.get("dates"),
            "kind": entry.get("kind"),
        })
    return paths


def correction_command(row):
    """The exact command that corrects this path's rows when it lands.

    THE PRINTED TEMPLATE IS NOT NARROWED TO WHATEVER A GIVEN RUN HAPPENS TO
    NEED. A run may legitimately drop flags -- a path whose prose and approach
    are unchanged passes no `--supersede-done` / `--done` / `--supersede-how` /
    `--how` -- and that is a DEVIATION the running plan states, never a reason
    to shorten this template. Three surfaces move together when a measurement
    lands, and a template that showed only the metric would keep producing
    entries that describe work nobody did that way.
    """
    if row["backs_no_bullet"]:
        return "(backs no bullet -- no correction)"
    return (
        "python -m scripts.shared.collections_correction --field %s --slug %s "
        "--caller import-github --supersede <old row> --metric <measured row> "
        "--supersede-done <old prose> --done <what was actually done> "
        "--supersede-how <old approach> --how <what was actually used> "
        "--note <why it changed> --dry-run"
        % (row["field"], row["collections_slug"]))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="correspondence.py",
        description="What each example project is, what it corresponds to, its state.")
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--live-store", default=None)
    parser.add_argument("--slug", default=None,
                        help="print the full detail for ONE path")
    parser.add_argument("--report", default=None)
    args = parser.parse_args(argv)

    live_store = args.live_store or os.path.join(
        os.path.dirname(_HERE), backing.LIVE_STORE_RELATIVE)
    manifest = read_manifest(args.manifest)
    entries = read_entries(live_store)
    rows = build_map(manifest, entries, live_store)

    for canon, entry in sorted(entries.items()):
        flag = "" if entry.get("kind") == REQUIRED_KIND else "  <-- NOT %r" % REQUIRED_KIND
        print("%-14s %-46s %s | %s | kind=%r%s"
              % (canon, entry.get("company"), entry.get("role"),
                 entry.get("dates"), entry.get("kind"), flag))
    print()

    header = ("%-30s %-14s %-5s %-8s %-6s %s"
              % ("path", "corresponds to", "ws", "status", "rows", "unbacked"))
    print(header)
    print("-" * len(header))
    summed_ids = summed_unbacked = 0
    for row in sorted(rows, key=lambda r: (r["canon"] or "~", r["slug"])):
        summed_ids += len(row["bullet_ids"])
        summed_unbacked += row["unbacked"]
        kinds = " ".join("%s=%d" % kv for kv in sorted(row["kinds"].items()))
        cited = sorted(k for k, f in (row.get("fields") or {}).items()
                       if f == "backs_bullets")
        if cited:
            kinds = (kinds + " cited=%s" % ",".join(cited)).strip()
        print("%-30s %-14s %-5s %-8s %-6d %d %s"
              % (row["slug"], row["canon"] or "-", row["example project"] or "-",
                 row["status"], len(row["bullet_ids"]), row["unbacked"], kinds))

    # BOTH NUMBERS, ALWAYS. The distinct count is the programme's real
    # population; the summed one is larger exactly when two paths legitimately
    # name one claim. A reader shown only the first cannot tell a double-claim
    # from a bug, and a reader shown only the second is reading an inflated
    # scoreboard.
    total_ids = len(distinct_keys(rows))
    total_unbacked = len(distinct_unbacked(rows))
    double_claimed = summed_ids - total_ids

    if args.slug:
        one = next((r for r in rows if r["slug"] == args.slug), None)
        if one is None:
            core.die(core.EXIT_DID_NOT_RUN,
                     "%s no path named %r in the manifest."
                     % (core.REFUSAL_PREFIX, args.slug))
        print()
        print("%s -- %s %s (%s)"
              % (one["slug"], one["role"], one["organization"], one["dates"]))
        print("  example project : %s" % one["example project"])
        print("  entry      : %s" % one["entry"])
        print("  rows       : %s" % ", ".join(one["bullet_ids"]))
        print("  unbacked   : %d" % one["unbacked"])
        print("  on landing : %s" % correction_command(one))

    note = ("paths=%d | rows still unbacked=%d of %d"
            % (len(rows), total_unbacked, total_ids))
    if double_claimed:
        note += (" | %d claim(s) named by two paths, counted once: %s"
                 % (double_claimed,
                    ", ".join(sorted(_double_claimed_keys(rows)))))
    verdict = core.report(CHECK_ID, True, found=total_unbacked,
                          checked=total_ids, floor=1, note=note)

    if args.report:
        core.atomic_write_json(args.report, {
            "schema": "correspondence/1",
            "schema_version": 1,
            "paths": rows,
            "rows_total": total_ids,
            "rows_unbacked": total_unbacked,
            # The summed pair rides beside the distinct pair under names a
            # later consumer can read without parsing prose.
            "rows_total_summed": summed_ids,
            "rows_unbacked_summed": summed_unbacked,
            "double_claimed": sorted(_double_claimed_keys(rows)),
        })
    return core.code_for(verdict)


if __name__ == "__main__":
    sys.exit(main())
