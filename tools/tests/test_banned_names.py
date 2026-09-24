"""the banned-spelling rule -- the banned-name lint: LIVE versus FROZEN versus DETECTOR.

THIS FILE CARRIES ZERO OCCURRENCES OF THE LITERAL IT TESTS, and that is
structural rather than tidy. Every fixture below assembles the path at run time
from a directory component and a filename component, exactly as
`tools/lint_banned_names.py` and `tools/conformance.py` do. A test module that
pasted the literal would seed hits into a file the lint scans, and the first
repair anyone reached for would be the exclusion list the whole design exists to
avoid.

WHY THERE IS NO `live == 0` ASSERTION OVER THE REAL REPOSITORY HERE, stated in
the open rather than left as an absence a reader has to notice. Measured on this
worktree, the tree carries LIVE and UNCLASSIFIED hits, and every one of them
sits in a file this plan does not own: the owner decision record and the two
generated question files derived from it, plus one diagram line in
`the project features document`. The sanctioned repair is an IN-PLACE
ADJUDICATION -- a short note beside the hit, inside its span -- and an earlier plan
owns the files. Asserting `live == 0` here would be asserting something false;
asserting it over a tmp_path tree instead, which the role tests below do, is the
assertion that actually discriminates. What IS asserted over the real tree is
the identity (the four role counts sum to the occurrence count), the exit
ladder, and that no hit in any `*-PLAN.md` or in `SKELETON.md` is LIVE -- the
six paths a directory-keyed rule would have got wrong.

THE SIBLING TRAP, which a green run cannot reveal: a test asserting the ban's
TEXT exists can be satisfied by one of the frozen quotations. So the positive
assertion below is paired with a negative one scoped to the LIVE role only, and
the trap is DEMONSTRATED by inserting a quotation-shaped hit and showing the
positive assertion does not move.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT
LINT = REPO_ROOT / "tools" / "lint_banned_names.py"
CONFORMANCE = REPO_ROOT / "tools" / "conformance.py"

# Every figure the planning documents quote for this literal's population. They
# were measured at different moments, they disagree with each other, and all of
# them are stale by construction -- the count rises with every document that
# discusses the ban. None may appear in the detector.
PLANNING_COUNTS = (15, 24, 30, 36, 43)
PLANNING_COUNT_PATTERN = r"\b(%s)\b" % "|".join(
    str(count) for count in PLANNING_COUNTS)


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


lint = _load("lint_banned_names_under_test", LINT)


# ---------------------------------------------------------------------------
# Fixture material -- every sentence assembles the path at run time
# ---------------------------------------------------------------------------

_DIRECTORY = "res" + "ults"
_FILENAME = "mani" + "fest" + "." + "json"


def banned():
    return _DIRECTORY + "/" + _FILENAME


# One sentence per role, each written the way the real repository writes it.
def sentence_live():
    return "The build script writes " + banned() + " into the artifact root.\n"


def sentence_live_with_particle():
    return ("The build script must not write " + banned()
            + " into the artifact root.\n")


def sentence_frozen():
    return ("the banned-spelling rule bans the name " + banned() + " outright, and records why.\n")


def sentence_frozen_quotation():
    """Quotation-shaped and NOTHING else: no prohibition word, no quoting word.

    Only the STRUCTURAL cue -- the path sitting inside a matched pair of quote
    characters -- can classify this one, which is exactly what the sibling-trap
    test needs it to exercise.
    """
    return "The decision quotes `" + banned() + "` verbatim.\n"


def sentence_detector():
    return ("A test creates " + banned()
            + " in a tmp_path artifact and asserts a non-zero exit.\n")


def sentence_bare_cell():
    return "| " + banned() + " |\n"


def tree(tmp_path, files, name="tree"):
    """Write `files` (relative -> text) under tmp_path/name. Returns (root, rels)."""
    root = Path(tmp_path) / name
    for relative, text in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    return root, sorted(files)


def scan(tmp_path, files, name="tree"):
    root, relatives = tree(tmp_path, files, name=name)
    return lint.scan(root, relative_paths=relatives)


def roles_at(report, path):
    return [hit.verdict.role for hit in report.hits if hit.path == path]


def run_cli(tmp_path, root, tag="cli"):
    out = Path(tmp_path) / ("out-" + tag)
    out.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, str(LINT), str(root),
            "--report", str(out / "report.json")]
    return conftest.run_cli(argv, cwd=REPO_ROOT, log_dir=out / "log")


# ---------------------------------------------------------------------------
# The detector carries no needle
# ---------------------------------------------------------------------------


def test_the_detector_and_the_runner_carry_zero_occurrences():
    """The gate whose own needle is assembled, over the two files that hunt it.

    A detector carrying its own needle reports itself on every run, and the
    obvious repair -- excluding the detector's own path -- is the exclusion list
    this design exists to avoid.
    """
    forward = banned()
    backward = _DIRECTORY + chr(92) + _FILENAME
    for path in (LINT, CONFORMANCE):
        text = path.read_text(encoding="utf-8")
        assert text.count(forward) == 0, path
        assert text.count(backward) == 0, path
        # And the same question asked through the lint's own compiled needle,
        # so a regex that had silently stopped matching would show up here.
        assert lint.BANNED_PATH_RE.search(text) is None, path


def test_the_lint_reads_its_own_source_like_any_other_file(tmp_path):
    """Scope check: the detector is NOT excluded from the scan.

    It contributes zero hits because it carries no literal, which is a different
    fact from being skipped -- and only one of the two survives a refactor.
    """
    result = run_cli(tmp_path, REPO_ROOT)
    scanned = json.loads(
        (Path(tmp_path) / "out-cli" / "report.json").read_text(encoding="utf-8"))
    assert scanned["scanned"] > 0
    assert result.exit_code in (lint.EXIT_PASS, lint.EXIT_FINDING,
                                lint.EXIT_DID_NOT_RUN)
    own = "tools/lint_banned_names.py"
    report = lint.scan(REPO_ROOT, relative_paths=[own])
    assert report.scanned == 1, report.as_dict()
    assert report.occurrences == 0


def test_the_tool_never_prints_the_literal_it_hunts(tmp_path):
    """Everything that LEAVES this process carries the placeholder.

    Without this, every RED transcript, every report file and every failing
    assertion message that quoted a span would seed the needle into a file this
    lint scans on the next run -- the tool reading its own output back to
    itself, with a fresh crop of hits nobody wrote by hand.
    """
    report = scan(tmp_path, {"a.md": sentence_live() + sentence_frozen()},
                  name="redaction")
    assert report.hits
    for hit in report.hits:
        assert banned() not in hit.span, hit.span
        assert lint.REDACTION in hit.span, hit.span

    text = []

    class Sink(object):
        def write(self, chunk):
            text.append(chunk)

    lint.print_report(report, stream=Sink())
    printed = "".join(text)
    # NOT ONCE, not even in the header: the header names the DECISION. A tool
    # that spelled its own needle on every run would put the literal into every
    # captured transcript and redirected run log in this repository.
    assert printed.count(banned()) == 0, printed
    assert "the banned-spelling rule" in printed, printed
    assert json.dumps(report.as_dict()).count(banned()) == 0

    # And the placeholder carries no word that any cue table would fire on.
    for _name, table in lint.CUE_TABLES:
        for cue, is_prefix, _reason in table:
            pattern = lint._cue_pattern(cue, is_prefix)
            assert pattern.search(lint.REDACTION) is None, (cue, lint.REDACTION)


def test_the_needle_is_tested_before_it_is_trusted():
    """A regex that silently stopped matching reports a confident ZERO."""
    assert lint.needle_self_test() is True
    assert lint.BANNED_PATH_RE.search("x " + banned() + " y") is not None
    assert lint.BANNED_PATH_RE.search(
        "x " + _DIRECTORY + chr(92) + _FILENAME + " y") is not None
    # And it does NOT match the legitimate expected-set file, which shares the
    # filename component and is named all over this repository.
    assert lint.BANNED_PATH_RE.search("tools/" + _FILENAME) is None


def test_a_population_below_the_effective_floor_is_did_not_run(tmp_path):
    """a design rule over this tool: the floor is declared in code, overridable, and the
    EFFECTIVE value is what prints. A verdict over a tree the scan did not
    really read is the 0/0 pass with a number beside it."""
    root, relatives = tree(tmp_path, {"a.md": sentence_frozen()}, name="floor")

    ok = lint.scan(root, relative_paths=relatives)
    assert ok.floor == lint.DEFAULT_FILE_FLOOR
    assert not ok.below_floor
    assert ok.code == lint.EXIT_PASS

    demoted = lint.scan(root, relative_paths=relatives, floor=100)
    assert demoted.scanned == 1
    assert demoted.below_floor
    assert demoted.code == lint.EXIT_DID_NOT_RUN

    text = []

    class Sink(object):
        def write(self, chunk):
            text.append(chunk)

    lint.print_report(demoted, stream=Sink())
    printed = "".join(text)
    assert "floor=100" in printed, printed
    assert "REFUSING" in printed, printed


def test_the_floor_overrides_a_live_finding_rather_than_hiding_it(tmp_path):
    """The population branch comes FIRST. A tree too small to be meaningful is
    DID-NOT-RUN even when a hit in it looks live -- and the hit is still
    printed, so nothing is hidden, only unranked."""
    root, relatives = tree(tmp_path, {"a.md": sentence_live()}, name="floor-live")
    demoted = lint.scan(root, relative_paths=relatives, floor=100)
    assert demoted.counts[lint.ROLE_LIVE] == 1
    assert demoted.code == lint.EXIT_DID_NOT_RUN


def test_no_planning_count_is_hard_coded_in_the_detector():
    """Every figure in the planning documents is stale by construction."""
    import re
    text = LINT.read_text(encoding="utf-8")
    hits = re.findall(PLANNING_COUNT_PATTERN, text)
    assert hits == [], hits


# ---------------------------------------------------------------------------
# The cue tables
# ---------------------------------------------------------------------------


def test_every_cue_carries_a_reason_and_exactly_one_is_a_prefix():
    seen = set()
    prefixes = []
    for name, table in lint.CUE_TABLES:
        assert table, name
        for cue, is_prefix, reason in table:
            assert cue and isinstance(cue, str), (name, cue)
            assert isinstance(reason, str) and reason.strip(), (name, cue)
            assert (name, cue) not in seen, (name, cue)
            seen.add((name, cue))
            if is_prefix:
                prefixes.append((name, cue))
    assert len(prefixes) == 1, prefixes


def test_cues_match_on_word_boundaries_and_not_as_substrings(tmp_path):
    """`ban` must not fire on `urban`; `not` must not fire on `nothing`.

    A substring reading of "the span contains a cue" classifies by accident,
    which is the failure this whole design exists to prevent. Both sentences
    below are LIVE: each carries an authoring verb and NO prohibition, and only
    a substring match could see one.
    """
    files = {
        "a.md": "The urban pipeline writes " + banned() + " nightly.\n",
        "b.md": "Nothing in the notes writes " + banned() + " here.\n",
    }
    report = scan(tmp_path, files)
    assert roles_at(report, "a.md") == [lint.ROLE_LIVE], report.as_dict()
    assert roles_at(report, "b.md") == [lint.ROLE_LIVE], report.as_dict()


def test_the_run_prints_which_cues_matched_nothing(tmp_path):
    """An unused cue is visible rather than accreting quietly."""
    report = scan(tmp_path, {"a.md": sentence_detector()})
    assert report.unused_cues, "every cue matched, which cannot be right here"
    assert any(name.startswith("AUTHORING_VERBS:") for name in report.unused_cues)
    text = []

    class Sink(object):
        def write(self, chunk):
            text.append(chunk)

    lint.print_report(report, stream=Sink())
    printed = "".join(text)
    assert "unused cues" in printed
    assert "live" in printed and "frozen" in printed
    assert "detector" in printed and "unclassified" in printed


# ---------------------------------------------------------------------------
# The three role tests -- the set a directory-keyed rule got wrong
# ---------------------------------------------------------------------------


def test_role_live_an_instruction_inside_a_templates_file(tmp_path):
    """(a) A sentence instructing an author to WRITE the path, in a copy of a
    templates/ file. A directory rule would have called this LIVE for the wrong
    reason; the point is that the SENTENCE decides."""
    root, relatives = tree(
        tmp_path, {"templates/README-SKELETON.md": sentence_live()}, name="a")
    report = lint.scan(root, relative_paths=relatives)
    assert report.counts[lint.ROLE_LIVE] == 1, report.as_dict()
    assert report.code == lint.EXIT_FINDING
    hit = report.hits[0]
    assert hit.verdict.arm == 2
    assert hit.verdict.cue.startswith("write")


def test_role_frozen_a_documenting_sentence_in_a_decision_record(tmp_path):
    """(b) A sentence quoting the ban, in a copy of a decision record."""
    root, relatives = tree(
        tmp_path, {"note-b.md": sentence_frozen()}, name="b")
    report = lint.scan(root, relative_paths=relatives)
    assert report.counts[lint.ROLE_FROZEN] == 1, report.as_dict()
    assert report.counts[lint.ROLE_LIVE] == 0
    assert report.code == lint.EXIT_PASS


def test_role_detector_a_needle_inside_a_plan_file(tmp_path):
    """(c) The literal as a detector needle in a copy of a *-PLAN.md.

    A two-verdict lint cannot express this case and would report the
    ENFORCEMENT of the ban as a violation of it.
    """
    root, relatives = tree(
        tmp_path, {"note-c.md": sentence_detector()}, name="c")
    report = lint.scan(root, relative_paths=relatives)
    assert report.counts[lint.ROLE_DETECTOR] == 1, report.as_dict()
    assert report.counts[lint.ROLE_LIVE] == 0
    assert report.code == lint.EXIT_PASS
    assert report.hits[0].verdict.arm == 1


def test_the_same_literal_in_the_same_file_classifies_two_ways(tmp_path):
    """The assertion that proves classification is keyed on ROLE, not on PATH."""
    files = {"note-c.md": sentence_detector() + sentence_live()}
    report = scan(tmp_path, files, name="two-ways")
    assert report.occurrences == 2, report.as_dict()
    assert roles_at(report, "note-c.md") == [lint.ROLE_DETECTOR,
                                                 lint.ROLE_LIVE]
    assert report.code == lint.EXIT_FINDING


# ---------------------------------------------------------------------------
# The particle flip and the stated default
# ---------------------------------------------------------------------------


def test_the_particle_flip_one_token_changes_the_verdict(tmp_path):
    """The SAME sentence, LIVE without `must not` and FROZEN with it.

    This is what makes arm 2 a decision procedure rather than a reading.
    """
    live = scan(tmp_path, {"a.md": sentence_live()}, name="flip-live")
    frozen = scan(tmp_path, {"a.md": sentence_live_with_particle()},
                  name="flip-frozen")
    assert roles_at(live, "a.md") == [lint.ROLE_LIVE], live.as_dict()
    assert roles_at(frozen, "a.md") == [lint.ROLE_FROZEN], frozen.as_dict()
    assert live.code == lint.EXIT_FINDING
    assert frozen.code == lint.EXIT_PASS


def test_a_bare_mention_with_no_cue_is_unclassified_and_is_printed(tmp_path):
    """Arm 4. Ambiguity becomes a COUNT the owner must close, not a silence."""
    root, relatives = tree(tmp_path, {"table.md": sentence_bare_cell()},
                           name="bare")
    report = lint.scan(root, relative_paths=relatives)
    assert report.counts[lint.ROLE_UNCLASSIFIED] == 1, report.as_dict()
    assert report.counts[lint.ROLE_LIVE] == 0
    assert report.code == lint.EXIT_DID_NOT_RUN

    hit = report.hits[0]
    assert hit.path == "table.md"
    assert hit.line == 1
    assert hit.col >= 0
    # The span is echoed with the needle REDACTED, so the tool never seeds its
    # own literal into a transcript, a report file or a test failure message.
    assert lint.REDACTION in hit.span, hit.span
    assert banned() not in hit.span, hit.span

    text = []

    class Sink(object):
        def write(self, chunk):
            text.append(chunk)

    lint.print_report(report, stream=Sink())
    printed = "".join(text)
    assert "table.md:1:" in printed, printed
    assert "UNCLASSIFIED" in printed, printed
    assert "span:" in printed, printed


def test_an_in_place_adjudication_closes_an_unclassified_hit(tmp_path):
    """The SANCTIONED repair, demonstrated: a note beside the hit, inside its
    span, supplies a cue. No exclusion list, no widened cue set."""
    before = scan(tmp_path, {"t.md": sentence_bare_cell()}, name="adj-before")
    assert before.counts[lint.ROLE_UNCLASSIFIED] == 1

    adjudicated = "| " + banned() + " -- superseded by the banned-spelling rule |\n"
    after = scan(tmp_path, {"t.md": adjudicated}, name="adj-after")
    assert after.counts[lint.ROLE_UNCLASSIFIED] == 0, after.as_dict()
    assert after.counts[lint.ROLE_FROZEN] == 1
    assert after.code == lint.EXIT_PASS


# ---------------------------------------------------------------------------
# Arm 0 -- the file arm, which no cue can override
# ---------------------------------------------------------------------------


def test_a_real_file_on_disk_is_live_whatever_the_sentence_says(tmp_path):
    files = {
        _DIRECTORY + "/" + _FILENAME: "{}\n",
        "notes.md": sentence_frozen(),
    }
    report = scan(tmp_path, files, name="arm-zero")
    assert report.real_files == [banned()], report.as_dict()
    # The prose hit carries a prohibition particle and would be FROZEN on cues
    # alone; arm 0 overrides it because the file is really there.
    assert roles_at(report, "notes.md") == [lint.ROLE_LIVE], report.as_dict()
    assert report.hits[0].verdict.arm == 0
    assert report.code == lint.EXIT_FINDING


# ---------------------------------------------------------------------------
# The exit ladder
# ---------------------------------------------------------------------------


def test_the_exit_ladder_on_all_four_rungs(tmp_path):
    live = scan(tmp_path, {"a.md": sentence_live()}, name="rung-live")
    assert live.counts[lint.ROLE_LIVE] > 0
    assert live.code == lint.EXIT_FINDING

    unclassified = scan(tmp_path, {"a.md": sentence_bare_cell()},
                        name="rung-unclassified")
    assert unclassified.counts[lint.ROLE_LIVE] == 0
    assert unclassified.counts[lint.ROLE_UNCLASSIFIED] > 0
    assert unclassified.code == lint.EXIT_DID_NOT_RUN

    clean = scan(tmp_path, {"a.md": sentence_frozen() + sentence_detector()},
                 name="rung-clean")
    assert clean.counts[lint.ROLE_FROZEN] > 0
    assert clean.counts[lint.ROLE_DETECTOR] > 0
    assert clean.counts[lint.ROLE_LIVE] == 0
    assert clean.counts[lint.ROLE_UNCLASSIFIED] == 0
    assert clean.code == lint.EXIT_PASS

    empty = lint.scan(Path(tmp_path) / "nothing-here", relative_paths=[])
    assert empty.scanned == 0
    assert empty.code == lint.EXIT_DID_NOT_RUN


def test_growth_in_the_harmless_roles_never_moves_the_exit(tmp_path):
    """The total is EXPECTED to rise with every document that discusses the ban."""
    small = scan(tmp_path, {"a.md": sentence_frozen() + sentence_detector()},
                 name="grow-small")
    big = scan(tmp_path,
               {"a.md": sentence_frozen() * 3 + sentence_detector() * 4},
               name="grow-big")
    assert small.code == lint.EXIT_PASS
    assert big.code == lint.EXIT_PASS
    assert big.counts[lint.ROLE_FROZEN] > small.counts[lint.ROLE_FROZEN]
    assert big.counts[lint.ROLE_DETECTOR] > small.counts[lint.ROLE_DETECTOR]
    assert big.counts[lint.ROLE_LIVE] == small.counts[lint.ROLE_LIVE] == 0
    assert big.counts[lint.ROLE_UNCLASSIFIED] == 0


def test_the_cli_returns_the_ladder_from_a_real_git_tree(tmp_path):
    """End to end, through git ls-files, with the CHILD's own exit code."""
    clean_src = Path(tmp_path) / "clean"
    (clean_src / "docs").mkdir(parents=True)
    (clean_src / "docs" / "record.md").write_text(
        sentence_frozen(), encoding="utf-8", newline="\n")
    clean = conftest.committed_tree(tmp_path, clean_src)

    result = run_cli(tmp_path, clean, tag="clean")
    assert result.exit_code == lint.EXIT_PASS, result.stdout
    assert "live 0" in result.stdout, result.stdout

    live_src = Path(tmp_path) / "live"
    (live_src / "docs").mkdir(parents=True)
    (live_src / "docs" / "record.md").write_text(
        sentence_frozen(), encoding="utf-8", newline="\n")
    (live_src / "docs" / "pipeline.md").write_text(
        sentence_live(), encoding="utf-8", newline="\n")
    dirty = run_cli(tmp_path, conftest.committed_tree(tmp_path, live_src),
                    tag="live")
    assert dirty.exit_code == lint.EXIT_FINDING, dirty.stdout
    assert "live 1" in dirty.stdout, dirty.stdout


