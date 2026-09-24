"""The machine side six checks hang off: offset timestamps and the cost triple.

WHY THIS FILE EXISTS AT ALL, MEASURED RATHER THAN ASSUMED.
The shared pattern note probed both shipped artifacts for
`started_at|finished_at|dated_at|"timestamp"|isoformat` and found exactly ONE
hit -- a synthetic log document's `@timestamp` field, not a run stamp. So
CHECK-02 ("the README date equals the date component of a machine-emitted
`started_at`") has no machine side today, and of the cost triple only
`total_runtime_seconds` exists anywhere. Every assertion below is therefore
about new construction, not about preserving an existing behaviour.

THE TWO SHAPES THESE TESTS REFUSE, both of which type-check happily:

  A NAIVE TIMESTAMP WEARING AN OFFSET. The banned constructor returns a datetime
  carrying no timezone at all; appending a literal UTC marker to it produces a
  string that CLAIMS an offset while the object never had one. Every downstream
  consumer then parses an aware datetime built from an unaware one. The test
  below parses what was actually written and asserts on `tzinfo`.

  AN OMITTED COST FIELD READING AS A ZERO. A run that spent nothing and a run
  that never recorded what it spent are different claims. a project requirement re-derives
  per-path spend before each path starts, and that re-derivation depends on the
  second one being distinguishable from the first -- so all three fields are
  REQUIRED and a run that spent nothing writes 0.0.
"""

import datetime
import io
import json
import subprocess
import tokenize
from pathlib import Path

import pytest

from tools.tests import conftest
from tools.tests.test_canonkit import load_core
from tools.tests.test_gate_token import (
    TEMPLATES_DIR,
    load_template,
    materialize_artifact,
)

core = load_core()

REPO_ROOT = conftest.REPO_ROOT

RUN_TEMPLATES = ("runmeta.py", "provenance.py", "run_example.py")
GATE_TOKEN = "f" * 64


def run_artifact(tmp_path):
    root = materialize_artifact(tmp_path, templates=RUN_TEMPLATES)
    return root, load_template(root, "runmeta.py")


def provenance_artifact(tmp_path):
    root = materialize_artifact(tmp_path, templates=RUN_TEMPLATES)
    return root, load_template(root, "provenance.py")


def results_dir(root):
    return Path(root) / "results"


# ---------------------------------------------------------------------------
# a design rule: real offsets, written by the run
# ---------------------------------------------------------------------------


def test_started_at_parses_as_an_aware_datetime_with_a_real_offset(tmp_path):
    """Parsed, not pattern-matched.

    A regex over the string would pass against a naive datetime with a literal
    offset pasted on the end, which is exactly the lie this test exists to
    catch. Parsing and reading `tzinfo` is the observation that discriminates.
    """
    root, runmeta = run_artifact(tmp_path)

    handle = runmeta.start_run(results_dir(root), "run-0001", GATE_TOKEN)
    record = json.loads(Path(handle.path).read_text(encoding="utf-8"))

    parsed = datetime.datetime.fromisoformat(record["started_at"])
    assert parsed.tzinfo is not None, (
        "started_at parsed to a NAIVE datetime: %r. A string carrying an offset "
        "whose object has none is a lie that type-checks."
        % record["started_at"])

    real_offset = datetime.datetime.now().astimezone().utcoffset()
    assert parsed.utcoffset() == real_offset, (
        "started_at carries offset %s while this machine's local offset is %s -- "
        "the stamp is not this machine's local time"
        % (parsed.utcoffset(), real_offset))
    assert parsed.utcoffset() != datetime.timedelta(0), (
        "started_at carries a +00:00 offset on a machine whose local offset is "
        "%s, so the value was hard-coded to UTC rather than read" % real_offset)


