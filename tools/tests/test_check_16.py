"""CHECK-16 -- a retracted figure that is still being asserted.

Every test here runs `tools/checks/check_16.py` AS A SUBPROCESS, by path,
through conftest.run_cli, for the two reasons every sibling check test does it:
by path under a bare module name is exactly how the vendored copy runs inside an
artifact, and the thing under test is an EXIT CODE, which run_cli returns from
the child rather than from a pipeline stage.

WHAT MAKES THE RED IN red-transcripts/CHECK-16.txt A REAL RED. The module is
registered and RUNNABLE in the commit that captures the transcript: it walks the
artifact, prunes the directories, opens every text file, counts what it read and
what it did not, and reports a population. Only the JUDGEMENT is stubbed -- it
reads no declaration and classifies no hit -- so every failure line in that
transcript is an assertion about a VERDICT, never about an import or a missing
file.

THE HARD HALF IS THE FALSE POSITIVE, AND IT IS MEASURED RATHER THAN IMAGINED.
A one-off sweep over one of this programme's artifacts found that a needle of
`98.8` matches `"rps": 6398.8` -- a throughput reading with nothing to do with
the hit rate that was withdrawn. The sweep's own conclusion is this check's
rule, and it is the reason half this file exists: a checker that fires on a
throughput number in a results file trains its reader to ignore it, and a
checker that is routinely ignored is worse than none.

THE OTHER HARD HALF IS THE OPPOSITE ERROR. A retraction RECORD quotes the figure
it withdrew, and so does the withdrawn run's own machine record. A check that
called those live would make writing an honest retraction impossible, so FROZEN
is a first-class arm and there are positive tests for it.

THIS FILE QUOTES RETRACTED-LOOKING FIGURES, and they are invented. They are not
any figure any artifact in this programme ever published: a test module that
quoted a real withdrawn number would become a carrier for the very scan it is
testing, which is the shape this repository has already been bitten by several
times.
"""

import importlib.util
import json
import sys
from pathlib import Path

from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT
CHECKS_DIR = REPO_ROOT / "tools" / "checks"
CHECK_16 = CHECKS_DIR / "check_16.py"

FIXTURE = "broken-retracted-figure-live"
EXPECTATION_FILE = "expected-CHECK-16.json"

PINNED_FIELDS = ("check_id", "code", "found", "checked", "finding_ids",
                 "schema_version")

PROSE_FIELDS = ("note", "notes", "stdout", "stderr", "message", "messages",
                "summary", "detail", "details", "findings", "text", "line",
                "context", "description", "hits", "not_examined_entries")

# INVENTED figures, in the shapes a real declaration uses. Nothing here is a
# number any artifact in this programme published.
INVENTED_RATIO = "4.321"
INVENTED_RATE = "77.7"


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


core = _load("frozen_core_for_check_16_tests",
             REPO_ROOT / "tools" / "canonkit.py")
check_16 = _load("check_16_under_test", CHECK_16)
contract = _load("check_contract_for_check_16", CHECKS_DIR / "__init__.py")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def declaration(entries=None, reviewed_on="2026-09-21", schema=True):
    payload = {"retracted": list(entries or [])}
    if reviewed_on is not None:
        payload["reviewed_on"] = reviewed_on
    if schema:
        payload["schema"] = "canonkit/retractions/1"
    return payload


def retraction(rid="an-invented-ratio", needles=None, context_terms=None,
               withdrawn_on="2026-07-31", why="an invented retraction, for a test"):
    """One declared retraction.

    `needles=[]` means AN EMPTY LIST and `needles=None` means "use the default".
    Written as an explicit `is None` test because the obvious `needles or
    [default]` spelling collapses the two -- and it did, measured: the test that
    exists to prove an entry with NO needles is a finding was handed one needle
    and passed the artifact instead. A falsy value silently replaced by a
    default is the same shape as an empty string testing True for membership,
    and both were in this change.
    """
    entry = {"id": rid, "withdrawn_on": withdrawn_on, "why": why,
             "needles": list(needles if needles is not None
                             else [INVENTED_RATIO])}
    if context_terms is not None:
        entry["context_terms"] = list(context_terms)
    return entry


