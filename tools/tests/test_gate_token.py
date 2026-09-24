"""The gate: refuse first, mint a CONTENT-only token, record a failure as a record.

WHAT THIS MODULE GUARDS, AND WHY EACH TEST IS SHAPED THE WAY IT IS.
Two of the assertions below encode decisions marked HARD, and both are the kind
that keep passing for the wrong reason if written loosely:

  a design rule  the run token is a function of gate CONTENT ONLY. `dated_at` is stamped
        BESIDE it, never folded into the digest. The test that guards this runs
        the gate TWICE with two different dates and asserts the tokens are
        EQUAL -- a test that merely asserted "a token exists" would pass against
        an implementation that folds the date in, which is precisely the
        implementation a design rule overrides.
  a design rule  a FAILED gate still writes a full record and still MINTS its token. The
        test asserts the exit code, the record's existence, `passed: false`, a
        non-empty `failed_ids` AND a non-empty token together -- because an
        implementation that exits 3 without writing anything satisfies any one
        of those in isolation.

HOW THIS MODULE REACHES THE TEMPLATES.
A template is ARTIFACT-side source: in a generated artifact, `gate.py` sits
beside a vendored `canonkit.py` and reaches it with a plain sibling import. This
repository has no such layout, so every test here MATERIALISES one -- it copies
the frozen core and the templates under test into a temp directory and runs them
there. That is not a convenience: running the template in the layout it will
actually ship in is the only way these tests are evidence about the shipped
thing rather than about a repo-only arrangement.

The frozen core is reached through `test_canonkit.load_core()`, which loads it BY
PATH under its bare sibling name. This module therefore contains no
import of it, static or dynamic, and `test_repo_hygiene.py` scans this file
along with every other repo-side module to keep that true.
"""

import builtins
import importlib.util
import io
import json
import os
import shutil
import sys
import tokenize
from pathlib import Path

import pytest

from tools.tests import conftest
from tools.tests.test_canonkit import CORE_PATH, load_core

core = load_core()

REPO_ROOT = conftest.REPO_ROOT
TEMPLATES_DIR = REPO_ROOT / "templates"

# The one absolute boundary in this program. Assembled from fragments
# rather than pasted as one literal, for the same reason test_repo_hygiene.py
# assembles its needles: a pasted literal would itself be a hit for any future
# repo-wide scan looking for reads of the live store, and the natural "fix" --
# excluding this file -- would put the hole exactly where the guard belongs.
LIVE_STORE_PREFIX = "c:/users/an-account-name/research/" + "information"


def _normalise(path_text):
    """Lowercase with forward slashes, so a Windows path compares predictably."""
    return str(path_text).replace(chr(92), "/").lower()


# ---------------------------------------------------------------------------
# Materialising an artifact -- shared with test_runmeta.py and
# test_verify_chain.py, which import these two helpers from here.
# ---------------------------------------------------------------------------

_LOAD_COUNTER = [0]


def materialize_artifact(tmp_path, templates=("gate.py",), slug="demo-artifact"):
    """Copy the frozen core plus the named templates into a runnable artifact dir.

    The artifact layout is flat by contract: `canonkit.py` sits at the root
    beside the scripts that import it as a sibling, and `results/` is created
    empty. Nothing else is copied, so a template that reached for a file outside
    this set would fail here rather than silently succeed against the
    repository's own tree.
    """
    root = Path(tmp_path) / slug
    (root / "results").mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(CORE_PATH), str(root / "canonkit.py"))
    for name in templates:
        source = TEMPLATES_DIR / name
        assert source.is_file(), "no such template: %s" % source
        shutil.copy2(str(source), str(root / name))
    return root


