"""CHECK-01 -- a figure that appears without its population.

Every test here runs `tools/checks/check_01.py` AS A SUBPROCESS, by path,
through conftest.run_cli, for the same two reasons test_render.py does it:

  * by path, under a bare module name, is exactly how the vendored copy is run
    inside an artifact (the design rules). A test that imported it as
    `tools.checks.check_01` would exercise a code path no artifact ever takes.
  * the thing under test is an EXIT CODE, and run_cli returns the CHILD's own
    returncode, so the piped-exit-code trap is structurally impossible here.

WHAT MAKES THE RED IN red-transcripts/CHECK-01.txt A REAL RED. The check module
is registered and RUNNABLE in the commit that captures the transcript, with its
detection logic stubbed to return a passing verdict. Every failure line in that
transcript is therefore an assertion about the VERDICT -- `assert 0 == 2`,
`assert 0 == 1` -- and not a collection failure, a missing module, or an absent
input. A transcript recording any of those exits non-zero for the wrong reason
and proves nothing about whether the check discriminates.

THE FOUR TESTS THAT CARRY THE EVIDENCE, in the order they appear below:

    test_zero_figures_is_did_not_run_and_never_a_pass
    test_an_absent_figures_record_is_did_not_run
    test_a_figure_without_its_population_is_a_finding_naming_the_key
    test_a_figure_value_in_prose_is_caught_by_the_value_rule   (the design rules)

The last one is the one a shape allow-list cannot pass: its leaked value
classifies as a PORT and a shape-only rule reports that document clean.

WHAT THIS MODULE CLOSED, AND WHO ASSIGNED IT. an earlier plan open item 13 -- the CHECK-01
vs CHECK-09 conflict on verbatim canon bullet text -- was worked around by a
committed waiver whose count printed, and its owner line read "the plan that
next edits `tools/checks/check_01.py`; an earlier round is the first that will hit it for
real". an earlier plan is that plan. The section near the end of this file carries
the tests; the audit trail is here so it sits beside the assertions rather than
only in a summary somebody has to go and find.
"""

import importlib.util
import json
import re
import sys
from pathlib import Path

from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT
CHECKS_DIR = REPO_ROOT / "tools" / "checks"
CHECK_01 = CHECKS_DIR / "check_01.py"
# CHECK-09 is run BESIDE CHECK-01 on one tree by the open-item-13 tests below:
# the whole point of that repair is that the two checks stop contradicting each
# other, and a claim asserted against only one of them cannot show it.
CHECK_09 = CHECKS_DIR / "check_09.py"
SNAPSHOT = REPO_ROOT / "tools" / "canon-bullets.json"
RENDER = REPO_ROOT / "tools" / "render.py"


