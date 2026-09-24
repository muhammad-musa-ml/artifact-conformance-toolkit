"""the banned-spelling rule -- the repo-wide lint for the banned results-record spelling.

    python lint_banned_names.py [ROOT] [--report FILE]

the banned-spelling rule bans one spelling of the results record outright. `conformance.py` already
FAILS on a real file at that path inside an artifact; this is the other half --
the repo-wide needle the banned-spelling rule says an earlier round's eighteen-plan re-homing sweep must have,
because a name that survives in PROSE gets inherited by the next plan that reads
it.

THE PROBLEM THIS TOOL EXISTS TO SOLVE, AND IT IS NOT "FIND THE STRING"
=======================================================================
The literal is already in this repository many times over, and almost every one
of those occurrences is the DECISION RECORD THAT CREATES THE BAN. A lint written
as "FAIL on the literal in any plan or doc" is red on day one, on its own
charter. The two repairs a maintainer reaches for both destroy it:

  * WEAKEN THE RULE -- and the ban stops being enforceable at all.
  * ADD AN EXCLUSION LIST -- and it grows every time anyone documents the ban.
    A list that grows each time it is run is the warning sign, not the fix.

A third repair looks better and is the same mistake in better clothes: key the
classification on the DIRECTORY (live in `templates/`, `tools/` or any
`*-PLAN.md`; frozen everywhere else). Measured against this tree, that rule
classifies this file, `tools/conformance.py`, and a dozen plan lines that
INSTRUCT the ban's enforcement as violations of the ban they enforce.

And the population GROWS. Re-derive it with this tool rather than quoting any
figure: it rose substantially during one planning pass, entirely through
documents discussing the ban, and the plan that specified this tool added to it
again. Any rule keyed on a static COUNT is obsolete on the next commit. So:

    CLASSIFY BY THE ROLE OF THE SENTENCE, with an ORDERED CUE PROCEDURE, a
    STATED DEFAULT, and all four counts printed.

THE FOUR ROLES
===============
  DETECTOR   the literal is a needle a detector matches on, the payload of a
             deliberately-broken fixture, or the subject of a test or an
             acceptance criterion that creates or greps the path in order to
             prove it is CAUGHT. Counted, printed, never a finding. "A test
             creates the banned path in a tmp_path artifact and asserts a
             non-zero exit" is the ban being ENFORCED, not violated.
  FROZEN     a document quoting, naming or describing the ban, the superseded
             name, or the decision that created it, in order to EXPLAIN it.
             Counted, printed, never a finding.
  LIVE       a finding. Either a real FILE at that path on disk, or prose that
             INSTRUCTS an author to write, emit, read or consume that path as a
             real artifact output.
  UNCLASSIFIED  the DEFAULT, and it is not a role. A hit no cue describes is
             printed with its span, counted, and exits non-zero.

WHY THE DEFAULT IS UNCLASSIFIED AND NOT ONE OF THE THREE
=========================================================
This is the load-bearing part of the procedure.

  Defaulting to FROZEN would make every hit the cue lists fail to describe
  vanish into a count nobody reads, and the LIVE arm would shrink to the
  file-exists check `conformance.py` already performs inside an artifact --
  which is precisely the needle the banned-spelling rule says the eighteen-plan sweep must have and
  would not need this tool for.

  Defaulting to LIVE would make the lint red on day one and invite the exclusion
  list this design exists to avoid.

UNCLASSIFIED is neither: ambiguity becomes a COUNT the owner must close, one hit
at a time, and a hit that nobody has adjudicated cannot masquerade as a clean
tree.

HOW AN UNCLASSIFIED HIT IS CLOSED, AND HOW IT IS NOT
=====================================================
SANCTIONED: an IN-PLACE ADJUDICATION. The owner adds a short note BESIDE the hit
-- inside its span, which means on its own line -- that supplies a cue, making
the classification a property of the TEXT rather than of a list held somewhere
else.

NOT SANCTIONED: widening a cue set to sweep up an inconvenient hit, and not an
exclusion list. Both move the ambiguity somewhere it stops being counted.

THIS FILE CARRIES ZERO OCCURRENCES OF THE LITERAL IT HUNTS
===========================================================
The needle is ASSEMBLED AT RUN TIME from a directory component and a filename
component held as separate strings. This is not fastidiousness. A detector that
carried its own needle would report ITSELF on every run, and the obvious repair
-- excluding the detector's own path -- is exactly the exclusion list this design
exists to avoid. It also makes a grep over this file's source a usable gate,
which the test suite relies on. `tools/conformance.py` assembles its own needle
for the same reason.

The measured history behind that rule, all of it from this phase: a fail-closed
hook check matched the `exit 0` inside its own explanatory COMMENT; five guards
shipped that could not discriminate, four of which matched their own
documentation; a RED transcript failed its own gate because it pasted the grep
pattern it was documenting.

THE SPAN
=========
A hit's SENTENCE SPAN is the text between the nearest span terminator before it
and the nearest after it, where a terminator is `.`, `!`, `?`, a newline, or a
markdown table-cell pipe. The search starts OUTSIDE the match, so the `.` inside
the filename is not a terminator for its own hit. In a source file the span is
additionally capped at the physical line -- redundant under the newline rule
above, implemented anyway and said out loud rather than silently dropped.

All cue matching is case-insensitive, happens over that span and nowhere else,
and the span is echoed in every reported hit so any decision is reproducible by
hand.

CUES MATCH ON WORD BOUNDARIES, NOT AS SUBSTRINGS
=================================================
A substring reading of "the span contains `ban`" fires on `urban` and
`bandwidth`; of `not` on `note`, `nothing` and `cannot`; of `read` on `already`
and `thread`. A cue set that matched those would classify by accident, which is
the failure this whole design is about. Every cue is matched with word
boundaries, multi-word cues tolerate any run of whitespace between their words,
and the ONE prefix cue is declared as a prefix in its own table rather than
inferred.

EXIT CODES
===========
    0  live 0 and unclassified 0
    1  live > 0 -- the ban is being violated
    2  live 0 with unclassified > 0, or zero files scanned. A DID-NOT-RUN:
       under a design rule a check that could not look is never a pass.

A non-zero FROZEN or DETECTOR count NEVER affects the exit, and growth in either
is explicitly NOT a finding. The total is expected to rise with every document
that discusses the ban -- including this one.

NO COUNT IS HARD-CODED ANYWHERE IN THIS FILE. Both the occurrence count and the
line count are computed at run time and printed as SEPARATE numbers, because a
generated HTML file in this repository holds several occurrences on two long
lines and the two figures genuinely disagree. The discrepancy is surfaced rather
than reconciled away.

Stdlib only. ASCII only.
"""

