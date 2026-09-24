"""The chain a mutation must break: per-item records -> count -> figure -> verify.

WHAT "THE CHAIN" MEANS HERE, AND WHY IT IS TESTED RATHER THAN DRAWN.

    per-item records -> count(predicate) -> numerator -> / denominator -> rendered

Every link is re-walked by verify.py. If any link is short-circuited -- if the
figure is read from a summary someone typed instead of recomputed from the
records -- then a mutation of one per-item record propagates nowhere and
verify.py passes over a corrupted artifact. That is why
test_changing_one_per_item_record_changes_the_derived_figure exists here rather
than in the mutation plan: an earlier plan owns a design rule and a design rule, and what this plan
owes it is a chain PROVEN to propagate, so its mutants are testing a live chain
rather than a short-circuited one.

THE TWO ERROR WORDINGS THAT ARE ASSERTED AS EXACT STRINGS.
A figure with no per-item record behind it fails hardest. When that same figure
ALSO equals the canon figure, the message must say so in those terms, because
that pair -- no evidence, and exactly the number the canon already claimed -- is
the signature of a QUOTATION rather than a measurement. The wording is what
teaches the next executor, so it is pinned as a constant and asserted verbatim;
a test that only checked the exit code would keep passing while the message
decayed into a generic missing-source error.
"""

import ast
import hashlib
import io
import json
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

CHAIN_TEMPLATES = ("gate.py", "runmeta.py", "provenance.py", "run_example.py",
                   "derive.py", "finalize.py", "verify.py")

# 8 items, of which those with index % 4 == 3 are not ok -> 6 of 8 -> 75.0%.
ITEM_COUNT = 8
EXPECTED_OK_RATE = 75.0
CANON_BULLET = "example-alpha:P4-01"


def build_chain(tmp_path, item_count=ITEM_COUNT, slug="demo-artifact"):
    """Gate, then run, then per-item records -- in that order, for real.

    The gate is actually executed rather than faked, so the token every record
    below carries is one the gate genuinely minted from its own content.
    """
    root = materialize_artifact(tmp_path, templates=CHAIN_TEMPLATES, slug=slug)
    gate = load_template(root, "gate.py")
    code = gate.run_gate(root, slug=slug, env={}, stream=io.StringIO())
    assert code == core.EXIT_PASS, "the fixture gate did not pass"

    runmeta = load_template(root, "runmeta.py")
    results = Path(root) / "results"
    token = json.loads((results / "gate.json").read_text(encoding="utf-8"))["run_token"]

    handle = runmeta.start_run(results, "run-0001", token)
    for index in range(item_count):
        runmeta.write_item(results, "item-%04d" % index,
                           {"index": index, "ok": index % 4 != 3,
                            "latency_ms": 10.0 + index})
    runmeta.finish_run(handle, api_spend_usd=0.0, gpu_minutes=0.0)
    return root, token


def ok_rate_spec(**overrides):
    """The declared figure the fixture chain supports."""
    spec = {
        "key": "ok_rate_pct",
        "unit": "percent",
        "kind": "rate",
        "predicate": "ok",
        "population_label": "replayed items",
        "canon_bullet": CANON_BULLET,
        "canon_value": 75.0,
        "similar": "CONFIRMS",
        "similar_reason_ref": "prior-run-note.md#ok-rate",
        "tier_achieved": "T1",
        "reproduce_criterion": {"kind": "relative", "tolerance": 0.01},
        "threshold_claim": False,
        "not_shown": "A hermetic template fixture; it measures nothing real.",
    }
    spec.update(overrides)
    return spec


def derive_into(root, specs, **kwargs):
    derive = load_template(root, "derive.py")
    kwargs.setdefault("stream", io.StringIO())
    return derive, derive.derive(root, specs=specs, **kwargs)


def read_figures(root):
    return json.loads(
        (Path(root) / "results" / "figures.json").read_text(encoding="utf-8"))


def run_verify(root, argv=None, stream=None):
    verify = load_template(root, "verify.py")
    stream = stream if stream is not None else io.StringIO()
    code = verify.main(argv or ["--tier", "derive", "--root", str(root)],
                       stream=stream)
    return verify, code, stream.getvalue()


# ---------------------------------------------------------------------------
# derive.py -- the ONLY place a number is authored
# ---------------------------------------------------------------------------


