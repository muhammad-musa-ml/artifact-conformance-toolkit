"""The run-metadata emitter: offset timestamps, the gate token, the cost triple.

SIX CHECKS HANG OFF THIS FILE, AND TODAY NONE OF THEM HAS A MACHINE SIDE.
A probe over both shipped artifacts for started_at / finished_at / dated_at /
isoformat returns exactly ONE hit, and it is a synthetic log document's field
rather than a run stamp. So CHECK-02 (the README's date equals the date
component of a machine-emitted started_at), CHECK-04 (gate-before-measurement
ordering), CHECK-09, CHECK-10 and CHECK-24 have nothing to read. This is the
cheapest high-value item in the program: roughly a hundred lines that turn five
unrunnable checks into runnable ones.

THE TIMESTAMPS ARE WRITTEN BY THE RUN, NEVER BY A HUMAN.
Both forms are stored. The local stamp carries a REAL offset because CHECK-02
compares its LOCAL date component against the README's date, and on this machine
a silently-UTC stamp is wrong by a day for several hours of every day. The UTC
counterpart sits beside it for ordering across a ~103-day program. Two fields
cost nothing; picking one costs either the reader's intuition or correct
ordering.

Both come from the frozen core's now_local() / now_utc(). The naive UTC
constructor is never used here -- it returns a datetime carrying no timezone at
all, so a literal offset appended to it produces a string that claims what the
object never had. That failure type-checks, which is why it is worth a paragraph.

THE COST TRIPLE IS {api_spend_usd, gpu_minutes, wall_seconds}, ALL THREE REQUIRED.
A run that spent nothing writes 0.0. It does not omit the key. An omitted key
and a zero are different claims, and a project requirement re-derives each path's metered
spend and GPU hours before that path starts -- a re-derivation that depends
entirely on being able to tell "recorded as nothing" from "never recorded".

`wall_seconds` is DERIVED from the handle and cannot be supplied. It is measured
on the monotonic clock rather than by subtracting the two wall-clock stamps, so
a clock adjustment or a DST transition mid-run cannot produce a negative
duration.
"""

import os
import time

import canonkit

SCHEMA = "canonkit/run/1"

# Where a run's own record lives, and where the PER-ITEM records the chain walks
# live. Kept apart deliberately: derive.py and verify.py enumerate the per-item
# directory, and a run record sitting in the same glob would be counted as an
# item -- inflating a denominator with a file that is not one.
RAW_DIRNAME = "raw"
ITEMS_DIRNAME = "items"

# The sentinel that makes an omitted cost field a REFUSAL rather than a zero.
# A default of 0.0 would silently record "this run was free" for every caller
# who forgot, which is the exact confusion the triple exists to prevent.
_REQUIRED = object()


class RunHandle(object):
    """What start_run returns and finish_run consumes."""

    def __init__(self, results_dir, run_id, gate_token, started_at, started_at_utc,
                 started_monotonic, path, record):
        self.results_dir = results_dir
        self.run_id = run_id
        self.gate_token = gate_token
        self.started_at = started_at
        self.started_at_utc = started_at_utc
        self.started_monotonic = started_monotonic
        self.path = path
        self.record = record


def raw_dir(results_dir):
    return os.path.join(str(results_dir), RAW_DIRNAME)


def items_dir(results_dir):
    return os.path.join(str(results_dir), RAW_DIRNAME, ITEMS_DIRNAME)


def environment_fingerprint():
    """What the machine was, recorded PER RUN rather than once."""
    import platform
    import sys

    return {
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
    }