import argparse
import json
import os
import re
import subprocess
import sys

# ---------------------------------------------------------------------------
# The needle, assembled at run time. See the docstring.
# ---------------------------------------------------------------------------

_DIRECTORY_COMPONENT = "res" + "ults"
_FILENAME_COMPONENT = "mani" + "fest" + "." + "json"

# Both separators. A document written on this platform may spell the path with a
# backslash, and a needle that only knew about the forward slash would report a
# confident zero over prose that carries the name.
BANNED_PATH_RE = re.compile(
    re.escape(_DIRECTORY_COMPONENT) + r"[/\\]" + re.escape(_FILENAME_COMPONENT))


def banned_relative_path():
    """The banned path, joined at call time. Never a module-level literal."""
    return _DIRECTORY_COMPONENT + "/" + _FILENAME_COMPONENT


# THE TOOL NEVER PRINTS THE LITERAL INTO A SPAN ECHO, and that is structural.
# Every span this tool reports would otherwise carry the needle into the RED
# transcript, the report file and the test output that quotes them -- and this
# lint would then be reading its own output back to itself on the next run, with
# a fresh crop of hits to classify in files nobody wrote by hand. tools/
# conformance.py records the same reasoning for its own PASS note.
#
# Nothing is lost: there is exactly ONE path this tool looks for, it is named in
# the header line of every run, and the sentence around it -- the thing an
# operator actually needs in order to adjudicate -- is echoed intact.
#
# The placeholder deliberately contains no word that appears in any cue table,
# so a redacted span can never acquire a cue it did not have.
REDACTION = "<redacted-path>"


