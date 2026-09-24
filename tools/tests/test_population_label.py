"""The retired population label is gone from LIVE SOURCE, and the new one prints.

Written 2026-09-21 to close the fourth requirement the deferred record set for
this repair: *"a negative pin scoped tightly enough to exclude the QUOTATIONS"*.

WHY A BARE SWEEP FOR THE WORD CANNOT BE THAT PIN, AND THIS IS THE WHOLE DESIGN
------------------------------------------------------------------------------
The retired spelling is quoted, verbatim and correctly, in three kinds of place
that must NOT be repaired:

  * the deferred-items record, the conventions document and three phase
    summaries, which quote it in order to say what was retired -- a record that
    cannot quote what it withdrew is not a record;
  * ten committed RED transcripts, which are frozen captures of runs that
    happened and may never be edited to match a later rename;
  * `canonkit.BANNED_VERDICT`, which IS the detector's needle. The word has to
    exist somewhere or nothing can scan for it.

So the pin is scoped two ways at once. Its POPULATION is live source only --
`tools/` and `templates/`, the code this repository runs and vendors. Its NEEDLE
is the three SHAPES that reach a reader: a printed label `<word>=`, a keyword
argument `<word>=` in a call, and a `"<word>"` dict key. Ordinary English about
skipping, in a docstring or a comment, is not output and is not a hit.

AND THE INVERSE, WHICH IS THE HALF THAT USUALLY GETS LEFT OUT
-------------------------------------------------------------
A test asserting the OLD wording is GONE passes just as happily when its needle
is broken as when the tree is clean, so every negative here is paired with a
LIVE CONTROL that must FIRE. The project's own record of this rename names the
sibling failure too -- a test asserting the old wording is PRESENT goes on
passing against a frozen quotation of it -- and a sibling module's population
assertion was re-keyed in the same commit for exactly that reason.
"""

import ast
import importlib.util
import io
import re
import sys

import pytest

from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT

# The frozen core, loaded BY PATH under a bare module name. Never a dotted
# package import: test_repo_hygiene.py scans for one and the core raises on it.
_SPEC = importlib.util.spec_from_file_location(
    "frozen_core_for_label_pin", str(REPO_ROOT / "tools" / "canonkit.py"))
core = importlib.util.module_from_spec(_SPEC)
sys.modules["frozen_core_for_label_pin"] = core
_SPEC.loader.exec_module(core)

# The retired spelling, READ from the constant that declares it rather than
# typed here. A needle this module typed for itself would go stale silently the
# day the constant moved, and would also make this file a hit for its own scan.
RETIRED = core.BANNED_VERDICT

# What replaced it, in the two spellings that are correct in their own slot: a
# hyphen in the PRINTED label, an underscore in the PYTHON keyword.
LABEL = "not-examined"
KEYWORD = "not_examined"

# THE LIVE-SOURCE POPULATION. Deliberately not the tracked tree: the project's planning tree,
# `inherited/`, `red-transcripts/` and `_records/` are frozen records, and this
# scan would report every one of their legitimate quotations as a finding.
LIVE_ROOTS = ("tools", "templates")

# The one permitted carrier, NAMED rather than filtered. It is the declaration
# of the needle itself; a scan that cannot tolerate its own detector cannot be
# run at all. Named so the exemption is countable: an unexplained absence from a
# scan is an input dropped.
DETECTOR_SITE = "tools/canonkit.py"

# The three shapes that reach a reader. A comment or a docstring sentence using
# the word as ordinary English is not one of them.
SHAPES = (
    ("printed-label", re.compile(RETIRED + r"=%")),
    ("dict-key", re.compile(r'"' + RETIRED + r'"\s*:')),
    ("call-keyword", None),   # AST, below -- a regex cannot tell a call apart
)


