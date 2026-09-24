"""CHECK-09 -- an ambiguous id, a paraphrased bullet and an invented verdict.

Every exit-code test here runs `tools/checks/check_09.py` AS A SUBPROCESS, by
path, through conftest.run_cli, for the two reasons test_check_01.py and
test_check_03.py both record: by path under a bare module name is exactly how
the vendored copy runs inside an artifact, and the thing under test is an EXIT
CODE, which run_cli returns from the child rather than from a pipeline stage.

WHAT MAKES THE RED IN red-transcripts/CHECK-09.txt A REAL RED. The module is
registered and RUNNABLE in the commit that captures the transcript, with only
`claim_findings()` stubbed to return nothing. It loads the snapshot with an
explicit encoding, reads the documents, finds the claim tables structurally and
reports a real population; the transcript's own PASS line reads
`found=0 checked=2` over the broken fixture. Every failure line in that capture
is therefore an assertion about a VERDICT, not a module that could not be
imported and not an input that was not there.

THE ANTI-FALSE-RED GUARD, and it is measured rather than theoretical: plan
an earlier plan's first RED capture was a genuine false RED because an anti-rot pin read an
expectation file that did not exist, so the failure said nothing about the check.
test_the_committed_expectation_files_exist asserts both pins' inputs are on disk
BEFORE any test consumes them, so that failure mode cannot recur silently here.

NOTHING IN THIS MODULE JUDGES A COMPARISON BY CONSOLE OUTPUT. The Windows
console renders correct UTF-8 as replacement characters, so an equal pair can
look unequal and an unequal pair can look equal. Every byte assertion below runs
on `str.encode("utf-8")` or on the parsed --report JSON, never on captured
stdout text.
"""

import importlib.util
import json
import sys
from pathlib import Path

from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT
CHECKS_DIR = REPO_ROOT / "tools" / "checks"
CHECK_09 = CHECKS_DIR / "check_09.py"
SNAPSHOT = REPO_ROOT / "tools" / "canon-bullets.json"

FIXTURE_CLAIM_BLOCK = "broken-claim-block"
FIXTURE_BARE_ID = "broken-bare-bullet-id"
EXPECTATION_FILE = "expected-CHECK-09.json"

# The pin holds only fields that are not prose. A pin holding a message is the
# byte-for-byte-over-prose failure wearing a JSON hat: it goes red on a reworded
# sentence and stays green on a broken verdict.
PINNED_FIELDS = ("check_id", "code", "found", "checked", "finding_ids",
                 "schema_version")
PROSE_FIELDS = ("note", "notes", "stdout", "stderr", "message", "messages",
                "summary", "detail", "details", "findings", "text", "line",
                "context", "description")


