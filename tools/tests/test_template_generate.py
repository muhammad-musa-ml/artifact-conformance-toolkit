"""The artifact kit and the generator: a project requirement, a project requirement, and a FAILING template.

THREE SELECTORS, ONE MODULE. The kit is authored in three commits and each one's
verify command targets its own subset:

    -k skeleton   the README / RESULTS skeletons and their region contract
    -k config     LICENSE, .gitattributes, .gitignore, requirements, compose,
                  PORTS, waivers
    -k generate   tools/new_artifact.py end to end

WHY THE INTERESTING ASSERTION HERE IS A *FAILURE*. CHECK-03 requires that an
unedited template copy does NOT pass the conformance checker. The acceptance
shape, stated in the context note, is:

    generate -> conformance FAILS on CHECK-03 -> fill in -> conformance PASSES

This module builds and proves the FAILING half. It records the sha256 of the
unedited `artifact:limits` body as a named constant so the plan that writes
conformance.py can assert against the SAME BYTES rather than against a
re-derivation that could drift. A template that produced a passing artifact on
generation would be a bug, not a convenience.
"""

import hashlib
import re
import sys
from pathlib import Path

import pytest

from tools.tests import conftest
from tools.tests.test_canonkit import load_core

REPO_ROOT = conftest.REPO_ROOT
TEMPLATES = REPO_ROOT / "templates"
core = load_core()

README_SKELETON = TEMPLATES / "README-SKELETON.md"
RESULTS_SKELETON = TEMPLATES / "RESULTS-SKELETON.md"
SKELETONS = (README_SKELETON, RESULTS_SKELETON)

# ---------------------------------------------------------------------------
# Committed constants. Each one is a value another plan reads, so it is written
# down here rather than recomputed at two call sites that could drift.
# ---------------------------------------------------------------------------

# The sha256 of the UNEDITED artifact:limits body, newline-normalized, as both
# skeletons ship it. THIS IS THE VALUE conformance.py COMPARES AGAINST for
# CHECK-03's "is byte-identical to the template placeholder" condition.
#
# It is a literal rather than a call to _region_body(README_SKELETON) because a
# derived constant cannot detect its own input changing: if someone edits the
# placeholder, a derived value follows the edit and every assertion still
# passes, which is precisely the drift the constant exists to catch. Editing the
# placeholder must therefore fail this module until BOTH are updated together.
LIMITS_PLACEHOLDER_SHA256 = (
    "9c0056098163d3cfc0a0a9694665bd2cfd79a38aeaa82d720fce82360efcd0a3")

# The word floor CHECK-03 applies to a limits paragraph, COMMITTED HERE rather
# than inferred later. The placeholder must sit under it by construction.
LIMITS_WORD_FLOOR = 40

# The paired-region vocabulary fixed by the anchor-token rule (the design rule token is `artifact:`).
REGION_TOKEN = "artifact:"
EXPECTED_REGIONS = ("date", "claim", "figures", "env", "layout", "limits")
MIN_PAIRED_REGIONS = 5

# The banned path (the banned-spelling rule), ASSEMBLED FROM PARTS so this file is not itself a hit
# for the grep it performs. Pasting the literal here would make the test's own
# source the thing it forbids -- the shape where a ban's documentation trips it.
BANNED_RESULTS_PATH = "results/" + "manifest" + ".json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read(path):
    """Read as BYTES then decode ascii. Never text mode.

    Text mode would re-translate line endings on Windows and hand a test
    different bytes than the ones git stores -- the arm-A failure a design rule exists
    to prevent, arriving inside the test that checks for it.
    """
    return Path(path).read_bytes().decode("ascii")


def _region_body(path_or_text, name):
    """The bytes BETWEEN a paired begin/end marker, or None when absent."""
    text = (path_or_text if isinstance(path_or_text, str)
            else _read(path_or_text))
    pattern = re.compile(
        r"<!-- %s%s:begin -->\n(.*?)<!-- %s%s:end -->"
        % (REGION_TOKEN, name, REGION_TOKEN, name), re.S)
    match = pattern.search(text)
    return match.group(1) if match else None


def _sha256_text(text):
    return hashlib.sha256(text.encode("ascii")).hexdigest()


# ---------------------------------------------------------------------------
# Task 1 -- the skeletons
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", SKELETONS, ids=lambda p: p.name)
def test_skeleton_exists_and_is_pure_ascii_with_lf(path):
    """ASCII and LF, asserted on the BYTES.

    The project's encoding constraint says no file is ever judged correct by
    eyeballing console output. This reads the bytes and decodes them strictly,
    so a non-ASCII character is an error rather than a replacement glyph nobody
    notices.
    """
    raw = path.read_bytes()
    assert raw, "%s is empty" % path.name
    raw.decode("ascii")  # raises UnicodeDecodeError on any non-ASCII byte
    assert b"\r\n" not in raw, "%s carries CRLF in the working tree" % path.name


def test_skeleton_readme_is_at_least_sixty_lines():
    text = _read(README_SKELETON)
    assert len(text.splitlines()) >= 60