def test_started_at_and_its_utc_counterpart_are_the_same_instant(tmp_path):
    """Two fields, one moment. a design rule stores both; neither may drift from the other."""
    root, runmeta = run_artifact(tmp_path)

    handle = runmeta.start_run(results_dir(root), "run-0001", GATE_TOKEN)
    record = json.loads(Path(handle.path).read_text(encoding="utf-8"))

    local = datetime.datetime.fromisoformat(record["started_at"])
    utc = datetime.datetime.fromisoformat(record["started_at_utc"])
    assert utc.tzinfo is not None, record["started_at_utc"]
    assert abs((local - utc).total_seconds()) < 2.0, (
        "started_at (%s) and started_at_utc (%s) are %.1f seconds apart"
        % (record["started_at"], record["started_at_utc"],
           (local - utc).total_seconds()))


def test_finish_run_writes_the_closing_stamps(tmp_path):
    root, runmeta = run_artifact(tmp_path)

    handle = runmeta.start_run(results_dir(root), "run-0001", GATE_TOKEN)
    path = runmeta.finish_run(handle, api_spend_usd=0.0, gpu_minutes=0.0)
    record = json.loads(Path(path).read_text(encoding="utf-8"))

    for key in ("finished_at", "finished_at_utc"):
        assert record.get(key), "the record carries no %s" % key
        assert datetime.datetime.fromisoformat(record[key]).tzinfo is not None


# ---------------------------------------------------------------------------
# The gate token
# ---------------------------------------------------------------------------


def test_the_record_carries_the_gate_token(tmp_path):
    root, runmeta = run_artifact(tmp_path)

    handle = runmeta.start_run(results_dir(root), "run-0001", GATE_TOKEN)
    record = json.loads(Path(handle.path).read_text(encoding="utf-8"))

    assert record["gate_token"] == GATE_TOKEN


def test_start_run_refuses_an_empty_gate_token(tmp_path):
    """A run with no token is a run nothing can be checked against.

    Both the empty string and whitespace are refused: a token that is present
    but blank would satisfy a truthiness check while carrying no key.
    """
    root, runmeta = run_artifact(tmp_path)

    for empty in ("", "   ", None):
        with pytest.raises(ValueError) as excinfo:
            runmeta.start_run(results_dir(root), "run-0001", empty)
        assert "gate" in str(excinfo.value).lower(), str(excinfo.value)


# ---------------------------------------------------------------------------
# The cost triple -- a project requirement's literal field names
# ---------------------------------------------------------------------------