def test_derive_refuses_a_population_of_zero_and_names_the_figure(tmp_path, capsys):
    """Prevention, not detection. The refusal names the KEY so it is actionable.

    A figure over zero inputs did not measure anything, and every count derived
    from it downstream would be a 0/0 pass -- the exact shape this whole phase
    exists to refuse.

    The message is read from STDERR rather than from the exception: the frozen
    core's die() writes the text and then raises SystemExit carrying only the
    CODE, so asserting on str(exc) would be asserting on the string "2" and
    would pass against any refusal at all.
    """
    root, _ = build_chain(tmp_path, item_count=0)
    capsys.readouterr()

    with pytest.raises(SystemExit) as excinfo:
        derive_into(root, [ok_rate_spec()])

    assert excinfo.value.code == core.EXIT_DID_NOT_RUN
    message = capsys.readouterr().err
    assert "ok_rate_pct" in message, (
        "the refusal did not name the figure key:\n%s" % message)


def test_derive_accepts_a_population_of_one_and_renders_it(tmp_path):
    """a design rule: population 1 is LEGAL.

    Peak VRAM, free VRAM at run start and disk free are legitimately
    single-sample population facts, and the shipped matched-load-replicated.json
    already carries "n": 1 beside "n": 3 for exactly this reason. Refusing n=1
    would be inventing a constraint nobody asked for.
    """
    root, _ = build_chain(tmp_path, item_count=1)

    _, record = derive_into(root, [ok_rate_spec(canon_value=100.0)])

    figure = record["figures"]["ok_rate_pct"]
    assert figure["population"] == 1
    assert figure["value"] == 100.0


def test_derive_refuses_a_threshold_claim_with_two_runs(tmp_path, capsys):
    """a design rule, enforced where the number is AUTHORED rather than where it is read.

    One run landing the right side of a line does not establish that the line
    was crossed.
    """
    root, _ = build_chain(tmp_path)
    capsys.readouterr()

    with pytest.raises(SystemExit) as excinfo:
        derive_into(root, [ok_rate_spec(threshold_claim=True,
                                        runs=[74.0, 75.0])])

    assert excinfo.value.code == core.EXIT_DID_NOT_RUN
    message = capsys.readouterr().err
    assert "ok_rate_pct" in message, message
    assert "2" in message, (
        "the refusal did not state the run COUNT, so the operator cannot tell "
        "how far short it fell:\n%s" % message)


def test_derive_accepts_a_threshold_claim_with_three_runs(tmp_path):
    root, _ = build_chain(tmp_path)

    _, record = derive_into(root, [ok_rate_spec(threshold_claim=True,
                                                runs=[74.0, 75.0, 76.0])])

    figure = record["figures"]["ok_rate_pct"]
    assert figure["threshold_claim"] is True
    assert figure["runs"] == [74.0, 75.0, 76.0], (
        "an earlier finding: the RAW replicate list is written beside the summary statistic, "
        "never collapsed into an interval")


def test_derive_refuses_when_the_gate_left_no_token(tmp_path):
    root, _ = build_chain(tmp_path)
    (Path(root) / "results" / "gate.json").unlink()

    with pytest.raises(SystemExit) as excinfo:
        derive_into(root, [ok_rate_spec()])

    assert excinfo.value.code == core.EXIT_DID_NOT_RUN


def test_derive_stamps_the_gate_token_and_the_date(tmp_path):
    root, token = build_chain(tmp_path)

    _, record = derive_into(root, [ok_rate_spec()])

    assert record["gate_token"] == token
    assert record["dated_at"], "no dated_at was stamped beside the token"
    assert record["started_at"], "no started_at was carried from the run record"


def test_the_derived_figures_validate_against_the_frozen_core(tmp_path):
    root, _ = build_chain(tmp_path)

    _, record = derive_into(root, [ok_rate_spec()])

    violations = core.validate_figures(record)
    assert violations == [], "\n".join(violations)


def test_derive_records_which_files_each_figure_came_from(tmp_path):
    """`derived_from` is what makes the chain walkable at all."""
    root, _ = build_chain(tmp_path)

    _, record = derive_into(root, [ok_rate_spec()])
    figure = record["figures"]["ok_rate_pct"]

    assert len(figure["derived_from"]) == ITEM_COUNT
    assert figure["numerator"] == 6 and figure["denominator"] == ITEM_COUNT
    assert figure["value"] == EXPECTED_OK_RATE


