"""The reference measurement driver: refuse, open a run, measure, close it.

THE ORDER OF THE FIRST THREE STATEMENTS IS THE POINT OF THIS FILE.
require_gate() is called BEFORE anything is opened, written or measured. That
ordering is what makes gate-before-measurement a fact about the run rather than
an inference from two dates the same author wrote: the gate mints a token from
its own content, this driver stamps that token into everything it writes, and
verify.py refuses any results file whose token does not match.

Copied from the shipped drivers (run_k6_sweep.py, run_rate_test.py,
run_benchmark.py), which the shared pattern note marks as an exact analog. Three of their
conventions are carried verbatim in spirit:

  THE REFUSAL AT THE HEAD. Three copies of it exist across that artifact, all
  exiting 2, all to stderr -- it is the artifact's convention, not one author's
  habit. The variant worth copying is the one that tells the operator what to
  DO, so every refusal here carries a repair instruction.

  DIGEST-PINNED IMAGES. A moving tag means "the same benchmark" can silently
  become a different load generator on a later run. The run would still produce
  numbers; they would be numbers about something else.

  WINDOWS PATH HANDLING, in the chr(92) form this project's rules require, plus
  MSYS_NO_PATHCONV so Git Bash does not rewrite a container-side absolute path
  into a Windows one on the way through.

WHAT A REAL DRIVER REPLACES. `measure_one_item` here is a deterministic stand-in
so the template is runnable and testable as shipped. A real path swaps it for
the actual measurement and changes nothing else -- the record shape, the token
stamping and the cost triple all stay.
"""

import argparse
import os
import sys

import canonkit
import provenance
import runmeta

# Digest-pinned, never a tag. See the docstring: "latest" is a moving target and
# a benchmark that silently changes its own tooling is not a benchmark.
EXAMPLE_IMAGE = "redis@sha256:" + "0" * 64

HERE = os.path.dirname(os.path.abspath(__file__))


def _win(path):
    """Forward slashes for anything crossing into a container or a shell.

    chr(92) rather than a literal escape: on this machine an escape typed into
    tool input is collapsed on the way in, so the literal form does not survive
    being authored through tooling. The shipped run_rate_test.py:37 uses exactly
    this shape.
    """
    return str(path).replace(chr(92), "/")


def container_env():
    """Git Bash rewrites container-side absolute paths without this flag set."""
    env = dict(os.environ)
    env["MSYS_NO_PATHCONV"] = "1"
    return env


def measure_one_item(index):
    """A deterministic stand-in for the real measurement.

    Deterministic on purpose: the template's own tests must be able to assert
    that changing ONE per-item record changes the derived figure, and a random
    value would make that assertion flaky for a reason unrelated to the chain.
    """
    return {
        "index": index,
        "latency_ms": 10.0 + index,
        "ok": index % 4 != 3,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Reference measurement driver.")
    parser.add_argument("--root", default=HERE)
    parser.add_argument("--items", type=int, default=10)
    parser.add_argument("--run-id", default="run-0001")
    args = parser.parse_args(argv)

    root = args.root
    results = os.path.join(str(root), "results")

    # REFUSE FIRST. Before a directory is created, before a file is opened,
    # before anything is measured. require_gate exits 2 when the gate is absent
    # or failed, and quotes the canon's fallback wording when it failed.
    gate_token = canonkit.require_gate(results)

    if args.items < 1:
        canonkit.die(canonkit.EXIT_DID_NOT_RUN,
                     "%s --items=%d. A run over zero items is a DID-NOT-RUN, "
                     "never a clean run.\n  REPAIR: pass --items with a positive "
                     "count." % (canonkit.REFUSAL_PREFIX, args.items))

    handle = runmeta.start_run(results, args.run_id, gate_token,
                               extra={"items": args.items,
                                      "image": EXAMPLE_IMAGE,
                                      "artifact_root": _win(root)})

    written = 0
    for index in range(args.items):
        runmeta.write_item(results, "item-%04d" % index, measure_one_item(index))
        written += 1

    path = runmeta.finish_run(handle, api_spend_usd=0.0, gpu_minutes=0.0,
                              extra={"items_written": written})

    free_vram = None
    try:
        import gate as gate_module

        free_vram = gate_module.read_free_vram_mib()
    except (ImportError, OSError, ValueError):
        # Absent on a machine with no card. Recorded as an absence below rather
        # than guessed at, because the nameplate figure is never the number to
        # compute against.
        free_vram = None

    record = provenance.build_record(
        root, run=_cost_block(path), free_vram_mib=free_vram,
        image_runner=None if free_vram is not None else _absent_probe)
    canonkit.atomic_write_json(os.path.join(results, "provenance.json"), record)

    canonkit.report("RUN", True, 0, written, 1,
                    note="run %s token %s" % (args.run_id, gate_token[:12]))
    return canonkit.EXIT_PASS


def _cost_block(run_path):
    import json

    with open(str(run_path), "rb") as handle:
        record = json.loads(handle.read().decode("utf-8"))
    return dict((key, record.get(key)) for key in
                ("started_at", "started_at_utc", "finished_at", "finished_at_utc",
                 "api_spend_usd", "gpu_minutes", "wall_seconds"))


def _absent_probe(argv):
    raise OSError("docker was not probed: this template run measures nothing real")


if __name__ == "__main__":
    sys.exit(main())