# ---------------------------------------------------------------------------
# The sibling trap
# ---------------------------------------------------------------------------


def test_the_positive_assertion_is_not_satisfied_by_a_quotation(tmp_path):
    """A test asserting the ban's TEXT exists can be satisfied by a quotation.

    So: the positive assertion is `live == 0`, scoped to the LIVE role alone.
    Inserting a quotation-shaped hit must not move it -- and inserting a real
    instruction must, or the assertion is decoration.
    """
    base = {"doc.md": sentence_frozen()}
    first = scan(tmp_path, base, name="trap-1")
    assert first.counts[lint.ROLE_LIVE] == 0

    quoted = {"doc.md": sentence_frozen() + sentence_frozen_quotation()}
    second = scan(tmp_path, quoted, name="trap-2")
    assert second.counts[lint.ROLE_LIVE] == 0, second.as_dict()
    assert second.counts[lint.ROLE_FROZEN] == first.counts[lint.ROLE_FROZEN] + 1
    assert second.code == lint.EXIT_PASS

    real = {"doc.md": sentence_frozen() + sentence_frozen_quotation()
                      + sentence_live()}
    third = scan(tmp_path, real, name="trap-3")
    assert third.counts[lint.ROLE_LIVE] == 1, third.as_dict()
    assert third.code == lint.EXIT_FINDING