def load_template(root, name):
    """Import a materialised template BY PATH, with its artifact root importable.

    Registered under a unique module name so two tests loading the same template
    never share mutated module state. `canonkit` is already in sys.modules under
    its bare sibling name (load_core did that), so the template's sibling import
    resolves to the same core object this module asserts against.
    """
    _LOAD_COUNTER[0] += 1
    stem = name[: -len(".py")]
    unique = "%s_materialised_%d" % (stem, _LOAD_COUNTER[0])
    path = Path(root) / name
    sys.path.insert(0, str(root))
    try:
        spec = importlib.util.spec_from_file_location(unique, str(path))
        if spec is None or spec.loader is None:
            raise ImportError("could not build a spec for %s" % path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[unique] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(root))
    return module


def fixed_clock(value):
    """A clock returning one fixed ISO string, so a test can vary ONLY the date."""
    return lambda: value


# Two instants far enough apart that no rounding could collapse them, and with
# DIFFERENT offsets, so an implementation folding either field into the digest
# is caught.
DATE_A = "2026-09-15T10:00:00-05:00"
DATE_B = "2027-01-02T23:45:01+02:00"
DATE_A_UTC = "2026-09-15T15:00:00+00:00"
DATE_B_UTC = "2027-01-02T21:45:01+00:00"

FIXTURE_FALLBACK = (
    "The 8B serving figure is NOT reproduced on this machine; the canon's "
    "fallback wording governs and the bullet ships the 4B measurement instead."
)
CANON_BULLET = "example-alpha:P4-01"


