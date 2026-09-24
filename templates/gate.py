"""The opening gate: refuse before measuring, mint the run token, record a failure.

    "the arm is verified against the running service's /stats before anything is
     measured -- this script records the arm, it does not assert it."
        -- example-cache-benchmark/run_k6_sweep.py:1-7, this program's owner,
           in a shipped artifact, before this repository existed.

That sentence is this file's whole posture. THE GATE RECORDS A FACT READ FROM THE
WORLD; it does not assert one. Every value under `realized` below was read at
gate time, and the token is a digest of what was read.

THERE ARE TWO DIFFERENT FAILURES HERE AND THEY MUST NOT BE COLLAPSED.

    REFUSAL (exit 2)    An environment precondition makes measuring unsafe or
                        meaningless. The gate COULD NOT LOOK. No record is
                        written, because a record would imply it did.
    FAILED GATE (exit 3) The gate looked, and a declared assertion did not hold.
                        A FULL record IS written, `passed: false`, the failing
                        ids named -- AND THE TOKEN IS STILL MINTED.

WHY A FAILED GATE STILL MINTS ITS TOKEN.
Minting no token would leave a failed gate with no key at all, and a measurement
that ran anyway would then be UNDETECTABLE -- there would be nothing to compare.
Minting one means such a measurement carries a POISONED token that verify.py
rejects loudly. The failure becomes evidence instead of a silence.

WHY `dated_at` IS NOT AN ARGUMENT TO THE MINT.
The token is a function of gate CONTENT ONLY, and `dated_at` is stamped BESIDE
it. Do not "fix" this back. The two failures a run token exists to catch are
(i) results produced under a gate that has since CHANGED, caught exactly by a
content digest, and (ii) results copied from an EARLIER SESSION, caught by the
separately stamped `dated_at`, which names the gate INSTANCE. Folding the date
into the digest buys no discrimination over that pair and costs a full re-measure
after any gate re-run -- on a machine whose free VRAM has been observed at three
values across two days, a gate re-run is routine, not exceptional.

ORDERING IS BY THE RECORDED ISO TIMESTAMPS INSIDE THE JSON. The reason is stated
in a real comment beside the imports, not here -- see the note above them.

THE ENVIRONMENT ASSERTIONS SHIP NOW EVEN THOUGH MOST BITE LATER.
Artifacts are GENERATED from this file, so an assertion missing here is missing
everywhere, invisibly. The tracing assertion is the clearest case: its
exposure lands earlier, but `langgraph` exfiltrates traces silently while
appearing to run offline, and by then fourteen artifacts would already have been
generated without the check.
"""

# ORDERING RULE, and why it is a comment rather than prose in the docstring:
# a guard over this file judges by TOKEN TYPE, and a docstring is a string
# expression, not a comment. Stating the rule here puts it where the guard can
# tell an explanation apart from a use.
#
# Records are ordered by the recorded ISO timestamps INSIDE the JSON, never by
# file mtime. mtime is weak across the NTFS/WSL2 boundary, it is preserved by
# ordinary copies, and it is trivially touched -- so a results file copied
# forward from an earlier session keeps an entirely plausible mtime while its
# recorded dated_at cannot be laundered the same way. That is a second,
# independent reason the content token beats a date: neither field this file
# writes can be rewritten by moving a file around.

import argparse
import json
import os
import subprocess
import sys

import canonkit

SCHEMA = "canonkit/gate/1"

# The Windows path ceiling this program works under. Printed on EVERY branch --
# a limit that is only mentioned when it is breached leaves the passing run
# unable to say what it measured.
MAX_PATH_CHARS = 240

# Assertions whose failure is a REFUSAL (exit 2) rather than a failed gate.
# These say the gate could not look at all.
REFUSAL_ASSERTION_IDS = (
    "ENV-PATH-LENGTH",
    "ENV-PATH-CASE",
    "ENV-TRACING-UNSET",
)

# a project requirement / an earlier step. Presence alone is recorded, never the VALUE: a gate record is
# not a place a credential may land.
TRACING_EXACT = ("LANGCHAIN_TRACING_V2",)
TRACING_PREFIX = "LANGSMITH_"

ONEDRIVE_MARKERS = ("onedrive",)


class AssertionResult(object):
    """One declared assertion, its verdict, and the value READ FROM THE WORLD."""

    def __init__(self, id, passed, realized, detail=""):
        self.id = id
        self.passed = passed
        self.realized = realized
        self.detail = detail

    def as_string(self):
        """The stable rendering that enters the token.

        json.dumps with sort_keys so a nested realized value renders identically
        in every process. repr() would not be safe: float formatting and set
        iteration order can both vary, and a token that is not reproducible is
        not a token.
        """
        return "%s=%s" % (self.id, json.dumps(self.passed, sort_keys=True))