# ---------------------------------------------------------------------------
# Determinism, and the span
# ---------------------------------------------------------------------------


def test_classify_reads_only_its_arguments():
    span = "The build script writes the record into the artifact root"
    first = lint.classify("a.md", 1, 0, span)
    second = lint.classify("b/c/d.md", 999, 42, span)
    third = lint.classify("a.md", 1, 0, span)
    assert first.role == second.role == third.role
    assert first.arm == second.arm == third.arm
    assert first.cue == second.cue == third.cue


def test_the_span_is_not_cut_by_the_dot_inside_the_filename():
    text = "The build script writes " + banned() + " into the artifact root.\n"
    match = lint.BANNED_PATH_RE.search(text)
    span = lint.sentence_span(text, match.start(), match.end(), False)
    assert banned() in span, span
    assert "writes" in span, span
    assert span.endswith("artifact root"), span


# ---------------------------------------------------------------------------
# The real tree -- the identity, the two counts, and the six named paths
# ---------------------------------------------------------------------------


def test_the_repo_run_closes_its_own_identity(tmp_path):
    result = run_cli(tmp_path, REPO_ROOT, tag="repo")
    report = json.loads(
        (Path(tmp_path) / "out-repo" / "report.json").read_text(encoding="utf-8"))

    assert report["scanned"] >= 100, report["scanned"]
    assert report["occurrences"] > 0, (
        "zero hits over a tree known to carry them -- the needle stopped "
        "matching, which is the failure a count-free lint hides")

    total = sum(report["counts"][role] for role in lint.ROLES)
    assert total == report["occurrences"], report["counts"]

    # The exit code IS the ladder applied to the measured counts.
    counts = report["counts"]
    if counts["live"]:
        expected = lint.EXIT_FINDING
    elif counts["unclassified"]:
        expected = lint.EXIT_DID_NOT_RUN
    else:
        expected = lint.EXIT_PASS
    assert result.exit_code == expected, (result.exit_code, counts)

    for fragment in ("live ", "frozen ", "detector ", "unclassified ",
                     "occurrences", "scanned="):
        assert fragment in result.stdout, (fragment, result.stdout)


