"""Run the integrity guards, write results/results.json, exit 3 on any failure.

THE GUARDS ARE THE POINT. A headline number is worthless on its own -- a cache
can be made to look fast by serving less, by serving stale, or by both arms
simply hitting the load generator's ceiling. Each guard closes one of those and
FAILS LOUD rather than degrading to a warning.

Each guard declares three things, and the third is the one usually missing:

    an id                 so a failure can be named
    the flattering error  it closes, stated in prose beside it
    a FALSIFIABLE BOUND   a floor, printed whether the guard passed or failed

HOW TO RECORD A GUARD THAT WAS WRONG -- the shape to copy, from the shipped
analog's corrected-guard comment. State what the first formulation compared, why
the GUARD was wrong rather than the system, and refuse the tempting repair:

    "Relaxing the bound to whatever the run produced would have been the real
     error -- a guard tuned to pass measures nothing."

That paragraph is the model for the mutant-to-guard catalogue entries an earlier plan
writes. A guard whose bound was lowered until the run passed has stopped being a
guard and become a description.

TWO DEPARTURES FROM THE ANALOG, BOTH NAMED.

  1. len(guards) >= 1 IS REQUIRED, AND THE COUNT IS PRINTED. The analog's
     `all(g["passed"] for g in guards)` carries no length check. It is safe
     THERE only because seven appends are unconditional -- a copy whose guards
     were conditional would report every guard passing over zero guards, because
     all() over an empty sequence is True. This is the highest-leverage pitfall
     in the phase and it is closed at the copy site.
  2. THE GUARD SHAPE IS ENFORCED (owner ruling C1) via canonkit.validate_guards.
     Across seven shipped guards the population integer went by FIVE different
     names, and five of the seven declared no floor at all -- so a checker could
     not mechanically locate either. Every guard here carries `population`,
     `population_label` and `minimum_required`.

a design rule's load-bearing half is the PRINT, not the declaration. Printing the
EFFECTIVE floor beside every guard turns "checked N of M" into a claim a reader
can evaluate, and it is what stops a floor being quietly lowered between runs in
an artifact whose verdict stays green either way.
"""

import argparse
import json
import os
import sys

import canonkit

SCHEMA = "canonkit/results/1"


def finalize(root, guards, summary=None, stream=None):
    """Validate the guards, print every floor, write results.json, return a code."""
    stream = stream if stream is not None else sys.stdout
    results_dir = os.path.join(str(root), "results")
    guards = list(guards or [])

    # THE LENGTH CHECK COMES FIRST, BEFORE ANY AGGREGATION.
    # Printed on this branch too: a refusal that does not state the count leaves
    # a reader unable to tell an empty guard array from a malformed one.
    if len(guards) < 1:
        stream.write("[finalize] guards=0\n")
        canonkit.die(
            canonkit.EXIT_DID_NOT_RUN,
            "%s guards=0. Zero guards is a DID-NOT-RUN, never a pass: all() "
            "over an empty sequence is True, which is how a guard array that "
            "was never populated reports every guard passing.\n"
            "  REPAIR: append at least one guard, each with an id, a "
            "population, a population_label and a minimum_required floor."
            % canonkit.REFUSAL_PREFIX)

    record = {
        "schema": SCHEMA,
        "schema_version": canonkit.SCHEMA_VERSION,
        "summary": dict(summary or {}),
        "guards": guards,
        # `len(guards) >= 1` is re-stated INSIDE the expression, on the same
        # line as the all(), so the anti-pattern cannot reappear by someone
        # moving the check above out of the way. all([]) is True; this is not.
        "all_guards_passed": len(guards) >= 1 and all(
            bool(guard.get("passed")) for guard in guards),
    }

    violations = canonkit.validate_guards(record)
    if violations:
        stream.write("[finalize] guards=%d shape violations=%d\n"
                     % (len(guards), len(violations)))
        canonkit.die(
            canonkit.EXIT_DID_NOT_RUN,
            "%s %d guard-shape violation(s) under owner ruling C1:\n%s\n"
            "  REPAIR: every guard carries id, passed, population (int), "
            "population_label (str) and minimum_required (number). The "
            "domain-specific key stays beside them, it does not replace them."
            % (canonkit.REFUSAL_PREFIX, len(violations), "\n".join(violations)))

    canonkit.atomic_write_json(os.path.join(results_dir, "results.json"), record)

    # EVERY guard's effective floor, printed on both verdicts.
    stream.write("[finalize] guards=%d\n" % len(guards))
    for guard in guards:
        stream.write("  [%s] %-28s population=%d %s floor=%s\n"
                     % ("PASS" if guard.get("passed") else "FAIL",
                        guard.get("id"), guard.get("population"),
                        guard.get("population_label"),
                        guard.get("minimum_required")))

    failed = [g for g in guards if not g.get("passed")]
    canonkit.report("FINALIZE", not failed, len(failed), len(guards), 1,
                    note="all_guards_passed=%s" % record["all_guards_passed"])
    return canonkit.EXIT_GUARD_FAIL if failed else canonkit.EXIT_PASS


def main(argv=None, stream=None):
    parser = argparse.ArgumentParser(description="Run this artifact's guards.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--guards", required=True,
                        help="path to a JSON file holding the guard records")
    args = parser.parse_args(argv)
    with open(args.guards, "rb") as handle:
        guards = json.loads(handle.read().decode("utf-8"))
    return finalize(args.root, guards, stream=stream)


if __name__ == "__main__":
    sys.exit(main())