# ---------------------------------------------------------------------------
# Reading the world
# ---------------------------------------------------------------------------


# Directories excluded from the enumeration, and the exclusion is load-bearing
# rather than tidiness. Two separate failures were MEASURED by running the gate
# and reading what it enumerated:
#
#   THE TOKEN MOVED BETWEEN A COLD AND A WARM RUN. The longest path is a
#   `realized` value, so it enters the digest. With __pycache__ included, the
#   first run (no cache) and the second (cache present) minted DIFFERENT tokens
#   for a gate whose content had not changed by a byte -- destroying exactly the
#   stability a design rule exists to provide, and for a reason having nothing to do with
#   the gate.
#
#   `results/` IS WRITTEN BY THE RUNS THIS GATE AUTHORISES. Enumerating it makes
#   the gate's own token depend on the output of measurements taken under it, so
#   re-running the gate after a measurement would invalidate that measurement.
#   The gate must describe the environment it authorises, never the results of
#   what it authorised.
EXCLUDED_DIRS = ("__pycache__", ".git", ".venv", ".pytest_cache", "results")


def enumerate_paths(root):
    """Every ARTIFACT path under `root`, as ABSOLUTE forward-slash strings.

    ABSOLUTE, because the ceiling this feeds is a limit on absolute paths. An
    earlier draft measured the relative form, which under-reported by the whole
    length of the leading directories -- it would have reported a comfortable 40
    characters for a tree whose real paths were near the limit, which is to say
    it could not detect the condition it exists to detect.

    Returned rather than acted on, so a caller (and a test) can supply the list
    instead. Two of the assertions below describe conditions that CANNOT be
    built on this filesystem -- NTFS will not hold two names differing only by
    case, and creating a 240-character path fails for reasons of its own -- yet
    both reach this program through a tree checked out somewhere that will.
    """
    found = []
    for base, dirnames, filenames in os.walk(str(root)):
        # Pruned in place, so os.walk does not descend into them at all.
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for name in filenames:
            full = os.path.abspath(os.path.join(base, name))
            found.append(str(full).replace(chr(92), "/"))
    return sorted(found)


def assert_path_length(paths, limit=MAX_PATH_CHARS):
    longest = max((len(p) for p in paths), default=0)
    return AssertionResult(
        "ENV-PATH-LENGTH", longest < limit, longest,
        "longest path is %d character(s), limit %d" % (longest, limit))


def assert_no_case_collision(paths):
    seen = {}
    for path in paths:
        seen.setdefault(path.lower(), []).append(path)
    collisions = sorted(v for v in seen.values() if len(v) > 1)
    return AssertionResult(
        "ENV-PATH-CASE", not collisions, len(collisions),
        "case-only collision(s): %s" % (collisions or "none"))


def assert_not_onedrive(root):
    """Refuse a sync-managed directory. Matched against the ABSOLUTE root.

    MEASURED DEFECT, fixed here: the first draft matched `str(root)` as passed.
    The documented way to run this file is `python gate.py` from the artifact
    root, which makes `root` the string ".", and no sync marker can ever appear
    in ".". So the assertion reported a clean pass from inside a OneDrive
    directory -- a check that could not fire is not a check, and this one would
    have passed for the entire life of the program without anyone noticing.

    The realized value is the matched marker rather than a bare bool, so the
    record says WHICH marker fired instead of only that something did.
    """
    lowered = os.path.abspath(str(root)).replace(chr(92), "/").lower()
    hit = [marker for marker in ONEDRIVE_MARKERS if marker in lowered]
    return AssertionResult(
        "ENV-NOT-SYNCED", not hit, hit,
        "artifact root matched %s" % (hit or "no sync marker"))


def assert_no_tracing(env):
    """a project requirement. Records PRESENCE, never the value.

    A gate record that carried the value would put a credential into a file this
    program hashes, prints and commits.
    """
    names = sorted(
        [name for name in env if name in TRACING_EXACT]
        + [name for name in env if name.startswith(TRACING_PREFIX)])
    return AssertionResult(
        "ENV-TRACING-UNSET", not names, names,
        "set: %s" % (", ".join(names) if names else "none"))


def read_free_vram_mib(runner=None):
    """Free VRAM, READ at gate time. Never computed from the nameplate.

    Three different values have been observed on this card across two days, so
    the nameplate figure is never the number to compute against. This reading is
    a POPULATION FACT for the record, not housekeeping.
    """
    if runner is None:
        runner = _default_nvidia_smi
    raw = runner(["nvidia-smi", "--query-gpu=memory.free",
                  "--format=csv,noheader,nounits"])
    return int(str(raw).strip().splitlines()[0].strip())