def test_the_occurrence_count_and_the_line_count_disagree(tmp_path):
    """Two hits on ONE line make two numbers, and both are printed.

    The discrepancy is SURFACED rather than reconciled away: a lint that
    printed one of them would be answering a question nobody asked.

    RE-KEYED by an earlier plan. The old form asserted `occurrences >
    lines_with_hits` over THIS REPOSITORY, which held because a generated HTML
    file here happens to carry several hits on two long lines. That is a fact
    about one working tree: an export carrying one hit on one line reported
    `1 > 1` and failed, over a population that simply does not contain the
    shape. The shape is now SEEDED, so the discrepancy is demonstrated in every
    tree, and the real tree is checked for the identity that must hold in all
    of them -- never for a number only one of them has.
    """
    doubled = sentence_frozen().rstrip("\n") + " " + banned() + "\n"
    seeded = scan(tmp_path, {"docs/RECORD.md": doubled})
    assert seeded.occurrences == 2, seeded.occurrences
    assert seeded.lines_with_hits == 1, seeded.lines_with_hits
    assert seeded.occurrences > seeded.lines_with_hits, (
        "two hits on one line did not produce two different numbers, so the "
        "lint is reconciling away the discrepancy it exists to surface")

    report = lint.scan(REPO_ROOT)
    print("this tree: occurrences=%d lines_with_hits=%d scanned=%d"
          % (report.occurrences, report.lines_with_hits, report.scanned))
    assert report.occurrences >= report.lines_with_hits, (
        "fewer occurrences than lines carrying them is arithmetically "
        "impossible: %d < %d" % (report.occurrences, report.lines_with_hits))
    assert (report.lines_with_hits > 0) == (report.occurrences > 0), (
        "one count is zero while the other is not: %d occurrence(s) over %d "
        "line(s)" % (report.occurrences, report.lines_with_hits))