# ---------------------------------------------------------------------------
# derive.py is BYTE-STABLE -- an earlier plan open item 11
# ---------------------------------------------------------------------------
#
# Item 11, verbatim: "derive.py is not byte-stable across runs (re-stamps
# dated_at with microseconds). Consequence is concrete: re-deriving over
# identical records yields different bytes, so anyone hash-pinning figures.json
# will be wrong." an earlier round re-runs every artifact from a clean checkout and
# re-derives, so this is the property that makes that comparison possible at
# all -- without it, every re-derivation reports tampering on an unchanged
# measurement.
#
# THE PAIR IS THE POINT. "twice gives the same bytes" is satisfied by a derive
# that writes a constant, so the second test -- change one record, the bytes
# change -- is what makes the first one mean anything. Neither is written
# without the other.


def figures_sha256(root):
    return hashlib.sha256(
        (Path(root) / "results" / "figures.json").read_bytes()).hexdigest()


def test_deriving_twice_over_identical_records_is_byte_identical(tmp_path):
    """Hash-pinning figures.json has to be possible, and today it is not."""
    root, _ = build_chain(tmp_path)

    derive_into(root, [ok_rate_spec()])
    first = figures_sha256(root)
    derive_into(root, [ok_rate_spec()])
    second = figures_sha256(root)

    assert first == second, (
        "two derivations over identical records produced different bytes "
        "(%s then %s). Something in the record varies for a reason no "
        "measurement caused, and every sha256 assertion over a re-derived "
        "figures.json will report tampering on an unchanged artifact."
        % (first[:12], second[:12]))


def test_changing_one_per_item_record_changes_the_derived_bytes(tmp_path):
    """The paired direction. Stability must not be bought by dropping evidence.

    Operates on a temp-path copy and rewrites the record in place -- never
    `git checkout --`, which restores from HEAD and would make the verdict
    wrong in the direction that flatters us.
    """
    root, _ = build_chain(tmp_path)
    derive_into(root, [ok_rate_spec()])
    before = figures_sha256(root)

    mutant = Path(root) / "results" / "raw" / "items" / "item-0000.json"
    record = json.loads(mutant.read_text(encoding="utf-8"))
    assert record["ok"] is True, "the fixture item was already not-ok"
    record["ok"] = False
    mutant.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8", newline="\n")

    derive_into(root, [ok_rate_spec(canon_value=62.5)])
    after = figures_sha256(root)

    assert after != before, (
        "flipping one per-item record left the derived bytes at %s. Either the "
        "chain is short-circuited or the stability above was bought by writing "
        "a constant." % before[:12])


def test_the_written_key_ordering_does_not_follow_the_spec_order(tmp_path):
    """A record whose key order follows insertion hashes two ways for one payload."""
    root, _ = build_chain(tmp_path)
    specs = [ok_rate_spec(), ok_rate_spec(key="ok_rate_pct_again")]

    derive_into(root, specs)
    forward = (Path(root) / "results" / "figures.json").read_text(
        encoding="utf-8")
    derive_into(root, list(reversed(specs)))
    reversed_order = (Path(root) / "results" / "figures.json").read_text(
        encoding="utf-8")

    assert forward == reversed_order, (
        "re-ordering the declared specs re-ordered the written record")


def test_the_derivation_carries_machine_provenance_rather_than_its_own_clock(
        tmp_path):
    """Stability must not be achieved by DROPPING the timestamp.

    The run record already carries machine started_at and finished_at. The
    figure record is dated by the run it derives from, so the provenance
    survives and the bytes stop moving; an earlier round's re-derive reads both.
    """
    root, _ = build_chain(tmp_path)
    run = json.loads(
        (Path(root) / "results" / "raw" / "run-0001.json").read_text(
            encoding="utf-8"))

    _, record = derive_into(root, [ok_rate_spec()])

    assert record["dated_at"], "the record carries no dated_at at all"
    assert record["dated_at"] in (run["finished_at"], run["started_at"]), (
        "dated_at is %r, which is neither of the run record's own machine "
        "stamps (%r, %r) -- so it came from a clock read at derivation time"
        % (record["dated_at"], run["started_at"], run["finished_at"]))
    assert record["started_at"] == run["started_at"]