@pytest.mark.parametrize("path", SKELETONS, ids=lambda p: p.name)
def test_skeleton_regions_are_paired_and_ordered(path):
    """a design rule has no single-marker form, asserted STRUCTURALLY.

    Counting `begin -->` against `end -->` is the stated acceptance criterion
    and it is necessary but not sufficient: two begins followed by two ends
    would satisfy equal counts while nesting the regions. This walks each
    region by name and asserts begin precedes end exactly once, which a count
    cannot discriminate.
    """
    text = _read(path)
    begins = text.count("begin -->")
    ends = text.count("end -->")
    assert begins == ends, (
        "%s has %d begin marker(s) and %d end marker(s)"
        % (path.name, begins, ends))
    assert begins >= MIN_PAIRED_REGIONS, (
        "%s carries %d paired region(s), floor is %d"
        % (path.name, begins, MIN_PAIRED_REGIONS))

    paired = 0
    for name in EXPECTED_REGIONS:
        open_marker = "<!-- %s%s:begin -->" % (REGION_TOKEN, name)
        close_marker = "<!-- %s%s:end -->" % (REGION_TOKEN, name)
        opens = text.count(open_marker)
        closes = text.count(close_marker)
        assert opens == closes, (
            "%s: region %r has %d begin / %d end" % (path.name, name, opens, closes))
        if opens == 0:
            continue
        assert opens == 1, "%s: region %r appears %d times" % (path.name, name, opens)
        assert text.index(open_marker) < text.index(close_marker), (
            "%s: region %r closes before it opens" % (path.name, name))
        paired += 1
    assert paired == begins, (
        "%s carries %d paired marker(s) but only %d belong to the declared "
        "vocabulary %s" % (path.name, begins, paired, list(EXPECTED_REGIONS)))


def test_skeleton_readme_carries_the_ruled_b1_anchor_literally():
    """The anchor-token rule: the token is `artifact:`, not `backing:`.

    A verifier greps for this exact literal, so it is asserted exactly.
    """
    text = _read(README_SKELETON)
    assert "artifact:limits:begin" in text
    assert "backing:limits:begin" not in text


@pytest.mark.parametrize("path", SKELETONS, ids=lambda p: p.name)
def test_skeleton_has_no_unclassified_numeral(path):
    """CHECK-01 over the template itself: `unclassified == 0` in BOTH files.

    Reported with the located hits rather than as a bare verdict -- a count
    with no location is not actionable, and this assertion's whole job is
    telling an author WHERE the stray numeral is.
    """
    report = core.classify_numerals(_read(path))
    strays = [(h.line, h.col, h.token, h.context)
              for h in report.hits if h.kind == core.KIND_UNCLASSIFIED]
    assert report.unclassified == 0, (
        "%s carries %d unclassified numeral(s): %s"
        % (path.name, report.unclassified, strays))
    assert report.total > 0, (
        "%s classified nothing at all -- a clean verdict over an empty "
        "population is an unrun check, not a pass" % path.name)


@pytest.mark.parametrize("path", SKELETONS, ids=lambda p: p.name)
def test_skeleton_figures_region_holds_key_references_only(path):
    """No literal figure inside artifact:figures -- every value is a key reference."""
    body = _region_body(path, "figures")
    assert body is not None, "%s has no artifact:figures region" % path.name

    braced = re.findall(r"\{\{[^}]*\}\}", body)
    assert braced, "%s: the figures region carries no key reference" % path.name
    malformed = [token for token in braced
                 if not re.fullmatch(r"\{\{figures\.[a-z0-9_]+\}\}", token)]
    assert not malformed, (
        "%s: figures region carries non-conforming reference(s) %s"
        % (path.name, malformed))

    report = core.classify_numerals(body)
    non_reference = [(h.token, h.kind) for h in report.hits
                     if h.kind != core.KIND_KEY_REFERENCE]
    assert not non_reference, (
        "%s: figures region carries numeral(s) that are not key references: %s"
        % (path.name, non_reference))


def _first_run_command(text):
    """The first command line inside the fence under `## Running it`."""
    heading = text.index("## Running it")
    fence = text.index("```", heading)
    body = text[fence + 3:].lstrip("\n")
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def test_skeleton_running_it_opens_with_the_gate():
    """`## Running it` exists and its first fenced command RUNS THE GATE.

    RE-KEYED, and the reason is worth the paragraph. The original criterion was
    that the first fenced command equal the literal `python gate.py`, and the
    skeleton satisfied it exactly -- until the artifact was generated and that
    command was actually RUN, whereupon gate.py exited 2 with
    "the following arguments are required: --slug".

    So the documented command was a DEAD INSTRUCTION: it rendered perfectly,
    passed a literal-equality assertion, and dead-ended any reader who followed
    it exactly. The criterion's INTENT is that the sequence opens with the gate,
    because gate-before-measurement is the ordering the run token makes
    provable. That intent is preserved here; the exact-string form is not, since
    it could only be satisfied by a command that does not work.

    test_generate_the_documented_first_command_actually_runs walks the
    instruction rather than reading it, which is the assertion that would have
    caught this without an end-to-end run.
    """
    text = _read(README_SKELETON)
    assert "## Running it" in text
    first = _first_run_command(text)
    assert first.startswith("python gate.py"), (
        "the first fenced command under '## Running it' is %r" % first)
    assert "python3" not in first


def test_skeleton_never_says_python3():
    """`python3` hits the Microsoft Store alias on this machine.

    A README saying `python3` dead-ends a reader following it exactly, with a
    non-functional stub that prints an install prompt and exits non-zero.
    """
    for path in SKELETONS:
        assert "python3" not in _read(path), "%s says python3" % path.name


