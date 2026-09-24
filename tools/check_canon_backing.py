"""check_canon_backing -- count the claims still marked as not yet measured.

TWO POPULATIONS, AND THE DIFFERENCE IS THE WHOLE POINT
------------------------------------------------------
DEFAULT (offline): reads the COMMITTED snapshot (tools/canon-bullets.json),
never the live store. That is deliberate and is the reason a design rule commits the
snapshot at all: CHECK-09 must be answerable offline from a clean checkout, and
a check that needs the live data dir cannot run at closeout on a fresh clone.
This population is the FROZEN BASELINE -- 48 of 49 canon bullets carry
`not yet run` -- and it never moves again, because the archive is never edited.
It is the BEFORE side of every comparison this program makes.

`--live` (opt-in): reads the two LIVE collections entries, which are what this
program actually corrects, and counts the figures still carrying the
designed-not-yet-measured marker. This is the population a project requirement drives to zero.

WHY --live EXISTS RATHER THAN A RE-KEY OF THE DEFAULT
------------------------------------------------------
Simply pointing the existing scan at the entries would have been WORSE than
leaving it alone. Measured 2026-09-16: the live entries carry the canon's
`not yet run` marker on ZERO of their 49 metric rows -- the earlier round conversion
dropped the per-bullet disclosure -- so a re-keyed scan would have reported a
clean sweep on day one, before a single example project had run. A check that passes
because it found nothing to look at is an unrun check wearing a verdict, and
this module already exists to prevent exactly that shape one level down.

So the two modes are kept apart: the frozen count stays readable offline, the
live count is the one that closes, and neither can be mistaken for the other
because each prints its own population.

EXIT CODES -- the canonkit contract, a caller branches on these
    0  the scan ran over a non-empty population and found nothing outstanding
    1  a finding the owner must act on (claims still unmeasured)
    2  could NOT look: no snapshot, an empty population, or a refused needle

WHY `--needle` IS REFUSABLE, AND WHY THAT IS NOT PATERNALISM
-------------------------------------------------------------
The marker is written two different ways across the two canons:

    example-beta    "BACKING STATUS: BP-3, example project not yet run."
    example-alpha   "BACKING STATUS: example project P3 not yet run."

alpha INTERPOLATES THE PROJECT ID. So the longer, more specific-looking
literal `example project not yet run` matches 28 of example-beta's 29 bullets and
ZERO of alpha's 20 -- it silently halves the population while looking like
a tightening. An operator who passes it gets a smaller number and no error, and
a smaller number with no error is the single most expensive shape in this
program.

The refusal therefore names BOTH wordings AND THE COUNTS EACH ACTUALLY MATCHES,
re-measured from the snapshot at refusal time rather than quoted from a
constant. A refusal that asserts a number it did not measure is the same defect
one level up.
"""

import argparse
import importlib.util
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

CHECK_ID = "CHECK-09"

# The needle at the length that actually matches, and the longer form that does
# not. Both are DATA here; the counts each matches are measured, never stored.
DEFAULT_NEEDLE = "not yet run"
REFUSED_NEEDLES = ("example project not yet run",)

FIELDS = ("text", "metric", "metric_basis", "backing")