def _load(stem, path):
    if stem in sys.modules:
        return sys.modules[stem]
    spec = importlib.util.spec_from_file_location(stem, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError("could not build a spec for %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[stem] = module
    spec.loader.exec_module(module)
    return module


core = _load("frozen_core_for_check_09_tests", REPO_ROOT / "tools" / "canonkit.py")
check_09 = _load("check_09_under_test", CHECK_09)

# Read with an EXPLICIT encoding, the same way the module does. The default
# locale read on this machine is cp1252 and would either raise or mojibake the
# very bytes every comparison below depends on.
SNAPSHOT_RECORD = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
BULLETS = SNAPSHOT_RECORD["bullets"]


# ---------------------------------------------------------------------------
# Fixture material
# ---------------------------------------------------------------------------

CLAIM_ROWS_ORDER = ("Canon", "Project", "Bullet id", "Bullet text, verbatim",
                    "Measured counterpart", "Verdict")


def claim_table(rows):
    """A claim-under-test table, rendered as the skeletons render it."""
    body = "".join("| %s | %s |\n" % (name, value) for name, value in rows)
    return "| Field | Value |\n|---|---|\n" + body


def readme_with(rows, wrap_in_region=True, prologue="# demo-artifact\n\n"):
    table = claim_table(rows)
    if wrap_in_region:
        table = ("<!-- artifact:claim:begin -->\n" + table
                 + "<!-- artifact:claim:end -->\n")
    return prologue + table


def rows_for(key, **overrides):
    """A correct claim table for `key`, with named cells overridden."""
    entry = BULLETS[key]
    values = {
        "Canon": entry["canon"],
        "Project": entry["project"],
        "Bullet id": key,
        "Bullet text, verbatim": entry["text"],
        "Measured counterpart": "the headline figure in the results record",
        "Verdict": "SUPPORTS-WITH-REVISION",
    }
    drop = overrides.pop("drop", ())
    values.update(overrides)
    return [(name, values[name]) for name in CLAIM_ROWS_ORDER
            if name not in drop]


class _Delete(object):
    """Sentinel: a figure key to REMOVE rather than set. `None` cannot serve --
    a figure whose `value` is literally null is a different case from a figure
    carrying no `value` key at all, and branch 5 must tell them apart."""

    def __repr__(self):
        return "<delete>"


DELETE = _Delete()


def figures_record(key, bullet, **entry_overrides):
    entry = {
        "canon_bullet": bullet,
        "canon_value": 1,
        "derived_from": ["results.json#" + key],
        "not_shown": "A hermetic fixture.",
        "population": 3,
        "population_label": "hermetic samples",
        "reproduce_criterion": {"kind": "abs", "tolerance": 0},
        "runs": [],
        "similar": "SUPPORTS-WITH-REVISION",
        "similar_reason_ref": "register-fragments/demo.md",
        "threshold_claim": False,
        "tier_achieved": "recompute",
        "unit": "count",
        "value": 1,
    }
    for name, value in entry_overrides.items():
        if value is DELETE:
            entry.pop(name, None)
        else:
            entry[name] = value
    return {
        "artifact": "demo-artifact",
        "dated_at": "2026-09-15",
        "figures": {key: entry},
        "gate_token": "0" * 64,
        "schema": "canonkit/figures/1",
        "schema_version": "canonkit/1",
        "started_at": "2026-09-15T09:00:00+05:00",
        "started_at_utc": "2026-09-15T04:00:00Z",
    }


def run_check(tmp_path, artifact, extra=(), tag="report"):
    """Run the check as a subprocess, writing its report OUTSIDE the artifact.

    a design rule: the checker must not mutate what it checks. A report written into the
    directory under test would be a file the next run then sees.
    """
    out = Path(tmp_path) / ("out-" + tag)
    out.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, str(CHECK_09), str(artifact),
            "--report", str(out / "report.json")] + list(extra)
    return conftest.run_cli(argv, cwd=REPO_ROOT, log_dir=out / "log")


def build(tmp_path, readme, figures, slug="demo-artifact"):
    return conftest.tmp_artifact(tmp_path, slug=slug, readme=readme,
                                 figures=figures, gate=None)


def kinds_of(result):
    return sorted({f["kind"] for f in result.report["findings"]})


# ---------------------------------------------------------------------------
# The contract, and the guard against a false RED
# ---------------------------------------------------------------------------


def test_the_module_satisfies_the_check_contract():
    assert check_09.CHECK_ID == "CHECK-09"
    assert isinstance(check_09.DEFAULT_FLOOR, int)
    assert check_09.DEFAULT_FLOOR >= 1
    assert callable(check_09.run)


def test_discover_finds_check_09_inside_the_declared_universe():
    from tools import checks
    report = checks.discover(CHECKS_DIR, verbose=False)
    assert "CHECK-09" in report.ids
    assert report.declared == checks.DECLARED_MODULE_COUNT
    assert not report.protocol_violations, report.protocol_violations


def test_the_committed_expectation_files_exist():
    """The earlier plan false-RED guard: a pin whose INPUT is missing proves nothing."""
    for name in (FIXTURE_CLAIM_BLOCK, FIXTURE_BARE_ID):
        path = conftest.broken_fixture(name) / EXPECTATION_FILE
        assert path.is_file(), (
            "%s has no %s, so any pin reading it would fail for a reason that "
            "says nothing about CHECK-09" % (name, EXPECTATION_FILE))
        pinned = json.loads(path.read_text(encoding="utf-8"))
        assert set(PINNED_FIELDS) <= set(pinned), sorted(pinned)
        assert not (set(PROSE_FIELDS) & set(pinned)), (
            "the pin holds a prose field, which makes it sensitive to wording "
            "instead of to the verdict")


# ---------------------------------------------------------------------------
# Branch 2 -- the ambiguous id
# ---------------------------------------------------------------------------


def test_compound_key_resolves_and_a_bare_id_names_both_candidates():
    """`example-beta:P2-B1` resolves; a bare `P2-B1` is a finding, not a guess."""
    snapshot = check_09.load_snapshot(str(SNAPSHOT))

    resolved = check_09.resolve_reference("example-beta:P2-B1", snapshot)
    assert resolved.resolved
    assert resolved.key == "example-beta:P2-B1"

    bare = check_09.resolve_reference("P2-B1", snapshot)
    assert not bare.resolved
    assert bare.how == check_09.UNRESOLVED_BARE
    assert sorted(bare.candidates) == ["example-alpha:P2-B1", "example-beta:P2-B1"]


def test_a_bare_colliding_id_is_reported_with_both_resolutions(tmp_path):
    artifact = conftest.broken_fixture(FIXTURE_BARE_ID)
    result = run_check(tmp_path, artifact)
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert check_09.KIND_BARE_ID in kinds_of(result)
    detail = " ".join(f["detail"] for f in result.report["findings"])
    assert "example-alpha:P2-B1" in detail, detail
    assert "example-beta:P2-B1" in detail, detail


def test_the_snapshot_really_holds_ids_in_both_canons():
    """A guard on the guard: if the collision set were empty, the test above
    would pass over a population that cannot express the thing it asserts."""
    snapshot = check_09.load_snapshot(str(SNAPSHOT))
    assert len(snapshot.collision_ids) >= 2, snapshot.collision_ids
    assert "P2-B1" in snapshot.collision_ids


# ---------------------------------------------------------------------------
# The BP-n display reference, resolved through the snapshot and not a pattern
# ---------------------------------------------------------------------------


def test_bp_display_ref_resolves_to_beta_and_never_to_alpha():
    snapshot = check_09.load_snapshot(str(SNAPSHOT))
    resolved = check_09.resolve_reference("BP-2-B1", snapshot)
    assert resolved.resolved
    assert resolved.key == "example-beta:P2-B1"
    assert resolved.key != "example-alpha:P2-B1"
    assert resolved.how == check_09.RESOLVED_DISPLAY
    assert snapshot.display_prefix_canon["BP-2"] == {"example-beta"}


def test_every_display_prefix_belongs_to_exactly_one_canon():
    """The mapping is canon-specific data, not a pattern over an id string."""
    snapshot = check_09.load_snapshot(str(SNAPSHOT))
    assert snapshot.display_prefix_canon, "no display prefixes were derived"
    for prefix, canons in sorted(snapshot.display_prefix_canon.items()):
        assert canons == {"example-beta"}, (prefix, canons)


def test_a_bp_reference_in_a_claim_table_passes(tmp_path):
    key = "example-beta:P2-B1"
    artifact = build(tmp_path,
                     readme_with(rows_for(key, **{"Bullet id": "BP-2-B1"})),
                     figures_record("headline", key))
    result = run_check(tmp_path, artifact)
    assert result.exit_code == core.EXIT_PASS, result.stdout


# ---------------------------------------------------------------------------
# Branch 4 -- the byte comparison
# ---------------------------------------------------------------------------


def test_one_changed_character_in_the_bullet_text_is_a_finding(tmp_path):
    key = "example-alpha:P2-B3"
    original = BULLETS[key]["text"]
    edited = original[:-2] + ("X" if original[-2] != "X" else "Y") + original[-1]
    assert edited != original
    assert len(edited) == len(original)

    artifact = build(tmp_path,
                     readme_with(rows_for(key, **{"Bullet text, verbatim": edited})),
                     figures_record("headline", key))
    result = run_check(tmp_path, artifact)
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert check_09.KIND_TEXT_MISMATCH in kinds_of(result)


def test_the_comparison_is_on_encoded_bytes_and_not_a_normalized_form():
    """Two strings that RENDER identically and differ in bytes must not match.

    NFC 'e-acute' against NFD 'e' + combining acute. A comparison that called
    unicodedata.normalize, casefold or a whitespace collapse would call these
    equal -- and a paraphrase would pass through the same door.
    """
    nfc = "café"
    nfd = "café"
    assert nfc != nfd
    assert nfc.encode("utf-8") != nfd.encode("utf-8")
    assert not check_09.texts_match(nfc, nfd)
    assert check_09.texts_match(nfc, nfc)

    # The same rule on the shapes a paraphrase actually takes.
    assert not check_09.texts_match("a b", "a  b")
    assert not check_09.texts_match("Retired 30 steps", "retired 30 steps")
    assert not check_09.texts_match("a - b", "a — b")
    assert not check_09.texts_match("text.", "text")


def test_a_non_ascii_paraphrase_is_caught_through_the_cli(tmp_path):
    """The byte rule, exercised end to end against a hermetic snapshot.

    The committed snapshot happens to be all-ASCII today, so a test that only
    used it could not show that the comparison survives a non-ASCII bullet. The
    --canon flag exists for exactly this.
    """
    key = "demo:X1-B1"
    snapshot = {"bullets": {key: {"canon": "demo", "project": "X1",
                                  "id": "X1-B1", "display_ref": None,
                                  "text": "Cut café latency by half."}}}
    snapshot_path = Path(tmp_path) / "hermetic-canon.json"
    snapshot_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8", newline="\n")

    rows = [("Canon", "demo"), ("Project", "X1"), ("Bullet id", key),
            ("Bullet text, verbatim", "Cut café latency by half."),
            ("Measured counterpart", "the headline figure"),
            ("Verdict", "SUPPORTS")]
    artifact = build(tmp_path, readme_with(rows),
                     figures_record("headline", key))
    result = run_check(tmp_path, artifact,
                       extra=["--canon", str(snapshot_path)])
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert check_09.KIND_TEXT_MISMATCH in kinds_of(result)

    # The diagnostic is read from the REPORT FILE, never from the console: on
    # this machine correct UTF-8 renders as replacement characters.
    mismatch = [f for f in result.report["findings"]
                if f["kind"] == check_09.KIND_TEXT_MISMATCH][0]
    assert mismatch["byte_offset"] >= 0


def test_the_snapshot_is_read_with_an_explicit_utf8_encoding(tmp_path):
    """A snapshot that is valid UTF-8 and invalid cp1252 must still load."""
    key = "demo:X1-B1"
    text = "Reduced écart-type by 12 points."
    path = Path(tmp_path) / "utf8-canon.json"
    path.write_bytes(json.dumps(
        {"bullets": {key: {"canon": "demo", "project": "X1", "id": "X1-B1",
                           "display_ref": None, "text": text}}},
        ensure_ascii=False).encode("utf-8"))
    snapshot = check_09.load_snapshot(str(path))
    assert snapshot.text_for(key) == text
    assert snapshot.text_for(key).encode("utf-8") == text.encode("utf-8")


# ---------------------------------------------------------------------------
# Branches 5 and 6 -- the counterpart and the verdict
# ---------------------------------------------------------------------------


def test_an_illegal_verdict_is_a_finding_and_the_message_lists_the_three(tmp_path):
    artifact = conftest.broken_fixture(FIXTURE_CLAIM_BLOCK)
    result = run_check(tmp_path, artifact)
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    verdicts = [f for f in result.report["findings"]
                if f["kind"] == check_09.KIND_VERDICT]
    assert verdicts, kinds_of(result)
    detail = verdicts[0]["detail"]
    assert "PARTIALLY-SUPPORTS" in detail, detail
    for legal in ("SUPPORTS", "SUPPORTS-WITH-REVISION", "DOES-NOT-SUPPORT"):
        assert legal in detail, (legal, detail)


def test_the_legal_verdict_set_is_not_canonkits_similarity_vocabulary():
    """Three, not five. CONFIRMS and REFRESH are the FIGURE-level `similar`
    vocabulary and must never be admitted into a claim block."""
    assert check_09.LEGAL_VERDICTS == (
        "SUPPORTS", "SUPPORTS-WITH-REVISION", "DOES-NOT-SUPPORT")
    assert set(check_09.LEGAL_VERDICTS) < set(core.SIMILARITY_VERDICTS)
    assert "CONFIRMS" not in check_09.LEGAL_VERDICTS
    assert "REFRESH" not in check_09.LEGAL_VERDICTS


def test_a_missing_verdict_row_is_a_finding(tmp_path):
    key = "example-alpha:P2-B3"
    artifact = build(tmp_path, readme_with(rows_for(key, drop=("Verdict",))),
                     figures_record("headline", key))
    result = run_check(tmp_path, artifact)
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert check_09.KIND_VERDICT in kinds_of(result)


def test_a_missing_measured_counterpart_is_a_finding(tmp_path):
    key = "example-alpha:P2-B3"
    artifact = build(tmp_path,
                     readme_with(rows_for(key, drop=("Measured counterpart",))),
                     figures_record("headline", key))
    result = run_check(tmp_path, artifact)
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert check_09.KIND_NO_COUNTERPART in kinds_of(result)


def test_a_figure_with_a_canon_value_and_no_value_is_a_finding(tmp_path):
    key = "example-alpha:P2-B3"
    artifact = build(tmp_path, readme_with(rows_for(key)),
                     figures_record("headline", key, value=DELETE))
    result = run_check(tmp_path, artifact)
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert check_09.KIND_NO_COUNTERPART in kinds_of(result)


def test_an_unknown_compound_key_is_a_finding_naming_the_key(tmp_path):
    key = "example-alpha:P2-B3"
    rows = rows_for(key, **{"Bullet id": "example-alpha:P9-B9"})
    artifact = build(tmp_path, readme_with(rows),
                     figures_record("headline", key))
    result = run_check(tmp_path, artifact)
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    unknown = [f for f in result.report["findings"]
               if f["kind"] == check_09.KIND_UNKNOWN_KEY]
    assert unknown, kinds_of(result)
    assert "example-alpha:P9-B9" in unknown[0]["detail"]


# ---------------------------------------------------------------------------
# Branch 1, the population, and the six-kind identity
# ---------------------------------------------------------------------------


def test_the_zero_input_fixture_is_did_not_run(tmp_path):
    """No claim table anywhere and no figure carrying a canon_bullet."""
    figures = figures_record("headline", "example-alpha:P2-B3",
                             canon_bullet=DELETE)
    artifact = build(tmp_path, "# demo-artifact\n\nNo claim table here.\n",
                     figures)
    result = run_check(tmp_path, artifact)
    assert result.exit_code == core.EXIT_DID_NOT_RUN, result.stdout
    assert result.report["checked"] == 0
    assert result.report["found"] == 0
    assert core.REFUSAL_PREFIX in result.stderr


def test_figures_naming_a_bullet_with_no_claim_table_is_a_finding(tmp_path):
    """The other side of branch 1, and the distinction an earlier finding calls the most
    important in the checker: this artifact DID declare a canon claim, so
    "could not look" would be the wrong answer."""
    artifact = build(tmp_path, "# demo-artifact\n\nNo claim table here.\n",
                     figures_record("headline", "example-alpha:P2-B3"))
    result = run_check(tmp_path, artifact)
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert check_09.KIND_ABSENT in kinds_of(result)
    assert result.report["checked"] >= 1


def test_the_six_branches_produce_six_distinct_finding_ids(tmp_path):
    """All six kinds, and every id distinct.

    Two artifacts rather than one, stated rather than worked around: branch 1
    fires on the ABSENCE of the claim table that branches 2, 4, 5 and 6 need in
    order to fire at all, so no single artifact can carry all six.
    """
    key = "example-alpha:P2-B3"
    entry = BULLETS[key]

    # Three id tokens: one BARE (branch 2), one unknown compound (branch 3),
    # and one that RESOLVES -- without the third there is nothing to compare the
    # paraphrased text against, so branch 4 could not fire at all.
    rows = [("Canon", entry["canon"]), ("Project", entry["project"]),
            ("Bullet id", "P2-B1, example-alpha:P9-B9, " + key),
            ("Bullet text, verbatim", "A paraphrase of the bullet."),
            ("Verdict", "MOSTLY-SUPPORTS")]
    five = build(tmp_path, readme_with(rows),
                 figures_record("headline", key), slug="five-branches")
    absent = build(tmp_path, "# a\n\nNo claim table.\n",
                   figures_record("headline", key), slug="absent-branch")

    ids = []
    kinds = set()
    for artifact in (five, absent):
        result = run_check(tmp_path, artifact, tag=artifact.name)
        assert result.exit_code == core.EXIT_FINDING, result.stdout
        ids.extend(result.report["finding_ids"])
        kinds.update(f["kind"] for f in result.report["findings"])

    assert kinds == set(check_09.FINDING_KINDS), sorted(kinds)
    assert len(ids) == len(set(ids)), ids
    assert len(set(ids)) >= 6, sorted(set(ids))


def test_a_correct_claim_block_passes(tmp_path):
    """The negative direction. A check that only ever fails is not a check."""
    key = "example-beta:P1-B5"
    artifact = build(tmp_path, readme_with(rows_for(key)),
                     figures_record("headline", key))
    result = run_check(tmp_path, artifact)
    assert result.exit_code == core.EXIT_PASS, result.stdout
    assert result.report["found"] == 0
    assert result.report["checked"] >= 1


def test_the_claim_table_is_found_outside_the_anchor_region(tmp_path):
    """RESULTS-SKELETON.md puts a DIFFERENT table inside its artifact:claim
    region and the claim-under-test table outside it. An anchor-keyed check
    reads the wrong table in one of the two skeletons this program ships."""
    key = "example-alpha:P2-B3"
    readme = (
        "# demo-artifact\n\n"
        "<!-- artifact:claim:begin -->\n"
        "| | Before | After |\n|---|---|---|\n| latency | 10 | 5 |\n"
        "<!-- artifact:claim:end -->\n\n"
        + claim_table(rows_for(key, **{"Verdict": "NEARLY-SUPPORTS"})))
    artifact = build(tmp_path, readme, figures_record("headline", key))
    result = run_check(tmp_path, artifact)
    assert result.report["claim_tables"] == 1, result.report
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert check_09.KIND_VERDICT in kinds_of(result)


def test_the_population_line_prints_the_effective_floor(tmp_path):
    """a design rule: the floor actually applied is the one that prints."""
    key = "example-alpha:P2-B3"
    artifact = build(tmp_path, readme_with(rows_for(key)),
                     figures_record("headline", key))
    result = run_check(tmp_path, artifact, extra=["--min-claims", "7"])
    assert "floor=7" in result.stdout, result.stdout
    assert result.exit_code == core.EXIT_DID_NOT_RUN, result.stdout
    assert result.report["floor"] == 7


# ---------------------------------------------------------------------------
# a design rule -- the anti-rot pins over the two committed fixtures
# ---------------------------------------------------------------------------


def _pin(tmp_path, name):
    artifact = conftest.broken_fixture(name)
    expected = json.loads((artifact / EXPECTATION_FILE).read_text(
        encoding="utf-8"))
    result = run_check(tmp_path, artifact)
    assert result.report is not None, result.stdout
    for field in PINNED_FIELDS:
        assert result.report[field] == expected[field], (
            "%s: %s is %r; the committed expectation says %r"
            % (name, field, result.report[field], expected[field]))
    assert result.exit_code == expected["code"], result.stdout


def test_broken_claim_block_still_matches_its_committed_expectation(tmp_path):
    _pin(tmp_path, FIXTURE_CLAIM_BLOCK)


def test_broken_bare_bullet_id_still_matches_its_committed_expectation(tmp_path):
    _pin(tmp_path, FIXTURE_BARE_ID)


def test_the_fixture_bullet_text_is_byte_identical_to_the_snapshot():
    """The pin's own input, checked. broken-claim-block must differ from the
    canon in its COUNTERPART and its VERDICT and in nothing else; if its bullet
    text had drifted, the text branch would fire too and the pinned found count
    would be measuring a typo rather than the two defects the fixture is for."""
    artifact = conftest.broken_fixture(FIXTURE_CLAIM_BLOCK)
    text = (artifact / "README.md").read_text(encoding="utf-8")
    tables = check_09.find_claim_tables("README.md", text)
    assert len(tables) == 1
    cell = tables[0].value(check_09.F_TEXT)
    assert check_09.texts_match(cell, BULLETS["example-alpha:P2-B3"]["text"])


# ---------------------------------------------------------------------------
# Applicability is the RUNNER's, and this module's refusal is a DIFFERENT fact
# ---------------------------------------------------------------------------
#
# a design rule asks for "an applicability predicate, like CHECK-07's". Measured: no
# check module in this repository has one -- `applicab` appears nowhere under
# tools/checks/ -- and what check_07.py actually carries is an in-module early
# refusal returning code 2. That difference decides whether an artifact can ever
# reach EXIT=0, because `run_artifact` aggregates every record's code and any 2
# lifts to 1. So the predicate lives in the RUNNER, and this module keeps
# refusing exactly as it did. The two tests below pin both halves.


def _exempting_manifest(slug="demo-artifact"):
    """The row shape that makes the RUNNER declare CHECK-09 not applicable."""
    return {
        "schema": "manifest/1",
        "schema_version": 1,
        "slugs": [{
            "slug": slug,
            "scanned": True,
            "status": "built",
            "register_row": False,
            "bullets": [],
            "backs_bullets": [],
            "no_row_reason": "Cited by no bullet in either canon.",
        }],
    }


def test_the_zero_reference_refusal_survives_the_exempting_manifest_row(tmp_path):
    """Handed the row that exempts it, the MODULE still refuses.

    This is the discriminating test for where the predicate lives. If a future
    edit moved it into the module, this call would come back PASS or with the
    check declining to look -- and every vendored copy invoked directly as
    `python check_09.py <artifact>` would then report a clean verdict over a
    population of nothing, which is the one reading a design rule forbids.

    The refusal being preserved is also what keeps redis honest: its row DOES
    name a claim, so the same sentence must still fire for want of a claim
    table.
    """
    contract = check_09.load_contract()
    artifact = build(tmp_path, "# demo-artifact\n\nNo claim table here.\n",
                     figures_record("headline", "example-alpha:P2-B3",
                                    canon_bullet=DELETE))
    ctx = contract.CheckContext(artifact_slug="demo-artifact",
                                manifest=_exempting_manifest())
    result = check_09.run(artifact, ctx)
    assert result.code == core.EXIT_DID_NOT_RUN, (
        "the module reported code %d over an exempting manifest row; "
        "applicability is the runner's decision and this module's zero-"
        "reference refusal is a different fact" % result.code)
    assert result.checked == 0, result.checked
    assert "ZERO bullet references" in result.note, result.note


def test_the_module_points_a_reader_at_the_runner_side_declaration():
    """A comment, asserted, so a second in-module predicate is not added.

    The failure this prevents is not hypothetical: an in-module refusal and a
    runner-side inapplicability render almost identically in a log, and only one
    of them lets an artifact reach EXIT=0. A reader who finds the refusal and
    not the declaration has every reason to "fix" it in the wrong place.
    """
    source = CHECK_09.read_text(encoding="utf-8")
    assert "ARTIFACT_SUBSET" in source, (
        "check_09.py does not name the runner-side declaration, so the next "
        "reader of its refusal has no pointer to where applicability is decided")
    assert "no_row_reason" in source, source[:200]


# ---------------------------------------------------------------------------
# Branch 5 over the FIGURES record is one-directional, and the measurement that
# made it so
# ---------------------------------------------------------------------------
#
# canonkit.validate_figures REQUIRES a compound-keyed `canon_bullet` on EVERY
# figure -- `None` is a schema violation, measured. So a derivation that
# authors supporting evidence beside the headline (a load-generator ceiling, a
# replicate count, a cache hit rate) must name a bullet on all of it.
#
# A SYMMETRIC branch 5 then demands that the CANON state a number for every one
# of them, and no canon does. Measured on example-cache-benchmark: ten
# figures, ten `no-counterpart` findings, and the message's own repair --
# "re-run derive.py" -- is a dead instruction, because no derivation can
# produce a value the canon does not carry.
#
# The two directions are not the same fact and they get different answers:
#
#   canon_value present, value absent   -> FINDING. A comparison was declared
#                                          and nothing was measured for it.
#   value present, canon_value absent   -> NOT a finding. A measurement the
#                                          canon states no number for is what
#                                          supporting evidence IS. It is
#                                          COUNTED and printed instead, as
#                                          `no-canon-value=`, so the population
#                                          stays visible rather than silent.
#
# The comparison that decides whether a claim is supported still has to be
# made: it is the claim TABLE's `Measured counterpart` row, which branch 5
# still requires, and the correction record CHECK-20 requires afterwards.


def test_a_figure_the_canon_states_no_number_for_is_not_a_finding(tmp_path):
    """Supporting evidence is not a defect, and every artifact will carry it."""
    key = "example-beta:P1-B5"
    artifact = build(tmp_path, readme_with(rows_for(key)),
                     figures_record("supporting", key, canon_value=None))

    result = run_check(tmp_path, artifact)

    assert result.exit_code == core.EXIT_PASS, (
        "a measurement the canon states no number for was reported as a "
        "finding:\n%s" % result.stdout)
    assert result.report["found"] == 0, result.report
    assert result.report["figures_without_canon_value"] == 1, (
        "the figure was not counted: %r" % (result.report,))
    assert "no-canon-value=1" in result.report["note"], result.report["note"]


def test_a_canon_value_with_nothing_measured_beside_it_is_still_a_finding(tmp_path):
    """The other half. One direction is a real defect and keeps firing.

    This is the same assertion as test_a_figure_with_a_canon_value_and_no_value
    _is_a_finding above, restated here beside its new inverse so a reader sees
    the pair rather than one of them.
    """
    key = "example-beta:P1-B5"
    artifact = build(tmp_path, readme_with(rows_for(key)),
                     figures_record("headline", key, value=None))

    result = run_check(tmp_path, artifact)

    assert result.exit_code == core.EXIT_FINDING, (
        "a declared canon value with nothing measured beside it stopped being "
        "a finding:\n%s" % result.stdout)
    assert check_09.KIND_NO_COUNTERPART in kinds_of(result), kinds_of(result)
    assert result.report["figures_without_canon_value"] == 0, result.report