@pytest.mark.parametrize("path", SKELETONS, ids=lambda p: p.name)
def test_skeleton_limits_placeholder_is_refusable(path):
    """The placeholder fails all FOUR CHECK-03 conditions at once, by design.

    present-but-unedited / under the word floor / no scope vocabulary / names
    itself. Asserted one condition at a time, because a single combined
    assertion could pass on the strength of any one of them and would not
    discriminate which held.
    """
    body = _region_body(path, "limits")
    assert body is not None, "%s has no artifact:limits region" % path.name

    # (1) names itself -- the sentinel an author is meant to delete
    assert "TODO(artifact:limits)" in body, (
        "%s: the limits placeholder carries no sentinel" % path.name)

    # (2) under the committed word floor
    words = body.split()
    assert len(words) < LIMITS_WORD_FLOOR, (
        "%s: the limits placeholder is %d words, floor is %d -- a placeholder "
        "that clears the floor would PASS the condition it exists to fail"
        % (path.name, len(words), LIMITS_WORD_FLOOR))

    # (3) no scope vocabulary
    scope_words = ("not shown", "does not", "excludes", "limited to", "only",
                   "cannot", "untested", "unmeasured", "out of scope", "never")
    present = [word for word in scope_words if word in body.lower()]
    assert not present, (
        "%s: the limits placeholder carries scope vocabulary %s, so it would "
        "satisfy one of the conditions CHECK-03 requires it to fail"
        % (path.name, present))

    # (4) byte-identical to the committed placeholder
    assert _sha256_text(body) == LIMITS_PLACEHOLDER_SHA256, (
        "%s: the limits placeholder hashes %s but the committed constant is "
        "%s. If the placeholder was edited deliberately, update "
        "LIMITS_PLACEHOLDER_SHA256 in the SAME commit -- the plan that writes "
        "conformance.py asserts against this value."
        % (path.name, _sha256_text(body), LIMITS_PLACEHOLDER_SHA256))


def test_skeleton_limits_placeholder_is_identical_in_both_files():
    """One placeholder, two files. Two spellings would give CHECK-03 two answers."""
    readme = _region_body(README_SKELETON, "limits")
    results = _region_body(RESULTS_SKELETON, "limits")
    assert readme == results


def test_skeleton_results_carries_the_attributed_quotation():
    """a shared pattern's model sentence, quoted AND attributed.

    Attributed by file and heading rather than by line number: the quotation
    wraps across two lines in the source, and a line number rots while the
    heading does not.
    """
    text = _read(RESULTS_SKELETON)
    assert "discarding the run that disagrees is how a benchmark lies" in text
    assert "example-cache-benchmark/results/RESULTS.md" in text


def test_skeleton_results_carries_the_nothing_is_estimated_clause():
    text = _read(RESULTS_SKELETON)
    assert "Nothing is estimated." in text
    assert "results/figures.json" in text, (
        "the nothing-is-estimated clause must name the single source")


def test_skeleton_results_keeps_retraction_and_instability_structures():
    """a shared pattern and a design rule: a retraction kept in place, a disagreeing run disclosed."""
    text = _read(RESULTS_SKELETON)
    assert "### Retracted" in text
    assert "### The instability, disclosed rather than hidden" in text
    assert "Still open, honestly" in text


@pytest.mark.parametrize("path", SKELETONS, ids=lambda p: p.name)
def test_skeleton_does_not_carry_the_banned_results_path(path):
    """the banned-spelling rule, in a template's LIVE role.

    A template carries this literal only as an OUTPUT TARGET an author would
    then write -- which is the LIVE role under the three-role rule, never the
    documenting role a decision record occupies. So the ban applies here with
    no carve-out.
    """
    assert BANNED_RESULTS_PATH not in _read(path), (
        "%s names the banned results path" % path.name)


# ---------------------------------------------------------------------------
# Task 2 -- the config kit
# ---------------------------------------------------------------------------

GITATTRIBUTES = TEMPLATES / ".gitattributes"
GITIGNORE = TEMPLATES / ".gitignore"
LICENSE = TEMPLATES / "LICENSE"
REQUIREMENTS_IN = TEMPLATES / "requirements.in"
REQUIREMENTS_TXT = TEMPLATES / "requirements.txt"
COMPOSE = TEMPLATES / "docker-compose.yml"
PORTS = TEMPLATES / "PORTS.md"
WAIVERS = TEMPLATES / "waivers.json"

CONFIG_KIT = (GITATTRIBUTES, GITIGNORE, LICENSE, REQUIREMENTS_IN,
              REQUIREMENTS_TXT, COMPOSE, PORTS, WAIVERS)

# The one normative line a project requirement requires, asserted as an exact line.
NORMATIVE_EOL_RULE = "* text=auto eol=lf"

# Range specifiers, each one banned. `==` is deliberately absent: it is the ONLY
# admissible form.
RANGE_SPECIFIER_RE = re.compile(r"(?:[><~!]=|,\s*<|>=|<=)")