def write_fixture_canon(tmp_path, wording=FIXTURE_FALLBACK, name="canon-bullets.json"):
    """A FIXTURE canon, in tmp_path, never the real read-only store.

    an earlier round exercises a design rule's live read against this. The real store is not
    touched until an earlier round, and test_this_plan_opens_no_path_under_the_live_store
    asserts that mechanically rather than by assurance.
    """
    path = Path(tmp_path) / name
    payload = {
        "schema": "canon-bullets/1",
        "bullets": {
            CANON_BULLET: {
                "text": "Served an 8B model and measured the load curve.",
                "fallback_wording": wording,
            }
        },
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8", newline="\n")
    return path


def gate_artifact(tmp_path):
    root = materialize_artifact(tmp_path, templates=("gate.py",))
    return root, load_template(root, "gate.py")


def run_ok(gate, root, **kwargs):
    """Run the gate with the fixture defaults every passing test shares."""
    kwargs.setdefault("slug", "demo-artifact")
    kwargs.setdefault("env", {})
    kwargs.setdefault("clock_local", fixed_clock(DATE_A))
    kwargs.setdefault("clock_utc", fixed_clock(DATE_A_UTC))
    kwargs.setdefault("stream", io.StringIO())
    return gate.run_gate(root, **kwargs)


def read_gate(root):
    return json.loads((Path(root) / "results" / "gate.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The passing gate
# ---------------------------------------------------------------------------


def test_passing_gate_writes_a_record_and_exits_zero(tmp_path):
    root, gate = gate_artifact(tmp_path)
    stream = io.StringIO()

    code = run_ok(gate, root, stream=stream)

    assert code == core.EXIT_PASS, (
        "a gate whose assertions all hold exited %d:\n%s" % (code, stream.getvalue()))
    record = read_gate(root)
    assert record["passed"] is True
    assert record["failed_ids"] == []
    assert record["run_token"], "a passing gate minted no token"
    assert record["dated_at"] == DATE_A
    assert record["dated_at_utc"] == DATE_A_UTC


def test_gate_record_validates_against_the_frozen_core(tmp_path):
    """The record the gate writes must satisfy the core's own validator.

    Asserted against `validate_gate` rather than against a key list restated
    here: a second copy of the schema is a second thing to forget to update,
    and the core is the one that later refuses a malformed record.
    """
    root, gate = gate_artifact(tmp_path)
    run_ok(gate, root)

    violations = core.validate_gate(read_gate(root))
    assert violations == [], (
        "the gate wrote a record the frozen core rejects (%d violation(s)):\n%s"
        % (len(violations), "\n".join(violations)))


# ---------------------------------------------------------------------------
# a design rule (HARD): the token is CONTENT ONLY
# ---------------------------------------------------------------------------


def test_token_is_stable_across_differing_dated_at(tmp_path):
    """THE a design rule GUARD. Two runs, two dates, ONE token.

    This is the test that discriminates a design rule from the research's formula,
    which folds `dated_at` into the digest. Both implementations write a token
    and both write a date; only this comparison tells them apart.
    """
    root_a, gate_a = gate_artifact(tmp_path / "a")
    root_b, gate_b = gate_artifact(tmp_path / "b")

    run_ok(gate_a, root_a, clock_local=fixed_clock(DATE_A),
           clock_utc=fixed_clock(DATE_A_UTC))
    run_ok(gate_b, root_b, clock_local=fixed_clock(DATE_B),
           clock_utc=fixed_clock(DATE_B_UTC))

    first, second = read_gate(root_a), read_gate(root_b)

    assert first["dated_at"] != second["dated_at"], (
        "the two runs recorded the SAME dated_at, so this test could not have "
        "discriminated anything -- the fixture is broken, not the gate")
    assert first["run_token"] == second["run_token"], (
        "a design rule (HARD): the run token moved when only `dated_at` changed.\n"
        "  %s at %s\n  %s at %s\n"
        "The token is a function of gate CONTENT ONLY; the date is stamped "
        "BESIDE it. Folding the date in costs a full re-measure after any gate "
        "re-run and buys no discrimination the separate stamp does not already "
        "provide."
        % (first["run_token"], first["dated_at"],
           second["run_token"], second["dated_at"]))


def test_the_token_survives_a_measurement_and_a_warm_bytecode_cache(tmp_path):
    """REGRESSION, and it was found by running the gate rather than by reading it.

    The first draft enumerated every path under the artifact root, including
    `__pycache__` and `results/`. Both are written AFTER the gate runs, and the
    longest path is a `realized` value that enters the digest -- so the gate
    minted one token on a cold run and a different one once a bytecode cache
    existed or a measurement had written its records. a design rule's stability was
    destroyed by transient state having nothing to do with gate content, and
    every downstream token comparison would have failed for that reason.

    `results/` is the worse half: it holds the output of the very measurements
    this gate authorises, so re-running the gate afterwards would invalidate
    them. A gate describes the environment it authorises, never the results of
    what it authorised.
    """
    root, gate = gate_artifact(tmp_path)
    run_ok(gate, root)
    before = read_gate(root)["run_token"]

    cache = Path(root) / "__pycache__"
    cache.mkdir(exist_ok=True)
    (cache / "canonkit.cpython-312.pyc").write_bytes(b"\x00" * 16)
    items = Path(root) / "results" / "raw" / "items"
    items.mkdir(parents=True, exist_ok=True)
    for index in range(3):
        (items / ("item-%04d.json" % index)).write_text(
            '{"ok": true}\n', encoding="ascii", newline="\n")

    run_ok(gate, root, clock_local=fixed_clock(DATE_B),
           clock_utc=fixed_clock(DATE_B_UTC))
    after = read_gate(root)["run_token"]

    assert after == before, (
        "the token moved after a measurement wrote records and a bytecode "
        "cache appeared:\n  before %s\n  after  %s\n"
        "Neither is gate content. A token that tracks them cannot tell a "
        "changed gate from a gate that has simply been used."
        % (before, after))


def test_the_path_length_assertion_measures_absolute_paths(tmp_path):
    """The Windows ceiling applies to ABSOLUTE paths, so that is what is measured.

    Measuring the relative form under-reports by the whole length of the leading
    directories -- it would report a comfortable figure for a tree whose real
    paths sit just under the limit, which is the condition the assertion exists
    to detect.
    """
    root, gate = gate_artifact(tmp_path)

    paths = gate.enumerate_paths(root)

    assert paths, "the enumeration found no files at all"
    for path in paths:
        assert os.path.isabs(path), "%r is not an absolute path" % path
    assert not any("__pycache__" in p or "/results/" in p for p in paths), (
        "the enumeration includes transient or run-written paths:\n%s"
        % "\n".join(p for p in paths if "__pycache__" in p or "/results/" in p))


def test_a_sync_managed_root_fails_the_gate_even_when_invoked_as_dot(tmp_path):
    """REGRESSION: the assertion is matched against the ABSOLUTE root.

    Found by running the gate from inside a directory named OneDrive and
    watching it report a clean pass. The documented invocation is
    `python gate.py` from the artifact root, which makes `root` the string "."
    -- and no sync marker can appear in ".". The check could not fire, and a
    check that cannot fire is not a check; it would have passed for the entire
    life of the program while never once looking.

    Note this is a FAILED GATE (exit 3), not a refusal: the gate looked, and a
    declared assertion did not hold.
    """
    synced = Path(tmp_path) / "OneDrive" / "demo"
    root = materialize_artifact(synced, templates=("gate.py",))
    gate = load_template(root, "gate.py")
    canon = write_fixture_canon(tmp_path)

    inside = os.getcwd()
    os.chdir(str(root))
    try:
        # Invoked exactly as the REPAIR instructions tell an operator to.
        code = run_ok(gate, ".", canon_path=canon, canon_bullet=CANON_BULLET)
    finally:
        os.chdir(inside)

    assert code == core.EXIT_GUARD_FAIL, (
        "the gate passed from inside a sync-managed directory (exit %d)" % code)
    record = json.loads(
        (Path(root) / "results" / "gate.json").read_text(encoding="utf-8"))
    assert "ENV-NOT-SYNCED" in record["failed_ids"], record["failed_ids"]
    assert record["realized"]["ENV-NOT-SYNCED"] == ["onedrive"], (
        "the record does not say WHICH marker fired: %r"
        % (record["realized"]["ENV-NOT-SYNCED"],))
    assert record["run_token"], "a design rule: the failed gate minted no token"


def test_changing_one_assertion_string_changes_the_token(tmp_path):
    """The other half of a design rule: content really is what the token tracks.

    Without this, `return "constant"` would pass the stability test above. The
    pair is the check; neither half alone discriminates.
    """
    root, gate = gate_artifact(tmp_path)
    run_ok(gate, root)
    baseline = read_gate(root)["run_token"]

    moved = core.mint_run_token(
        "demo-artifact",
        [a + "-EDITED" if i == 0 else a
         for i, a in enumerate(baseline_assertions(root))],
        read_gate(root)["realized"],
        read_gate(root)["inputs_hash"])

    assert moved != baseline, (
        "editing one assertion string left the token unchanged at %s" % baseline)


def baseline_assertions(root):
    return list(read_gate(root)["assertions"])


def test_changing_a_realized_value_changes_the_token(tmp_path):
    """A realized value is read from the world, so it MUST move the token.

    a design rule's whole claim is that results produced under a gate that has since
    CHANGED are caught. A gate whose token ignored what it actually read would
    make that claim false while still passing the stability test.
    """
    root, gate = gate_artifact(tmp_path)
    run_ok(gate, root)
    record = read_gate(root)

    realized = dict(record["realized"])
    assert realized, "the gate recorded no realized values at all"
    key = sorted(realized)[0]
    realized[key] = "a value the world did not report"

    moved = core.mint_run_token("demo-artifact", record["assertions"], realized,
                                record["inputs_hash"])
    assert moved != record["run_token"], (
        "changing realized[%r] left the token unchanged" % key)


# ---------------------------------------------------------------------------
# a design rule: a FAILED gate is a full record WITH a token
# ---------------------------------------------------------------------------


def test_failed_gate_still_mints_a_token(tmp_path):
    """THE a design rule GUARD, asserted as a conjunction.

    Exit code, record existence, `passed: false`, a named failure and a minted
    token are all asserted together. An implementation that exits 3 and writes
    nothing satisfies the exit-code half alone -- and that implementation is
    exactly the one a design rule exists to forbid, because a measurement that ran anyway
    would then carry no key at all and be UNDETECTABLE.
    """
    root, gate = gate_artifact(tmp_path)
    canon = write_fixture_canon(tmp_path)
    stream = io.StringIO()

    code = run_ok(gate, root, force_failed_ids=["GATE-DEMO-PRECONDITION"],
                  canon_path=canon, canon_bullet=CANON_BULLET, stream=stream)

    assert code == core.EXIT_GUARD_FAIL, (
        "a failing gate exited %d, expected %d:\n%s"
        % (code, core.EXIT_GUARD_FAIL, stream.getvalue()))

    path = Path(root) / "results" / "gate.json"
    assert path.is_file(), (
        "a design rule: the FAILED gate wrote no record at all. A failed gate with no "
        "record leaves any measurement that ran anyway with no key to check.")

    record = read_gate(root)
    assert record["passed"] is False
    assert record["failed_ids"], "the record names no failed assertion"
    assert isinstance(record["run_token"], str) and record["run_token"], (
        "a design rule: the FAILED gate minted no token (got %r). Minting one is what "
        "makes a measurement that ran anyway carry a POISONED token rather "
        "than none." % (record.get("run_token"),))
    assert core.validate_gate(record) == [], core.validate_gate(record)


def test_require_gate_on_a_failed_gate_exits_2_and_echoes_the_fallback(tmp_path, capsys):
    """The refusal a later run meets, and the wording it must carry.

    Exit 2, not 1: an absent or failed gate means the measurement COULD NOT
    LOOK, which is a different claim from "looked and found a problem".
    """
    root, gate = gate_artifact(tmp_path)
    canon = write_fixture_canon(tmp_path)
    run_ok(gate, root, force_failed_ids=["GATE-DEMO-PRECONDITION"],
           canon_path=canon, canon_bullet=CANON_BULLET)
    capsys.readouterr()

    with pytest.raises(SystemExit) as excinfo:
        core.require_gate(str(Path(root) / "results"))

    assert excinfo.value.code == core.EXIT_DID_NOT_RUN, (
        "require_gate exited %r, expected %d"
        % (excinfo.value.code, core.EXIT_DID_NOT_RUN))
    stderr = capsys.readouterr().err
    assert core.REFUSAL_PREFIX in stderr, stderr
    assert FIXTURE_FALLBACK in stderr, (
        "the refusal did not quote the canon's fallback wording VERBATIM. A "
        "refusal that does not say what governs instead is a dead end.\n%s"
        % stderr)


def test_audit_mode_returns_the_poisoned_token(tmp_path):
    """a design rule's payoff: the failed gate's token is retrievable for auditing.

    Without this branch the token minted on failure would be unreachable, and
    minting it would buy nothing.
    """
    root, gate = gate_artifact(tmp_path)
    canon = write_fixture_canon(tmp_path)
    run_ok(gate, root, force_failed_ids=["GATE-DEMO-PRECONDITION"],
           canon_path=canon, canon_bullet=CANON_BULLET)

    token = core.require_gate(str(Path(root) / "results"), audit=True)
    assert token == read_gate(root)["run_token"]


# ---------------------------------------------------------------------------
# a design rule: the fallback wording is read LIVE, with a date and a hash
# ---------------------------------------------------------------------------


def test_fallback_wording_is_read_live_with_its_sha256_and_read_date(tmp_path):
    """A stale fallback quoted at the moment of a refusal is worse than none."""
    root, gate = gate_artifact(tmp_path)
    canon = write_fixture_canon(tmp_path)

    run_ok(gate, root, force_failed_ids=["GATE-DEMO-PRECONDITION"],
           canon_path=canon, canon_bullet=CANON_BULLET)
    record = read_gate(root)

    assert record["fallback_wording"] == FIXTURE_FALLBACK, (
        "the wording was not copied VERBATIM: %r" % record["fallback_wording"])
    source = record["fallback_source"]
    assert source["sha256"] == core.sha256_file(str(canon)), (
        "the recorded sha256 is not the canon file's")
    assert source["read_at"] == DATE_A, "the read date was not stamped"
    assert _normalise(canon) == _normalise(source["path"])


def test_an_unreadable_canon_is_an_error_object_not_a_missing_key(tmp_path):
    """A missing key and a failed read are DIFFERENT claims and stay different."""
    root, gate = gate_artifact(tmp_path)
    missing = Path(tmp_path) / "no-such-canon.json"

    run_ok(gate, root, force_failed_ids=["GATE-DEMO-PRECONDITION"],
           canon_path=missing, canon_bullet=CANON_BULLET)
    record = read_gate(root)

    assert "fallback_source" in record, "the key was omitted on a failed read"
    source = record["fallback_source"]
    assert source.get("error"), (
        "a failed canon read recorded no error object: %r" % (source,))
    assert "FileNotFoundError" in source["error"], source["error"]
    assert core.validate_gate(record) == [], core.validate_gate(record)


# ---------------------------------------------------------------------------
# The refusals (exit 2) -- the gate could not even look
# ---------------------------------------------------------------------------


def test_langsmith_variable_refuses_with_exit_2_and_names_it(tmp_path, capsys):
    """a project requirement / an earlier step. `langgraph` exfiltrates traces while appearing offline.

    Authored here although the exposure lands earlier: artifacts are
    GENERATED from this template, so an assertion missing here is invisible
    everywhere later.
    """
    root, gate = gate_artifact(tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        run_ok(gate, root, env={"LANGSMITH_API_KEY": "sk-not-a-real-key"})

    assert excinfo.value.code == core.EXIT_DID_NOT_RUN
    stderr = capsys.readouterr().err
    assert core.REFUSAL_PREFIX in stderr, stderr
    assert "LANGSMITH_API_KEY" in stderr, (
        "the refusal did not NAME the variable, so the operator cannot act on "
        "it:\n%s" % stderr)
    assert not (Path(root) / "results" / "gate.json").exists(), (
        "a refused gate wrote a record. Exit 2 means it COULD NOT LOOK; a "
        "record would imply it did.")


def test_langchain_tracing_variable_refuses_with_exit_2(tmp_path, capsys):
    root, gate = gate_artifact(tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        run_ok(gate, root, env={"LANGCHAIN_TRACING_V2": "true"})

    assert excinfo.value.code == core.EXIT_DID_NOT_RUN
    assert "LANGCHAIN_TRACING_V2" in capsys.readouterr().err


def test_a_path_of_240_characters_refuses_with_exit_2(tmp_path, capsys):
    """The path is BUILT as a string and fed through the enumeration seam.

    Deliberately not created on disk. Creating a 240-character path on this
    machine can fail for reasons of its own, and a refusal that arrives because
    the FIXTURE could not be built is a non-zero exit for the wrong reason --
    it would prove nothing about the assertion under test.
    """
    root, gate = gate_artifact(tmp_path)
    long_path = "C:/" + ("d" * 200) + "/" + ("f" * 36) + ".json"
    assert len(long_path) >= gate.MAX_PATH_CHARS, (
        "the fixture path is %d characters, below the %d limit it must exceed"
        % (len(long_path), gate.MAX_PATH_CHARS))
    stream = io.StringIO()

    with pytest.raises(SystemExit) as excinfo:
        run_ok(gate, root, paths=[long_path], stream=stream)

    assert excinfo.value.code == core.EXIT_DID_NOT_RUN
    combined = capsys.readouterr().err + stream.getvalue()
    assert core.REFUSAL_PREFIX in combined, combined
    assert str(len(long_path)) in combined, (
        "the refusal did not print the measured length:\n%s" % combined)


def test_the_path_length_is_printed_on_the_passing_case_too(tmp_path):
    """Printed on EVERY branch, or a clean run is silent about what it measured.

    Same property as the population line in the frozen core: a print guarded by
    the failure branch makes the passing run indistinguishable from a run that
    never measured the path at all.
    """
    root, gate = gate_artifact(tmp_path)
    short = ["C:/short/a.json", "C:/short/b.json"]
    stream = io.StringIO()

    code = run_ok(gate, root, paths=short, stream=stream)
    printed = stream.getvalue()

    assert code == core.EXIT_PASS, printed
    expected = max(len(p) for p in short)
    assert str(expected) in printed, (
        "the passing run never printed the longest-path length (%d):\n%s"
        % (expected, printed))


def test_two_paths_differing_only_by_case_refuse(tmp_path, capsys):
    """Case-only collisions survive a case-insensitive filesystem silently.

    Fed through the enumeration seam for the same reason as the length test:
    NTFS will not hold both files at once, so a disk-built fixture could not
    exist -- and the pair still reaches this program through a git tree
    checked out somewhere that will.
    """
    root, gate = gate_artifact(tmp_path)
    colliding = ["results/Raw/item.json", "results/raw/item.json"]

    with pytest.raises(SystemExit) as excinfo:
        run_ok(gate, root, paths=colliding)

    assert excinfo.value.code == core.EXIT_DID_NOT_RUN
    stderr = capsys.readouterr().err
    assert core.REFUSAL_PREFIX in stderr, stderr
    assert "raw/item.json" in stderr.lower(), stderr


# ---------------------------------------------------------------------------
# The GPU branch -- present but INERT unless the slug is flagged
# ---------------------------------------------------------------------------


def test_the_gpu_branch_is_inert_unless_the_slug_is_flagged(tmp_path):
    """No plan earlier touches the GPU, so an unflagged run must not probe it.

    The stub raises if called. An implementation that probed unconditionally
    would surface here rather than in the first phase that has a real card
    under load.
    """
    root, gate = gate_artifact(tmp_path)

    def exploding_runner(argv):
        raise AssertionError("nvidia-smi was probed on an unflagged slug: %r" % (argv,))

    code = run_ok(gate, root, gpu_required=False, nvidia_smi_runner=exploding_runner)

    assert code == core.EXIT_PASS
    assert "free_vram_mib" not in read_gate(root)["realized"]


def test_a_flagged_slug_records_free_vram_as_a_population_fact(tmp_path):
    """Free VRAM is READ, never computed against the nameplate 6,141 MiB.

    Three values have been observed across two days on this machine, so the
    nameplate is never the number to compute against -- the reading at the
    moment of the run is a population fact for the record.
    """
    root, gate = gate_artifact(tmp_path)

    code = run_ok(gate, root, gpu_required=True,
                  nvidia_smi_runner=lambda argv: "5854\n")

    assert code == core.EXIT_PASS
    assert read_gate(root)["realized"]["free_vram_mib"] == 5854


# ---------------------------------------------------------------------------
# Structural guards over the template's own source
# ---------------------------------------------------------------------------


def test_mtime_is_named_only_in_comments(tmp_path):
    """Judged by TOKEN TYPE, not by a text match.

    `grep -c mtime` cannot tell a call from a comment explaining why the call is
    not made -- and this file must explain exactly that, because ordering by
    mtime is weak across the NTFS/WSL2 boundary and is trivially touched. A
    guard that fires on its own rationale is the failure this phase has already
    paid for five times; tokenizing is the observation that discriminates.
    """
    source = TEMPLATES_DIR / "gate.py"
    comments = 0
    offenders = []
    with tokenize.open(str(source)) as handle:
        for token in tokenize.generate_tokens(handle.readline):
            if "mtime" not in token.string:
                continue
            if token.type == tokenize.COMMENT:
                comments += 1
            else:
                offenders.append("line %d: %s %r"
                                 % (token.start[0], tokenize.tok_name[token.type],
                                    token.string.strip()[:70]))

    assert not offenders, (
        "gate.py names mtime outside a comment (%d occurrence(s)):\n%s"
        % (len(offenders), "\n".join(offenders)))
    assert comments >= 1, (
        "gate.py never mentions mtime at all. The absence of the ordering trap "
        "from the record is how the next maintainer reintroduces it; state in a "
        "comment why recorded ISO timestamps are used instead.")


def test_this_plan_opens_no_path_under_the_live_store(tmp_path):
    """an earlier step, asserted by observation rather than by assurance.

    Every `open` performed while the gate runs end to end -- including a design rule's
    LIVE canon read, the one call that crosses toward the store -- is recorded
    and checked. The recorded population is asserted non-empty first: a patch
    that silently failed to install would otherwise report a clean run over zero
    observations, which is an UNRUN check wearing a pass.
    """
    root, gate = gate_artifact(tmp_path)
    canon = write_fixture_canon(tmp_path)
    opened = []
    real_open = builtins.open

    def recording_open(file, *args, **kwargs):
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    builtins.open = recording_open
    try:
        run_ok(gate, root, force_failed_ids=["GATE-DEMO-PRECONDITION"],
               canon_path=canon, canon_bullet=CANON_BULLET)
    finally:
        builtins.open = real_open

    assert len(opened) > 0, (
        "recorded 0 open() calls while running the gate -- the patch did not "
        "take, so this assertion checked nothing")
    offenders = [p for p in opened if _normalise(p).startswith(LIVE_STORE_PREFIX)]
    assert not offenders, (
        "observed %d open() call(s); %d crossed into the read-only live store:\n%s"
        % (len(opened), len(offenders), "\n".join(offenders)))


def test_the_canon_is_opened_read_only_in_binary(tmp_path):
    """The store is READ-ONLY, so the live read may not carry a writable mode.

    Binary also keeps the sha256 honest: reading as text re-introduces the
    line-ending translation that would hash the same content two ways on two
    machines.
    """
    root, gate = gate_artifact(tmp_path)
    canon = write_fixture_canon(tmp_path)
    modes = []
    real_open = builtins.open

    def recording_open(file, mode="r", *args, **kwargs):
        if _normalise(file) == _normalise(canon):
            modes.append(mode)
        return real_open(file, mode, *args, **kwargs)

    builtins.open = recording_open
    try:
        run_ok(gate, root, force_failed_ids=["GATE-DEMO-PRECONDITION"],
               canon_path=canon, canon_bullet=CANON_BULLET)
    finally:
        builtins.open = real_open

    assert modes, "the canon was never opened, so a design rule's live read did not happen"
    bad = [m for m in modes if "w" in m or "a" in m or "+" in m]
    assert not bad, "the canon was opened writable: %r" % (bad,)
    assert all("b" in m for m in modes), (
        "the canon was opened in text mode %r; the sha256 recorded beside the "
        "wording must be over BYTES" % (modes,))


# ---------------------------------------------------------------------------
# The gate as a subprocess -- real exit codes, no pipeline in between
# ---------------------------------------------------------------------------


def test_the_gate_runs_as_a_script_and_reports_its_own_exit_code(tmp_path):
    """Run the template the way an artifact runs it, and read the CHILD's status.

    A shell pipeline would report its last stage's status instead; `run_cli`
    uses shell=False and returns `CompletedProcess.returncode`, so the code
    asserted here is the gate's own.
    """
    root = materialize_artifact(tmp_path, templates=("gate.py",))
    env = dict(os.environ)
    env.pop("LANGCHAIN_TRACING_V2", None)
    for name in [k for k in env if k.startswith("LANGSMITH_")]:
        env.pop(name)

    result = conftest.run_cli([sys.executable, "gate.py", "--slug", "demo-artifact"],
                              cwd=root, env=env)

    assert result.exit_code == core.EXIT_PASS, (
        "gate.py exited %d\nSTDOUT:\n%s\nSTDERR:\n%s"
        % (result.exit_code, result.stdout, result.stderr))
    assert (Path(root) / "results" / "gate.json").is_file()

    poisoned = dict(env)
    poisoned["LANGSMITH_API_KEY"] = "sk-not-a-real-key"
    refused = conftest.run_cli([sys.executable, "gate.py", "--slug", "demo-artifact"],
                               cwd=root, env=poisoned)
    assert refused.exit_code == core.EXIT_DID_NOT_RUN, (
        "gate.py exited %d with LANGSMITH_API_KEY set\nSTDERR:\n%s"
        % (refused.exit_code, refused.stderr))