def redact(text):
    """Every occurrence of the needle replaced by the placeholder."""
    return BANNED_PATH_RE.sub(REDACTION, text)


ROLE_DETECTOR = "detector"
ROLE_FROZEN = "frozen"
ROLE_LIVE = "live"
ROLE_UNCLASSIFIED = "unclassified"

ROLES = (ROLE_LIVE, ROLE_FROZEN, ROLE_DETECTOR, ROLE_UNCLASSIFIED)
FINDING_ROLES = (ROLE_LIVE, ROLE_UNCLASSIFIED)

EXIT_PASS = 0
EXIT_FINDING = 1
EXIT_DID_NOT_RUN = 2

# a design rule, applied to this tool: the floor is DECLARED IN CODE, overridable on the
# command line, and the EFFECTIVE floor is what prints. One file is the smallest
# population over which a search means anything; zero is DID-NOT-RUN by a design rule.
#
# The floor is deliberately NOT sized for this repository. A tool that refused
# any tree smaller than this checkout could not be pointed at a single file, and
# the caller who needs a bigger floor is the one who knows how big -- which is
# what `--min-files` is for and why the effective value prints on every run. The
# suite's repo-wide assertion passes a floor two orders of magnitude above this
# one, so a scan that silently saw four files fails loudly there.
DEFAULT_FILE_FLOOR = 1


def needle_self_test():
    """The needle still matches a path assembled from the same parts.

    Three lines, and they close the failure mode a count-free lint cannot see:
    a regex that has silently stopped matching reports a confident ZERO over a
    tree full of hits, and every downstream number agrees with it. A negative is
    only as strong as its pattern, so the pattern is tested before it is
    trusted.
    """
    probe = "x " + banned_relative_path() + " y"
    if BANNED_PATH_RE.search(probe) is None:
        raise RuntimeError(
            "the compiled needle does not match a path assembled from its own "
            "parts. Every count this tool prints would be a confident zero.")
    backslash_probe = ("x " + _DIRECTORY_COMPONENT + chr(92)
                       + _FILENAME_COMPONENT + " y")
    if BANNED_PATH_RE.search(backslash_probe) is None:
        raise RuntimeError(
            "the compiled needle does not match the backslash spelling, so any "
            "document written on this platform would read as clean.")
    return True

SPAN_TERMINATORS = frozenset(".!?\n|")
QUOTE_CHARACTERS = "`\"'"

# Files whose span is additionally capped at the physical line. Redundant under
# the newline terminator; kept because the rule says so.
SOURCE_SUFFIXES = (".py", ".json", ".html", ".sh", ".toml", ".cfg", ".txt",
                   ".yml", ".yaml", ".ini")

MAX_SPAN_ECHO = 300
MAX_LISTED = 200

# ---------------------------------------------------------------------------
# The cue tables. One line of reason per cue, committed in the module.
# A cue that matches nothing is PRINTED by every run, so an unused cue is
# visible rather than accreting quietly.
# ---------------------------------------------------------------------------

# (cue, is_prefix, reason)
DETECTOR_CUES = (
    ("assert", False, "an assertion about the path is the ban being enforced"),
    ("asserts", False, "same, third person"),
    ("expect", False, "an expectation about the path, not a use of it"),
    ("a test", False, "the sentence is describing a test"),
    ("tests that", False, "same, in the plural"),
    ("fixture", False, "a deliberately-broken payload exists to be caught"),
    ("needle", False, "the path is the thing a search looks for"),
    ("grep", False, "the path is a search pattern"),
    ("lint", False, "the sentence is about this tool or one like it"),
    ("detector", False, "the sentence is about the mechanism, not the output"),
    ("classif", True, "classify / classifies / classification -- this tool's "
                      "own vocabulary. The ONE prefix cue"),
    ("tmp_path", False, "a hermetic test tree, never a shipped artifact"),
    ("acceptance criterion", False, "a criterion naming the path is enforcing it"),
    ("is caught", False, "the sentence states the outcome of a detection"),
    ("is reported", False, "same"),
    ("exits 2", False, "an exit-code expectation is a detector's contract"),
    ("non-zero exit", False, "same"),
)