def start_run(results_dir, run_id, gate_token, extra=None, clock_local=None,
              clock_utc=None, monotonic=None):
    """Open a run record. Refuses a run that carries no gate token.

    The token is what later ties this record to the gate that authorised it. A
    run with a blank one cannot be checked against anything, so it is refused
    here rather than written and discovered later.
    """
    if gate_token is None or not str(gate_token).strip():
        raise ValueError(
            "start_run(%r): refusing to open a run with an empty gate token. A "
            "run record with no token cannot be tied to the gate that "
            "authorised it, so nothing downstream can tell it from a run that "
            "measured without one. Call canonkit.require_gate() first and pass "
            "what it returns." % (run_id,))

    clock_local = clock_local or canonkit.now_local
    clock_utc = clock_utc or canonkit.now_utc
    monotonic = monotonic or time.monotonic

    started_at = clock_local()
    started_at_utc = clock_utc()
    path = os.path.join(raw_dir(results_dir), "%s.json" % run_id)

    record = {
        "schema": SCHEMA,
        "schema_version": canonkit.SCHEMA_VERSION,
        "run_id": run_id,
        "gate_token": gate_token,
        "started_at": started_at,
        "started_at_utc": started_at_utc,
        "finished_at": None,
        "finished_at_utc": None,
        "env": environment_fingerprint(),
    }
    if extra:
        record.update(extra)

    canonkit.atomic_write_json(path, record)
    return RunHandle(results_dir, run_id, gate_token, started_at, started_at_utc,
                     monotonic(), path, record)


def finish_run(handle, api_spend_usd=_REQUIRED, gpu_minutes=_REQUIRED,
               clock_local=None, clock_utc=None, monotonic=None, extra=None,
               **derived):
    """Close a run record. All three cost fields are REQUIRED.

    THE REFUSALS HAPPEN BEFORE ANYTHING IS WRITTEN, so a refused call leaves the
    opening record exactly as start_run wrote it. A partial record written and
    then rejected would be indistinguishable, to any later reader, from a run
    that genuinely recorded nothing.

    `wall_seconds` is REFUSED rather than accepted-and-ignored. An
    accepted-but-ignored parameter does not hold a decision: the next caller
    passes it, and the one after that reads it back expecting to see what they
    sent. The RED for both refusals is quoted in an earlier summary.
    """
    clock_local = clock_local or canonkit.now_local
    clock_utc = clock_utc or canonkit.now_utc
    monotonic = monotonic or time.monotonic

    missing = [name for name, value in (("api_spend_usd", api_spend_usd),
                                        ("gpu_minutes", gpu_minutes))
               if value is _REQUIRED]
    if missing:
        raise ValueError(
            "finish_run(%r): the cost triple is incomplete -- %s not supplied. "
            "All three of api_spend_usd, gpu_minutes and wall_seconds are "
            "REQUIRED; a run that spent nothing writes 0.0 and does not omit "
            "the key. An omitted field reads downstream as a run that cost "
            "nothing, because .get(key, 0.0) cannot tell an absence from a "
            "zero, and a project requirement re-derives per-path spend from exactly this "
            "record." % (handle.run_id, " and ".join(missing)))

    if "wall_seconds" in derived:
        raise ValueError(
            "finish_run(%r): wall_seconds is DERIVED from the handle and cannot "
            "be supplied (got %r). It is measured on the monotonic clock, so a "
            "clock adjustment or a DST transition mid-run cannot produce a "
            "negative duration -- and a caller-supplied duration would record "
            "what the caller believed rather than what elapsed."
            % (handle.run_id, derived["wall_seconds"]))

    unknown = sorted(set(derived) - {"wall_seconds"})
    if unknown:
        raise ValueError(
            "finish_run(%r): unknown field(s) %s. Pass run-specific values "
            "through `extra=` so they are recorded deliberately rather than "
            "absorbed by a signature that accepts anything."
            % (handle.run_id, unknown))

    wall_seconds = monotonic() - handle.started_monotonic

    record = dict(handle.record)
    record.update({
        "finished_at": clock_local(),
        "finished_at_utc": clock_utc(),
        "api_spend_usd": float(api_spend_usd),
        "gpu_minutes": float(gpu_minutes),
        "wall_seconds": wall_seconds,
    })
    if extra:
        record.update(extra)

    canonkit.atomic_write_json(handle.path, record)
    handle.record = record
    return handle.path


def write_item(results_dir, item_id, payload):
    """Write ONE per-item record -- the first link of the chain verify.py walks.

    Per-item records are what make a figure re-derivable: a count over them is
    reproducible, while a numerator typed into a summary is not.
    """
    path = os.path.join(items_dir(results_dir), "%s.json" % item_id)
    record = dict(payload)
    record.setdefault("item_id", item_id)
    canonkit.atomic_write_json(path, record)
    return path
