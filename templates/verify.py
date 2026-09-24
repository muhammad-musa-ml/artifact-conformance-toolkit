"""Re-derive every figure by walking the WHOLE chain, not the last link.

    per-item records -> count(predicate) -> numerator -> / denominator -> rendered

WHY THIS SCRIPT RE-READS WHAT WAS JUST WRITTEN.
The argument is already written, in a shipped file, and it transfers exactly:

    "the copy loop used to report only how many component DIRECTORIES it had
     attempted. That count cannot discriminate a complete sync from a
     half-finished one ... A sync that 'looks done' is worse than no sync,
     because the next run of the plugin tests OLD code and returns a
     confidently wrong result."

Substitute "figure" for "sync" and the sentence is this file's purpose. A
figures.json that looks derived is worse than none, because everything
downstream -- the README, the register row, the published claim -- then ships a
confidently wrong number.

IF ANY LINK IS SHORT-CIRCUITED, THE WHOLE THING IS DECORATION. Changing one
per-item record must propagate through count(predicate) to the rendered figure.
That is also what makes an earlier plan's mutation testing meaningful: a mutant that
cannot reach the figure proves nothing about the guards it was supposed to trip.

STALENESS IS JUDGED BY CONTENT, NEVER BY TIMESTAMPS.
# Ordinary copies PRESERVE mtime, so a results tree copied forward from an
# earlier session carries entirely plausible file times. This script re-computes
# from the records instead. The same reasoning is why the gate's token is over
# content and why ordering uses the ISO stamps recorded INSIDE each record.

THE THREE TIERS. Only `derive` runs earlier; `recompute` and `remeasure`
carry an explicit DID-NOT-RUN rather than a pass, because a tier that silently
returns 0 is indistinguishable from a tier that verified something.

TWO ERROR WORDINGS ARE PINNED AS CONSTANTS BELOW. A figure with no per-item
record behind it fails hardest; and when that figure ALSO equals the canon
figure, the message says so in those terms, because that pair is the signature
of a quotation rather than a measurement. They are constants so a test can
assert them verbatim -- the wording is what teaches the next executor, and a
test that checked only the exit code would let it decay into a generic
missing-source error.
"""

import argparse
import json
import os
import sys

import canonkit
import derive as derive_module
import runmeta

TIERS = ("derive", "recompute", "remeasure")

# How many findings are printed before the list is truncated -- with its own
# count, never silently.
MAX_LISTED = 20

NO_RECORD_MESSAGE = (
    "NO per-item record file stands behind this figure. The chain "
    "(per-item records -> count(predicate) -> numerator -> denominator -> "
    "rendered) has no first link, so nothing here was measured")

QUOTATION_SIGNATURE = (
    "and this figure ALSO EQUALS THE CANON FIGURE -- no result file behind it "
    "and exactly the number the canon already claimed. That pair is the "
    "signature of a QUOTATION, not a measurement")


def _load(path):
    with open(str(path), "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


def verify_derive(root, stream):
    """Re-derive every figure. Returns (checked, problems) -- separate values.

    Population and findings are returned apart rather than collapsed into a
    bool, which is the frozen core's report() contract and the shipped analog's
    `(checked, problems)` shape. One number cannot make a run that checked
    nothing visible.
    """
    results_dir = os.path.join(str(root), "results")
    figures_path = os.path.join(results_dir, "figures.json")
    problems = []

    if not os.path.isfile(figures_path):
        return 0, ["results/figures.json is absent -- nothing to re-derive"]

    record = _load(figures_path)
    figures = record.get("figures") or {}
    items = derive_module.load_items(results_dir)
    by_name = dict(items)

    # THE TOKEN COMPARISON COMES BEFORE ANY RE-DERIVATION (a project requirement).
    # Re-deriving first would compute a perfectly correct number from records
    # that a DIFFERENT gate authorised, and report it as verified. The token is
    # over gate CONTENT, so it moves the moment any assertion changes -- which
    # is exactly the "results produced under a since-changed gate" case it
    # exists to catch.
    gate_path = os.path.join(results_dir, "gate.json")
    if not os.path.isfile(gate_path):
        return 0, ["results/gate.json is absent -- nothing authorised these figures"]
    gate_token = _load(gate_path).get("run_token")
    claimed_token = record.get("gate_token")
    if claimed_token != gate_token:
        problems.append(
            "gate_token mismatch: figures.json carries %r but results/gate.json "
            "minted %r. These figures were not produced under the gate now in "
            "this artifact -- either the gate changed after they were derived, "
            "or the results were copied in from another session."
            % (claimed_token, gate_token))

    checked = 0
    for key in sorted(figures):
        figure = figures[key]
        checked += 1

        backing = [name for name in figure.get("derived_from") or []
                   if name in by_name]

        # THE HARDEST FAILURE IN THE CHAIN, and it is checked before the value
        # is compared -- a figure with no first link cannot be "re-derived to a
        # different number", it was never derived at all. Reporting it as an
        # ordinary mismatch would file a fabrication as an arithmetic slip.
        if not backing:
            message = "%s: %s" % (key, NO_RECORD_MESSAGE)
            if _close(figure.get("value"), figure.get("canon_value")):
                message = "%s %s" % (message, QUOTATION_SIGNATURE)
            problems.append(message)
            continue

        subset = [(name, by_name[name]) for name in backing]
        spec = {"key": key, "kind": figure.get("kind", "rate"),
                "predicate": figure.get("predicate")}
        numerator, denominator, value = derive_module.compute(spec, subset)

        if not _close(value, figure.get("value")):
            problems.append(
                "%s: claims %r but re-derives to %r from %d record(s)"
                % (key, figure.get("value"), value, denominator))
        elif numerator != figure.get("numerator"):
            problems.append(
                "%s: claims numerator %r but re-derives %d"
                % (key, figure.get("numerator"), numerator))

    return checked, problems


def _close(left, right, tolerance=1e-6):
    if left is None or right is None:
        return left is right
    try:
        return abs(float(left) - float(right)) <= tolerance
    except (TypeError, ValueError):
        return left == right


def _print_problems(problems, stream):
    for problem in problems[:MAX_LISTED]:
        stream.write("[verify]   %s\n" % problem)
    if len(problems) > MAX_LISTED:
        stream.write("[verify]   ... and %d more\n" % (len(problems) - MAX_LISTED))


def main(argv=None, stream=None):
    parser = argparse.ArgumentParser(
        description="Re-derive this artifact's figures from its own records.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--tier", choices=TIERS, default="derive")
    args = parser.parse_args(argv)
    stream = stream if stream is not None else sys.stdout

    if args.tier != "derive":
        # An explicit DID-NOT-RUN. A tier that silently returned 0 would be
        # indistinguishable from one that verified something.
        canonkit.report("VERIFY-%s" % args.tier.upper(), False, 0, 0, 1,
                        note="tier not implemented in this phase")
        stream.write("[verify] tier %s: %s -- not implemented in this phase\n"
                     % (args.tier, canonkit.VERDICT_DID_NOT_RUN))
        return canonkit.EXIT_DID_NOT_RUN

    checked, problems = verify_derive(args.root, stream)

    stream.write("[verify] re-derived %d of %d figure(s)\n"
                 % (checked - len(problems), checked))
    _print_problems(problems, stream)

    verdict = canonkit.report("VERIFY-DERIVE", not problems, len(problems),
                              checked, 1)
    return canonkit.code_for(verdict)


if __name__ == "__main__":
    sys.exit(main())