AUTHORING_VERBS = (
    ("write", False, "an instruction to produce the file"),
    ("writes", False, "same, third person"),
    ("written", False, "same, passive"),
    ("writing", False, "same, progressive"),
    ("emit", False, "a tool producing the file as output"),
    ("emits", False, "same, third person"),
    ("produce", False, "same"),
    ("produces", False, "same, third person"),
    ("output", False, "the path named as a real output"),
    ("outputs", False, "same, plural"),
    ("read", False, "a tool consuming the file keeps the second name alive"),
    ("reads", False, "same, third person"),
    ("load", False, "same"),
    ("loads", False, "same, third person"),
    ("consume", False, "same"),
    ("consumes", False, "same, third person"),
    ("save", False, "same, producing side"),
    ("saves", False, "same, third person"),
    ("generate", False, "same"),
    ("generates", False, "same, third person"),
)

PROHIBITION_PARTICLES = (
    ("not", False, "a negation somewhere in the sentence"),
    ("never", False, "same, absolute"),
    ("no longer", False, "the name is being retired"),
    ("banned", False, "the sentence states the ban"),
    ("ban", False, "same, as a noun or a bare verb"),
    ("bans", False, "same, third person"),
    ("forbidden", False, "same"),
    ("prohibited", False, "same"),
    ("must not", False, "an explicit prohibition"),
    ("refuses", False, "a tool refusing the path is enforcing the ban"),
    ("rejects", False, "same"),
    ("instead of", False, "the sentence is contrasting two names"),
    ("rather than", False, "same"),
    ("superseded", False, "the in-place adjudication this tool sanctions"),
    ("the banned-spelling rule", False, "the decision id itself"),
)

QUOTING_CUES = (
    ("formerly", False, "the sentence is historical"),
    ("used to", False, "same"),
    ("the old name", False, "same, explicit"),
    ("historical", False, "same"),
    ("records", False, "the sentence is describing a record"),
    ("documents", False, "same, as a verb"),
    ("explains", False, "same"),
)

CUE_TABLES = (
    ("DETECTOR_CUES", DETECTOR_CUES),
    ("AUTHORING_VERBS", AUTHORING_VERBS),
    ("PROHIBITION_PARTICLES", PROHIBITION_PARTICLES),
    ("QUOTING_CUES", QUOTING_CUES),
)

# The quoting arm's one STRUCTURAL cue, which is not a word and so cannot live in
# a table above: the path sits immediately between a matched pair of quote
# characters. Backticks count -- in markdown they ARE the quoting mechanism.
CUE_QUOTED = "quoted:the path sits inside a matched pair of quote characters"

# Arm 1's one structural cue: the hit sits inside a string expression that is
# concatenated from parts, which is how a detector carries a needle without
# carrying the literal.
CUE_ASSEMBLED = "assembled:the hit sits inside a concatenated string expression"
ASSEMBLED_RE = re.compile(r"[\"']\s*\+|\+\s*[\"']|\.join\(")

# Arm 0's cue.
CUE_REAL_FILE = "file:a real file exists at that path on disk"


def _cue_pattern(cue, is_prefix):
    """Word-boundary regex for one cue. Multi-word cues tolerate any whitespace."""
    words = cue.split()
    body = r"\s+".join(re.escape(word) for word in words)
    prefix = r"\b" if cue[0].isalnum() or cue[0] == "_" else ""
    if is_prefix:
        suffix = ""
    else:
        last = cue[-1]
        suffix = r"\b" if last.isalnum() or last == "_" else ""
    return re.compile(prefix + body + suffix, re.I)