def _plan_shaped(hits_or_names, key=lambda item: item):
    """The paths a DIRECTORY-KEYED rule would have got wrong: plans, skeletons."""
    selected = []
    for item in hits_or_names:
        name = key(item)
        if name.endswith("-PLAN.md") or name.rsplit("/", 1)[-1] == "SKELETON.md":
            selected.append(item)
    return selected


def test_no_hit_in_a_plan_file_or_the_skeleton_is_live(tmp_path):
    """The paths a directory-keyed rule would have classified as violations.

    RE-KEYED by an earlier plan. The old form required at least SIX such paths in
    the tree under test. Six is this repository's plan count at one moment --
    the docstring even said the assertion "has to keep meaning something after
    an earlier round re-homes eighteen more" -- and in a published export, where the
    planning tree is excluded by definition, the count is zero and the
    assertion read `0 >= 6`.

    The floor moves to a SEEDED tree that always carries the shapes, so the
    classification is demonstrated in every tree rather than only where the
    planning documents happen to live. The real tree is then checked over
    whatever population it has, with that population PRINTED -- which is the
    honest form of a zero: a count beside a verdict, not a silent pass.
    """
    seeded_files = {}
    for index in range(1, 7):
        seeded_files["plans/%02d-PLAN.md" % index] = sentence_frozen()
    seeded_files["skeletons/SKELETON.md"] = sentence_detector()
    seeded = scan(tmp_path, seeded_files)

    seeded_hits = _plan_shaped(seeded.hits, key=lambda hit: hit.path)
    seeded_paths = sorted({hit.path for hit in seeded_hits})
    assert len(seeded_paths) == 7, seeded_paths
    assert len(seeded_hits) >= len(seeded_paths)
    for hit in seeded_hits:
        assert hit.verdict.role in (lint.ROLE_FROZEN, lint.ROLE_DETECTOR), (
            "%s:%d classified %s over a SEEDED tree -- the rule is keyed to "
            "the directory rather than to the sentence. span: %s"
            % (hit.path, hit.line, hit.verdict.role, hit.span))

    report = lint.scan(REPO_ROOT)
    selected = _plan_shaped(report.hits, key=lambda hit: hit.path)
    paths = sorted({hit.path for hit in selected})
    print("this tree: %d plan-shaped path(s) carrying %d hit(s), of %d scanned"
          % (len(paths), len(selected), report.scanned))
    assert len(selected) >= len(paths)
    for hit in selected:
        assert hit.verdict.role in (lint.ROLE_FROZEN, lint.ROLE_DETECTOR), (
            "%s:%d classified %s -- a plan that documents or enforces the ban "
            "is not violating it. span: %s"
            % (hit.path, hit.line, hit.verdict.role, hit.span))
        assert hit.verdict.reason.strip(), hit.path
        assert hit.verdict.cue.strip(), hit.path


