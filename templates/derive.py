"""THE ONLY PLACE A NUMBER IS AUTHORED.

Every figure this artifact ships is computed here, from per-item records, and
written to results/figures.json. Nothing else in the artifact may author a
number: the README and RESULTS.md are RENDERED from this file, the register row
is generated from it, and verify.py re-walks the chain back to the records.

    per-item records -> count(predicate) -> numerator -> / denominator -> rendered

THREE REFUSALS, ALL PREVENTION RATHER THAN DETECTION.
A number that cannot be authored cannot be shipped and later caught; these
refuse at the moment of authorship, which is the only moment the operator still
has the context to fix it.

  MISSING OR ZERO POPULATION. A figure over zero inputs measured nothing, and
      every count derived from it downstream is a 0/0 pass wearing a figure's
      clothes. The refusal NAMES the key, because a refusal that names nothing
      cannot be acted on.
  A THRESHOLD CLAIM WITH FEWER THAN THREE RUNS. One run landing the right
      side of a line does not establish that the line was crossed. The rule lives
      HERE, where the number is authored, rather than in a checker that reads it
      later.
  NO GATE TOKEN. A number authored without an authorising gate has nothing to be
      checked against.

WHAT IS DELIBERATELY NOT REFUSED: population 1. Peak VRAM, free VRAM at
run start and disk free are legitimately single-sample population facts, and the
shipped matched-load-replicated.json already carries "n": 1 beside "n": 3 for
exactly that reason. Requiring a written excuse for every n=1 figure was
considered and rejected -- it would be a constraint nobody asked for, applied
uniformly, damaging the artifact in its own name.

WHEN THERE ARE THREE OR MORE RUNS, THE RAW LIST IS WRITTEN BESIDE THE SUMMARY.
an earlier finding's replicates-over-intervals rule, and the shipped file's own shape. An
interval computed from three numbers hides which three; the list does not.

THIS FILE READS NO CLOCK, AND THAT IS WHAT MAKES figures.json HASH-PINNABLE.
Every stamp in the written record comes from a MACHINE record that already
exists: the run's own started_at and finished_at, or, when no run record does,
the gate's dated_at. So two derivations over identical records produce
byte-identical output, and changing one record still changes it.

The defect this replaced was small and its consequence was not: `dated_at` was
re-stamped from the wall clock on every run, so re-deriving an untouched
artifact produced different bytes and any sha256 assertion over figures.json
reported tampering on a measurement nobody had touched. an earlier round re-runs every
artifact from a clean checkout and re-derives, which is precisely the
comparison that could not be made.

THE FIX IS NOT "DROP THE TIMESTAMP." The provenance is load-bearing and is read
downstream. It is MOVED to where variation is correct -- the run record, which
the machine writes at measurement time -- and the figure record carries the run
it derives from rather than the derivation's own wall clock. That is also the
more honest field: a figures record dated at re-derivation time claims a
freshness the numbers in it do not have.
"""

import argparse
import json
import os
import sys

import canonkit
import runmeta

SCHEMA = "canonkit/figures/1"


def load_items(results_dir):
    """Read every per-item record. The population the whole chain rests on."""
    directory = runmeta.items_dir(results_dir)
    if not os.path.isdir(directory):
        return []
    items = []
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(directory, name), "rb") as handle:
            items.append((name, json.loads(handle.read().decode("utf-8"))))
    return items


def count_predicate(items, predicate):
    """count(predicate) -- the second link of the chain.

    A field name rather than a callable, so the predicate that produced a figure
    is RECORDED in figures.json and can be re-applied by verify.py. A lambda
    would compute the same number and leave nothing behind to re-walk.
    """
    return sum(1 for _, record in items if bool(record.get(predicate)))


def compute(spec, items):
    """Return (numerator, denominator, value) for one declared figure."""
    denominator = len(items)
    kind = spec.get("kind", "rate")
    if kind == "rate":
        numerator = count_predicate(items, spec["predicate"])
        value = (100.0 * numerator / denominator) if denominator else None
    elif kind == "count":
        numerator = count_predicate(items, spec["predicate"])
        value = float(numerator)
    elif kind == "mean":
        field = spec["predicate"]
        values = [float(r.get(field, 0.0)) for _, r in items]
        numerator = len(values)
        value = (sum(values) / len(values)) if values else None
    else:
        raise ValueError("derive: unknown figure kind %r for %r"
                         % (kind, spec["key"]))
    if value is not None:
        value = round(value, 6)
    return numerator, denominator, value


def latest_run_record(results_dir):
    """The run whose timestamps figures.json carries forward.

    Selected by the recorded started_at INSIDE the record, never by file mtime.
    """
    directory = runmeta.raw_dir(results_dir)
    if not os.path.isdir(directory):
        return {}
    records = []
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(directory, name), "rb") as handle:
            records.append(json.loads(handle.read().decode("utf-8")))
    if not records:
        return {}
    return sorted(records, key=lambda r: str(r.get("started_at") or ""))[-1]


def gate_dated_at(results_dir):
    """The gate's own machine stamp -- the fallback when no run record exists.

    Read rather than re-derived, and safe to read unconditionally because
    require_gate() has already refused an absent, unparseable or undated gate
    by the time this is called. It is the last machine-written instant before
    the measurement, so an artifact that derived before writing a run record
    still carries a real stamp instead of None.
    """
    path = os.path.join(str(results_dir), "gate.json")
    try:
        with open(path, "rb") as handle:
            return json.loads(handle.read().decode("utf-8")).get("dated_at")
    except (OSError, ValueError):
        return None