def test_cost_triple_is_required(tmp_path):
    """Omitting any one field RAISES rather than writing a partial record.

    The failure mode this forbids is silent: a record missing `api_spend_usd`
    reads downstream as a run that cost nothing, because `.get(key, 0.0)` cannot
    tell an absence from a zero. The refusal happens before the write, so no
    partial record exists to be read later.
    """
    root, runmeta = run_artifact(tmp_path)

    handle = runmeta.start_run(results_dir(root), "run-0001", GATE_TOKEN)
    before = Path(handle.path).read_text(encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        runmeta.finish_run(handle, gpu_minutes=0.0)
    assert "api_spend_usd" in str(excinfo.value), str(excinfo.value)

    with pytest.raises(ValueError) as excinfo:
        runmeta.finish_run(handle, api_spend_usd=0.0)
    assert "gpu_minutes" in str(excinfo.value), str(excinfo.value)

    assert Path(handle.path).read_text(encoding="utf-8") == before, (
        "a refused finish_run still rewrote the record; the refusal must happen "
        "before anything is written")


def test_a_run_that_spent_nothing_writes_zero_rather_than_omitting_the_key(tmp_path):
    """An omitted key and a zero are different claims and must stay different."""
    root, runmeta = run_artifact(tmp_path)

    handle = runmeta.start_run(results_dir(root), "run-0001", GATE_TOKEN)
    path = runmeta.finish_run(handle, api_spend_usd=0.0, gpu_minutes=0.0)
    record = json.loads(Path(path).read_text(encoding="utf-8"))

    for key in ("api_spend_usd", "gpu_minutes", "wall_seconds"):
        assert key in record, "the record omits %s" % key
        assert isinstance(record[key], (int, float)), (
            "%s is %r, expected a number" % (key, record[key]))
    assert record["api_spend_usd"] == 0.0
    assert record["gpu_minutes"] == 0.0


def test_wall_seconds_is_derived_from_the_handle_not_supplied_by_the_caller(tmp_path):
    """Both halves: the caller's value is REFUSED, and the derived one is real.

    An accepted-but-ignored parameter would not hold this decision -- the next
    caller passes it and the one after that reads it back expecting to see it.
    So passing `wall_seconds` raises, and a separate assertion proves the value
    that IS written comes from the handle.
    """
    root, runmeta = run_artifact(tmp_path)
    claimed = 999999.0

    handle = runmeta.start_run(results_dir(root), "run-0001", GATE_TOKEN)
    with pytest.raises(ValueError) as excinfo:
        runmeta.finish_run(handle, api_spend_usd=0.0, gpu_minutes=0.0,
                           wall_seconds=claimed)
    assert "wall_seconds" in str(excinfo.value), str(excinfo.value)

    # Rewind the handle's own start marker, so the derived duration is a value
    # only the handle could have produced.
    handle.started_monotonic -= 5.0
    path = runmeta.finish_run(handle, api_spend_usd=0.0, gpu_minutes=0.0)
    record = json.loads(Path(path).read_text(encoding="utf-8"))

    assert record["wall_seconds"] >= 5.0, (
        "wall_seconds is %r; the handle was rewound 5 seconds, so a value "
        "derived from it cannot be smaller" % record["wall_seconds"])
    assert record["wall_seconds"] != claimed


# ---------------------------------------------------------------------------
# provenance.py -- the assertion the shipped analog lacks
# ---------------------------------------------------------------------------


def test_provenance_asserts_its_sources_count_against_a_committed_literal(tmp_path):
    """a design rule's derive-and-assert shape, which the analog has only half of.

    The shipped `provenance.py` derives its count by filtering `SOURCES` on
    existence -- and never asserts `len(SOURCES)` against a literal. Without
    that assertion a name silently dropped from the list makes the derived count
    agree with the shorter list and the census stops checking.
    """
    root, provenance = provenance_artifact(tmp_path)

    assert provenance.SOURCES_DECLARED == len(provenance.SOURCES), (
        "the declaration and its literal already disagree in the shipped file")
    assert provenance.SOURCES_DECLARED > 0, "an empty declared set checks nothing"

    with pytest.raises(RuntimeError) as excinfo:
        provenance.assert_sources_declared(
            sources=list(provenance.SOURCES)[:-1],
            declared=provenance.SOURCES_DECLARED)
    message = str(excinfo.value)
    assert "SOURCES" in message and str(provenance.SOURCES_DECLARED) in message, message


def test_a_failed_image_probe_is_an_error_object_never_a_bare_null(tmp_path):
    """The one line in the analog that must NOT be copied.

    `except Exception: return None` makes an unreachable daemon, a missing
    binary and an image with no digest into one indistinguishable `null`. Under
    CHECK-08 a null digest is a FINDING, so the probe records the exception
    CLASS and the caller can count it.
    """
    root, provenance = provenance_artifact(tmp_path)

    def failing_runner(argv):
        raise subprocess.TimeoutExpired(argv, 60)

    result = provenance.image_digest("postgres:16.4", runner=failing_runner)

    assert result is not None, "the probe returned a bare None"
    assert result["ok"] is False
    assert result["error_class"] == "TimeoutExpired", result
    assert "TimeoutExpired" in result["error"], result


def test_a_failed_image_probe_is_counted_in_the_printed_summary(tmp_path):
    """A finding nobody counted is a finding nobody acts on.

    The population line prints probed / ok / failed as SEPARATE numbers, for the
    same reason the frozen core prints found and checked separately: one number
    cannot make a probe that silently returned nothing visible.
    """
    root, provenance = provenance_artifact(tmp_path)
    stream = io.StringIO()

    def failing_runner(argv):
        raise OSError("docker daemon is not running")

    record = provenance.build_record(
        root, run=_run_block(), free_vram_mib=5854,
        image_runner=failing_runner, host_runner=_stub_host_runner,
        stream=stream)
    printed = stream.getvalue()

    failed = [t for t, v in record["images"].items() if not v.get("ok")]
    assert failed, "no image probe failed, so this test checked nothing"
    assert "failed=%d" % len(failed) in printed, (
        "the printed summary did not count the %d failed probe(s):\n%s"
        % (len(failed), printed))
    for tag in failed:
        assert record["images"][tag]["error_class"] == "OSError"


def test_provenance_record_validates_against_the_frozen_core(tmp_path):
    root, provenance = provenance_artifact(tmp_path)

    record = provenance.build_record(
        root, run=_run_block(), free_vram_mib=5854,
        image_runner=lambda argv: "postgres@sha256:" + "a" * 64,
        host_runner=_stub_host_runner, stream=io.StringIO())

    violations = core.validate_provenance(record)
    assert violations == [], "\n".join(violations)


def test_provenance_carries_the_run_block_both_shipped_artifacts_lack(tmp_path):
    """The measured gap: no timestamp, no GPU block, no cost triple as shipped."""
    root, provenance = provenance_artifact(tmp_path)

    record = provenance.build_record(
        root, run=_run_block(), free_vram_mib=5854,
        image_runner=lambda argv: "postgres@sha256:" + "a" * 64,
        host_runner=_stub_host_runner, stream=io.StringIO())

    for key in ("started_at", "finished_at", "started_at_utc", "finished_at_utc",
                "api_spend_usd", "gpu_minutes", "wall_seconds"):
        assert key in record["run"], "the run block omits %s" % key
    assert record["free_vram_mib"] == 5854
    assert record["host"]["docker_desktop_version"], (
        "the Docker Desktop version is recorded PER RUN, never once")
    assert record["host"]["docker_ncpu"] == 24
    assert record["host"]["docker_mem_total"] > 0


def test_provenance_sources_are_hashed_and_counted(tmp_path):
    """The derived count is over the files that EXIST, and it is printed."""
    root, provenance = provenance_artifact(tmp_path)
    stream = io.StringIO()

    record = provenance.build_record(
        root, run=_run_block(), free_vram_mib=5854,
        image_runner=lambda argv: "postgres@sha256:" + "a" * 64,
        host_runner=_stub_host_runner, stream=stream)

    assert record["sources"], "no source file was hashed"
    for name, digest in record["sources"].items():
        assert len(digest) == 64, "%s hashed to %r" % (name, digest)
    assert "%d of %d" % (len(record["sources"]), provenance.SOURCES_DECLARED) \
        in stream.getvalue(), stream.getvalue()


def _run_block():
    now = datetime.datetime.now().astimezone()
    return {
        "started_at": now.isoformat(),
        "started_at_utc": now.astimezone(datetime.timezone.utc).isoformat(),
        "finished_at": now.isoformat(),
        "finished_at_utc": now.astimezone(datetime.timezone.utc).isoformat(),
        "api_spend_usd": 0.0,
        "gpu_minutes": 0.0,
        "wall_seconds": 1.5,
    }


def _stub_host_runner(argv):
    """Stands in for `docker info` / `docker version`, so no daemon is needed."""
    joined = " ".join(argv)
    if "version" in joined:
        return "4.46.0"
    return json.dumps({"NCPU": 24, "MemTotal": 15546056704})


# ---------------------------------------------------------------------------
# Structural guards over the templates' own source
# ---------------------------------------------------------------------------


def test_the_naive_utc_constructor_appears_nowhere(tmp_path):
    """Asserted over TOKENS, and the needle is assembled rather than pasted.

    A pasted literal would put the banned name into this file, which is itself
    scanned by the repo-wide guards -- the same trap `test_repo_hygiene.py`
    avoids by building its needles from fragments.
    """
    needle = "utc" + "now"
    for name in ("runmeta.py", "provenance.py"):
        path = TEMPLATES_DIR / name
        hits = []
        with tokenize.open(str(path)) as handle:
            for token in tokenize.generate_tokens(handle.readline):
                if needle in token.string:
                    hits.append("%s:%d %s" % (name, token.start[0],
                                              token.string.strip()[:60]))
        assert not hits, (
            "%s names the naive UTC constructor (%d occurrence(s)); it returns "
            "an unaware datetime and a design rule needs a real offset:\n%s"
            % (name, len(hits), "\n".join(hits)))


def test_run_example_uses_the_chr92_form_for_windows_paths(tmp_path):
    """The `chr(92)` form this project's own rules require.

    A literal backslash escape typed into tool input is collapsed on the way in
    on this machine, so the shipped `run_rate_test.py:37` shape is the one that
    survives being authored through a tool. Either that form is present, or the
    file contains no backslash path literal at all.
    """
    text = (TEMPLATES_DIR / "run_example.py").read_text(encoding="utf-8")
    assert text.count("chr(92)") >= 1, (
        "run_example.py contains no chr(92) path handling")


def test_run_example_requires_the_gate_before_it_measures(tmp_path):
    """The refusal block sits at the HEAD of the driver, before any work.

    Asserted by running it: a driver that called require_gate somewhere after
    its first write would still contain the call.
    """
    root = materialize_artifact(tmp_path, templates=RUN_TEMPLATES)
    result = conftest.run_cli(
        [__import__("sys").executable, "run_example.py", "--items", "3"], cwd=root)

    assert result.exit_code == core.EXIT_DID_NOT_RUN, (
        "run_example.py exited %d with no gate present, expected %d\nSTDERR:\n%s"
        % (result.exit_code, core.EXIT_DID_NOT_RUN, result.stderr))
    assert core.REFUSAL_PREFIX in result.stderr, result.stderr
    assert not list((Path(root) / "results" / "raw").glob("*.json")), (
        "the driver wrote per-item records despite refusing")


def test_run_example_measures_once_the_gate_has_passed(tmp_path):
    """End to end: gate, then driver, then a record carrying the gate's token.

    This is the ordering the whole plan exists to make PROVABLE -- and it is
    proved by running the two in sequence and reading what the second wrote,
    not by comparing two dates a single author supplied.
    """
    import sys as _sys

    root = materialize_artifact(tmp_path, templates=RUN_TEMPLATES + ("gate.py",))
    gated = conftest.run_cli(
        [_sys.executable, "gate.py", "--slug", "demo-artifact"], cwd=root,
        env=_clean_env())
    assert gated.exit_code == core.EXIT_PASS, gated.stderr

    token = json.loads(
        (Path(root) / "results" / "gate.json").read_text(encoding="utf-8"))["run_token"]

    driven = conftest.run_cli(
        [_sys.executable, "run_example.py", "--items", "3"], cwd=root)
    assert driven.exit_code == core.EXIT_PASS, (
        "run_example.py exited %d\nSTDOUT:\n%s\nSTDERR:\n%s"
        % (driven.exit_code, driven.stdout, driven.stderr))

    records = sorted((Path(root) / "results" / "raw").glob("*.json"))
    assert records, "the driver wrote no run record"
    written = json.loads(records[0].read_text(encoding="utf-8"))
    assert written["gate_token"] == token, (
        "the run stamped %r, the gate minted %r"
        % (written["gate_token"], token))
    assert written["items"] == 3


def _clean_env():
    import os as _os

    env = dict(_os.environ)
    env.pop("LANGCHAIN_TRACING_V2", None)
    for name in [k for k in env if k.startswith("LANGSMITH_")]:
        env.pop(name)
    return env