def artifact(tmp_path, slug="retraction-demo", declared=None, files=None):
    """A minimal artifact plus a retraction declaration and extra text files.

    `declared=None` means the declaration is ABSENT, and it has to say so to
    conftest EXPLICITLY: tmp_artifact() writes a dated, empty one by default,
    because an artifact that withdrew nothing still declares that it withdrew
    nothing. Leaving the override off would hand every "no declaration" test an
    artifact that has one -- measured, and it turned four refusal tests green
    against a tree that could not have produced a refusal.
    """
    root = conftest.tmp_artifact(
        tmp_path, slug=slug,
        retractions=declared if declared is not None else None)
    if declared is not None:
        (root / "results" / "retractions.json").write_text(
            json.dumps(declared, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")
    for relative, text in (files or {}).items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    return root


def run_check(root, report=None, extra=()):
    argv = [sys.executable, str(CHECK_16), str(root)]
    if report is not None:
        argv += ["--report", str(report)]
    argv += list(extra)
    return conftest.run_cli(argv, cwd=Path(root).parent)


# ---------------------------------------------------------------------------
# THE ZERO-INPUT CASE (a design rule requires one)
# ---------------------------------------------------------------------------


def test_an_artifact_with_no_declaration_refuses_rather_than_passing(tmp_path):
    """The free pass this check exists to refuse.

    "No retracted figure is asserted here", said over an artifact nobody
    reviewed, is a sentence rather than a measurement -- and a clean verdict over
    a tree with no needles is the exact shape a design rule exists to refuse.
    """
    root = artifact(tmp_path, declared=None)
    assert not (root / "results" / "retractions.json").exists()

    result = run_check(root, report=tmp_path / "none.json")
    assert result.exit_code == core.EXIT_DID_NOT_RUN, (
        "an artifact with no retraction declaration exited %d; a scan with no "
        "needles found nothing because it hunted nothing:\n%s"
        % (result.exit_code, result.stdout))
    assert result.report["code"] == core.EXIT_DID_NOT_RUN, result.report
    assert result.report["checked"] == 0, result.report


def test_the_refusal_names_the_file_and_the_repair(tmp_path):
    """A refusal that does not say what would fix it is a dead end."""
    root = artifact(tmp_path, declared=None)
    result = run_check(root, report=tmp_path / "none.json")
    combined = (result.stdout + result.stderr).lower()
    assert "results/retractions.json" in combined, combined
    assert "repair" in combined, (
        "the refusal carries no REPAIR clause:\n%s" % combined)


def test_a_declaration_that_is_not_json_refuses_rather_than_reporting_clean(
        tmp_path):
    """Unreadable is DID-NOT-RUN. A file that could not be parsed declares nothing."""
    root = artifact(tmp_path, declared=declaration())
    (root / "results" / "retractions.json").write_text(
        "{ this is not json", encoding="utf-8", newline="\n")
    result = run_check(root, report=tmp_path / "bad.json")
    assert result.exit_code == core.EXIT_DID_NOT_RUN, result.stdout


def test_a_declaration_with_no_retracted_key_refuses(tmp_path):
    """An ABSENT key and an EMPTY list are different facts.

    One says nothing was withdrawn; the other says nobody wrote the key. A check
    that cannot tell them apart hands out a pass for a file nobody finished.
    """
    root = artifact(tmp_path, declared={"reviewed_on": "2026-09-21"})
    result = run_check(root, report=tmp_path / "nokey.json")
    assert result.exit_code == core.EXIT_DID_NOT_RUN, result.stdout


# ---------------------------------------------------------------------------
# THE ONE-KNOWN-BAD CASE (a design rule requires one)
# ---------------------------------------------------------------------------


def test_a_live_retracted_figure_is_a_finding(tmp_path):
    """The whole point. A withdrawn figure asserted in current prose."""
    root = artifact(
        tmp_path,
        declared=declaration([retraction(needles=[INVENTED_RATIO])]),
        files={"NOTES.md": "The speed-up we measure is %sx across the sweep.\n"
                           % INVENTED_RATIO})

    result = run_check(root, report=tmp_path / "live.json")
    assert result.exit_code == core.EXIT_FINDING, (
        "a withdrawn figure asserted in current prose exited %d:\n%s"
        % (result.exit_code, result.stdout))
    assert result.report["found"] >= 1, result.report
    assert result.report["arms"]["LIVE"] >= 1, result.report
    assert any("NOTES.md" in fid for fid in result.report["finding_ids"]), (
        "the finding does not name the file that carries it: %r"
        % (result.report["finding_ids"],))


def test_the_finding_carries_its_line_number(tmp_path):
    """A finding a reader cannot navigate to is a finding nobody repairs."""
    root = artifact(
        tmp_path,
        declared=declaration([retraction(needles=[INVENTED_RATIO])]),
        files={"NOTES.md": "first line\nsecond line\nthe ratio is %sx here\n"
                           % INVENTED_RATIO})
    result = run_check(root, report=tmp_path / "line.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    hits = [hit for hit in result.report["hits"] if hit["arm"] == "LIVE"]
    assert hits, result.report
    assert hits[0]["line"] == 3, hits


# ---------------------------------------------------------------------------
# THE FALSE POSITIVE THAT SHAPED THE NEEDLE RULE
# ---------------------------------------------------------------------------


def test_a_bare_numeric_needle_inside_a_longer_number_is_not_a_finding(tmp_path):
    """MEASURED, not imagined: `98.8` matches `"rps": 6398.8`.

    Reproduced here with invented numbers. If this ever fails, the check has
    started firing on throughput readings in results files, which is how a
    checker teaches its reader to ignore it.
    """
    root = artifact(
        tmp_path,
        declared=declaration([retraction(rid="an-invented-rate",
                                         needles=[INVENTED_RATE])]),
        files={"results/throughput.json":
               '{\n  "rps": 63%s\n}\n' % INVENTED_RATE})

    result = run_check(root, report=tmp_path / "fp.json")
    assert result.exit_code == core.EXIT_PASS, (
        "the check fired on a throughput number that merely ENDS with the "
        "needle's digits:\n%s" % result.stdout)
    assert result.report["arms"]["FALSE-POSITIVE"] >= 1, (
        "the hit was not classified FALSE-POSITIVE, so it was not counted at "
        "all -- an adjudicated hit that vanishes is worse than one that fires: "
        "%r" % (result.report["arms"],))
    assert result.report["arms"]["LIVE"] == 0, result.report


def test_the_false_positive_is_counted_rather_than_dropped(tmp_path):
    """A hit that is excluded without being counted is a hit silently dropped."""
    root = artifact(
        tmp_path,
        declared=declaration([retraction(rid="an-invented-rate",
                                         needles=[INVENTED_RATE])]),
        files={"results/throughput.json":
               '{\n  "rps": 63%s,\n  "p99": 63%s\n}\n'
               % (INVENTED_RATE, INVENTED_RATE)})
    result = run_check(root, report=tmp_path / "fp2.json")
    assert result.report["arms"]["FALSE-POSITIVE"] == 2, result.report
    assert "false-positive=2" in result.stdout, result.stdout


def test_a_needle_carrying_its_unit_does_not_match_the_longer_number(tmp_path):
    """The sweep's other half: `98.8%` does not match `6398.8` in the first place."""
    root = artifact(
        tmp_path,
        declared=declaration([retraction(rid="an-invented-rate",
                                         needles=[INVENTED_RATE + "%"])]),
        files={"results/throughput.json":
               '{\n  "rps": 63%s\n}\n' % INVENTED_RATE})
    result = run_check(root, report=tmp_path / "unit.json")
    assert result.exit_code == core.EXIT_PASS, result.stdout
    assert result.report["arms"]["LIVE"] == 0, result.report
    assert result.report["arms"]["FALSE-POSITIVE"] == 0, (
        "a unit-carrying needle should not have matched at all, so there is "
        "nothing to adjudicate: %r" % (result.report["arms"],))


def test_a_word_form_needle_without_its_context_terms_is_a_false_positive(
        tmp_path):
    """Ordinary English is not a retracted claim.

    The sweep found `almost nothing` twice in a sibling benchmark, both times
    about how many documents a query matches. Reported rather than tuned away,
    because a false positive you can see is worth more than a needle somebody
    quietly narrowed.
    """
    root = artifact(
        tmp_path,
        declared=declaration([retraction(rid="an-invented-claim",
                                         needles=["almost nothing"],
                                         context_terms=["cache", "hit rate"])]),
        files={"NOTES.md": "The filter matches almost nothing on this corpus.\n"})
    result = run_check(root, report=tmp_path / "word.json")
    assert result.exit_code == core.EXIT_PASS, result.stdout
    assert result.report["arms"]["FALSE-POSITIVE"] == 1, result.report


def test_a_word_form_needle_WITH_its_context_terms_is_live(tmp_path):
    """The other direction, or the rule above is just a way of never firing."""
    root = artifact(
        tmp_path,
        declared=declaration([retraction(rid="an-invented-claim",
                                         needles=["almost nothing"],
                                         context_terms=["cache", "hit rate"])]),
        files={"NOTES.md": "The cache returns almost nothing on this workload.\n"})
    result = run_check(root, report=tmp_path / "word2.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert result.report["arms"]["LIVE"] == 1, result.report


# ---------------------------------------------------------------------------
# FROZEN -- a record quoting what it withdrew is doing its job
# ---------------------------------------------------------------------------


def test_a_figure_quoted_beside_a_withdrawal_marker_is_frozen_not_live(tmp_path):
    """A retraction that cannot quote what it withdrew is not a retraction."""
    root = artifact(
        tmp_path,
        declared=declaration([retraction(needles=[INVENTED_RATIO])]),
        files={"results/RETRACTED.md":
               "## Retracted\n\nThe earlier %sx ratio is **withdrawn**: the run "
               "that produced it executed no guards.\n" % INVENTED_RATIO})
    result = run_check(root, report=tmp_path / "frozen.json")
    assert result.exit_code == core.EXIT_PASS, (
        "a figure quoted inside its own retraction was called live:\n%s"
        % result.stdout)
    assert result.report["arms"]["FROZEN"] >= 1, result.report
    assert result.report["arms"]["LIVE"] == 0, result.report


def test_the_declaration_is_scanned_like_every_other_file(tmp_path):
    """NO FILE IS EXCLUDED BY NAME, and the declaration is the tempting one.

    Its own hits land in FROZEN on the ordinary rule, because a withdrawal date
    sits beside each of them -- the correct answer arrived at by the classifier
    rather than bought with an exemption.
    """
    root = artifact(tmp_path,
                    declared=declaration([retraction(needles=[INVENTED_RATIO])]))
    result = run_check(root, report=tmp_path / "self.json")
    assert result.exit_code == core.EXIT_PASS, result.stdout
    carriers = {hit["file"] for hit in result.report["hits"]}
    assert "results/retractions.json" in carriers, (
        "the declaration was not scanned, so this check has an exclusion list "
        "after all: %r" % (sorted(carriers),))


def test_a_declared_frozen_region_freezes_a_hit_the_radius_cannot_reach(tmp_path):
    """A whole-document historical record does not fit inside a radius.

    MEASURED on a real artifact: a file whose title and opening paragraph say it
    is superseded carries its adjudication at the TOP and its figures thirty
    lines down, and the marker rule produced three findings against a document
    doing exactly what it was kept to do. The author declares the region instead
    -- the SAME paired anchor CHECK-01 already uses, written in the file where a
    reader can see it, never inferred from the file's name.
    """
    body = ("<!-- artifact:frozen:begin -->\n"
            + ("filler\n" * 40)
            + "The ratio was %sx.\n" % INVENTED_RATIO
            + ("filler\n" * 40)
            + "<!-- artifact:frozen:end -->\n")
    root = artifact(tmp_path,
                    declared=declaration([retraction(needles=[INVENTED_RATIO])]),
                    files={"SUPERSEDED.md": body})
    result = run_check(root, report=tmp_path / "region.json")
    assert result.exit_code == core.EXIT_PASS, result.stdout
    assert result.report["arms"]["LIVE"] == 0, result.report
    assert result.report["region_frozen"] == 1, result.report
    assert [row["path"] for row in result.report["region_files"]] \
        == ["SUPERSEDED.md"], result.report


def test_the_region_count_prints_and_names_its_files(tmp_path):
    """An adjudication nobody can count is an exclusion list with a better name."""
    body = ("<!-- artifact:frozen:begin -->\n"
            + ("filler\n" * 40)
            + "The ratio was %sx.\n" % INVENTED_RATIO
            + "<!-- artifact:frozen:end -->\n")
    root = artifact(tmp_path,
                    declared=declaration([retraction(needles=[INVENTED_RATIO])]),
                    files={"SUPERSEDED.md": body})
    result = run_check(root, report=tmp_path / "regionprint.json")
    assert "region=1 in 1 file(s)" in result.stdout, result.stdout


def test_an_UNCLOSED_frozen_region_freezes_nothing(tmp_path):
    """The loud direction. A stray begin marker must not swallow the document.

    Copied from CHECK-01's rule rather than re-decided: an unpaired region is
    ignored. The quiet failure -- freezing every live claim below a typo -- is
    the one that would make this check report clean over a real leak.
    """
    body = ("<!-- artifact:frozen:begin -->\n"
            + ("filler\n" * 40)
            + "The ratio was %sx.\n" % INVENTED_RATIO)
    root = artifact(tmp_path,
                    declared=declaration([retraction(needles=[INVENTED_RATIO])]),
                    files={"SUPERSEDED.md": body})
    result = run_check(root, report=tmp_path / "unpaired.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert result.report["arms"]["LIVE"] == 1, result.report
    assert result.report["region_frozen"] == 0, result.report


def test_the_region_predicate_is_the_SAME_one_CHECK_01_uses(tmp_path):
    """Two checks disagreeing about what a frozen region IS would be invisible.

    Not a code comparison -- a BEHAVIOURAL one, over the same text, because two
    implementations can read identically and diverge on an edge. The unpaired
    case is included deliberately: it is the edge the two would most plausibly
    disagree on.
    """
    check_01 = _load("check_01_for_region_parity", CHECKS_DIR / "check_01.py")
    samples = (
        "<!-- artifact:frozen:begin -->\na\nb\n<!-- artifact:frozen:end -->\n",
        "a\n<!-- artifact:frozen:begin -->\nb\n",
        "a\nb\nc\n",
        "<!--artifact:frozen:begin-->\nx\n<!--artifact:frozen:end-->\n",
    )
    for text in samples:
        assert check_16.frozen_lines(text) == check_01.frozen_lines(text), (
            "the two checks disagree about which lines a frozen region covers, "
            "for %r: %r vs %r"
            % (text, check_16.frozen_lines(text), check_01.frozen_lines(text)))
    assert check_16.FROZEN_ANCHOR == check_01.FROZEN_ANCHOR


def test_a_marker_outside_the_radius_does_not_freeze_a_live_line(tmp_path):
    """The radius is a real boundary, not decoration.

    A withdrawal marker two hundred lines away does not make a sentence on line
    one a record. If it did, one `retracted` anywhere in a long document would
    freeze the whole file.
    """
    body = ("The ratio is %sx.\n" % INVENTED_RATIO) + ("filler\n" * 200) + \
           "That figure was withdrawn.\n"
    root = artifact(tmp_path,
                    declared=declaration([retraction(needles=[INVENTED_RATIO])]),
                    files={"NOTES.md": body})
    result = run_check(root, report=tmp_path / "radius.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert result.report["arms"]["LIVE"] >= 1, result.report


def test_the_effective_radius_prints_so_a_widening_cannot_be_invisible(tmp_path):
    """A cue set adjusted until the count reads zero is measuring the adjuster."""
    body = ("The ratio is %sx.\n" % INVENTED_RATIO) + ("filler\n" * 30) + \
           "That figure was withdrawn.\n"
    root = artifact(tmp_path,
                    declared=declaration([retraction(needles=[INVENTED_RATIO])]),
                    files={"NOTES.md": body})

    tight = run_check(root, report=tmp_path / "tight.json")
    assert tight.exit_code == core.EXIT_FINDING, tight.stdout
    assert "radius=%d" % check_16.DEFAULT_RADIUS in tight.stdout, tight.stdout

    wide = run_check(root, report=tmp_path / "wide.json", extra=["--radius", "60"])
    assert wide.exit_code == core.EXIT_PASS, wide.stdout
    assert "radius=60" in wide.stdout, (
        "the OVERRIDDEN radius did not print, so a widening is invisible: %s"
        % wide.stdout)


# ---------------------------------------------------------------------------
# AN ARTIFACT THAT RETRACTED NOTHING
# ---------------------------------------------------------------------------


def test_an_empty_declaration_with_a_review_date_passes_over_a_real_population(
        tmp_path):
    """`retracted: []` is a dated, committed statement, not an absence."""
    root = artifact(tmp_path, declared=declaration([]))
    result = run_check(root, report=tmp_path / "empty.json")
    assert result.exit_code == core.EXIT_PASS, result.stdout
    assert result.report["checked"] > 0, (
        "the scan passed over zero files, which is the 0/0 pass this project "
        "refuses: %r" % result.report)
    assert result.report["retractions"] == 0, result.report
    assert result.report["needles"] == 0, result.report


def test_an_empty_declaration_with_NO_review_date_is_a_finding(tmp_path):
    """The free pass an empty list would otherwise buy.

    Without a review date, `{"retracted": []}` is indistinguishable from a file
    nobody read, and the check would hand out a clean verdict for shipping four
    characters.
    """
    root = artifact(tmp_path, declared=declaration([], reviewed_on=None))
    result = run_check(root, report=tmp_path / "undated.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert any("reviewed-on" in fid for fid in result.report["finding_ids"]), (
        result.report["finding_ids"])


def test_a_retraction_with_no_needles_is_a_finding(tmp_path):
    """An entry nothing hunts is decoration in a list that looks like evidence."""
    root = artifact(tmp_path,
                    declared=declaration([retraction(needles=[])]))
    result = run_check(root, report=tmp_path / "noneedles.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert any("no-needles" in fid for fid in result.report["finding_ids"]), (
        result.report["finding_ids"])


def test_a_retraction_with_no_reason_is_a_finding(tmp_path):
    """A retraction with no stated reason cannot be reviewed."""
    entry = retraction()
    entry.pop("why")
    root = artifact(tmp_path, declared=declaration([entry]))
    result = run_check(root, report=tmp_path / "noreason.json")
    assert result.exit_code == core.EXIT_FINDING, result.stdout
    assert any("no-reason" in fid for fid in result.report["finding_ids"]), (
        result.report["finding_ids"])


# ---------------------------------------------------------------------------
# THE POPULATION LINE
# ---------------------------------------------------------------------------


def test_the_population_line_carries_both_counts_and_the_needle_count(tmp_path):
    """Two numbers about two different things, and neither stands in for the other."""
    root = artifact(tmp_path,
                    declared=declaration([retraction(needles=[INVENTED_RATIO,
                                                              INVENTED_RATE])]))
    result = run_check(root, report=tmp_path / "pop.json")
    line = next(row for row in result.stdout.splitlines()
                if row.startswith("CHECK-16"))
    assert "checked=" in line and " of " in line, line
    assert "not-examined=" in line, line
    assert "retractions=1" in line, line
    assert "needles=2" in line, line
    assert core.BANNED_VERDICT not in line.lower(), line


def test_the_population_identity_closes(tmp_path):
    """checked + not-examined == listed, asserted by the caller as well as the core."""
    root = artifact(tmp_path, declared=declaration([]),
                    files={"results/raw/blob.bin": "not utf8 text\n"})
    result = run_check(root, report=tmp_path / "identity.json")
    report = result.report
    assert report["checked"] + report["not_examined"] == report["listed"], report
    assert len(report["not_examined_entries"]) == report["not_examined"], (
        "every not-examined input must be NAMED with its reason, not merely "
        "counted: %d entries for a count of %d"
        % (len(report["not_examined_entries"]), report["not_examined"]))
    for entry in report["not_examined_entries"]:
        assert entry.get("reason"), entry


def test_a_min_population_override_cannot_buy_a_pass_over_zero(tmp_path):
    """a design rule lowers a floor; it does not invent a population."""
    root = artifact(tmp_path, declared=None)
    result = run_check(root, report=tmp_path / "floor.json",
                       extra=["--min-population", "0"])
    assert result.exit_code == core.EXIT_DID_NOT_RUN, result.stdout


# ---------------------------------------------------------------------------
# THE COMMITTED FIXTURE AND THE ANTI-ROT PIN
# ---------------------------------------------------------------------------


def test_the_committed_fixture_reproduces_its_pinned_report(tmp_path):
    """a design rule's anti-rot comparison, over the STRUCTURED report and nothing prose."""
    root = conftest.broken_fixture(FIXTURE)
    expectation = json.loads(
        (Path(root) / EXPECTATION_FILE).read_text(encoding="utf-8"))

    result = run_check(root, report=tmp_path / "fixture.json")
    assert result.report is not None, result.stdout

    for field in PINNED_FIELDS:
        assert field in expectation, (
            "the expectation file does not pin %r, so this comparison is "
            "weaker than it reads" % field)
        assert result.report[field] == expectation[field], (
            "%s: report %r != pinned %r"
            % (field, result.report[field], expectation[field]))

    for field in PROSE_FIELDS:
        assert field not in expectation, (
            "the expectation pins %r, which is wording-sensitive: the first "
            "message improvement breaks the pin and the standard repair is to "
            "weaken it" % field)


def test_the_module_declares_an_id_inside_the_universe():
    assert check_16.CHECK_ID == "CHECK-16"
    assert check_16.CHECK_ID in contract.DECLARED_CHECK_IDS, (
        "a module whose id is outside the declared universe runs, reports, and "
        "is reconciled against nothing")
    assert isinstance(check_16.DEFAULT_FLOOR, int)


def test_the_module_quotes_no_needle_any_BUILT_ARTIFACT_declares():
    """THE EIGHTH INSTANCE OF A GUARD MATCHING ITS OWN DOCUMENTATION, pinned.

    This module is VENDORED into every artifact, so it is inside the population
    of its own scan. Its first draft quoted the real withdrawn hit rate the
    false-positive case is about, it shipped into an artifact that declares that
    figure, and the check reported a LIVE finding against the exact line of its
    own docstring that explains the rule. It is a defect whose whole life is
    between two runs, so nothing but a standing assertion catches the next one.

    THE POPULATION IS THE REAL ARTIFACTS, not a synthetic case: what matters is
    what those declarations actually contain, and that changes without this file
    being touched. If there are none to read, that is a REFUSAL rather than a
    pass -- a sweep over zero declarations agrees with everything.
    """
    root = Path(REPO_ROOT).parent
    declarations = sorted(root.glob("*/results/retractions.json"))
    assert declarations, (
        "no built artifact under %s carries results/retractions.json, so this "
        "assertion examined nothing. It is not a pass." % root)

    source = CHECK_16.read_text(encoding="utf-8")
    needles, carriers = [], []
    for path in declarations:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for entry in payload.get("retracted") or []:
            for needle in entry.get("needles") or []:
                text = needle if isinstance(needle, str) \
                    else str(needle.get("needle") or "")
                if not text.strip():
                    continue
                needles.append((path.parent.parent.name, text))
                if text.lower() in source.lower():
                    carriers.append((path.parent.parent.name, text))

    assert needles, "the declarations found declare no needles at all: %r" % (
        [str(p) for p in declarations],)
    assert not carriers, (
        "tools/checks/check_16.py quotes %d needle(s) a built artifact declares "
        "retracted, and this module is VENDORED into that artifact: %r"
        % (len(carriers), carriers))

    # THE LIVE CONTROL. A clean result is only a measurement if the search works.
    probe = needles[0][1]
    assert probe.lower() in (source + probe).lower(), (
        "the containment test cannot find a needle in a string that holds it, "
        "so the zero above is a property of the search")


def test_the_marker_set_is_declared_with_a_reason_beside_every_term():
    """Widening this list weakens the check, so every term carries its reason."""
    markers = check_16.FROZEN_MARKERS
    assert markers, "the marker set is empty, so nothing can ever be FROZEN"
    for term, why in markers:
        assert term and term == term.lower(), term
        assert why and len(why) > 10, (term, why)