def derive(root, specs, slug=None, stream=None):
    """Author every declared figure and write results/figures.json.

    There is deliberately no `clock_local` parameter. It existed only to make
    the wall-clock stamp injectable for tests, and a clock this function no
    longer reads is a parameter whose name promises control it does not have.
    """
    stream = stream if stream is not None else sys.stdout
    results_dir = os.path.join(str(root), "results")
    slug = slug or os.path.basename(os.path.abspath(str(root)))

    # Refuses with exit 2 when the gate is absent or failed, quoting the canon's
    # fallback wording. A number authored past a failed gate is a number with
    # nothing behind it.
    token = canonkit.require_gate(results_dir)

    items = load_items(results_dir)
    run = latest_run_record(results_dir)
    figures = {}

    for spec in specs:
        key = spec["key"]
        numerator, denominator, value = compute(spec, items)

        if denominator < 1:
            canonkit.die(
                canonkit.EXIT_DID_NOT_RUN,
                "%s figure %r has a population of %d. A figure over zero inputs "
                "did not measure anything, and every count derived from it "
                "would be a 0/0 pass. Population 1 is legal; 0 is not.\n"
                "  REPAIR: run the measurement driver so %s holds per-item "
                "records, then re-run derive.py."
                % (canonkit.REFUSAL_PREFIX, key, denominator,
                   runmeta.items_dir(results_dir)))

        runs = list(spec.get("runs") or [])
        if spec.get("threshold_claim"):
            if len(runs) < canonkit.THRESHOLD_CLAIM_MIN_RUNS:
                canonkit.die(
                    canonkit.EXIT_DID_NOT_RUN,
                    "%s figure %r carries threshold_claim: true with %d "
                    "recorded run(s); a design rule requires at least %d. A single run "
                    "landing the right side of a line does not establish that "
                    "the line was crossed.\n"
                    "  REPAIR: record %d more run(s), or drop threshold_claim "
                    "and report the figure without the crossing claim."
                    % (canonkit.REFUSAL_PREFIX, key, len(runs),
                       canonkit.THRESHOLD_CLAIM_MIN_RUNS,
                       canonkit.THRESHOLD_CLAIM_MIN_RUNS - len(runs)))

        figure = {
            "value": value,
            "unit": spec["unit"],
            "population": denominator,
            "population_label": spec["population_label"],
            "derived_from": [name for name, _ in items],
            "canon_bullet": spec["canon_bullet"],
            "canon_value": spec.get("canon_value"),
            "similar": spec.get("similar"),
            "similar_reason_ref": spec.get("similar_reason_ref"),
            "tier_achieved": spec.get("tier_achieved"),
            "reproduce_criterion": spec.get("reproduce_criterion"),
            "threshold_claim": bool(spec.get("threshold_claim")),
            "not_shown": spec.get("not_shown"),
            # The chain, recorded so verify.py can re-walk it rather than trust
            # the value above.
            "kind": spec.get("kind", "rate"),
            "predicate": spec.get("predicate"),
            "numerator": numerator,
            "denominator": denominator,
        }
        # an earlier finding: the RAW replicates, never only a summary statistic over them.
        if len(runs) >= canonkit.THRESHOLD_CLAIM_MIN_RUNS or runs:
            figure["runs"] = runs
        figures[key] = figure

    record = {
        "schema": SCHEMA,
        "schema_version": canonkit.SCHEMA_VERSION,
        "artifact": slug,
        "gate_token": token,
        # NOT a wall clock (an earlier plan item 11). The instant the run these figures
        # rest on FINISHED, read from that run's own record, falling back to
        # the gate's stamp when no run record exists. Both are machine-written
        # and neither moves when the derivation is repeated, which is what lets
        # figures.json be hash-pinned.
        "dated_at": (run.get("finished_at") or run.get("started_at")
                     or gate_dated_at(results_dir)),
        "started_at": run.get("started_at"),
        "started_at_utc": run.get("started_at_utc"),
        "figures": figures,
    }

    violations = canonkit.validate_figures(record)
    if violations:
        canonkit.die(
            canonkit.EXIT_DID_NOT_RUN,
            "%s derive.py assembled a figures record its own validator rejects "
            "(%d violation(s)):\n%s\n"
            "  REPAIR: this is a defect in the figure SPECS or in derive.py, "
            "not in the measurement."
            % (canonkit.REFUSAL_PREFIX, len(violations), "\n".join(violations)))

    canonkit.atomic_write_json(os.path.join(results_dir, "figures.json"), record)
    canonkit.report("DERIVE", True, 0, len(figures), 1,
                    note="authored %d figure(s) over %d per-item record(s)"
                         % (len(figures), len(items)))
    for key in sorted(figures):
        figure = figures[key]
        stream.write("[derive] %s = %s %s  (%d of %d %s)\n"
                     % (key, figure["value"], figure["unit"],
                        figure["numerator"], figure["denominator"],
                        figure["population_label"]))
    return record


def main(argv=None, stream=None):
    parser = argparse.ArgumentParser(description="Author this artifact's figures.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--specs", required=True,
                        help="path to a JSON file holding the declared figure specs")
    args = parser.parse_args(argv)
    with open(args.specs, "rb") as handle:
        specs = json.loads(handle.read().decode("utf-8"))
    derive(args.root, specs, stream=stream)
    return canonkit.EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