# ---------------------------------------------------------------------------
# finalize.py -- guards, floors, and the all()-over-empty trap
# ---------------------------------------------------------------------------


def test_finalize_refuses_an_empty_guard_list_and_prints_a_count_of_zero(
        tmp_path, capsys):
    """The highest-leverage pitfall in the phase, closed at the copy site.

    `all([])` is True, so the analog's `all(g["passed"] for g in guards)` would
    report every guard passing over a guard array that was never populated. It
    is safe THERE only because seven appends are unconditional.
    """
    root, _ = build_chain(tmp_path)
    finalize = load_template(root, "finalize.py")
    stream = io.StringIO()
    capsys.readouterr()

    with pytest.raises(SystemExit) as excinfo:
        finalize.finalize(root, guards=[], stream=stream)

    assert excinfo.value.code != core.EXIT_PASS
    printed = stream.getvalue() + capsys.readouterr().err
    assert "guards=0" in printed, (
        "the refusal never printed a guard count of 0:\n%s" % printed)
    assert "all guards passed" not in printed.lower(), (
        "an empty guard list reported guards passing:\n%s" % printed)


def test_finalize_prints_the_effective_floor_for_every_guard(tmp_path):
    """a design rule's load-bearing half is the PRINT.

    It turns `checked N of M` into a claim a reader can evaluate, and it stops a
    floor being quietly lowered between runs -- a change that is otherwise
    invisible in an artifact whose verdict stays green.
    """
    root, _ = build_chain(tmp_path)
    finalize = load_template(root, "finalize.py")
    stream = io.StringIO()

    guards = [
        {"id": "G1-coverage", "passed": True, "population": 8,
         "population_label": "replayed items", "minimum_required": 4},
        {"id": "G2-headroom", "passed": True, "population": 8,
         "population_label": "replayed items", "minimum_required": 2},
    ]
    code = finalize.finalize(root, guards=guards, stream=stream)
    printed = stream.getvalue()

    assert code == core.EXIT_PASS, printed
    for guard in guards:
        assert "floor=%s" % guard["minimum_required"] in printed, (
            "guard %s printed no effective floor:\n%s" % (guard["id"], printed))
    assert "guards=2" in printed, printed


def test_finalize_exits_3_when_any_guard_fails(tmp_path):
    root, _ = build_chain(tmp_path)
    finalize = load_template(root, "finalize.py")
    stream = io.StringIO()

    guards = [
        {"id": "G1-coverage", "passed": True, "population": 8,
         "population_label": "replayed items", "minimum_required": 4},
        {"id": "G2-headroom", "passed": False, "population": 8,
         "population_label": "replayed items", "minimum_required": 2},
    ]
    code = finalize.finalize(root, guards=guards, stream=stream)

    assert code == core.EXIT_GUARD_FAIL, stream.getvalue()
    record = json.loads(
        (Path(root) / "results" / "results.json").read_text(encoding="utf-8"))
    assert record["all_guards_passed"] is False
    assert core.validate_guards(record) == [], core.validate_guards(record)


def test_finalize_refuses_a_guard_missing_the_C1_triple(tmp_path, capsys):
    """Owner ruling C1: population, population_label and minimum_required.

    The measurement that forced the ruling: across seven shipped guards the
    population integer went by FIVE different names and five of seven declared
    no floor at all, so CHECK-11 could not mechanically locate either.
    """
    root, _ = build_chain(tmp_path)
    finalize = load_template(root, "finalize.py")
    capsys.readouterr()

    with pytest.raises(SystemExit) as excinfo:
        finalize.finalize(root, guards=[{"id": "G1", "passed": True}],
                          stream=io.StringIO())

    assert excinfo.value.code != core.EXIT_PASS
    message = capsys.readouterr().err
    assert "minimum_required" in message, message