def test_the_scanned_set_really_contains_those_six_paths(tmp_path):
    """A `live 0` over a tree that never READ those files has discriminated
    nothing. The scan's population is asserted, not assumed.

    RE-KEYED by an earlier plan from "this tree holds at least six plan files" --
    which is a fact about one tree at one moment -- to the property that makes
    the original assertion worth making: THE SCAN'S POPULATION IS THE TRACKED
    SET, with nothing filtered out on the way. A lint that quietly dropped the
    plan-shaped paths would report a clean `live 0` in any tree, and only a
    comparison against git's own answer can tell that apart from a clean tree.
    """
    seeded_files = {"plans/frozen-PLAN.md": sentence_frozen(),
                    "skeletons/SKELETON.md": sentence_detector(),
                    "docs/NOTE.md": sentence_frozen()}
    root, relatives = tree(tmp_path, seeded_files, name="population")
    seeded = _plan_shaped(relatives)
    assert len(seeded) == 2, seeded

    listed = lint.tracked_files(REPO_ROOT)
    assert listed, "the scan's population is empty, so any verdict is vacuous"

    completed = subprocess.run(
        ["git", "ls-files"], cwd=str(REPO_ROOT), capture_output=True,
        text=True, encoding="utf-8", errors="replace", shell=False)
    assert completed.returncode == 0, completed.stderr
    tracked = [name for name in completed.stdout.splitlines() if name.strip()]

    assert sorted(listed) == sorted(tracked), (
        "the lint reads %d path(s); git tracks %d. A scan over a SUBSET of the "
        "tracked set reports a clean verdict about files it never opened."
        % (len(listed), len(tracked)))
    print("population: %d tracked path(s), %d of them plan-shaped"
          % (len(listed), len(_plan_shaped(listed))))