_COMPILED = {}
for _name, _table in CUE_TABLES:
    for _cue, _is_prefix, _reason in _table:
        _COMPILED[(_name, _cue)] = _cue_pattern(_cue, _is_prefix)


def matching_cues(table_name, table, span):
    """Every cue in `table` the span contains, as (cue, reason) pairs."""
    hits = []
    for cue, _is_prefix, reason in table:
        if _COMPILED[(table_name, cue)].search(span):
            hits.append((cue, reason))
    return hits


# ---------------------------------------------------------------------------
# The span
# ---------------------------------------------------------------------------


def sentence_span(text, start, end, cap_to_line):
    """The span for a hit at [start, end).

    The backward scan begins at `start` and the forward scan at `end`, so the
    `.` inside the filename is never a terminator for its own hit -- the single
    most obvious way this function could quietly cut every span in half.
    """
    left = start
    while left > 0 and text[left - 1] not in SPAN_TERMINATORS:
        left -= 1
    right = end
    while right < len(text) and text[right] not in SPAN_TERMINATORS:
        right += 1
    if cap_to_line:
        newline_before = text.rfind("\n", 0, start)
        newline_after = text.find("\n", end)
        left = max(left, newline_before + 1)
        right = min(right, newline_after if newline_after != -1 else len(text))
    return text[left:right]


def is_quoted(text, start, end):
    """The path sits immediately between a matched pair of quote characters."""
    if start == 0 or end >= len(text):
        return False
    before = text[start - 1]
    after = text[end]
    return before in QUOTE_CHARACTERS and before == after


def line_and_column(text, offset):
    line = text.count("\n", 0, offset) + 1
    column = offset - (text.rfind("\n", 0, offset) + 1)
    return line, column


# ---------------------------------------------------------------------------
# classify() -- the ordered procedure
# ---------------------------------------------------------------------------


class Verdict(object):
    """One hit's role, the ARM that decided it and the CUE that fired."""

    def __init__(self, role, arm, cue, reason):
        self.role = role
        self.arm = arm
        self.cue = cue
        self.reason = reason

    def as_dict(self):
        return {"role": self.role, "arm": self.arm, "cue": self.cue,
                "reason": self.reason}

    def __repr__(self):
        return "Verdict(%s, arm=%s, cue=%r)" % (self.role, self.arm, self.cue)


def _structural(marker):
    """Split a `cue:reason` structural marker into its two halves."""
    cue, reason = marker.split(":", 1)
    return cue, reason