def test_every_all_call_in_finalize_is_guarded_by_a_length_check(tmp_path):
    """Structural, over the AST -- and the population is asserted non-empty.

    A text search for `all(` would match the word in a comment; walking the AST
    matches only a real call. Asserting at least one exists matters as much as
    the guard itself: a file with no `all()` call would satisfy "every hit is
    guarded" vacuously, which is the 0/0 pass in its subtlest form.
    """
    source = (TEMPLATES_DIR / "finalize.py").read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source, "finalize.py")

    calls = [node.lineno for node in ast.walk(tree)
             if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == "all"]

    assert calls, (
        "finalize.py contains no all() call, so this guard checked nothing. "
        "The aggregate over the guard list is supposed to BE an all() -- "
        "guarded by a length check, not replaced by something unrecognisable.")

    unguarded = []
    for lineno in calls:
        window = lines[max(0, lineno - 4):lineno]
        if not any("len(" in line for line in window):
            unguarded.append("line %d: %s" % (lineno, lines[lineno - 1].strip()))

    assert not unguarded, (
        "found %d all() call(s); %d carry no length check within 3 lines:\n%s"
        % (len(calls), len(unguarded), "\n".join(unguarded)))


# ---------------------------------------------------------------------------
# verify.py -- the chain walk
# ---------------------------------------------------------------------------


def test_verify_re_derives_every_figure_and_prints_the_population(tmp_path):
    root, _ = build_chain(tmp_path)
    derive_into(root, [ok_rate_spec()])

    _, code, printed = run_verify(root)

    assert code == core.EXIT_PASS, printed
    assert "re-derived 1 of 1" in printed, (
        "verify printed no population for its own work:\n%s" % printed)


def test_token_mismatch_fails_verify(tmp_path):
    """a project requirement's stated failure, and an earlier step's mitigation in action.

    A results file minted under an older gate no longer matches once any
    assertion has changed, so `verify.py` exits 1 rather than re-deriving a
    number that was authorised by something else.
    """
    root, _ = build_chain(tmp_path)
    derive_into(root, [ok_rate_spec()])

    path = Path(root) / "results" / "figures.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["gate_token"] = "9" * 64
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8", newline="\n")

    _, code, printed = run_verify(root)

    assert code == core.EXIT_FINDING, (
        "verify exited %d over a figures file whose token does not match the "
        "gate's, expected %d:\n%s" % (code, core.EXIT_FINDING, printed))
    assert "gate_token" in printed, printed


def test_figure_with_no_per_item_record_fails_loudly(tmp_path):
    """The hardest failure in the chain, with the wording pinned as a constant."""
    root, token = build_chain(tmp_path)
    _write_unbacked_figures(root, token, value=42.0, canon_value=99.0)

    verify, code, printed = run_verify(root)

    assert code == core.EXIT_FINDING, printed
    assert verify.NO_RECORD_MESSAGE in printed, (
        "the failure did not carry the pinned no-record wording.\n"
        "expected: %s\ngot:\n%s" % (verify.NO_RECORD_MESSAGE, printed))
    assert verify.QUOTATION_SIGNATURE not in printed, (
        "a figure that does NOT equal the canon value was reported as a "
        "quotation; the two cases must stay distinguishable:\n%s" % printed)


def test_an_unbacked_figure_equal_to_the_canon_value_is_named_a_quotation(tmp_path):
    """The pair -- no evidence, and exactly the canon's number -- is the signature.

    The exact message string is asserted, not merely the exit code: a test that
    checked only the code would keep passing while this wording decayed into a
    generic missing-source error, and the wording is the part that teaches the
    next executor what was actually caught.
    """
    root, token = build_chain(tmp_path)
    _write_unbacked_figures(root, token, value=75.0, canon_value=75.0)

    verify, code, printed = run_verify(root)

    assert code == core.EXIT_FINDING, printed
    assert verify.QUOTATION_SIGNATURE in printed, (
        "expected the pinned quotation wording.\nexpected: %s\ngot:\n%s"
        % (verify.QUOTATION_SIGNATURE, printed))


def test_verify_over_zero_figures_is_a_did_not_run_never_a_pass(tmp_path):
    """A verify run that examined nothing must not report success.

    This is the frozen core's zero-population rule reaching the chain: `checked
    0` is DID-NOT-RUN, and the banned word for it is never printed.
    """
    root, token = build_chain(tmp_path)
    _write_figures(root, token, figures={})

    _, code, printed = run_verify(root)

    assert code == core.EXIT_DID_NOT_RUN, (
        "verify exited %d over zero figures, expected %d:\n%s"
        % (code, core.EXIT_DID_NOT_RUN, printed))
    assert core.BANNED_VERDICT not in printed.lower(), printed