def _default_nvidia_smi(argv):
    completed = subprocess.run(argv, capture_output=True, text=True, timeout=60,
                               shell=False)
    if completed.returncode != 0:
        raise OSError("nvidia-smi exited %d: %s"
                      % (completed.returncode, completed.stderr.strip()))
    return completed.stdout


def read_fallback_wording(canon_path, bullet_key, read_at):
    """a design rule. Read the canon's fallback wording LIVE, verbatim, at gate time.

    The store is READ-ONLY: opened "rb", nothing is ever written back. Binary
    also keeps the recorded sha256 honest -- reading as text would re-introduce
    line-ending translation and hash the same content two ways on two machines.

    A stale fallback quoted at the moment of a refusal is worse than none, which
    is why this is a live read rather than a lookup in the committed snapshot.

    Returns (wording, source). On a failed read the source carries an ERROR
    OBJECT and the key is still present: a missing key and a failed read are
    different claims, and collapsing them would let a read that never happened
    look like a canon that says nothing.
    """
    source = {"path": str(canon_path).replace(chr(92), "/"),
              "sha256": None,
              "read_at": read_at,
              "bullet": bullet_key}
    try:
        with open(str(canon_path), "rb") as handle:
            payload = handle.read()
        source["sha256"] = canonkit.sha256_bytes(payload)
        data = json.loads(payload.decode("utf-8"))
        bullets = data.get("bullets", data)
        entry = bullets[bullet_key]
        wording = entry["fallback_wording"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        source["error"] = "%s: %s" % (exc.__class__.__name__, exc)
        return "", source
    return wording, source


def compute_inputs_hash(root, inputs):
    """Digest the DECLARED input set, recording absences rather than skipping them.

    A file that is simply missing from the digest is indistinguishable from one
    that was never declared. Recording `<absent>` keeps the two apart, so a
    disappearing input moves the token instead of quietly shrinking its domain.
    """
    lines = []
    for relative in sorted(inputs or []):
        full = os.path.join(str(root), relative)
        if os.path.isfile(full):
            lines.append("%s=%s" % (relative, canonkit.sha256_file(full)))
        else:
            lines.append("%s=<absent>" % relative)
    return canonkit.sha256_bytes("\n".join(lines).encode("ascii", "backslashreplace"))


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


def evaluate_assertions(root, env, paths=None, gpu_required=False,
                        nvidia_smi_runner=None):
    """Evaluate every declared assertion and return the results in a fixed order."""
    if paths is None:
        paths = enumerate_paths(root)
    results = [
        assert_path_length(paths),
        assert_no_case_collision(paths),
        assert_not_onedrive(root),
        assert_no_tracing(env),
    ]
    # INERT unless the slug is flagged. No plan earlier touches the GPU, and a
    # probe that runs unconditionally would fail on every machine without a card
    # for a reason unrelated to the gate.
    if gpu_required:
        try:
            free = read_free_vram_mib(nvidia_smi_runner)
            results.append(AssertionResult("GPU-FREE-VRAM", free > 0, free,
                                           "free VRAM %d MiB, read at gate time" % free))
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            results.append(AssertionResult(
                "GPU-FREE-VRAM", False, None,
                "could not read free VRAM: %s: %s" % (exc.__class__.__name__, exc)))
    return results


def _refuse(result, stream):
    canonkit.die(
        canonkit.EXIT_DID_NOT_RUN,
        "%s the gate cannot measure here -- %s failed: %s\n"
        "  REPAIR: %s"
        % (canonkit.REFUSAL_PREFIX, result.id, result.detail,
           _repair_for(result)))


def _repair_for(result):
    if result.id == "ENV-PATH-LENGTH":
        return ("move the artifact nearer the drive root so its longest path is "
                "under %d characters, then re-run `python gate.py`."
                % MAX_PATH_CHARS)
    if result.id == "ENV-PATH-CASE":
        return ("rename one of the colliding paths so no two differ only by "
                "case, then re-run `python gate.py`.")
    if result.id == "ENV-TRACING-UNSET":
        return ("unset %s in this shell and re-run `python gate.py`. Leaving it "
                "set exfiltrates traces to a managed service while the run "
                "appears to be offline."
                % (", ".join(result.realized) or "the tracing variable"))
    return "fix the condition named above, then re-run `python gate.py`."


def build_gate_record(slug, results, inputs_hash, dated_at, dated_at_utc,
                      fallback_wording, fallback_source, env):
    """Assemble the record. THE TOKEN IS MINTED FROM CONTENT ONLY."""
    assertions = [r.as_string() for r in results]
    realized = {}
    for result in results:
        realized[result.id] = result.realized
    if "GPU-FREE-VRAM" in realized:
        realized["free_vram_mib"] = realized["GPU-FREE-VRAM"]
    failed_ids = [r.id for r in results if not r.passed]

    # a design rule (HARD): CONTENT ONLY. `dated_at` is a parameter of this function and
    # is deliberately NOT passed to the mint -- it is stamped into the record
    # below, BESIDE the token. The RED that proves this line discriminates is
    # quoted in an earlier summary: folding the date in produced two different
    # tokens for one unchanged gate.
    token = canonkit.mint_run_token(slug, assertions, realized, inputs_hash)

    return {
        "schema": SCHEMA,
        "schema_version": canonkit.SCHEMA_VERSION,
        "artifact": slug,
        "passed": not failed_ids,
        "run_token": token,
        "dated_at": dated_at,
        "dated_at_utc": dated_at_utc,
        "assertions": assertions,
        "realized": realized,
        "inputs_hash": inputs_hash,
        "failed_ids": failed_ids,
        "fallback_wording": fallback_wording,
        "fallback_source": fallback_source,
        "env": env,
    }


def environment_fingerprint(env):
    """Presence-only for the tracing flags. Never a value."""
    return {
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "tracing_flags_set": sorted(
            [n for n in env if n in TRACING_EXACT]
            + [n for n in env if n.startswith(TRACING_PREFIX)]),
    }


def run_gate(root, slug, env=None, paths=None, canon_path=None, canon_bullet=None,
             gpu_required=False, nvidia_smi_runner=None, inputs=None,
             clock_local=None, clock_utc=None, force_failed_ids=None,
             stream=None):
    """Run the gate. Returns 0 (pass) or 3 (failed gate); refusals exit 2."""
    env = dict(os.environ) if env is None else dict(env)
    clock_local = clock_local or canonkit.now_local
    clock_utc = clock_utc or canonkit.now_utc
    stream = stream if stream is not None else sys.stdout

    results = evaluate_assertions(root, env, paths=paths,
                                  gpu_required=gpu_required,
                                  nvidia_smi_runner=nvidia_smi_runner)
    by_id = dict((r.id, r) for r in results)

    # PRINTED ON EVERY BRANCH, before any decision. A measurement the passing run
    # never reports is indistinguishable from one it never took.
    length = by_id["ENV-PATH-LENGTH"]
    stream.write("[gate] longest path = %d characters (limit %d)\n"
                 % (length.realized, MAX_PATH_CHARS))

    # REFUSE FIRST. Before any record, before the token, before measuring.
    for result in results:
        if result.id in REFUSAL_ASSERTION_IDS and not result.passed:
            _refuse(result, stream)

    if force_failed_ids:
        for forced in force_failed_ids:
            results.append(AssertionResult(forced, False, "forced",
                                           "declared failure supplied by the caller"))

    dated_at = clock_local()
    dated_at_utc = clock_utc()
    failed = [r for r in results if not r.passed]

    fallback_wording, fallback_source = "", None
    if failed and canon_path is not None:
        fallback_wording, fallback_source = read_fallback_wording(
            canon_path, canon_bullet, dated_at)

    record = build_gate_record(
        slug, results, compute_inputs_hash(root, inputs), dated_at, dated_at_utc,
        fallback_wording, fallback_source, environment_fingerprint(env))

    violations = canonkit.validate_gate(record)
    if violations:
        canonkit.die(canonkit.EXIT_DID_NOT_RUN,
                     "%s the gate assembled a record its own validator rejects "
                     "(%d violation(s)):\n%s\n  REPAIR: this is a defect in "
                     "gate.py, not in the environment."
                     % (canonkit.REFUSAL_PREFIX, len(violations),
                        "\n".join(violations)))

    # a design rule: THE RECORD IS WRITTEN ON BOTH BRANCHES, before the verdict is known.
    # A failed gate is a complete record that happens to say `passed: false`, not
    # an absence. Writing it here rather than inside the passing branch is the
    # whole of a design rule: a measurement that ran anyway then carries a POISONED token
    # verify.py rejects loudly, instead of no key at all.
    results_dir = os.path.join(str(root), "results")
    canonkit.atomic_write_json(os.path.join(results_dir, "gate.json"), record)

    if failed:
        canonkit.report("GATE", False, len(failed), len(results), 1,
                        note="FAILED: %s -- token %s minted anyway"
                             % (", ".join(r.id for r in failed),
                                record["run_token"][:12]))
        return canonkit.EXIT_GUARD_FAIL

    canonkit.report("GATE", True, 0, len(results), 1,
                    note="token %s dated %s" % (record["run_token"][:12], dated_at))
    return canonkit.EXIT_PASS


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the artifact's opening gate.")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--canon", default=None)
    parser.add_argument("--canon-bullet", default=None)
    parser.add_argument("--gpu-required", action="store_true")
    args = parser.parse_args(argv)
    return run_gate(args.root, args.slug, canon_path=args.canon,
                    canon_bullet=args.canon_bullet,
                    gpu_required=args.gpu_required)


if __name__ == "__main__":
    sys.exit(main())