def classify(path, line, col, context, quoted=False, real_file=False):
    """The ordered cue procedure. Returns a Verdict. The FIRST arm to match wins.

    The arms, in order, and each one's job:

      0  THE FILE ARM. Mechanical, unconditional, evaluated first. A real file
         exists at that path. NO cue in any arm below can override it -- a file
         that is really there is not made hypothetical by the sentence around it.
      1  DETECTOR. The span supplies a needle, a fixture payload or a test
         assertion, or the hit sits inside a string expression concatenated from
         parts. This arm comes BEFORE the live arm on purpose: "a test asserts
         the tool WRITES this path and is caught" carries an authoring verb, and
         an ordering that let arm 2 see it first would report the enforcement of
         the ban as a violation of it.
      2  LIVE. An authoring verb with NO prohibition particle anywhere in the
         span. One `must not` flips the verdict, which is what makes this a
         decision rather than a reading.
      3  FROZEN. A prohibition particle, a quoting word, or -- structurally --
         the path sitting inside a matched pair of quote characters. Backticks
         count: in markdown they ARE the quoting mechanism.
      4  UNCLASSIFIED. The stated default, and not a role.

    Reads ONLY its arguments and the committed cue tables. No filesystem access
    (arm 0's answer arrives as `real_file`), no clock, no environment, so the
    same input always yields the same verdict.
    """
    span = context or ""

    # -- Arm 0 ------------------------------------------------------------
    if real_file:
        cue, reason = _structural(CUE_REAL_FILE)
        return Verdict(ROLE_LIVE, 0, cue, reason)

    # -- Arm 1 ------------------------------------------------------------
    detector = matching_cues("DETECTOR_CUES", DETECTOR_CUES, span)
    if detector:
        cue, reason = detector[0]
        return Verdict(ROLE_DETECTOR, 1, cue, reason)
    if ASSEMBLED_RE.search(span):
        cue, reason = _structural(CUE_ASSEMBLED)
        return Verdict(ROLE_DETECTOR, 1, cue, reason)

    # -- Arm 2 ------------------------------------------------------------
    verbs = matching_cues("AUTHORING_VERBS", AUTHORING_VERBS, span)
    particles = matching_cues("PROHIBITION_PARTICLES", PROHIBITION_PARTICLES, span)
    if verbs and not particles:
        cue, reason = verbs[0]
        return Verdict(ROLE_LIVE, 2, cue, reason)

    # -- Arm 3 ------------------------------------------------------------
    if particles:
        cue, reason = particles[0]
        return Verdict(ROLE_FROZEN, 3, cue, reason)
    quoting = matching_cues("QUOTING_CUES", QUOTING_CUES, span)
    if quoting:
        cue, reason = quoting[0]
        return Verdict(ROLE_FROZEN, 3, cue, reason)
    if quoted:
        cue, reason = _structural(CUE_QUOTED)
        return Verdict(ROLE_FROZEN, 3, cue, reason)

    # -- Arm 4 ------------------------------------------------------------
    return Verdict(
        ROLE_UNCLASSIFIED, 4, "<none>",
        "no cue in any arm describes this span. The sanctioned repair is an "
        "IN-PLACE ADJUDICATION: a short note beside the hit, on its own line, "
        "that supplies a cue. Widening a cue set to sweep this up is not "
        "sanctioned, and neither is an exclusion list.")


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


class Hit(object):
    """One occurrence. `span` is stored REDACTED -- see REDACTION above.

    The classification ran over the RAW span; only what leaves this process
    carries the placeholder, so no cue decision is affected by the redaction.
    """

    def __init__(self, path, line, col, span, separator, verdict):
        self.path = path
        self.line = line
        self.col = col
        self.span = redact(span)
        self.separator = separator
        self.verdict = verdict

    def as_dict(self):
        record = {"path": self.path, "line": self.line, "column": self.col,
                  "span": self.span[:MAX_SPAN_ECHO],
                  "separator": self.separator}
        record.update(self.verdict.as_dict())
        return record


def repo_root_of(start):
    """The root of the checkout this file is running from."""
    return os.path.dirname(os.path.dirname(os.path.abspath(start)))