def _load(stem, path):
    """Load a module BY PATH under a bare stem, the local convention.

    a design rule forbids importing the vendored set as a package from this repository,
    and tools/tests/test_repo_hygiene.py::test_frozen_core_is_never_imported
    enforces it -- `import_module("tools.checks")` is a forbidden reference and
    that guard caught this file's first draft. spec_from_file_location is
    deliberately NOT one of the two calls that guard flags: loading by path
    under a bare name is the mechanism a design rule mandates.
    """
    if stem in sys.modules:
        return sys.modules[stem]
    spec = importlib.util.spec_from_file_location(stem, str(path))
    if spec is None or spec.loader is None:
        raise ImportError("could not build a spec for %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[stem] = module
    spec.loader.exec_module(module)
    return module


checks = _load("check_contract_for_tests", CHECKS_DIR / "__init__.py")
core = _load("frozen_core_for_check_01_tests", REPO_ROOT / "tools" / "canonkit.py")

WITHOUT_POPULATION = "broken-figure-without-population"
IN_PROSE = "broken-figure-in-prose"


# ---------------------------------------------------------------------------
# Running the check
# ---------------------------------------------------------------------------


def _run(artifact, *flags, report=None, cwd=None, log_dir=None):
    argv = [sys.executable, str(CHECK_01), str(artifact)]
    if report is not None:
        argv = argv + ["--report", str(report)]
    argv = argv + [str(flag) for flag in flags]
    return conftest.run_cli(argv, cwd=cwd or Path(artifact).parent,
                            log_dir=log_dir)


def _run_render(artifact, *flags):
    argv = [sys.executable, str(RENDER), str(artifact)] + [str(f) for f in flags]
    return conftest.run_cli(argv, cwd=Path(artifact).parent)


def _run_09(artifact, report=None, cwd=None):
    """CHECK-09 over the SAME tree. Its snapshot path is derived from its own
    module location, so the working directory does not enter into it."""
    argv = [sys.executable, str(CHECK_09), str(artifact)]
    if report is not None:
        argv = argv + ["--report", str(report)]
    return conftest.run_cli(argv, cwd=cwd or Path(artifact).parent)


# ---------------------------------------------------------------------------
# Hermetic fixtures built in tmp_path (the other half of a design rule)
# ---------------------------------------------------------------------------


def _figure(**overrides):
    entry = {
        "value": 12.5,
        "unit": "ms",
        "population": 500,
        "population_label": "replayed requests",
        "derived_from": ["results.json#replay.median"],
        "canon_bullet": "example-alpha:P2-B5",
        "canon_value": 14.0,
        "similar": "CONFIRMS",
        "similar_reason_ref": "register-fragments/demo.md",
        "tier_achieved": "recompute",
        "reproduce_criterion": {"kind": "rel", "tolerance": 0.1},
        "threshold_claim": False,
        "runs": [],
        "not_shown": "One replay on one machine.",
    }
    entry.update(overrides)
    return entry


def _record(slug="demo-artifact", figures=None):
    return {
        "schema": "canonkit/figures/1",
        "schema_version": "canonkit/1",
        "artifact": slug,
        "gate_token": "0" * 64,
        "dated_at": "2026-09-15",
        "started_at": "2026-09-15T09:00:00+05:00",
        "started_at_utc": "2026-09-15T04:00:00Z",
        "figures": {"median_latency_ms": _figure()} if figures is None else figures,
    }


_CLEAN_README = """# demo-artifact

Un-rendered prose carrying no figure at all, which is what a design rule requires of it.

<!-- artifact:figures:begin -->
The median was {{figures.median_latency_ms}} ms over the replay.
<!-- artifact:figures:end -->

## What this does not show

A hermetic fixture. It measures nothing.

Dated: 2026-09-15
"""


def _artifact(tmp_path, readme=_CLEAN_README, record=None, slug="demo-artifact"):
    root = Path(tmp_path) / slug
    (root / "results").mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text(readme, encoding="utf-8", newline="")
    payload = _record(slug=slug) if record is None else record
    (root / "results" / "figures.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="")
    return root


# ---------------------------------------------------------------------------
# The zero-input pair: a check over nothing must say so
# ---------------------------------------------------------------------------


def test_zero_figures_is_did_not_run_and_never_a_pass(tmp_path):
    """all() over an empty sequence is True. That is how a filter which removed
    everything reports every figure passing."""
    empty = _record()
    empty["figures"] = {}
    artifact = conftest.tmp_artifact(
        tmp_path, readme=_CLEAN_README, figures=empty, slug="zero-input")
    report_path = tmp_path / "zero-input.json"

    result = _run(artifact, report=report_path)

    assert result.exit_code != 0, (
        "a check over zero figures reported a PASS. stdout:\n%s" % result.stdout)
    assert result.exit_code == 2, (
        "zero population is DID-NOT-RUN (2), not a finding (1): the check could "
        "not look. exit=%d\n%s\n%s"
        % (result.exit_code, result.stdout, result.stderr))
    assert result.report is not None, "the check wrote no structured report"
    assert result.report["code"] == 2, result.report
    assert result.report["checked"] == 0, (
        "checked must be 0 over an empty figures block, got %r"
        % result.report["checked"])


def test_an_absent_figures_record_is_did_not_run(tmp_path):
    """An artifact that never produced a record is a DID-NOT-RUN, not a pass."""
    artifact = conftest.tmp_artifact(
        tmp_path, readme=_CLEAN_README, figures=None, slug="record-absent")
    report_path = tmp_path / "record-absent.json"

    result = _run(artifact, report=report_path)

    assert result.exit_code == 2, (
        "an artifact whose figures record was never written reported exit %d\n%s"
        % (result.exit_code, result.stdout))
    assert result.report is not None, "the check wrote no structured report"
    assert result.report["code"] == 2, result.report
    assert result.report["checked"] == 0, result.report


# ---------------------------------------------------------------------------
# The committed one-known-bad fixtures
# ---------------------------------------------------------------------------


def test_a_figure_without_its_population_is_a_finding_naming_the_key(tmp_path):
    """a success criterion's detection half. The KEY is named -- a bare verdict makes the
    operator search, and CHECK-01's own wording forbids a bare verdict."""
    artifact = conftest.broken_fixture(WITHOUT_POPULATION)
    report_path = tmp_path / "without-population.json"

    result = _run(artifact, report=report_path)

    assert result.exit_code == 1, (
        "a figure carrying no denominator was not reported as a finding. "
        "exit=%d\n%s\n%s" % (result.exit_code, result.stdout, result.stderr))
    report = result.report
    assert report is not None, "the check wrote no structured report"
    assert report["code"] == 1, report
    assert report["checked"] == 2, (
        "both figures in the fixture must be examined, got checked=%r"
        % report["checked"])
    assert "figure:cache_hit_ratio" in report["finding_ids"], (
        "the offending figure key is not named: %r" % (report["finding_ids"],))
    assert report["finding_ids"] == ["figure:cache_hit_ratio"], (
        "the VALID figure beside it was also reported. A check that refuses the "
        "whole record discriminates nothing: %r" % (report["finding_ids"],))
    assert report["unpopulated_figures"] == 1, report


def test_a_figure_value_in_prose_is_caught_by_the_value_rule(tmp_path):
    """the design rules: the case a shape allow-list cannot see.

    The leaked value classifies as a PORT, so the shape rule reports this
    document clean and only the value check fires. This is an earlier finding's back-solving
    failure in fixture form.
    """
    artifact = conftest.broken_fixture(IN_PROSE)
    report_path = tmp_path / "in-prose.json"

    result = _run(artifact, report=report_path)

    assert result.exit_code == 1, (
        "a figure value typed into un-rendered prose was not reported. "
        "exit=%d\n%s\n%s" % (result.exit_code, result.stdout, result.stderr))
    report = result.report
    assert report is not None, "the check wrote no structured report"
    assert report["code"] == 1, report
    assert report["value_leaks"] >= 1, (
        "the value rule did not fire: %r" % report)
    assert report["unclassified"] == 0, (
        "the SHAPE rule was what fired, which means this fixture is no longer "
        "the value-only case it exists to be: %r" % report)
    assert any(fid.startswith("leak:") for fid in report["finding_ids"]), (
        "no leak finding id: %r" % (report["finding_ids"],))


def test_both_committed_fixtures_are_named_broken_and_are_never_enumerated():
    """a design rule -> a design rule, for THIS plan's two fixtures specifically, by path
    resolution rather than by name."""
    scan_root = conftest.SCAN_ROOT
    enumerated = sorted(child.resolve() for child in scan_root.iterdir()
                        if child.is_dir())
    assert enumerated, (
        "enumerated 0 directories under SCAN_ROOT %s -- an empty scan set makes "
        "every assertion below vacuously true" % scan_root)

    for name in (WITHOUT_POPULATION, IN_PROSE):
        fixture = conftest.broken_fixture(name).resolve()
        assert fixture.name.startswith("broken-"), fixture
        assert fixture not in enumerated, (
            "%s is one of the %d enumerated artifact candidates under %s"
            % (fixture, len(enumerated), scan_root))
        assert (fixture / "results" / "figures.json").is_file(), (
            "%s carries no figures record" % fixture)


# ---------------------------------------------------------------------------
# The discriminating counterpart: a correct artifact must PASS
# ---------------------------------------------------------------------------


def test_a_correctly_rendered_artifact_passes(tmp_path):
    """Rendered with the real render.py, then checked. Without this test the
    findings above are equally consistent with a check that fails everything.

    It renders through the tool rather than hand-writing the rendered form, so
    the mask this check applies is pinned to what render.py actually writes.
    """
    artifact = _artifact(tmp_path)
    written = _run_render(artifact, "--write")
    assert written.exit_code == 0, written.stderr
    rendered = (artifact / "README.md").read_text(encoding="utf-8")
    assert "12.5" in rendered, rendered

    report_path = tmp_path / "clean.json"
    result = _run(artifact, report=report_path)
    assert result.exit_code == 0, (
        "a correctly rendered artifact was reported as a finding:\n%s\n%s"
        % (result.stdout, result.stderr))
    assert result.report["found"] == 0, result.report
    assert result.report["rendered_holes"] >= 1, (
        "no rendered hole was seen, so the mask was never exercised: %r"
        % result.report)


def test_an_ordered_list_marker_is_not_a_finding(tmp_path):
    """G-1. A checker that raises against the first author who writes a numbered
    list is a checker people learn to ignore."""
    readme = (
        "# demo-artifact\n"
        "\n"
        "<!-- artifact:figures:begin -->\n"
        "The median was {{figures.median_latency_ms}} ms.\n"
        "<!-- artifact:figures:end -->\n"
        "\n"
        "## Steps\n"
        "\n"
        "1. Start the service.\n"
        "2. Replay the corpus.\n"
        "10) Read the report.\n"
        "\n"
        "Dated: 2026-09-15\n"
    )
    artifact = _artifact(tmp_path, readme=readme)
    assert _run_render(artifact, "--write").exit_code == 0

    report_path = tmp_path / "ordered-list.json"
    result = _run(artifact, report=report_path)
    assert result.exit_code == 0, (
        "an ordered list was reported as unclassified numerals:\n%s"
        % result.stdout)
    assert result.report["unclassified"] == 0, result.report
    assert result.report["reclassified"]["ordered_list_marker"] == 3, (
        "expected three re-classified list markers, got %r"
        % (result.report["reclassified"],))


def test_a_slug_carrying_a_digit_is_not_a_finding(tmp_path):
    """G-2. The example-beta canon numbers its example projects, so an artifact slug
    carrying a digit is certain rather than hypothetical."""
    slug = "bp2-platform"
    readme = (
        "# bp2-platform\n"
        "\n"
        "Generated under Research/bp2-platform, which is where its results live.\n"
        "\n"
        "<!-- artifact:figures:begin -->\n"
        "The median was {{figures.median_latency_ms}} ms.\n"
        "<!-- artifact:figures:end -->\n"
        "\n"
        "Dated: 2026-09-15\n"
    )
    artifact = _artifact(tmp_path, readme=readme,
                         record=_record(slug=slug), slug=slug)
    assert _run_render(artifact, "--write").exit_code == 0

    report_path = tmp_path / "slug.json"
    result = _run(artifact, report=report_path)
    assert result.exit_code == 0, (
        "an artifact slug carrying a digit was reported as a finding:\n%s"
        % result.stdout)
    assert result.report["unclassified"] == 0, result.report
    assert result.report["reclassified"]["artifact_slug"] == 2, (
        "expected two re-classified slug tokens, got %r"
        % (result.report["reclassified"],))


def test_a_hand_typed_numeral_in_prose_is_still_a_finding(tmp_path):
    """The other half of G-1 and G-2: closing two false positives must not open
    a hole. A numeral that is neither a list marker nor the slug still fires."""
    readme = (
        "# demo-artifact\n"
        "\n"
        "<!-- artifact:figures:begin -->\n"
        "The median was {{figures.median_latency_ms}} ms.\n"
        "<!-- artifact:figures:end -->\n"
        "\n"
        "The service held 87 connections open for the whole window.\n"
        "\n"
        "Dated: 2026-09-15\n"
    )
    artifact = _artifact(tmp_path, readme=readme)
    assert _run_render(artifact, "--write").exit_code == 0

    report_path = tmp_path / "hand-typed.json"
    result = _run(artifact, report=report_path)
    assert result.exit_code == 1, (
        "a hand-typed numeral in un-rendered prose was not reported:\n%s"
        % result.stdout)
    assert result.report["unclassified"] == 1, result.report
    assert "numeral:README.md:87" in result.report["finding_ids"], result.report


# ---------------------------------------------------------------------------
# an earlier plan open item 13 -- the canon bullet text CHECK-09 REQUIRES is CLASSIFIED,
# and is not a leak
# ---------------------------------------------------------------------------
#
# CHECK-09 requires the canon bullet's text in the claim table VERBATIM, byte
# for byte, with no normalization -- a paraphrase is exactly what it exists to
# catch. CHECK-01 lints every numeral in the same documents. MEASURED over the
# committed snapshot: 0 of 49 bullets have text canonkit.classify_numerals
# reads cleanly, because a canon bullet IS a metric claim and metric claims
# carry numerals. The two checks therefore contradicted each other on every
# artifact this programme will ever ship, and the contradiction was held by an
# owner-authored committed waiver until this plan removed it.
#
# THE DISCRIMINATING PAIR is the first two tests below: the same numeral must
# PASS inside a claim table that quotes the cited bullet and FAIL outside it. A
# test that only asserted "the claim table passes" would pass just as happily
# against a CHECK-01 that had been switched off.

CLAIM_BULLET_KEY = "example-alpha:P5-B5"

CLAIM_ROW_ORDER = ("Canon", "Example project", "Bullet id", "Bullet text, verbatim",
                   "Measured counterpart", "Verdict")

# A numeral that is NOT in the cited bullet and is not a figure value, so a hit
# on it is attributable to the claim region rather than to anything else.
FOREIGN_NUMERAL = "87"


def _bullet(key=CLAIM_BULLET_KEY):
    """One bullet, READ from the committed snapshot with an EXPLICIT encoding.

    The snapshot is written with ensure_ascii=False, so the encoding is not
    incidental: a default-locale read on this machine is cp1252 and would
    either raise or silently mojibake the very bytes the comparison depends on.
    """
    record = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    bullets = record["bullets"]
    assert key in bullets, (
        "%s carries no bullet %r; it holds %d compound key(s)"
        % (SNAPSHOT, key, len(bullets)))
    entry = bullets[key]
    assert isinstance(entry.get("text"), str) and entry["text"], (
        "bullet %r carries no verbatim text, so there is nothing to mask" % key)
    return entry


def _unclassified_numerals(text):
    """The numerals a bullet's own text puts into CHECK-01's scan.

    DERIVED from the frozen core rather than typed. A hand-written `9` would go
    on reading as correct after the snapshot changed, and the assertions below
    would then be about a numeral the document no longer carries.
    """
    report = core.classify_numerals(text, {})
    return [hit.token for hit in report.hits
            if hit.kind == core.KIND_UNCLASSIFIED]


def _masking_fields(report):
    """Assert the three masking counts EXIST, then hand the report back.

    A `.get()` here would answer every question with a default, and a default
    is indistinguishable from a real measurement of zero -- which is the whole
    failure mode this repair's own population line exists to prevent.
    """
    missing = [name for name in ("canon_bullet_text", "claim_cells_masked",
                                 "claim_cells_unmasked")
               if name not in report]
    assert not missing, (
        "the report carries no %r, so any number read from it would be a "
        "default rather than a measurement: %r" % (missing, sorted(report)))
    return report


def _claim_rows(**overrides):
    """A claim table CHECK-09 accepts, with named cells overridden."""
    entry = _bullet()
    rows = {
        "Canon": entry["canon"],
        "Example project": entry["project"],
        "Bullet id": CLAIM_BULLET_KEY,
        "Bullet text, verbatim": entry["text"],
        "Measured counterpart": "the headline figure in the results record",
        "Verdict": "SUPPORTS-WITH-REVISION",
    }
    rows.update(overrides)
    return rows


def _claim_table(rows):
    return ("| Field | Value |\n|---|---|\n"
            + "".join("| %s | %s |\n" % (name, rows[name])
                      for name in CLAIM_ROW_ORDER))


def _claim_readme(rows=None, in_region=True, epilogue=""):
    table = _claim_table(_claim_rows() if rows is None else rows)
    if in_region:
        table = ("<!-- artifact:claim:begin -->\n" + table
                 + "<!-- artifact:claim:end -->\n")
    return (
        "# demo-artifact\n"
        "\n"
        "<!-- artifact:figures:begin -->\n"
        "The median was {{figures.median_latency_ms}} ms.\n"
        "<!-- artifact:figures:end -->\n"
        "\n"
        "**Claim under test.**\n"
        "\n"
        + table
        + epilogue
        + "\n"
        "Dated: 2026-09-15\n"
    )


def _claim_record(slug="demo-artifact"):
    """A figures record naming the SAME bullet the claim table cites, so
    CHECK-09 has a counterpart on both limbs and can legitimately exit 0."""
    return _record(slug=slug,
                   figures={"median_latency_ms":
                            _figure(canon_bullet=CLAIM_BULLET_KEY)})


def _claim_artifact(tmp_path, rows=None, in_region=True, epilogue="",
                    slug="demo-artifact"):
    """A rendered artifact carrying a claim-under-test table.

    Rendered through the real render.py rather than hand-written, so the
    rendered-hole mask this check applies stays pinned to what render.py
    actually writes.
    """
    artifact = _artifact(tmp_path,
                         readme=_claim_readme(rows, in_region, epilogue),
                         record=_claim_record(slug), slug=slug)
    rendered = _run_render(artifact, "--write")
    assert rendered.exit_code == 0, rendered.stderr
    return artifact


def test_a_verbatim_canon_bullet_passes_check_01_and_check_09_on_one_tree(tmp_path):
    """The conflict, closed: ONE tree, BOTH checks, both exit 0, no waiver.

    Before this repair the same tree was exit 1 on CHECK-01 (the bullet's own
    numerals read as unclassified prose) and exit 0 on CHECK-09 (the bullet's
    text was verbatim, which is what CHECK-09 requires).
    """
    entry = _bullet()
    numerals = _unclassified_numerals(entry["text"])
    assert numerals, (
        "bullet %r puts NO unclassified numeral into the scan, so this tree "
        "would pass whether or not the masking works" % CLAIM_BULLET_KEY)

    artifact = _claim_artifact(tmp_path)

    one = _run(artifact, report=tmp_path / "claim-01.json")
    assert one.exit_code == 0, (
        "the canon bullet text CHECK-09 REQUIRES was reported as a CHECK-01 "
        "finding. exit=%d\n%s\n%s"
        % (one.exit_code, one.stdout, one.stderr))
    assert one.report["found"] == 0, one.report
    assert _masking_fields(one.report)["canon_bullet_text"] == len(numerals), (
        "the mask removed %r finding(s); the bullet's text carries %r "
        "unclassified numeral(s) %r"
        % (one.report["canon_bullet_text"], len(numerals), numerals))

    nine = _run_09(artifact, report=tmp_path / "claim-09.json")
    assert nine.exit_code == 0, (
        "CHECK-09 rejected the same tree, so the two checks were never made to "
        "agree -- only CHECK-01 was quietened. exit=%d\n%s\n%s"
        % (nine.exit_code, nine.stdout, nine.stderr))
    assert nine.report["checked"] >= 1, (
        "CHECK-09 exited 0 over %r reference(s); a zero population is not "
        "agreement" % nine.report["checked"])


def test_the_same_numeral_outside_the_claim_table_is_still_a_finding(tmp_path):
    """The other half of the pair. A repair that simply blunted the numeral
    lint would satisfy the test above and nothing would notice."""
    entry = _bullet()
    numerals = _unclassified_numerals(entry["text"])
    assert numerals, CLAIM_BULLET_KEY
    numeral = numerals[0]

    epilogue = ("\nThe tuning arm ran for %s hours of wall clock in total.\n"
                % numeral)
    artifact = _claim_artifact(tmp_path, epilogue=epilogue)

    result = _run(artifact, report=tmp_path / "outside.json")
    assert result.exit_code == 1, (
        "the SAME numeral typed into un-rendered prose outside the claim table "
        "was not reported. exit=%d\n%s" % (result.exit_code, result.stdout))
    assert "numeral:README.md:%s" % numeral in result.report["finding_ids"], (
        "%r is not among the findings %r"
        % (numeral, result.report["finding_ids"]))
    assert _masking_fields(result.report)["canon_bullet_text"] == len(numerals), (
        "the claim table's own copy was not masked, so this test would fail "
        "for the wrong reason: %r" % result.report)


def test_a_numeral_the_cited_bullet_does_not_carry_is_a_finding(tmp_path):
    """The masking is keyed to the CITED BULLET, never to the region.

    A numeral sitting inside the claim region but outside the verbatim cell is
    a claim about this measurement, not a quotation of the canon, and stays a
    finding.
    """
    rows = _claim_rows(
        **{"Measured counterpart": "%s replayed requests" % FOREIGN_NUMERAL})
    artifact = _claim_artifact(tmp_path, rows=rows)

    result = _run(artifact, report=tmp_path / "foreign.json")
    assert result.exit_code == 1, (
        "a numeral the cited bullet does not carry passed because it sat "
        "inside the claim region. exit=%d\n%s"
        % (result.exit_code, result.stdout))
    assert "numeral:README.md:%s" % FOREIGN_NUMERAL in result.report["finding_ids"], (
        "%r is not among the findings %r"
        % (FOREIGN_NUMERAL, result.report["finding_ids"]))
    assert _masking_fields(result.report)["canon_bullet_text"] >= 1, (
        "the verbatim cell beside it was not masked either, so this finding "
        "does not show the masking is keyed to the bullet: %r" % result.report)


def test_a_paraphrased_bullet_text_is_masked_by_nothing(tmp_path):
    """The strongest form of "keyed to the bullet": change the CELL, not the
    region, and the numerals in it come back as findings -- while CHECK-09
    reports the same cell as a text mismatch. The two checks agree in both
    directions, which is what makes this a classification and not an
    exclusion (the conventions document, section 4)."""
    entry = _bullet()
    numerals = _unclassified_numerals(entry["text"])
    assert numerals, CLAIM_BULLET_KEY

    # RE-KEYED by an earlier plan from `replace("Tested", "Tests")` to a DERIVED
    # mutation. The old form depended on one bullet of one corpus containing
    # one English word: against any other corpus the replace was a no-op, the
    # "paraphrase" came back byte-identical, and the test stopped discriminating
    # while still running. What is needed is only a cell that differs from the
    # bullet's bytes and puts the SAME numerals into the scan, so the first
    # long alphabetic word has a letter doubled -- a change that cannot create
    # or destroy a numeral, which is the property the next assertion checks.
    word = re.search(r"[A-Za-z]{4,}", entry["text"])
    assert word, (
        "the cited bullet carries no alphabetic word to alter, so no "
        "paraphrase can be derived from it: %r" % entry["text"][:120])
    altered = word.group(0) + word.group(0)[-1]
    paraphrase = (entry["text"][:word.start()] + altered
                  + entry["text"][word.end():])
    assert paraphrase != entry["text"], (
        "the paraphrase is byte-identical to the bullet, so nothing about this "
        "test discriminates: %r" % paraphrase)
    assert _unclassified_numerals(paraphrase) == numerals, (
        "the paraphrase changed which numerals are in play, so a finding here "
        "would not attribute to the masking")

    rows = _claim_rows(**{"Bullet text, verbatim": paraphrase})
    artifact = _claim_artifact(tmp_path, rows=rows)

    result = _run(artifact, report=tmp_path / "paraphrase-01.json")
    assert result.exit_code == 1, (
        "a cell that is NOT the cited bullet's bytes was masked anyway, which "
        "makes the mask keyed to the REGION. exit=%d\n%s"
        % (result.exit_code, result.stdout))
    assert _masking_fields(result.report)["canon_bullet_text"] == 0, result.report
    assert result.report["claim_cells_unmasked"] == 1, (
        "the unmasked cell was not counted, so an author reading the report "
        "cannot tell a quotation from a paraphrase: %r" % result.report)

    nine = _run_09(artifact, report=tmp_path / "paraphrase-09.json")
    assert nine.exit_code == 1, (
        "CHECK-09 accepted the paraphrase, so the two checks no longer meet on "
        "the same cell. exit=%d\n%s" % (nine.exit_code, nine.stdout))
    assert "text-mismatch" in sorted({f["kind"] for f in nine.report["findings"]}), (
        "CHECK-09 fired on something other than the text: %r"
        % nine.report["findings"])


def test_a_claim_table_outside_every_region_is_masked_too(tmp_path):
    """results/RESULTS.md puts its claim table OUTSIDE its `artifact:claim`
    region -- the region there holds the headline before/after table instead,
    which is why CHECK-09 finds claim tables STRUCTURALLY. A mask keyed on the
    region would leave that document's bullet text a finding: the same defect
    this repair exists to close, relocated to the document nobody checks."""
    artifact = _claim_artifact(tmp_path, in_region=False)

    result = _run(artifact, report=tmp_path / "no-region.json")
    assert result.exit_code == 0, (
        "a claim table outside every artifact:claim region was not masked, so "
        "the mask is keyed on the anchor. exit=%d\n%s"
        % (result.exit_code, result.stdout))
    assert _masking_fields(result.report)["canon_bullet_text"] >= 1, result.report
    assert result.report["claim_cells_masked"] == 1, result.report


def test_the_masked_count_prints_as_its_own_number(tmp_path):
    """The conventions document, section 2, property 3: every input not examined is
    COUNTED and given a reason beside it. A masked numeral that silently left
    the denominator would be the same defect in a friendlier hat."""
    entry = _bullet()
    numerals = _unclassified_numerals(entry["text"])
    artifact = _claim_artifact(tmp_path)

    result = _run(artifact, report=tmp_path / "count.json")
    assert "canon-text=%d" % len(numerals) in result.stdout, (
        "the masked count was never printed:\n%s" % result.stdout)
    assert _masking_fields(result.report)["canon_bullet_text"] == len(numerals),         result.report
    assert result.report["claim_cells_masked"] == 1, result.report
    assert result.report["claim_cells_unmasked"] == 0, result.report


def test_an_artifact_with_no_claim_table_is_unchanged(tmp_path):
    """The fifth behaviour: a document carrying no claim table takes the same
    path it always did, and says so with three zeroes rather than silence."""
    artifact = _artifact(tmp_path)
    assert _run_render(artifact, "--write").exit_code == 0

    result = _run(artifact, report=tmp_path / "no-claim.json")
    assert result.exit_code == 0, (
        "a document with no claim table changed behaviour:\n%s" % result.stdout)
    assert _masking_fields(result.report)["canon_bullet_text"] == 0, result.report
    assert result.report["claim_cells_masked"] == 0, result.report
    assert result.report["claim_cells_unmasked"] == 0, result.report


# ---------------------------------------------------------------------------
# The population line (a design rule, CHECK-10, CHECK-11)
# ---------------------------------------------------------------------------


def test_the_summary_line_carries_every_population_number(tmp_path):
    """CHECK-01's own wording: the COUNT of unclassified numerals, never a bare
    verdict. The effective floor and the waiver count print beside it."""
    artifact = conftest.broken_fixture(IN_PROSE)
    result = _run(artifact, report=tmp_path / "line.json")
    line = [row for row in result.stdout.splitlines() if "CHECK-01" in row]
    assert line, "no CHECK-01 population line was printed:\n%s" % result.stdout
    printed = line[0]
    for needle in ("found=", "checked=", "floor=", "waived="):
        assert needle in printed, (
            "the population line is missing %r: %r" % (needle, printed))
    assert "unclassified=" in result.stdout, (
        "the count of unclassified numerals was never printed:\n%s"
        % result.stdout)


def test_the_floor_override_is_the_value_that_prints(tmp_path):
    """a design rule's load-bearing half. Printing the DECLARED floor while applying a
    different one is a population line that lies."""
    artifact = conftest.broken_fixture(IN_PROSE)
    result = _run(artifact, "--min-population", "99",
                  report=tmp_path / "floor.json")
    assert "floor=99" in result.stdout, (
        "the overridden floor was not what printed:\n%s" % result.stdout)
    assert result.report["floor"] == 99, result.report


def test_a_population_below_the_floor_is_demoted_to_did_not_run(tmp_path):
    """a design rule meeting a design rule. Two figures under a floor of 99 is a population too
    small for the verdict to mean anything, which is "could not look" (2), not
    "looked and found" (1). The demotion is PRINTED as well as returned: an exit
    code nobody can see is not a report."""
    artifact = conftest.broken_fixture(IN_PROSE)
    result = _run(artifact, "--min-population", "99",
                  report=tmp_path / "demote.json")
    assert result.exit_code == 2, (
        "a below-floor population was not demoted. exit=%d\n%s"
        % (result.exit_code, result.stdout))
    assert result.report["code"] == 2, result.report
    assert result.report["checked"] == 2, (
        "the demotion must not erase what WAS examined: %r" % result.report)
    assert "DEMOTED" in result.stdout, (
        "the demotion was never printed:\n%s" % result.stdout)


# ---------------------------------------------------------------------------
# The anti-rot regression -- the half of a design rule that keeps the evidence alive
# ---------------------------------------------------------------------------
#
# a design rule asks for "a test that re-runs each known-bad fixture and asserts the
# captured output still matches". Asserted byte-for-byte over stdout prose, the
# first error-message improvement breaks it and the standard repair is to WEAKEN
# the assertion -- which empties the mechanism it was added to protect.
#
# So the pin is over the structured --report, and over six stable fields
# of it. a design rule gave every tool a `schema_version` precisely so this comparison
# can survive a version change; this is its first real consumer.

EXPECTATION_FILE = "expected-CHECK-01.json"

PINNED_FIELDS = ("check_id", "code", "found", "checked", "finding_ids",
                 "schema_version")

# Every field name that would make the pin sensitive to WORDING. A pin holding
# any of these is the byte-for-byte-over-prose failure wearing a JSON hat.
PROSE_FIELDS = ("note", "notes", "stdout", "stderr", "message", "messages",
                "summary", "detail", "details", "findings", "text", "line",
                "context", "description")

KNOWN_BAD_FIXTURES = (WITHOUT_POPULATION, IN_PROSE)


def _pinned(report):
    """The six stable fields, and nothing else."""
    return {field: report[field] for field in PINNED_FIELDS}


def test_the_anti_rot_pin_holds_for_every_known_bad_fixture(tmp_path):
    """Re-run each committed fixture and compare the STRUCTURED report."""
    compared = 0
    for name in KNOWN_BAD_FIXTURES:
        artifact = conftest.broken_fixture(name)
        expectation_path = artifact / EXPECTATION_FILE
        assert expectation_path.is_file(), (
            "%s carries no %s, so its RED evidence has nothing pinning it"
            % (name, EXPECTATION_FILE))
        expected = json.loads(expectation_path.read_text(encoding="ascii"))

        result = _run(artifact, report=tmp_path / ("%s.json" % name))
        assert result.report is not None, (
            "%s: the check wrote no structured report" % name)

        missing = [field for field in PINNED_FIELDS
                   if field not in result.report]
        assert not missing, (
            "%s: the live report no longer carries %r. A renamed field would "
            "otherwise make this pin compare nothing." % (name, missing))

        assert _pinned(result.report) == expected, (
            "%s: the structured report drifted from its committed expectation.\n"
            "  expected: %r\n  measured: %r"
            % (name, expected, _pinned(result.report)))
        compared += 1

    assert compared == len(KNOWN_BAD_FIXTURES), (
        "compared %d of %d known-bad fixtures -- a loop that compared nothing "
        "would pass every assertion above"
        % (compared, len(KNOWN_BAD_FIXTURES)))


def test_the_anti_rot_expectation_carries_no_prose_field():
    """Inspect the committed key set itself, not the comparison that reads it.

    This is what makes "the pin does not read stdout" checkable rather than
    asserted: if no committed expectation holds a wording-bearing field, no
    wording change can break the pin, whatever the comparison later becomes.
    """
    inspected = 0
    for name in KNOWN_BAD_FIXTURES:
        path = conftest.broken_fixture(name) / EXPECTATION_FILE
        expectation = json.loads(path.read_text(encoding="ascii"))
        keys = set(expectation)

        assert keys == set(PINNED_FIELDS), (
            "%s pins %r; the six stable fields are %r"
            % (name, sorted(keys), sorted(PINNED_FIELDS)))
        leaked = sorted(keys & set(PROSE_FIELDS))
        assert not leaked, (
            "%s pins wording-bearing field(s) %r -- an error-message "
            "improvement would then break this pin, and the standard repair is "
            "to weaken it" % (name, leaked))
        inspected += 1

    assert inspected == len(KNOWN_BAD_FIXTURES), (
        "inspected %d of %d expectation files" % (inspected,
                                                  len(KNOWN_BAD_FIXTURES)))


# ---------------------------------------------------------------------------
# The module contract
# ---------------------------------------------------------------------------


def test_check_01_is_discovered_under_a_declared_id():
    """The module satisfies the protocol an earlier plan declared, and its id is one
    of the declared universe. A module outside it IS a finding.

    The size is READ from the contract rather than typed. It was typed until
    2026-09-21 and CHECK-16 moved it, at which point this test failed over a
    universe that had legitimately grown -- which says nothing about CHECK-01,
    the module this file is named for. The property worth pinning here is
    membership; the universe's SIZE is pinned once, in test_canonkit.py, against
    the committed literal that exists to be that tripwire.
    """
    report = checks.discover(str(CHECKS_DIR), verbose=False)

    assert report.declared == checks.DECLARED_MODULE_COUNT, (
        "discover() reports a universe of %d against a contract of %d"
        % (report.declared, checks.DECLARED_MODULE_COUNT))
    assert "CHECK-01" in report.ids, (
        "discover() found %d module(s) and CHECK-01 was not among them: %r"
        % (report.found, report.ids))
    assert report.protocol_violations == [], report.protocol_violations


def test_the_check_module_is_pure_ascii():
    """It is in the vendored set, copied by bytes into every artifact."""
    payload = CHECK_01.read_bytes()
    payload.decode("ascii")
    assert len(payload) > 0


# ---------------------------------------------------------------------------
# The four re-classifications a REAL artifact forced, and the needle-length
# repair an earlier plan handed over with them
# ---------------------------------------------------------------------------
#
# MEASURED, on example-cache-benchmark, before any of this existed:
# `found=319 checked=10 of 10 unclassified=304 leaks=15`. Reading the 171
# distinct (document, token) pairs rather than the total is what produced these
# four classes: `p99` appears nineteen times, `k6` six, the artifact's own
# `run_k6_sweep.py` three, and a retraction record quotes the withdrawn numbers
# it exists to withdraw. None of those is "a figure appearing without its
# population", which is what this check is for.
#
# EVERY ONE OF THE FOUR IS SAFE IN THE SAME STRUCTURAL WAY, and that is the
# property the second test of each pair below asserts rather than asserting the
# first alone: re-classification acts ONLY on canonkit's UNCLASSIFIED hits. The
# value rule runs over the same text independently and is never masked, so a
# figures.json VALUE typed inside a fenced block, inside a frozen region, or
# anywhere else is STILL a leak. A test that only showed "the new class passes"
# would pass just as happily against a CHECK-01 that had been switched off.

PERCENTILE_PROSE = (
    "# demo-artifact\n"
    "\n"
    "<!-- artifact:figures:begin -->\n"
    "The median was {{figures.median_latency_ms}} ms.\n"
    "<!-- artifact:figures:end -->\n"
    "\n"
    "%s\n"
    "\n"
    "Dated: 2026-09-15\n"
)


def test_a_percentile_label_is_not_a_finding(tmp_path):
    """A percentile label names WHICH order statistic, never its magnitude.

    `p50` and `p99` carry no value at all, so neither can be a figure typed
    into prose nor a number back-solved from a canon percentage. Every latency
    artifact this programme will build reports them.
    """
    readme = PERCENTILE_PROSE % (
        "The ceiling is a p99 budget and the p50 is reported beside it, "
        "because a p99 alone hides the shape of the distribution.")
    artifact = _artifact(tmp_path, readme=readme)
    assert _run_render(artifact, "--write").exit_code == 0

    result = _run(artifact, report=tmp_path / "percentile.json")

    assert result.exit_code == 0, (
        "percentile labels were reported as unclassified numerals:\n%s"
        % result.stdout)
    assert result.report["unclassified"] == 0, result.report
    assert result.report["reclassified"]["percentile_label"] == 3, (
        "expected three re-classified percentile labels, got %r"
        % (result.report["reclassified"],))


def test_a_percentile_VALUE_in_prose_is_still_a_finding(tmp_path):
    """The other half. Masking the LABEL must not mask the number beside it."""
    readme = PERCENTILE_PROSE % "The p99 was 64.09 ms at the matched rate."
    artifact = _artifact(tmp_path, readme=readme)
    assert _run_render(artifact, "--write").exit_code == 0

    result = _run(artifact, report=tmp_path / "percentile-value.json")

    assert result.exit_code == 1, (
        "a percentile VALUE typed into prose was not reported:\n%s"
        % result.stdout)
    assert result.report["unclassified"] == 1, result.report
    assert "numeral:README.md:64.09" in result.report["finding_ids"], (
        result.report)


def test_a_name_that_exists_in_the_tree_is_not_a_finding(tmp_path):
    """An artifact's own file and directory names are not claims.

    Derived from the tree by walking it, never from a committed list of words.
    A candidate must start with a letter, so a token shaped like a measurement
    can never be admitted by naming a file after it.
    """
    readme = (
        "# demo-artifact\n"
        "\n"
        "<!-- artifact:figures:begin -->\n"
        "The median was {{figures.median_latency_ms}} ms.\n"
        "<!-- artifact:figures:end -->\n"
        "\n"
        "The load is driven by k6, whose scripts live beside the service, and\n"
        "run_k6_sweep.py is the program that runs a sweep.\n"
        "\n"
        "Dated: 2026-09-15\n"
    )
    artifact = _artifact(tmp_path, readme=readme)
    (artifact / "k6").mkdir()
    (artifact / "k6" / "sweep.js").write_text("// sweep\n", encoding="utf-8")
    (artifact / "run_k6_sweep.py").write_text("# runner\n", encoding="utf-8")
    assert _run_render(artifact, "--write").exit_code == 0

    result = _run(artifact, report=tmp_path / "tree-path.json")

    assert result.exit_code == 0, (
        "the artifact's own file names were reported as findings:\n%s"
        % result.stdout)
    assert result.report["unclassified"] == 0, result.report
    assert result.report["reclassified"]["tree_path"] == 2, (
        "expected two re-classified tree paths, got %r"
        % (result.report["reclassified"],))


def test_a_name_that_does_NOT_exist_in_the_tree_is_still_a_finding(tmp_path):
    """The other half. The rule resolves against the tree, not against a shape."""
    readme = (
        "# demo-artifact\n"
        "\n"
        "<!-- artifact:figures:begin -->\n"
        "The median was {{figures.median_latency_ms}} ms.\n"
        "<!-- artifact:figures:end -->\n"
        "\n"
        "The load is driven by k9, which is not in this directory.\n"
        "\n"
        "Dated: 2026-09-15\n"
    )
    artifact = _artifact(tmp_path, readme=readme)
    assert _run_render(artifact, "--write").exit_code == 0

    result = _run(artifact, report=tmp_path / "no-tree-path.json")

    assert result.exit_code == 1, (
        "a name that is not in the tree was masked anyway:\n%s" % result.stdout)
    assert result.report["reclassified"]["tree_path"] == 0, result.report
    assert "numeral:README.md:k9" in result.report["finding_ids"], result.report


FENCED_README = (
    "# demo-artifact\n"
    "\n"
    "<!-- artifact:figures:begin -->\n"
    "The median was {{figures.median_latency_ms}} ms.\n"
    "<!-- artifact:figures:end -->\n"
    "\n"
    "## Running it\n"
    "\n"
    "```\n"
    "%s\n"
    "```\n"
    "\n"
    "Dated: 2026-09-15\n"
)


def test_a_fenced_block_is_a_transcript_and_is_not_a_finding(tmp_path):
    """A fenced block reproduces a command EXACTLY.

    Re-typing an argument, an environment assignment or an image tag to please
    a lint would make the documented command WRONG, and a documented command
    nobody can run is the defect the README rule exists to prevent.
    """
    readme = FENCED_README % (
        "MSYS_NO_PATHCONV=1 docker compose run --rm app python seed.py 20000\n"
        "python make_sequence.py 200000 20000")
    artifact = _artifact(tmp_path, readme=readme)
    assert _run_render(artifact, "--write").exit_code == 0

    result = _run(artifact, report=tmp_path / "fenced.json")

    assert result.exit_code == 0, (
        "a run block was reported as unclassified numerals:\n%s" % result.stdout)
    assert result.report["unclassified"] == 0, result.report
    assert result.report["reclassified"]["fenced_block"] == 4, (
        "expected four re-classified command literals -- one environment "
        "assignment and three arguments -- got %r"
        % (result.report["reclassified"],))


def test_a_figure_value_inside_a_fenced_block_is_still_a_leak(tmp_path):
    """THE SAFETY PROPERTY. Re-classification touches the shape limb only."""
    readme = FENCED_README % "echo 12.5"
    artifact = _artifact(tmp_path, readme=readme)
    assert _run_render(artifact, "--write").exit_code == 0

    result = _run(artifact, report=tmp_path / "fenced-leak.json")

    assert result.exit_code == 1, (
        "a figures.json VALUE inside a fenced block was masked:\n%s"
        % result.stdout)
    assert result.report["value_leaks"] == 1, result.report
    assert "leak:README.md:12.5" in result.report["finding_ids"], result.report


FROZEN_README = (
    "# demo-artifact\n"
    "\n"
    "<!-- artifact:figures:begin -->\n"
    "The median was {{figures.median_latency_ms}} ms.\n"
    "<!-- artifact:figures:end -->\n"
    "\n"
    "## Retracted\n"
    "\n"
    "<!-- artifact:frozen:begin -->\n"
    "%s\n"
    "<!-- artifact:frozen:end -->\n"
    "\n"
    "Dated: 2026-09-15\n"
)


def test_a_frozen_quotation_is_not_a_finding(tmp_path):
    """A retraction MUST quote the number it withdraws, or it records nothing.

    The frozen region is the same paired-region mechanism every other anchor
    uses, so it is declared in the document rather than inferred from wording,
    and its count prints beside the others.
    """
    readme = FROZEN_README % (
        "The withdrawn run reported a hit rate of 0.9882 falling to 0.9794, "
        "and a closed-loop ratio of 1.527x. All three are withdrawn.")
    artifact = _artifact(tmp_path, readme=readme)
    assert _run_render(artifact, "--write").exit_code == 0

    result = _run(artifact, report=tmp_path / "frozen.json")

    assert result.exit_code == 0, (
        "a frozen quotation was reported as unclassified numerals:\n%s"
        % result.stdout)
    assert result.report["unclassified"] == 0, result.report
    assert result.report["reclassified"]["frozen_quotation"] == 3, (
        "expected three re-classified frozen numerals, got %r"
        % (result.report["reclassified"],))


def test_a_CURRENT_figure_value_inside_a_frozen_region_is_still_a_leak(tmp_path):
    """THE SAFETY PROPERTY, and the one that makes the frozen region honest.

    A frozen region may only hold numbers that are NOT current figure values.
    Wrapping a live figure in one does not hide it, so the region cannot be
    used to smuggle a current measurement past the rule that it must be
    rendered.
    """
    readme = FROZEN_README % "The withdrawn run reported 12.5 ms."
    artifact = _artifact(tmp_path, readme=readme)
    assert _run_render(artifact, "--write").exit_code == 0

    result = _run(artifact, report=tmp_path / "frozen-leak.json")

    assert result.exit_code == 1, (
        "a CURRENT figure value inside a frozen region was masked:\n%s"
        % result.stdout)
    assert result.report["value_leaks"] == 1, result.report
    assert "leak:README.md:12.5" in result.report["finding_ids"], result.report


def _single_char_record(value):
    """A figures record whose only figure renders to a ONE-CHARACTER needle."""
    record = _record()
    record["figures"] = {
        "replicates_holding": _figure(value=value, unit="replicates",
                                      population=3,
                                      population_label="independent replicates",
                                      canon_value=None, canon_bullet=None,
                                      similar=None)}
    return record


def test_a_one_character_figure_value_is_not_a_leak_needle(tmp_path):
    """an earlier plan measured this and handed it here by name.

    Two of redis's fifteen leaks were the bare string `3`, produced from two
    replicate-count figures whose value is 3.0. A one-character numeric needle
    matches every `3` in ordinary prose, so it cannot DISCRIMINATE a leak from
    a coincidence -- and a needle that cannot discriminate is not a check. The
    count of needles dropped for length prints, so the exclusion is countable.
    """
    readme = (
        "# demo-artifact\n"
        "\n"
        "<!-- artifact:figures:begin -->\n"
        "It held for {{figures.replicates_holding}} replicates.\n"
        "<!-- artifact:figures:end -->\n"
        "\n"
        "The G-3 guard requires the ceiling to clear the faster arm.\n"
        "\n"
        "Dated: 2026-09-15\n"
    )
    artifact = _artifact(tmp_path, readme=readme,
                         record=_single_char_record(3.0))
    assert _run_render(artifact, "--write").exit_code == 0

    result = _run(artifact, report=tmp_path / "short-needle.json")

    assert result.exit_code == 0, (
        "a one-character needle matched ordinary prose and was reported:\n%s"
        % result.stdout)
    assert result.report["value_leaks"] == 0, result.report
    assert result.report["short_needle_leaks"] >= 1, (
        "the dropped needle was not counted: %r" % (result.report,))


def test_a_TWO_character_figure_value_is_still_a_leak_needle(tmp_path):
    """The other half. The repair is a length floor, not a switch."""
    readme = (
        "# demo-artifact\n"
        "\n"
        "<!-- artifact:figures:begin -->\n"
        "It held for {{figures.replicates_holding}} replicates.\n"
        "<!-- artifact:figures:end -->\n"
        "\n"
        "The uncached arm was typed into this sentence as 25 replicates.\n"
        "\n"
        "Dated: 2026-09-15\n"
    )
    artifact = _artifact(tmp_path, readme=readme,
                         record=_single_char_record(25.0))
    assert _run_render(artifact, "--write").exit_code == 0

    result = _run(artifact, report=tmp_path / "long-needle.json")

    assert result.exit_code == 1, (
        "a two-character needle stopped discriminating:\n%s" % result.stdout)
    assert result.report["value_leaks"] == 1, result.report
    assert result.report["short_needle_leaks"] == 0, result.report


def test_an_iso_year_month_is_not_a_finding(tmp_path):
    """G-7. The allow-list ALREADY classifies a date; this is the same category
    at month precision.

    the project technology-stack document section 8(b) makes an engagement's dates mandatory in every
    published artifact README, and a bare year (`2024`) is genuinely ambiguous
    with a measurement -- `2000 requests` is a figure. A year-MONTH is not: the
    frozen core's own `_ISO_DATE_RE` would accept `2024-06-01`, and inventing a
    day precision nobody measured to satisfy a lint is the shape this project
    refuses. So the tight form is admitted and the loose one is not.
    """
    readme = (
        "# demo-artifact\n"
        "\n"
        "<!-- artifact:figures:begin -->\n"
        "The median was {{figures.median_latency_ms}} ms.\n"
        "<!-- artifact:figures:end -->\n"
        "\n"
        "Built from an engagement running 2024-06 to 2024-08.\n"
        "\n"
        "Dated: 2026-09-15\n"
    )
    artifact = _artifact(tmp_path, readme=readme)
    assert _run_render(artifact, "--write").exit_code == 0

    result = _run(artifact, report=tmp_path / "year-month.json")

    assert result.exit_code == 0, (
        "an ISO year-month was reported as an unclassified numeral:\n%s"
        % result.stdout)
    assert result.report["reclassified"]["calendar_month"] == 2, (
        "expected two re-classified calendar months, got %r"
        % (result.report["reclassified"],))


def test_a_BARE_YEAR_is_still_a_finding(tmp_path):
    """The other half, and the reason the class stops at month precision.

    `2024` and `2000 requests` are the same token shape. Admitting a bare
    four-digit integer would admit a measurement, so it is not admitted.
    """
    readme = (
        "# demo-artifact\n"
        "\n"
        "<!-- artifact:figures:begin -->\n"
        "The median was {{figures.median_latency_ms}} ms.\n"
        "<!-- artifact:figures:end -->\n"
        "\n"
        "Built from an engagement running June 2024 to August 2024.\n"
        "\n"
        "Dated: 2026-09-15\n"
    )
    artifact = _artifact(tmp_path, readme=readme)
    assert _run_render(artifact, "--write").exit_code == 0

    result = _run(artifact, report=tmp_path / "bare-year.json")

    assert result.exit_code == 1, (
        "a bare four-digit year was masked, and so would a bare count be:\n%s"
        % result.stdout)
    assert result.report["reclassified"]["calendar_month"] == 0, result.report
    assert "numeral:README.md:2024" in result.report["finding_ids"], result.report