# ---------------------------------------------------------------------------
# The LIVE side.
# ---------------------------------------------------------------------------
# The marker written into every NOT-YET-BACKED `detail.metrics` row of the two
# live collections entries.
#
# ONE OUTSTANDING NEEDLE, TWO KINDS. `LIVE_MARKER` is the bracket that opens
# every marker, so ONE count answers "how many figures are not yet backed" and
# the kinds answer "why". Counting only the designed rows would have left the
# 49th figure outside the population entirely -- present, unbacked, and never
# counted down -- which is the shape of a gate that reports DONE over a row it
# never examined.
#
#   designed  P1-B3: <figure> [BACKING: designed, not yet measured --
#                              P1 has no reproducing artifact yet]
#   substitute P5-B3: <figure> [BACKING: measured on a substitute system --
#                              the backing artifact is not yet verified]
#
# THE NEEDLES INTERPOLATE NOTHING, and that is a deliberate correction of the
# trap this module documents below: alpha's CANON marker interpolates the
# project id, so the longer literal `example project not yet run` matches 28 of
# example-beta's 29 and ZERO of alpha's 20. A live marker that repeated that
# mistake would silently halve the live population in the same way. Every
# variable part sits AFTER the fixed needle, where it cannot break a match.
#
# NO PROGRAM VOCABULARY IN THE MARKER. It says nothing about this repository,
# its phases, its example projects or the tooling that writes it. The entry records
# the owner's engagement work; a marker that named the programme correcting it
# would put scaffolding into a private record. The example project is already the row's
# own `P1-B3:` prefix, so naming it again buys nothing.
LIVE_MARKER = "[BACKING:"

LIVE_MARKER_KINDS = (
    ("designed", "designed, not yet measured"),
    ("substitute", "measured on a substitute system"),
)

LIVE_STORE_RELATIVE = os.path.join("..", "information")

# Declared here and asserted against canon_snapshot.SOURCES by the suite. Two
# modules disagreeing about where an entry lives would mean one of them scanning
# a path that does not exist and reporting it as a clean population.
LIVE_ENTRIES = (
    {"canon": "example-alpha",
     "relative": "collections/collection-one/example-alpha/raw.json"},
    {"canon": "example-beta",
     "relative": "collections/collection-two/example-beta/raw.json"},
)

# The id a live metric row leads with: `P1-B3: ...` and `BP-5-B3: ...`.
# A row with no parseable id is NOT skipped -- it is counted with a positional
# fallback id, because dropping it would shrink the population silently, which
# is the one failure this whole module is built around.
_ROW_ID_RE = re.compile(r"^\s*([A-Z]+-?\d+-B\d+)\s*:")