def tracked_files(root):
    """Every tracked path, from git. The scan's POPULATION, and its SCOPE.

    Stated rather than implied: this lint sees what git tracks. An untracked
    working file is outside it, and so is anything in .gitignore. A negative
    result from this tool is only as strong as that scope, which is why the
    scanned count is printed on every run.
    """
    try:
        completed = subprocess.run(
            ["git", "ls-files"], cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", shell=False)
    except OSError:
        return []
    if completed.returncode != 0:
        return []
    return [name for name in completed.stdout.splitlines() if name.strip()]


def real_files_on_disk(root, relative_paths):
    """Arm 0's own limb: real files at the banned path anywhere in the tree."""
    target = banned_relative_path().replace("/", os.sep)
    found = []
    for relative in relative_paths:
        native = relative.replace("/", os.sep)
        if native.endswith(target) and os.path.isfile(os.path.join(root, native)):
            found.append(relative)
    return sorted(found)


def resolves_to_a_real_file(root, containing, matched):
    """Arm 0 for a TEXT hit: does the path it names exist on disk?"""
    native = matched.replace("/", os.sep).replace("\\", os.sep)
    candidates = [os.path.join(root, native),
                  os.path.join(root, os.path.dirname(containing), native)]
    return any(os.path.isfile(candidate) for candidate in candidates)


def scan_text(root, relative, text):
    """Every hit in one document, already classified."""
    cap = relative.endswith(SOURCE_SUFFIXES)
    hits = []
    for match in BANNED_PATH_RE.finditer(text):
        line, col = line_and_column(text, match.start())
        span = sentence_span(text, match.start(), match.end(), cap)
        verdict = classify(
            relative, line, col, span,
            quoted=is_quoted(text, match.start(), match.end()),
            real_file=resolves_to_a_real_file(root, relative, match.group(0)))
        separator = "\\" if "\\" in match.group(0) else "/"
        hits.append(Hit(relative, line, col, span, separator, verdict))
    return hits


class ScanReport(object):
    def __init__(self):
        self.root = ""
        self.floor = DEFAULT_FILE_FLOOR
        self.listed = 0
        self.scanned = 0
        self.unreadable = 0
        self.files_with_hits = 0
        self.occurrences = 0
        self.lines_with_hits = 0
        self.hits = []
        self.real_files = []
        self.counts = dict((role, 0) for role in ROLES)
        self.unused_cues = []

    @property
    def findings(self):
        return sum(self.counts[role] for role in FINDING_ROLES)

    @property
    def below_floor(self):
        return self.scanned < self.floor

    @property
    def code(self):
        # The population branch comes FIRST and overrides every count below it.
        # A verdict over a population too small to be meaningful is the 0/0 pass
        # with a number printed beside it.
        if self.below_floor:
            return EXIT_DID_NOT_RUN
        if self.counts[ROLE_LIVE] > 0:
            return EXIT_FINDING
        if self.counts[ROLE_UNCLASSIFIED] > 0:
            return EXIT_DID_NOT_RUN
        return EXIT_PASS

    def as_dict(self):
        return {
            "schema": "canonkit/lint-banned-names/1",
            "root": self.root,
            "floor": self.floor,
            "below_floor": self.below_floor,
            "listed": self.listed,
            "scanned": self.scanned,
            "unreadable": self.unreadable,
            "files_with_hits": self.files_with_hits,
            "occurrences": self.occurrences,
            "lines_with_hits": self.lines_with_hits,
            "counts": dict(self.counts),
            "code": self.code,
            "real_files_on_disk": list(self.real_files),
            "unused_cues": list(self.unused_cues),
            "hits": [hit.as_dict() for hit in self.hits[:MAX_LISTED]],
            "hits_listed": min(len(self.hits), MAX_LISTED),
        }


def scan(root, relative_paths=None, floor=DEFAULT_FILE_FLOOR):
    """Scan a tree. Returns a ScanReport with every count re-derived."""
    needle_self_test()
    root = os.path.abspath(str(root))
    report = ScanReport()
    report.root = root
    report.floor = floor
    listed = (tracked_files(root) if relative_paths is None
              else list(relative_paths))
    report.listed = len(listed)

    used = set()
    for relative in listed:
        native = os.path.join(root, relative.replace("/", os.sep))
        if not os.path.isfile(native):
            continue
        try:
            with open(native, "r", encoding="utf-8") as handle:
                text = handle.read()
        except (UnicodeDecodeError, OSError):
            report.unreadable += 1
            continue
        report.scanned += 1
        if not BANNED_PATH_RE.search(text):
            continue
        report.files_with_hits += 1
        report.lines_with_hits += sum(
            1 for line in text.split("\n") if BANNED_PATH_RE.search(line))
        for hit in scan_text(root, relative, text):
            report.occurrences += 1
            report.counts[hit.verdict.role] += 1
            report.hits.append(hit)
            used.add(hit.verdict.cue)

    report.real_files = real_files_on_disk(root, listed)

    report.unused_cues = sorted(
        "%s:%s" % (name, cue)
        for name, table in CUE_TABLES
        for cue, _is_prefix, _reason in table
        if cue not in used)
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def print_report(report, stream=None):
    """Both counts, all four roles, the scope, and every finding."""
    out = stream or sys.stdout
    out.write("lint-banned-names   scope=tracked files under %s\n" % report.root)
    # The needle is NAMED BY ITS DECISION, never spelled. Spelling it here would
    # put the literal into every captured transcript and every redirected run
    # log in this repository, and the next scan would read them back as fresh
    # hits. tools/conformance.py's the banned-spelling rule guard declines to spell it for the same
    # reason. There is exactly one path the banned-spelling rule bans and the decision record says
    # which; a reader who needs it looks there, not at a tool's stdout.
    out.write("  needle            the the banned-spelling rule banned results-record spelling "
              "(assembled at run time; this tool never prints it)\n")
    out.write("  population        listed=%d scanned=%d unreadable=%d "
              "files-with-hits=%d floor=%d\n"
              % (report.listed, report.scanned, report.unreadable,
                 report.files_with_hits, report.floor))
    out.write("  occurrences       %d  (lines with a hit: %d -- the two figures "
              "differ when one line carries several)\n"
              % (report.occurrences, report.lines_with_hits))
    out.write("  roles             live %d, frozen %d, detector %d, "
              "unclassified %d\n"
              % (report.counts[ROLE_LIVE], report.counts[ROLE_FROZEN],
                 report.counts[ROLE_DETECTOR],
                 report.counts[ROLE_UNCLASSIFIED]))
    out.write("  real files        %d on disk at the banned path\n"
              % len(report.real_files))
    out.write("  unused cues       %d%s\n"
              % (len(report.unused_cues),
                 (" -- " + ", ".join(report.unused_cues))
                 if report.unused_cues else ""))

    for role in FINDING_ROLES:
        listed_hits = [hit for hit in report.hits if hit.verdict.role == role]
        if not listed_hits:
            continue
        out.write("\n  %s (%d):\n" % (role.upper(), len(listed_hits)))
        for hit in listed_hits[:MAX_LISTED]:
            out.write("    %s:%d:%d  arm=%s cue=%s\n"
                      % (hit.path, hit.line, hit.col, hit.verdict.arm,
                         hit.verdict.cue))
            out.write("      span: %s\n"
                      % " ".join(hit.span[:MAX_SPAN_ECHO].split()))

    if report.below_floor:
        out.write("\n  REFUSING: this run scanned %d file(s), below the "
                  "effective floor of %d, so it looked at a population too "
                  "small for any verdict to mean anything. A lint over a tree "
                  "it did not really read cannot fail, so it must not be "
                  "allowed to report success. REPAIR: point it at the "
                  "tree you meant, or lower the floor deliberately with "
                  "--min-files and say why.\n"
                  % (report.scanned, report.floor))
    return report.code


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="lint_banned_names",
        description="the banned-spelling rule: the repo-wide lint for the banned results-record "
                    "spelling, classified by the ROLE of the sentence.")
    parser.add_argument("root", nargs="?", default=None,
                        help="the tree to scan (default: this checkout's root)")
    parser.add_argument("--report", default=None,
                        help="write the structured report here. A file rather "
                             "than a pipe: a command piped into tail returns "
                             "the PIPE's exit status.")
    parser.add_argument("--min-files", type=int, default=None,
                        help="override the effective file floor. The "
                             "OVERRIDDEN value is what prints. Raise it when "
                             "you know how big the tree should be -- a scan "
                             "that silently saw four files then fails loudly "
                             "instead of reporting a clean pass.")
    args = parser.parse_args(argv)

    root = args.root or repo_root_of(__file__)
    floor = DEFAULT_FILE_FLOOR if args.min_files is None else args.min_files
    report = scan(root, floor=floor)
    code = print_report(report)

    if args.report:
        directory = os.path.dirname(os.path.abspath(args.report))
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)
        with open(args.report, "w", encoding="utf-8") as handle:
            json.dump(report.as_dict(), handle, indent=2, sort_keys=True)
            handle.write("\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