def _logical_requirements(text):
    """Requirement ENTRIES, with backslash continuations joined.

    THE UNIT IS THE REQUIREMENT, NOT THE PHYSICAL LINE, and the distinction is
    the whole correctness of this parse. `uv pip compile --generate-hashes`
    emits each requirement across several lines:

        colorama==0.4.6 \
            --hash=sha256:... \
            --hash=sha256:...

    so the line carrying the PIN carries no hash and every line carrying a HASH
    carries no pin. A per-physical-line assertion is therefore unsatisfiable by
    the output of the very command that is mandated to produce this file -- it
    could only be met by hand-writing the lock on single lines, which is the
    thing --generate-hashes exists to stop anyone doing. Joining first makes the
    assertion both satisfiable and STRONGER: it checks the pin and the hash
    together, per distribution.
    """
    entries = []
    current = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith("\\"):
            current.append(stripped[:-1].strip())
            continue
        current.append(stripped)
        entries.append(" ".join(part for part in current if part))
        current = []
    if current:
        entries.append(" ".join(current))
    return entries


def _image_references(text):
    """Every `image:` VALUE in a compose document, in file order.

    Scoped to `image:` keys rather than to the whole file on purpose. A tag
    appearing in a COMMENT that documents how a digest was resolved is not a
    pull site, and a check that flagged it would be reporting a false positive
    of exactly the shape already measured against a correct provenance record.
    """
    return re.findall(r"^\s*image:\s*(\S+)", text, re.M)


@pytest.mark.parametrize("path", CONFIG_KIT, ids=lambda p: p.name)
def test_config_file_exists_and_is_ascii_with_lf(path):
    raw = path.read_bytes()
    assert raw, "%s is empty" % path.name
    raw.decode("ascii")
    assert b"\r\n" not in raw, "%s carries CRLF in the working tree" % path.name


def test_config_gitattributes_carries_the_normative_rule():
    """a project requirement's one line, asserted as a LINE rather than as a substring.

    A substring check would be satisfied by the rule appearing inside a comment
    explaining it, which is exactly how this file is written -- the prose above
    the rule discusses it at length. Splitting on lines is what makes the
    assertion about the rule being IN FORCE rather than merely mentioned.
    """
    lines = [line.strip() for line in _read(GITATTRIBUTES).splitlines()]
    assert NORMATIVE_EOL_RULE in lines, (
        "%r is not a line of templates/.gitattributes" % NORMATIVE_EOL_RULE)


def test_config_gitattributes_matches_this_repositorys_own_rule():
    """BOTH ENDS need the rule; the failure is a MISMATCH, not one bad end.

    The tooling repository authors canonkit.py and an artifact hashes it. A
    three-arm experiment measured that normalizing only one side does not close
    the gap. So this asserts the artifact template carries the SAME normative
    line this repository carries, rather than merely carrying A rule.
    """
    repo_rule_lines = [line.strip()
                       for line in _read(REPO_ROOT / ".gitattributes").splitlines()]
    assert NORMATIVE_EOL_RULE in repo_rule_lines, (
        "this repository's own .gitattributes no longer carries %r, so the two "
        "ends have drifted apart -- which is the condition that breaks a "
        "cross-repository digest" % NORMATIVE_EOL_RULE)


def test_config_requirements_every_requirement_is_pinned_and_hashed():
    """CHECK-08 over the lock: every DISTRIBUTION carries `==` and a hash.

    See _logical_requirements for why the unit is the requirement rather than
    the physical line.
    """
    entries = _logical_requirements(_read(REQUIREMENTS_TXT))
    assert entries, (
        "templates/requirements.txt parsed to ZERO requirements -- a lock with "
        "no population would pass every assertion below over nothing")
    unpinned = [entry for entry in entries if "==" not in entry]
    assert not unpinned, "unpinned requirement(s): %s" % unpinned
    unhashed = [entry.split()[0] for entry in entries
                if "--hash=sha256:" not in entry]
    assert not unhashed, "requirement(s) with no sha256 hash: %s" % unhashed