def _load_core():
    path = os.path.join(_HERE, "canonkit.py")
    spec = importlib.util.spec_from_file_location("frozen_core", path)
    if spec is None or spec.loader is None:
        raise ImportError("could not build an import spec for %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = _load_core()


def bullet_blob(bullet):
    """Every text-bearing field of one bullet, joined. The SEARCH SURFACE."""
    return "\n".join(str(bullet.get(field) or "") for field in FIELDS)


def count_matches(bullets, needle):
    """(matched_keys, per_canon_counts) for `needle` over `bullets`."""
    matched = []
    per_canon = {}
    for key, bullet in bullets.items():
        canon = bullet.get("canon") or "<unknown>"
        per_canon.setdefault(canon, {"matched": 0, "total": 0})
        per_canon[canon]["total"] += 1
        if needle in bullet_blob(bullet):
            matched.append(key)
            per_canon[canon]["matched"] += 1
    return sorted(matched), per_canon


def _format_per_canon(per_canon):
    return ", ".join(
        "%s %d of %d" % (canon, counts["matched"], counts["total"])
        for canon, counts in sorted(per_canon.items()))


def refuse_needle(bullets, needle):
    """Refuse a needle that silently shrinks the population. Exit 2.

    The counts in the message are MEASURED here, against the same bullet set
    the scan would have used, so the operator sees the actual cost of the
    override rather than a remembered figure.
    """
    _, refused_counts = count_matches(bullets, needle)
    _, default_counts = count_matches(bullets, DEFAULT_NEEDLE)
    core.die(core.EXIT_DID_NOT_RUN,
             "%s --needle %r is refused.\n"
             "  It LOOKS more specific and is measurably weaker. Measured "
             "against this snapshot right now:\n"
             "      %-24r matches %s\n"
             "      %-24r matches %s\n"
             "  The gap is not a quirk: example-alpha interpolates the project "
             "id into the marker\n"
             "      example-alpha   \"BACKING STATUS: example project P3 not yet "
             "run.\"\n"
             "      example-beta    \"BACKING STATUS: BP-3, example project not yet "
             "run.\"\n"
             "  so the longer literal cannot match an alpha bullet at all "
             "and would halve the\n"
             "  population while reporting no error.\n"
             "  REPAIR: drop --needle and use the default %r."
             % (core.REFUSAL_PREFIX, needle,
                needle, _format_per_canon(refused_counts),
                DEFAULT_NEEDLE, _format_per_canon(default_counts),
                DEFAULT_NEEDLE))


def scan(snapshot, needle=DEFAULT_NEEDLE, quiet=False):
    """Count bullets carrying `needle`. Returns (verdict, result dict).

    Raises SystemExit(2) on a refused needle or an empty bullet population.
    """
    bullets = (snapshot or {}).get("bullets") or {}

    if needle in REFUSED_NEEDLES:
        refuse_needle(bullets, needle)

    checked = len(bullets)
    matched, per_canon = count_matches(bullets, needle)

    # The population line prints on EVERY branch, including the refusal below.
    verdict = core.VERDICT_DID_NOT_RUN
    if not quiet:
        verdict = core.report(CHECK_ID, True, found=len(matched),
                              checked=checked, floor=1,
                              note="needle=%r  %s"
                                   % (needle, _format_per_canon(per_canon)))
    elif checked:
        verdict = core.VERDICT_PASS

    if checked == 0:
        core.die(core.EXIT_DID_NOT_RUN,
                 "%s the snapshot holds 0 bullets, so nothing was scanned.\n"
                 "  A scan over an empty population reports 'none outstanding' "
                 "about everything and\n"
                 "  is indistinguishable from a clean result at the seam a "
                 "caller reads. DID-NOT-RUN.\n"
                 "  REPAIR: regenerate tools/canon-bullets.json with "
                 "`python tools/canon_snapshot.py`."
                 % core.REFUSAL_PREFIX)

    result = {
        "schema": "claim-backing/1",
        "schema_version": 1,
        "check_id": CHECK_ID,
        "needle": needle,
        "found": len(matched),
        "checked": checked,
        "per_canon": per_canon,
        "matched": matched,
        "outstanding": len(matched),
        "backed": sorted(set(bullets) - set(matched)),
    }
    return verdict, result


def read_live_entry(live_store, spec):
    """Read one live collections entry. A missing one is a REFUSAL, never a zero.

    Opened in BINARY mode: this program corrects these two files through the
    `the-upstream-project` writer and through nothing else, so no reader here is ever
    given a mode that could write.
    """
    path = os.path.join(str(live_store), spec["relative"].replace("/", os.sep))
    if not os.path.isfile(path):
        core.die(core.EXIT_DID_NOT_RUN,
                 "%s no live collections entry at %s.\n"
                 "  A missing entry must never become a smaller population: "
                 "scanning one of two entries and\n"
                 "  reporting the result as the live count is the exact shape "
                 "this module refuses.\n"
                 "  REPAIR: point --live-store at the the-upstream-project data dir "
                 "that holds both entries."
                 % (core.REFUSAL_PREFIX, path))
    with open(path, "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


def live_metric_rows(entry, canon):
    """[(key, row_text)] for one entry's `detail.metrics`, ids parsed from the row."""
    rows = ((entry or {}).get("detail") or {}).get("metrics") or []
    out = []
    for index, row in enumerate(rows):
        text = str(row)
        match = _ROW_ID_RE.match(text)
        row_id = match.group(1) if match else "row-%04d" % (index + 1)
        out.append(("%s:%s" % (canon, row_id), text))
    return out


def scan_live(live_store, marker=LIVE_MARKER, quiet=False):
    """Count live metric rows still carrying `marker`. Returns (verdict, result).

    Raises SystemExit(2) on a missing entry or a zero-row population.
    """
    matched = []
    per_canon = {}
    by_kind = {name: [] for name, _needle in LIVE_MARKER_KINDS}
    by_kind["unclassified"] = []
    checked = 0
    for spec in LIVE_ENTRIES:
        canon = spec["canon"]
        entry = read_live_entry(live_store, spec)
        rows = live_metric_rows(entry, canon)
        per_canon[canon] = {"matched": 0, "total": len(rows)}
        checked += len(rows)
        for key, text in rows:
            if marker in text:
                matched.append(key)
                per_canon[canon]["matched"] += 1
                # A marked row whose KIND is unrecognised is reported, never
                # dropped: a row silently missing from every kind bucket would
                # make the kinds sum to less than `found` and the difference
                # would be invisible.
                kind = next((name for name, needle in LIVE_MARKER_KINDS
                             if needle in text), "unclassified")
                by_kind[kind].append(key)
    matched.sort()
    for bucket in by_kind.values():
        bucket.sort()

    kinds_note = " ".join(
        "%s=%d" % (name, len(by_kind[name]))
        for name in [n for n, _ in LIVE_MARKER_KINDS] + ["unclassified"])
    verdict = core.VERDICT_DID_NOT_RUN
    if not quiet:
        verdict = core.report(CHECK_ID, not matched, found=len(matched),
                              checked=checked, floor=1,
                              note="live marker=%r  %s | kinds: %s"
                                   % (marker, _format_per_canon(per_canon),
                                      kinds_note))
    elif checked:
        verdict = core.VERDICT_PASS if not matched else core.VERDICT_FAIL

    if checked == 0:
        core.die(core.EXIT_DID_NOT_RUN,
                 "%s the two live entries hold 0 metric rows between them, so "
                 "nothing was scanned.\n"
                 "  found=0 over an empty population reports 'nothing "
                 "outstanding' about everything and is\n"
                 "  indistinguishable from a finished program at the seam a "
                 "caller reads. DID-NOT-RUN.\n"
                 "  REPAIR: confirm --live-store points at the data dir whose "
                 "entries carry detail.metrics."
                 % core.REFUSAL_PREFIX)

    return verdict, {
        "schema": "claim-backing-live/1",
        "schema_version": 1,
        "check_id": CHECK_ID,
        "mode": "live",
        "marker": marker,
        "found": len(matched),
        "checked": checked,
        "per_canon": per_canon,
        "matched": matched,
        "by_kind": by_kind,
        "outstanding": len(matched),
    }


def read_snapshot(path):
    if not os.path.isfile(str(path)):
        core.die(core.EXIT_DID_NOT_RUN,
                 "%s no canon snapshot at %s.\n"
                 "  REPAIR: run `python tools/canon_snapshot.py`."
                 % (core.REFUSAL_PREFIX, path))
    with open(str(path), "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="check_canon_backing.py",
        description="Count canon bullets still marked `not yet run` (CHECK-09).")
    parser.add_argument("--snapshot",
                        default=os.path.join(_HERE, "canon-bullets.json"))
    parser.add_argument("--needle", default=DEFAULT_NEEDLE)
    parser.add_argument("--report", default=None)
    parser.add_argument(
        "--live", action="store_true",
        help="scan the two LIVE collections entries instead of the frozen "
             "snapshot. This is the population a project requirement drives to zero.")
    parser.add_argument(
        "--live-store", default=None,
        help="the the-upstream-project data dir holding both entries. Defaults to "
             "the repository's sibling `../information`.")
    args = parser.parse_args(argv)

    if args.live:
        live_store = args.live_store or os.path.join(
            os.path.dirname(_HERE), LIVE_STORE_RELATIVE)
        verdict, result = scan_live(live_store)
    else:
        snapshot = read_snapshot(args.snapshot)
        verdict, result = scan(snapshot, needle=args.needle)

    for canon, counts in sorted(result["per_canon"].items()):
        print("  %-14s found=%d checked=%d"
              % (canon, counts["matched"], counts["total"]))

    if args.report:
        core.atomic_write_json(args.report, result)

    return core.code_for(verdict)


if __name__ == "__main__":
    sys.exit(main())