def test_verify_exits_1_when_a_figure_value_does_not_re_derive(tmp_path):
    root, _ = build_chain(tmp_path)
    derive_into(root, [ok_rate_spec()])

    path = Path(root) / "results" / "figures.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["figures"]["ok_rate_pct"]["value"] = 12.5
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8", newline="\n")

    _, code, printed = run_verify(root)

    assert code == core.EXIT_FINDING, printed
    assert "12.5" in printed and str(EXPECTED_OK_RATE) in printed, (
        "the mismatch printed neither the claimed nor the re-derived value:\n%s"
        % printed)


def test_changing_one_per_item_record_changes_the_derived_figure(tmp_path):
    """What this plan owes an earlier plan: a chain PROVEN to propagate.

    Operates on a temp-path copy, and the record is rewritten in place rather
    than restored from git -- `git checkout --` restores from HEAD and would
    make the verdict wrong in the direction that flatters us.
    """
    root, _ = build_chain(tmp_path)
    _, before = derive_into(root, [ok_rate_spec()])
    baseline = before["figures"]["ok_rate_pct"]["value"]

    mutant = Path(root) / "results" / "raw" / "items" / "item-0000.json"
    record = json.loads(mutant.read_text(encoding="utf-8"))
    assert record["ok"] is True, "the fixture item was already not-ok"
    record["ok"] = False
    mutant.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8", newline="\n")

    _, after = derive_into(root, [ok_rate_spec(canon_value=62.5)])
    mutated = after["figures"]["ok_rate_pct"]["value"]

    assert mutated != baseline, (
        "flipping one per-item record left the figure at %r. The chain is "
        "short-circuited somewhere, and every mutant an earlier plan writes would "
        "pass silently against it." % baseline)
    assert mutated == 62.5, mutated


def test_the_recompute_and_remeasure_tiers_are_did_not_run_not_pass(tmp_path):
    """Only `derive` runs earlier. The other two must SAY so, not pass."""
    root, _ = build_chain(tmp_path)
    derive_into(root, [ok_rate_spec()])

    for tier in ("recompute", "remeasure"):
        _, code, printed = run_verify(root, argv=["--tier", tier,
                                                  "--root", str(root)])
        assert code == core.EXIT_DID_NOT_RUN, (
            "tier %s exited %d, expected %d:\n%s"
            % (tier, code, core.EXIT_DID_NOT_RUN, printed))
        assert core.VERDICT_DID_NOT_RUN in printed, printed


def test_verify_runs_as_a_script_and_reports_its_own_exit_code(tmp_path):
    import sys

    root, _ = build_chain(tmp_path)
    derive_into(root, [ok_rate_spec()])

    result = conftest.run_cli([sys.executable, "verify.py", "--tier", "derive"],
                              cwd=root)

    assert result.exit_code == core.EXIT_PASS, (
        "verify.py exited %d\nSTDOUT:\n%s\nSTDERR:\n%s"
        % (result.exit_code, result.stdout, result.stderr))
    assert "re-derived" in result.stdout, result.stdout


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _write_figures(root, token, figures):
    path = Path(root) / "results" / "figures.json"
    run = json.loads((Path(root) / "results" / "raw" / "run-0001.json")
                     .read_text(encoding="utf-8"))
    record = {
        "schema": "canonkit/figures/1",
        "schema_version": core.SCHEMA_VERSION,
        "artifact": "demo-artifact",
        "gate_token": token,
        "dated_at": run["started_at"],
        "started_at": run["started_at"],
        "started_at_utc": run["started_at_utc"],
        "figures": figures,
    }
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8", newline="\n")
    return record


def _write_unbacked_figures(root, token, value, canon_value):
    """A figure with a population but NO per-item record behind it.

    Exactly the shape a hand-written number takes once someone has filled in a
    plausible-looking population beside it.
    """
    return _write_figures(root, token, figures={
        "ok_rate_pct": {
            "value": value,
            "unit": "percent",
            "population": ITEM_COUNT,
            "population_label": "replayed items",
            "derived_from": [],
            "canon_bullet": CANON_BULLET,
            "canon_value": canon_value,
            "similar": "CONFIRMS",
            "similar_reason_ref": "prior-run-note.md#ok-rate",
            "tier_achieved": "T1",
            "reproduce_criterion": {"kind": "relative", "tolerance": 0.01},
            "threshold_claim": False,
            "not_shown": "A hermetic template fixture.",
        }
    })