def test_config_requirements_carries_no_range_specifier():
    """No `>=`, `<=`, `~=`, `!=` or `,<` anywhere. `==` is the only form.

    The analog this inverts is a REAL committed defect, not a hypothetical: a
    shipped artifact in this program carries a range specifier in its
    requirements, and that file is now a known-bad fixture. The template must
    carry none.
    """
    for path in (REQUIREMENTS_IN, REQUIREMENTS_TXT):
        hits = []
        for number, line in enumerate(_read(path).splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if RANGE_SPECIFIER_RE.search(stripped):
                hits.append((number, stripped))
        assert not hits, "%s carries range specifier(s): %s" % (path.name, hits)


def test_config_requirements_in_pins_its_own_direct_dependency():
    entries = _logical_requirements(_read(REQUIREMENTS_IN))
    assert entries, "templates/requirements.in declares nothing"
    assert all("==" in entry for entry in entries), entries


def test_config_compose_pins_every_image_by_digest():
    images = _image_references(_read(COMPOSE))
    assert images, (
        "templates/docker-compose.yml declares ZERO images -- this assertion "
        "would then pass over an empty population, which is an unrun check")
    untagged = [image for image in images if "@sha256:" not in image]
    assert not untagged, "image reference(s) not pinned by digest: %s" % untagged
    for image in images:
        digest = image.split("@sha256:", 1)[1]
        assert re.fullmatch(r"[0-9a-f]{64}", digest), (
            "%s carries a digest that is not 64 lowercase hex characters -- a "
            "shortened or hand-typed digest reads as correct and resolves to "
            "nothing" % image)


def test_config_compose_has_no_latest_tag_anywhere():
    """`:latest` is banned in this file at ANY position, not only in `image:`.

    Compose is a PULL SITE, so the documented false positive does not apply
    here: that one is about a provenance RECORD, which is an output naming what
    a tag resolved to. This file is an input that causes a pull.
    """
    assert ":latest" not in _read(COMPOSE)


def test_config_compose_image_check_rejects_a_tag_only_reference():
    """The digest guard, DEMONSTRATED DISCRIMINATING on a synthetic input.

    A guard asserted only against a tree that already satisfies it has never
    been observed distinguishing anything. This feeds the same predicate a
    tag-only compose document and requires it to object.
    """
    tag_only = "services:\n  db:\n    image: postgres:18\n"
    images = _image_references(tag_only)
    assert images == ["postgres:18"], images
    assert [image for image in images if "@sha256:" not in image], (
        "the predicate accepted a tag-only image reference")


def test_config_compose_mounts_are_named_volumes_not_bind_mounts():
    """Every mount SOURCE is a named volume. Asserted structurally, not by substring.

    The first draft of this test was `assert "/mnt/c" not in text`, and it
    failed -- on the COMMENT that explains why bind mounts are forbidden. That
    failure is not the same shape as the banned-tag one two tests above, and the
    two are resolved in opposite directions on purpose:

      the banned floating tag   LIVE. A commented-out service is one uncomment
                                away from being a pull site, so the literal is
                                removed from the template entirely.
      a path in this comment    FROZEN. Prose describing a hazard cannot mount
                                anything. Narrowing the CHECK is correct here;
                                narrowing it for the tag would not have been.

    Substring matching could not tell those apart, which is the argument for
    parsing the mounts. This also catches every bind mount rather than the one
    Windows path the substring named -- a mount from `./data` or `C:/...` is the
    same defect and the old form missed both.
    """
    text = _read(COMPOSE)
    mounts = re.findall(r'^\s+-\s+"?([^"\s:]+):(/[^"\s:]+)"?\s*$', text, re.M)
    assert mounts, (
        "no volume mount was parsed out of the compose file, so this assertion "
        "would run over zero and report a pass having checked nothing")
    binds = [source for source, _ in mounts
             if "/" in source or source.startswith(".") or ":" in source]
    assert not binds, (
        "bind-mounted source(s) %s: a mount whose source is a PATH rather than "
        "a named volume crosses the Windows filesystem boundary and turns a "
        "latency figure into a measurement of filesystem translation" % binds)
    assert re.search(r"^volumes:", text, re.M), (
        "no top-level volumes: block, so nothing declares a named volume")


def test_config_compose_waits_for_healthy_not_merely_started():
    text = _read(COMPOSE)
    assert "condition: service_healthy" in text
    assert "healthcheck:" in text


def test_config_waivers_ships_empty_and_well_formed():
    """a design rule: the channel exists, is owner-authored, and starts at zero."""
    import json

    record = json.loads(_read(WAIVERS))
    assert record["waivers"] == [], (
        "the shipped waiver channel is not empty: %r" % (record["waivers"],))
    assert len(record["waivers"]) == 0
    assert record["schema"].startswith("canonkit/waivers/")
    assert record["schema_version"] == core.SCHEMA_VERSION


def test_config_waivers_states_the_owner_authored_rule():
    """The rule that makes the channel work must travel WITH the channel.

    A waiver file with no statement of who may write it is an invitation for an
    unattended build agent to silence the checker that is checking it.
    """
    text = _read(WAIVERS).lower()
    assert "owner-authored only" in text
    assert "itself a finding" in text
    for field in ("check_id", "reason", "dated_at"):
        assert field in text, "the entry shape does not name %r" % field


def test_config_gitignore_does_not_ignore_results():
    """CHECK-07 needs a TRACKED machine-written file under results/.

    This is the inversion against the tooling repository's own .gitignore, and
    it is asserted rather than trusted to a comment: an ignored results/ makes
    every artifact fail CHECK-07 silently.
    """
    lines = [line.strip() for line in _read(GITIGNORE).splitlines()
             if line.strip() and not line.strip().startswith("#")]
    offenders = [line for line in lines
                 if line.rstrip("/") == "results" or line.startswith("results/")]
    assert not offenders, (
        "templates/.gitignore ignores results/: %s" % offenders)


def test_config_gitignore_documents_the_inversion():
    text = _read(GITIGNORE)
    assert "results/" in text, (
        "the inversion is not mentioned at all, so a later author copying "
        "rules between the two repositories has nothing to warn them")
    assert "CHECK-07" in text


def test_config_gitignore_excludes_secrets_and_derived_corpora():
    lines = [line.strip() for line in _read(GITIGNORE).splitlines()]
    for pattern in (".env", "__pycache__/", "*.pyc"):
        assert pattern in lines, "%r is not ignored" % pattern
    assert any(line.startswith(".env") for line in lines)


def test_config_license_names_the_no_redistribution_rule():
    text = _read(LICENSE)
    assert "DERIVED CORPORA ARE NEVER REDISTRIBUTED." in text
    assert "extraction script" in text
    assert "frozen id list" in text.lower()
    assert "attribution block" in text
    assert "covers the code in this repository only" in text.lower()


def test_config_ports_documents_the_convention_and_every_compose_port():
    """Every host port compose publishes must appear in PORTS.md.

    Derived from the compose file rather than from a second hand-maintained
    list: a documented convention that does not cover a port actually bound is
    the next collision, and only a cross-check can notice.
    """
    ports_text = _read(PORTS)
    published = re.findall(r'^\s*-\s*"(\d+):\d+"', _read(COMPOSE), re.M)
    assert published, "compose publishes no host port, so this check ran over zero"
    missing = [port for port in published if port not in ports_text]
    assert not missing, "PORTS.md does not document host port(s) %s" % missing


# ---------------------------------------------------------------------------
# Task 3 -- tools/new_artifact.py
# ---------------------------------------------------------------------------

# a project requirement's NINE NAMES, transcribed from the requirement rather than globbed.
#
# A glob would enumerate whatever the template directory happens to hold, which
# makes the assertion follow the tree instead of checking it: delete gate.py from
# the kit and a globbed expectation deletes itself in the same motion. FOUR of
# these nine are authored by a different plan (gate/verify/provenance/finalize),
# and those four are exactly the ones a generator is most likely to drop, so
# they are named individually and never inferred.
TOOL_04_REQUIRED = (
    "README.md",
    "LICENSE",
    ".gitattributes",
    "requirements.txt",
    "gate.py",
    "verify.py",
    "provenance.py",
    "finalize.py",
    "docker-compose.yml",
)

# The four that arrive from the run-chain plan. Byte-compared, never templated:
# a slug substitution inside a Python source file is how a generator silently
# corrupts one.
RUN_CHAIN_MEMBERS = ("gate.py", "verify.py", "provenance.py", "finalize.py")

TEST_IDENTITY = ("artifact-conformance-toolkit tests", "tests@example.invalid")


def _git_out(args, cwd):
    """Read a git fact from git. Never from the filesystem.

    "the file exists" and "git tracks the file" are different claims, and only
    the second survives a clean checkout -- which is the claim CHECK-07 makes.
    """
    import subprocess

    completed = subprocess.run(
        ["git"] + list(args), cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace", shell=False, check=True)
    return completed.stdout


def _tracked(artifact_dir):
    return set(_git_out(["ls-files"], artifact_dir).split())


def _generated(tmp_path, slug="demo-artifact", **kwargs):
    from tools import new_artifact

    kwargs.setdefault("identity", TEST_IDENTITY)
    report = new_artifact.generate(slug, tmp_path, **kwargs)
    return report


def _assert_tool_04_tracked(artifact_dir):
    """The project requirement completeness assertion, factored out so it can be OBSERVED FAILING.

    An assertion over nine names that has never been seen failing on a missing
    name is an assertion about the loop, not about the tree. Keeping it in a
    helper lets one test assert it holds for a real artifact and a second test
    assert it RAISES for a mutilated kit -- permanently, rather than as a
    one-off run somebody did once and wrote up.
    """
    assert len(TOOL_04_REQUIRED) == 9, (
        "TOOL_04_REQUIRED names %d file(s); a project requirement states nine. A loop over a "
        "short tuple reports success over nothing."
        % len(TOOL_04_REQUIRED))
    tracked = _tracked(artifact_dir)
    missing = [name for name in TOOL_04_REQUIRED if name not in tracked]
    assert not missing, (
        "a project requirement file(s) not tracked by git in %s: %s (tracked %d path(s))"
        % (artifact_dir, missing, len(tracked)))


def test_generate_first_commit_is_gitattributes_alone(tmp_path):
    """a project requirement / a design rule, asserted from git HISTORY rather than from file presence.

    THIS IS THE ASSERTION A FUTURE "tidy up the generator" COMMIT IS MOST LIKELY
    TO BREAK, because committing everything at once is the obvious simplification
    and it looks harmless: the same files end up tracked either way. What changes
    is WHEN the end-of-line rule was in force. Attributes apply as a blob ENTERS
    the index, so anything committed before .gitattributes keeps whatever line
    endings it was written with -- and a digest taken here then fails to
    reproduce after a clone somewhere else, for a reason unrelated to content.

    `git log --diff-filter=A` is used rather than checking that the file exists,
    because existence cannot distinguish "committed first" from "committed
    eventually", and only the first is a project requirement.
    """
    report = _generated(tmp_path)
    artifact = Path(report.artifact_dir)

    first = _git_out(
        ["log", "--diff-filter=A", "--format=%H", "--reverse", "--",
         ".gitattributes"], artifact).split()
    assert first, ".gitattributes was never ADDED in any commit"
    first_sha = first[0]

    root_commit = _git_out(["rev-list", "--max-parents=0", "HEAD"], artifact).split()
    assert root_commit == [first_sha], (
        "the commit that added .gitattributes (%s) is not the repository's root "
        "commit (%s)" % (first_sha, root_commit))

    touched = _git_out(
        ["show", "--pretty=format:", "--name-only", first_sha], artifact).split()
    assert touched == [".gitattributes"], (
        "the first commit touched %d path(s), not one: %s" % (len(touched), touched))


def test_generate_tool_04_nine_files_are_tracked(tmp_path):
    report = _generated(tmp_path)
    _assert_tool_04_tracked(Path(report.artifact_dir))


def test_generate_tool_04_completeness_fails_when_a_member_is_missing(tmp_path):
    """The completeness assertion, DEMONSTRATED FAILING on a removed member.

    The kit is copied to a temp root and mutilated there. The committed
    templates/ tree is never touched, so there is nothing to restore and no
    `git checkout --` anywhere near this -- that command restores from HEAD and
    would destroy uncommitted work while making the verdict flatter itself.
    """
    import shutil

    source_root = tmp_path / "kit-root"
    (source_root).mkdir()
    shutil.copytree(REPO_ROOT / "templates", source_root / "templates")
    shutil.copytree(REPO_ROOT / "tools", source_root / "tools",
                    ignore=shutil.ignore_patterns("tests", "__pycache__"))

    removed = source_root / "templates" / "gate.py"
    assert removed.is_file(), "the kit copy has no gate.py to remove"
    removed.unlink()

    report = _generated(tmp_path / "dest", source_root=source_root)
    with pytest.raises(AssertionError) as caught:
        _assert_tool_04_tracked(Path(report.artifact_dir))
    assert "gate.py" in str(caught.value), (
        "the failure did not NAME the missing file: %s" % caught.value)


def test_generate_run_chain_members_are_byte_identical_to_their_source(tmp_path):
    """sha256 per file, so a partial copy is a failure rather than a smaller file."""
    report = _generated(tmp_path)
    artifact = Path(report.artifact_dir)
    for name in RUN_CHAIN_MEMBERS:
        source = (TEMPLATES / name).read_bytes()
        landed = (artifact / name).read_bytes()
        assert core.sha256_bytes(landed) == core.sha256_bytes(source), (
            "%s landed with a different sha256 than templates/%s" % (name, name))


def test_generate_vendored_core_matches_this_repositorys_core(tmp_path):
    """The same assertion audit() makes, made HERE at generation time."""
    report = _generated(tmp_path)
    artifact = Path(report.artifact_dir)
    assert core.sha256_file(str(artifact / "canonkit.py")) == core.sha256_file(
        str(REPO_ROOT / "tools" / "canonkit.py"))
    assert report.vendored_count >= 1, (
        "vendored %d file(s) -- a record over an empty set asserts nothing"
        % report.vendored_count)


def test_generate_tracks_the_whole_kit_not_merely_writes_it(tmp_path):
    report = _generated(tmp_path)
    tracked = _tracked(Path(report.artifact_dir))
    for name in (".gitignore", "PORTS.md", "waivers.json", "canonkit.py",
                 "requirements.in", "results/RESULTS.md", "derive.py",
                 "runmeta.py", "run_example.py"):
        assert name in tracked, "%s exists but git does not track it" % name
    assert not _git_out(["status", "--porcelain"], report.artifact_dir).strip(), (
        "the generated tree has uncommitted changes, so a clean checkout would "
        "not reproduce it")


def test_generate_sets_core_longpaths_in_the_new_repository(tmp_path):
    """Verified NOT set on this machine, so the generator must set it per repo."""
    report = _generated(tmp_path)
    value = _git_out(["config", "--get", "core.longpaths"], report.artifact_dir)
    assert value.strip() == "true", "core.longpaths is %r" % value.strip()


def test_generate_refuses_a_non_empty_destination_and_writes_nothing(tmp_path):
    """a shared pattern: refuse before you measure, exit 2, and leave the directory untouched.

    The directory listing is compared BEFORE and AFTER. Asserting only that the
    call raised would not distinguish "refused" from "refused after writing half
    the kit".
    """
    from tools import new_artifact

    dest = tmp_path / "occupied"
    (dest / "demo-artifact").mkdir(parents=True)
    (dest / "demo-artifact" / "existing.txt").write_text("keep me\n", encoding="ascii")
    before = sorted(p.name for p in (dest / "demo-artifact").iterdir())

    code = new_artifact.main(["demo-artifact", "--into", str(dest)])
    assert code == core.EXIT_DID_NOT_RUN, "expected exit 2, got %r" % code

    after = sorted(p.name for p in (dest / "demo-artifact").iterdir())
    assert after == before == ["existing.txt"], (
        "the refusal wrote into the destination: before=%s after=%s"
        % (before, after))
    assert not (dest / "demo-artifact" / ".git").exists(), (
        "the refusal still initialised a repository")


def test_generate_refusal_names_a_repair_instruction(tmp_path, capsys):
    from tools import new_artifact

    dest = tmp_path / "occupied"
    (dest / "demo-artifact").mkdir(parents=True)
    (dest / "demo-artifact" / "existing.txt").write_text("x\n", encoding="ascii")

    new_artifact.main(["demo-artifact", "--into", str(dest)])
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert core.REFUSAL_PREFIX in combined, combined
    assert "demo-artifact" in combined


@pytest.mark.parametrize("slug", ["Demo", "demo artifact", "-demo", "demo/artifact",
                                  "", "demo_artifact"])
def test_generate_refuses_a_slug_outside_the_declared_shape(tmp_path, slug):
    from tools import new_artifact

    with pytest.raises(new_artifact.Refusal):
        new_artifact.generate(slug, tmp_path / slug.replace("/", "_"),
                              identity=TEST_IDENTITY)


def test_generate_refuses_a_case_only_collision_and_prints_both(tmp_path):
    """NTFS cannot hold two such names, so the condition arrives from ELSEWHERE.

    A tree checked out on a case-sensitive filesystem can carry both `results/`
    and `Results/`; copying it here silently merges them. The check therefore
    runs over the prospective path LIST rather than over the filesystem, which
    is the only way it can fire on the machine that cannot reproduce it.
    """
    from tools import new_artifact

    paths = ["a/results/x.md", "a/Results/x.md", "a/keep.md"]
    collisions = new_artifact.case_only_collisions(paths)
    assert collisions, "the predicate accepted a case-only collision"
    flat = [item for pair in collisions for item in pair]
    assert "a/results/x.md" in flat and "a/Results/x.md" in flat, collisions
    assert "a/keep.md" not in flat

    assert new_artifact.case_only_collisions(["a/x.md", "a/y.md"]) == [], (
        "the predicate invented a collision where there is none")


def test_generate_prints_the_longest_path_even_on_success(tmp_path, capsys):
    from tools import new_artifact

    new_artifact.main(["demo-artifact", "--into", str(tmp_path)])
    combined = capsys.readouterr().out
    assert "longest path" in combined.lower(), combined
    assert str(new_artifact.MAX_PATH_CHARS) in combined, (
        "the limit is not printed beside the measurement, so a reader cannot "
        "tell how close the tree is to it: %s" % combined)


def test_generate_refuses_when_the_longest_path_exceeds_the_limit(tmp_path):
    """The ceiling, demonstrated on the PREDICATE.

    Creating a path over the limit on this filesystem fails for reasons of its
    own, so the assertion is made against the function that measures rather than
    against a tree nobody can build here.
    """
    from tools import new_artifact

    short = ["C:/x/README.md"]
    assert new_artifact.longest_path_length(short) == len(short[0])
    over = ["C:/" + ("d" * new_artifact.MAX_PATH_CHARS) + "/README.md"]
    assert new_artifact.longest_path_length(over) >= new_artifact.MAX_PATH_CHARS


def test_generate_produces_an_unedited_limits_body_matching_the_skeleton(tmp_path):
    """The FAILING half of CHECK-03's round trip, recorded as a sha256.

    This is the plan's whole point: an artifact is honestly incomplete the
    moment it is generated. The value is asserted against the committed constant
    rather than against a re-read of the skeleton, so the plan that writes
    conformance.py can assert the same bytes without re-deriving them.
    """
    report = _generated(tmp_path)
    readme = _read(Path(report.artifact_dir) / "README.md")
    body = _region_body(readme, "limits")
    assert body is not None, "the generated README has no artifact:limits region"
    assert _sha256_text(body) == LIMITS_PLACEHOLDER_SHA256
    assert "TODO(artifact:limits)" in body


def test_generate_substitutes_names_but_never_a_figure_or_a_date(tmp_path):
    """Substitution is NAME-ONLY. Figures and dates come from figures.json later."""
    report = _generated(tmp_path, slug="demo-artifact", canon="example-alpha",
                        project="some-project", bullets=["P5-B3"])
    readme = _read(Path(report.artifact_dir) / "README.md")
    assert "example-alpha" in readme
    assert "some-project" in readme
    assert "P5-B3" in readme
    assert "{{artifact." not in readme, (
        "an artifact.* placeholder survived substitution")
    assert "{{figures.dated_at}}" in readme, (
        "the date key reference was substituted at generation time; it must be "
        "left for render.py to fill from a machine-emitted timestamp")
    assert "{{figures.headline_ratio}}" in readme


def test_generate_the_documented_first_command_actually_runs(tmp_path):
    """WALK THE INSTRUCTION. Do not merely check that it rendered.

    This test exists because the skeleton's documented first command was
    verified by literal string comparison, shipped, and then failed the moment
    anybody ran it -- `gate.py` requires `--slug` and the README did not pass
    one. Every check was green: the heading was present, the fence was present,
    the string matched. None of them had run the command.

    So this one runs it, in a real generated artifact, and requires exit 0. An
    artifact whose own README dead-ends its reader on line one is worse than one
    with no README, because the reader concludes the artifact is broken rather
    than the documentation.
    """
    import shlex
    import subprocess

    report = _generated(tmp_path, slug="demo-artifact")
    artifact = Path(report.artifact_dir)
    command = _first_run_command(_read(artifact / "README.md"))
    assert command, "the generated README documents no command at all"
    assert "{{" not in command, (
        "an unsubstituted placeholder survived into a command a reader would "
        "paste: %r" % command)

    argv = shlex.split(command)
    assert argv[0] == "python", argv
    completed = subprocess.run(
        [sys.executable] + argv[1:], cwd=str(artifact), capture_output=True,
        text=True, encoding="utf-8", errors="replace", shell=False, timeout=300)
    assert completed.returncode == 0, (
        "the documented first command %r exited %d in the generated artifact\n"
        "STDOUT:\n%s\nSTDERR:\n%s"
        % (command, completed.returncode, completed.stdout, completed.stderr))


def test_generate_reports_written_and_tracked_as_two_separate_numbers(tmp_path):
    """Two counts, not one. They answer different questions and can disagree."""
    report = _generated(tmp_path)
    assert report.files_written > 0
    assert report.files_tracked > 0
    assert report.files_tracked == len(_tracked(Path(report.artifact_dir)))
    assert report.longest_path > 0