def live_python_files():
    """Every .py file under the live roots, as (relative path, text)."""
    found = []
    for root in LIVE_ROOTS:
        base = REPO_ROOT / root
        assert base.is_dir(), "the live root %s does not exist" % base
        for path in sorted(base.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            found.append((rel, io.open(str(path), encoding="utf-8").read()))
    return found


def keyword_hits(text):
    """Line numbers where the retired name is used as a CALL KEYWORD.

    An AST question, because `x = 1` and `f(x=1)` are the same three characters
    to a regex and only the second is an argument a callee has to accept.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == RETIRED:
            hits.append(node.lineno)
        elif isinstance(node, ast.arg) and node.arg == RETIRED:
            hits.append(node.lineno)
    return sorted(set(hits))


def scan():
    """(findings, population). One pass, both numbers, no early return."""
    findings = []
    population = 0
    for rel, text in live_python_files():
        population += 1
        # NOTE THE ABSENCE OF AN EXEMPTION. DETECTOR_SITE is NAMED at the top of
        # this module as the one file permitted to hold the bare constant, and
        # it is still scanned here for all three shapes: the declaration
        # `BANNED_VERDICT = "<word>"` matches none of them, so no carve-out is
        # needed and none is taken. A printed label or a report key in that file
        # would be a finding like anywhere else, which is the correct answer.
        for lineno, line in enumerate(text.splitlines(), 1):
            for name, pattern in SHAPES:
                if pattern is None:
                    continue
                if pattern.search(line):
                    findings.append((rel, lineno, name, line.strip()[:120]))
        for lineno in keyword_hits(text):
            findings.append((rel, lineno, "call-keyword", ""))
    return findings, population


# ---------------------------------------------------------------------------
# The negatives, each with its own live control
# ---------------------------------------------------------------------------


def test_the_retired_population_label_is_gone_from_live_source():
    """No live module prints it, keys a report by it, or passes it as a keyword."""
    findings, population = scan()
    assert population >= 20, (
        "the scan examined %d file(s), which is fewer than this repository has "
        "under %s -- a zero-population sweep reports a clean tree it never read"
        % (population, list(LIVE_ROOTS)))
    assert not findings, (
        "%d live-source occurrence(s) of the retired population label %r:\n%s"
        % (len(findings), RETIRED,
           "\n".join("  %s:%d  %s  %s" % row for row in findings)))


def test_the_needle_fires_on_a_tree_that_carries_the_retired_label(tmp_path):
    """THE LIVE CONTROL. A clean result is only a measurement if the scan works.

    Each of the three shapes is written into a synthetic module and the scan's
    own predicates are pointed at it. All three must fire; a shape that cannot
    be detected is a shape the negative above is blind to, and the negative
    would report CLEAN over it.
    """
    lines = [
        'LABEL = "found=%d ' + RETIRED + '=%d"',
        'REPORT = {"' + RETIRED + '": 3}',
        "report(check_id, " + RETIRED + "=3)",
    ]
    text = "\n".join(lines) + "\n"

    fired = set()
    for lineno, line in enumerate(text.splitlines(), 1):
        for name, pattern in SHAPES:
            if pattern is not None and pattern.search(line):
                fired.add(name)
    if keyword_hits(text):
        fired.add("call-keyword")

    assert fired == {name for name, _ in SHAPES}, (
        "the scan detected %s but not %s; a shape it cannot see is a shape the "
        "negative test is blind to"
        % (sorted(fired), sorted({n for n, _ in SHAPES} - fired)))


def test_the_core_prints_the_new_label_and_accepts_the_new_keyword(capsys):
    """THE POSITIVE HALF, by RUNNING the core rather than by reading it."""
    verdict = core.report("CHECK-99", True, 0, 3, 1, not_examined=2, listed=5)
    out = capsys.readouterr().out

    assert verdict == core.VERDICT_PASS, out
    assert (LABEL + "=2") in out, (
        "the core's population line does not carry %r: %s" % (LABEL + "=2", out))
    assert "checked=3 of 5" in out, out
    assert RETIRED not in out.lower(), (
        "the core's own line still carries the retired spelling: %s" % out)


def test_the_core_rejects_the_retired_keyword():
    """The rename is a REAL rename, not an alias beside the old name.

    An alias would keep every existing caller green and would let the next
    author reach for the retired spelling and get a working call, which is how a
    retired name comes back one module at a time.
    """
    with pytest.raises(TypeError) as excinfo:
        core.report("CHECK-99", True, 0, 3, 1, **{RETIRED: 2})
    assert RETIRED in str(excinfo.value), str(excinfo.value)


def test_the_frozen_records_still_quote_it_and_are_not_a_finding():
    """The inverse control: the QUOTATIONS are still there, and still excluded.

    If this ever reads zero, either the records were edited -- which would
    destroy the account of what was retired -- or the scope above silently
    widened to cover them, which would make the negative test red for the right
    word in the wrong place.
    """
    quoted = 0
    carriers = []
    for root in ("red-transcripts",):
        base = REPO_ROOT / root
        assert base.is_dir(), base
        for path in sorted(base.rglob("*.txt")):
            text = io.open(str(path), encoding="utf-8").read()
            hits = text.lower().count(RETIRED)
            if hits:
                quoted += hits
                carriers.append((path.name, hits))

    assert quoted > 0, (
        "no frozen transcript quotes %r any more. Either they were edited to "
        "match the rename -- which is exactly what a frozen capture may not be "
        "-- or this control is looking in the wrong place." % RETIRED)

    live = {rel for rel, _, _, _ in scan()[0]}
    assert not live, (
        "the live-source scan is reporting %d finding(s) while the frozen "
        "quotations are what it is meant to leave alone: %s" % (len(live), live))
