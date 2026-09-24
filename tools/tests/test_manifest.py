"""`tools/manifest.json` -- ONE slug list whose counts are DERIVED and ASSERTED.

a design rule (HARD) is the whole of this module's subject, and its rationale is the
reason every test here is shaped the way it is: *a purely derived count silently
stops checking when a slug is dropped, because expected falls to match found.*
The committed literal is the tripwire on the derivation's own input, and
test_counts_derived_and_asserted is where that tripwire is demonstrated rather
than described.

Every canon, project and bullet id is RE-DERIVED here from
tools/canon-bullets.json. The manifest is never taken at its word about anything
the canon can settle.
"""

import ast
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT
MANIFEST_PATH = REPO_ROOT / "tools" / "manifest.json"
SNAPSHOT_PATH = REPO_ROOT / "tools" / "canon-bullets.json"


def _load(stem, path):
    if stem in sys.modules:
        return sys.modules[stem]
    spec = importlib.util.spec_from_file_location(stem, str(path))
    if spec is None or spec.loader is None:
        raise ImportError("could not build a spec for %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[stem] = module
    spec.loader.exec_module(module)
    return module


snap = _load("canon_snapshot", REPO_ROOT / "tools" / "canon_snapshot.py")
census = _load("census_live_store", REPO_ROOT / "tools" / "census_live_store.py")


def assert_scan_root_is_the_main_checkouts_parent(root, what):
    """The anchor assertion that REPLACED the `>= 10` population floor.

    WHAT THE OLD FLOOR WAS FOR, and why a number could not do the job. Inside an
    agent worktree, a root derived as `conftest.REPO_ROOT / ".."` resolves to
    `<repo>/agent-worktrees/worktrees` instead of the directory that holds the artifact
    slugs. Every "is not among the enumerated" assertion downstream still PASSES
    there, over a population of two or three sibling worktrees rather than the
    ~25 trees the property is about -- a pass over a population nobody confirmed.
    `>= 10` was put in to catch that, and it does catch it. What it also does is
    assert a fact about ONE MACHINE'S LAYOUT, so it cannot hold in a published
    export whose parent directory holds exactly one entry, and it cannot hold on
    anyone else's checkout either.

    So the floor is replaced by the thing the floor was proxying for, stated
    directly. Three identities, all true in an ordinary checkout, in a worktree
    AND in an export, and all three FALSE the moment the anchor slips:

      1. the root IS the parent of the MAIN checkout -- not of the working one
      2. the main checkout is a real checkout of this toolkit, not a guess
      3. the main checkout is itself one of the root's enumerated children

    (2) and (3) are what stop (1) from being satisfied by two wrong values that
    happen to agree: a `main_repo_root()` that returned nonsense would fail (2),
    and a root that is not actually the parent would fail (3).
    """
    root = Path(root).resolve()
    main = Path(census.main_repo_root()).resolve()

    assert root == (main / "..").resolve(), (
        "%s resolves to %s; the MAIN checkout's parent is %s. A root derived "
        "from the WORKING checkout is the measured worktree defect, and a "
        "count of what it enumerates cannot tell the two apart."
        % (what, root, (main / "..").resolve()))
    assert (main / "tools" / "manifest.json").is_file(), (
        "%s: main_repo_root() returned %s, which holds no tools/manifest.json, "
        "so it is not a checkout of this toolkit at all" % (what, main))
    children = {path.name for path in root.iterdir() if path.is_dir()}
    assert main.name in children, (
        "%s: the main checkout %r is not among the %d director(ies) under %s, "
        "so this root is not its parent" % (what, main.name, len(children), root))
    return root


@pytest.fixture(scope="module")
def manifest():
    assert MANIFEST_PATH.is_file(), MANIFEST_PATH
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def canon():
    assert SNAPSHOT_PATH.is_file(), SNAPSHOT_PATH
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


# The 12 rows of the project overview document's own path table, which is an INDEPENDENT source
# from the canon. The 11 canon-extracted slugs must equal this minus the
# substrate row; agreement between two sources is what makes the extraction
# checkable rather than merely self-consistent.
PROJECT_MD_TABLE = {
    "alpha-substrate", "alpha-artifact-1", "alpha-artifact-2", "alpha-artifact-3",
    "alpha-artifact-4", "alpha-artifact-5", "alpha-artifact-6",
    "beta-artifact-1", "beta-artifact-2",
    "beta-artifact-3", "beta-artifact-4",
    "beta-artifact-5",
}


def _scanned(manifest):
    return [s for s in manifest["slugs"] if s["scanned"]]


def _rows(manifest):
    return [s for s in manifest["slugs"] if s["register_row"]]


# ---------------------------------------------------------------------------
# THE HEADLINE: the literal is a tripwire on the derivation's own input
# ---------------------------------------------------------------------------

def test_counts_block_declares_both_literals(manifest):
    """Named failure, never a KeyError, when a literal is absent.

    The counts block's key set is asserted FIRST so that a manifest carrying
    only derived numbers fails by SAYING SO, rather than by exploding in the
    test that depends on it.
    """
    counts = manifest["counts"]
    required = {"scanned_derived", "register_rows_derived",
                "scanned_expected", "register_rows_expected"}
    missing = sorted(required - set(counts))
    assert not missing, (
        "counts is missing %d committed literal(s): %s. Without them both "
        "counts are PURELY DERIVED, and a purely derived count stops checking "
        "the moment a slug is dropped -- expected falls to match found and "
        "nothing errors. Present keys: %s"
        % (len(missing), missing, sorted(counts))
    )


def test_counts_derived_and_asserted(manifest):
    """Drop one slug; BOTH assertions must fail. This is G1's discrimination.

    The point is not that the counts are currently right. It is that they are
    checked against something the derivation cannot move. A manifest whose
    expectation is recomputed from its own list can lose thirteen slugs and
    still report a clean 1 of 1.
    """
    counts = manifest["counts"]
    scanned_expected = counts["scanned_expected"]
    rows_expected = counts["register_rows_expected"]

    # Baseline: intact, both derivations meet their literals.
    assert len(_scanned(manifest)) == scanned_expected == 14
    assert len(_rows(manifest)) == rows_expected == 12

    # Drop a slug that is BOTH scanned and register-row bearing, so one
    # deletion is capable of moving both numbers.
    victim = next(s for s in manifest["slugs"]
                  if s["scanned"] and s["register_row"])
    shrunk = {"slugs": [s for s in manifest["slugs"]
                        if s["slug"] != victim["slug"]]}

    derived_scanned = len(_scanned(shrunk))
    derived_rows = len(_rows(shrunk))

    assert derived_scanned != scanned_expected, (
        "dropping %r left the scanned derivation at %d, still equal to the "
        "literal %d -- the tripwire did not fire"
        % (victim["slug"], derived_scanned, scanned_expected)
    )
    assert derived_rows != rows_expected, (
        "dropping %r left the register-row derivation at %d, still equal to "
        "the literal %d -- the tripwire did not fire"
        % (victim["slug"], derived_rows, rows_expected)
    )
    assert derived_scanned == scanned_expected - 1
    assert derived_rows == rows_expected - 1


def test_derived_counts_match_their_literals_today(manifest):
    counts = manifest["counts"]
    assert len(_scanned(manifest)) == counts["scanned_derived"] \
        == counts["scanned_expected"] == 14
    assert len(_rows(manifest)) == counts["register_rows_derived"] \
        == counts["register_rows_expected"] == 12
    assert len(manifest["slugs"]) == 14
    assert len({s["slug"] for s in manifest["slugs"]}) == 14, "duplicate slug"


# ---------------------------------------------------------------------------
# Slug extraction: BOTH separators, and a short list is a FINDING
# ---------------------------------------------------------------------------

def test_slug_extraction_handles_both_separators(canon):
    """alpha writes `slug: ...`; example-beta writes `slug - ...`."""
    rows = [row for canon_rows in canon["build_paths"].values()
            for row in canon_rows]
    parsed = [row["slug"] for row in rows if row["slug"]]
    assert len(parsed) == snap.EXPECTED_BUILD_PATH_SLUGS == 11, parsed

    colon = [r for r in canon["build_paths"]["example-alpha"]]
    dash = [r for r in canon["build_paths"]["example-beta"]]
    assert all(r["artifact"].startswith(r["slug"] + ":") for r in colon), \
        "alpha's separator is not a colon in every row"
    assert all(r["artifact"].startswith(r["slug"] + " -") for r in dash), \
        "example-beta's separator is not space-dash in every row"


def test_removing_one_separator_is_a_finding_not_a_short_list(canon):
    """A parser keyed on ONE separator returns 6 or 5 and NOTHING ERRORS.

    The fixture is copied from the committed snapshot's verbatim `artifact`
    strings and mangled, so the mangling is applied to the real text rather
    than to an invented one.
    """
    mangled = {"build_paths": []}
    for canon_slug in ("example-alpha", "example-beta"):
        for row in canon["build_paths"][canon_slug]:
            artifact = row["artifact"]
            if canon_slug == "example-beta":
                # Remove the space-dash-space separator this canon uses.
                artifact = artifact.replace(" - ", " ", 1)
            mangled["build_paths"].append(
                {"project": row["project"], "artifact": artifact})

    parsed = [r["slug"] for r in snap.extract_build_path_slugs(mangled)
              if r["slug"]]
    assert len(parsed) == 6, (
        "expected the one-separator parse to drop example-beta's 5 rows, "
        "leaving 6; got %d" % len(parsed))

    message = snap.slug_count_message(len(parsed))
    assert "expected 11, found" in message, message
    assert "6" in message


def test_eleven_extracted_slugs_equal_the_project_md_table(canon, manifest):
    """Two INDEPENDENT sources agreeing is what makes the extraction checkable."""
    extracted = {row["slug"] for rows in canon["build_paths"].values()
                 for row in rows if row["slug"]}
    assert len(extracted) == 11, sorted(extracted)
    assert extracted == PROJECT_MD_TABLE - {"alpha-substrate"}, (
        "canon-extracted slugs disagree with the project overview document's table: only in "
        "canon %s; only in the project overview document %s"
        % (sorted(extracted - PROJECT_MD_TABLE),
           sorted(PROJECT_MD_TABLE - {"alpha-substrate"} - extracted))
    )
    manifest_slugs = {s["slug"] for s in manifest["slugs"]}
    assert PROJECT_MD_TABLE <= manifest_slugs, sorted(
        PROJECT_MD_TABLE - manifest_slugs)
    assert manifest_slugs - PROJECT_MD_TABLE == {
        "example-cache-benchmark", "example-search-benchmark"}


# ---------------------------------------------------------------------------
# a design rule: an exclusion must carry a reason
# ---------------------------------------------------------------------------

def test_every_excluded_slug_carries_a_reason(manifest):
    excluded = [s for s in manifest["slugs"] if not s["register_row"]]
    assert len(excluded) == 2, [s["slug"] for s in excluded]
    for entry in excluded:
        reason = entry.get("no_row_reason", "")
        assert isinstance(reason, str) and len(reason) >= 10, (
            "%s has register_row: false with a %d-character reason -- a design rule "
            "requires an explicit one" % (entry["slug"], len(reason)))
    assert {s["slug"] for s in excluded} == {
        "alpha-substrate", "example-search-benchmark"}


def test_included_slugs_carry_no_stray_reason(manifest):
    for entry in _rows(manifest):
        assert "no_row_reason" not in entry, (
            "%s has register_row: true but carries a no_row_reason"
            % entry["slug"])


def test_gpu_required_is_an_explicit_boolean_on_all_fourteen(manifest):
    """Never absent. An absent flag reads as False and is indistinguishable."""
    for entry in manifest["slugs"]:
        assert "gpu_required" in entry, entry["slug"]
        assert isinstance(entry["gpu_required"], bool), (
            "%s: gpu_required is %r, not a bool"
            % (entry["slug"], entry["gpu_required"]))
    gpu = sorted(s["slug"] for s in manifest["slugs"] if s["gpu_required"])
    # BOTH SIDES ARE SORTED, and the right-hand sort is not decoration.
    #
    # The left side is built with sorted(); the literal beside it was written
    # in sorted order too, which made the assertion depend on the ALPHABETICAL
    # ORDER OF THE SLUG NAMES THEMSELVES. A publish rewrite rule substitutes
    # strings in place and cannot reorder a list, so the moment the exported
    # copy renames these three to neutral names with a different collation the
    # literal stops being sorted and the assertion fails -- in the EXPORT only,
    # over a manifest that is perfectly correct. Measured: that is exactly what
    # happened, and it was the single failure in an otherwise green exported
    # suite of 906.
    #
    # Sorting the expected side costs nothing here (this list is already in
    # order, so the local reading is unchanged) and removes the dependence.
    # Equality between two sorted lists is still exact multiset equality, so
    # the assertion is no weaker -- a missing, extra or duplicated slug still
    # fails it.
    assert gpu == sorted(["beta-artifact-1",
                          "alpha-artifact-5", "alpha-artifact-4"]), gpu
    assert manifest["gpu_required_basis"], "the basis must be stated"


# ---------------------------------------------------------------------------
# The negative claim, verified with a BULLET-SCOPED probe
# ---------------------------------------------------------------------------

def test_document_and_bullet_scoped_probes_disagree(canon, capsys):
    """A negative is only as strong as its pattern AND its scope.

    A whole-document scan of example-beta returns ONE hit for
    example-search-benchmark, at $.consistency_notes[13], whose text says the
    artifact is "cited nowhere here" -- the canon AFFIRMING the exclusion. A
    document-scoped check reports a false citation and inverts the finding.
    Both numbers are recorded so the discrepancy is visible, not hidden.
    """
    record = canon["slug_citations"]["example-beta"]["example-search-benchmark"]
    document = record["document"]
    bullets = record["bullets"]

    print("example-search-benchmark in example-beta: document=%d bullets=%d "
          "locations=%s" % (document, bullets, record["locations"]))

    assert document != bullets, (
        "the two scopes agree (%d == %d). If they ever do agree the recorded "
        "trap has changed shape and the scoping rule needs re-deriving."
        % (document, bullets))
    assert document == 1, document
    assert bullets == 0, (
        "bullet-scoped hits must be 0 for a project requirement's exclusion to hold; got %d"
        % bullets)
    assert record["locations"] == ["$.consistency_notes[13]"], \
        record["locations"]

    # ... and the located hit must actually say what the exclusion relies on.
    assert record["bullet_population"] == 29, record["bullet_population"]


def test_redis_is_the_only_artifact_backed_bullet(canon, manifest):
    """Corroboration, re-derived: P5-B3's own backing field says so."""
    hits = sorted(
        key for key, b in canon["bullets"].items()
        if "example-cache-benchmark" in "\n".join(
            str(b.get(f) or "") for f in
            ("text", "metric", "metric_basis", "backing")))
    assert hits == ["example-beta:P5-B3"], hits
    assert "ONLY artifact-backed bullet" in \
        canon["bullets"]["example-beta:P5-B3"]["backing"]

    entry = next(s for s in manifest["slugs"]
                 if s["slug"] == "example-cache-benchmark")
    assert entry["backs_bullets"] == hits, (
        "the manifest's backs_bullets for redis was not derived from the "
        "canon: %s vs %s" % (entry["backs_bullets"], hits))
    assert entry["bullets"] == [], (
        "redis is not a canon EXAMPLE PROJECT, so it owns no project bullets; "
        "what it does is BACK one, which is a different relationship")


def test_bullets_partition_the_canon_exactly_once(manifest, canon):
    """50 vs 49 was a MEASURED defect, and this is the assertion that caught it.

    example-beta:P5-B3 is a bullet of example-beta P5 AND is backed by the
    existing redis artifact. Both are true. One `bullets` field would have
    claimed it twice and reported the 49-bullet partition as 50, which is why
    `backs_bullets` exists as a separate relationship.
    """
    known = set(canon["bullets"])
    owned = [b for s in manifest["slugs"] for b in s["bullets"]]
    assert owned, "0 owned bullet ids across the whole manifest"

    unknown = sorted(set(owned) - known)
    assert not unknown, (
        "%d manifest bullet id(s) do not exist in the canon snapshot: %s"
        % (len(unknown), unknown))

    assert len(owned) == len(set(owned)), (
        "a bullet is owned twice: %s"
        % sorted({b for b in owned if owned.count(b) > 1}))
    assert len(owned) == canon["counts"]["bullets_total"] == 49, (
        "the 11 canon paths own %d bullets; the canon holds %d"
        % (len(owned), canon["counts"]["bullets_total"]))
    assert set(owned) == known, sorted(known ^ set(owned))

    # Only canon example projects own bullets; only non-build-path artifacts back one.
    for entry in manifest["slugs"]:
        if entry["project"]:
            assert entry["bullets"], entry["slug"]
            assert entry["backs_bullets"] == [], entry["slug"]
        else:
            assert entry["bullets"] == [], entry["slug"]

    backed = [b for s in manifest["slugs"] for b in s["backs_bullets"]]
    assert backed == ["example-beta:P5-B3"], backed
    assert set(backed) <= known


# ---------------------------------------------------------------------------
# The scan root: ONE assertion with two ends (a design rule -> a design rule)
# ---------------------------------------------------------------------------

def test_declared_scan_root_resolves_equal_to_conftest_scan_root(manifest):
    """Criterion as written in the plan, and it is the correct half.

    an earlier plan pinned the constant, before this manifest existed.
    This is where the manifest is made to agree with it. Both ends are compared
    by PATH RESOLUTION from the same anchor, and the declared spelling is
    compared too -- a manifest that resolved equal by accident while declaring
    a different rule would agree today and diverge on the next checkout.
    """
    declared = manifest["scan_root"]["relative_to_repo_root"]
    assert declared == conftest.SCAN_ROOT_RELATIVE, (
        "the manifest declares scan root %r; conftest declares %r. The "
        "disagreement IS the finding -- neither is a value to pick over the "
        "other." % (declared, conftest.SCAN_ROOT_RELATIVE))

    # FINDING SITE 1, and the only one of an earlier finding's four whose worktree failure can be
    # established by READING. `conftest.SCAN_ROOT` is MAIN_REPO_ROOT / declared;
    # this line resolved the SAME declared rule against the WORKING checkout,
    # so the two sides used different anchors and disagreed in exactly the
    # environment the pair exists to reconcile. The rule is one rule, so both
    # ends now resolve it against the same anchor.
    resolved = (conftest.MAIN_REPO_ROOT / declared).resolve()
    assert resolved == conftest.SCAN_ROOT, (
        "declared scan root resolves to %s, conftest.SCAN_ROOT is %s"
        % (resolved, conftest.SCAN_ROOT))
    assert conftest.SCAN_ROOT == (conftest.MAIN_REPO_ROOT / "..").resolve(), (
        "conftest.SCAN_ROOT stopped being main-anchored, which is the defect "
        "this pair was re-keyed to catch")
    assert manifest["scan_root"]["depth"] == conftest.SCAN_DEPTH == 1


def test_no_suite_module_resolves_a_parent_path_against_the_WORKING_checkout():
    """an earlier finding's durable half: stop the defect class recurring, not just its four.

    THE MEASURED PROBLEM. Four tests failed inside an agent worktree and passed
    from the main checkout, at the same commit -- 971/970/1/0 against
    971/960/7/4. The count had gone from three to four because a plan written
    the same day anchored a NEW test on the working root, so the class is not
    static: every plan that writes `REPO_ROOT / ".."` adds an instance, and
    every instance is invisible from a green main run.

    THE RULE, and it is mechanical. A path that leaves this repository -- any
    `..` component -- is describing something BESIDE THE MAIN CHECKOUT: the
    scan root, the live store, a sibling artifact slug. Inside a worktree the
    working root is `<main>/agent-worktrees/worktrees/agent-<id>`, so the same
    expression lands two levels deep in a directory that holds sibling
    worktrees. `conftest.MAIN_REPO_ROOT` is the anchor that resolves the same
    in both places; `conftest.REPO_ROOT` is not.

    WHY THIS IS A SOURCE SCAN AND NOT A WORKTREE RUN. A worktree probe is the
    direct measurement and it is unavailable here: this phase runs sequentially
    on the main tree precisely BECAUSE the worktree is broken, and
    `conformance.py --self` reports the main checkout's scope from inside one,
    so a worktree cannot even verify itself. A source scan is available on
    every run, costs nothing, and fails on the line that introduces the defect
    rather than on a green suite somebody ran in the wrong place.
    """
    tests_dir = REPO_ROOT / "tools" / "tests"
    modules = sorted(tests_dir.glob("test_*.py"))
    assert len(modules) >= 20, (
        "found %d test module(s) under %s -- a scan this small is not a scan "
        "of the suite" % (len(modules), tests_dir))

    # PARSED, NOT GREPPED, and the first draft of this test is why. A text
    # scan for the pattern matched three DOCSTRINGS that describe the defect --
    # including the two in this file and the one in test_register.py, both
    # written by this same plan. That is the live-versus-frozen split in its
    # sharpest form: the prose explaining a retired rule is indistinguishable
    # from the rule itself to a regex, so documenting the fix disarms the check
    # guarding it. An AST walk sees expressions and never sees prose.
    hits = []
    for module in modules:
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=module.name)
        for node in ast.walk(tree):
            target = None
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                target = (node.left, [node.right])
            elif (isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Attribute)
                  and node.func.attr == "join"
                  and node.args):
                target = (node.args[0], list(node.args[1:]))
            if target is None:
                continue
            left, rights = target
            name = (left.id if isinstance(left, ast.Name)
                    else left.attr if isinstance(left, ast.Attribute) else "")
            if name != "REPO_ROOT":
                continue
            for right in rights:
                if isinstance(right, ast.Constant) and isinstance(right.value, str):
                    if ".." in right.value:
                        hits.append("%s:%d REPO_ROOT joined with %r"
                                    % (module.name, node.lineno, right.value))

    print("parsed %d module(s) for a working-anchored parent path; found %d"
          % (len(modules), len(hits)))
    assert not hits, (
        "%d site(s) resolve a path that leaves the repository against the "
        "WORKING checkout. Inside a worktree each lands in "
        "<main>/agent-worktrees/worktrees, which is a population nobody confirmed. "
        "Use conftest.MAIN_REPO_ROOT:\n%s" % (len(hits), "\n".join(hits)))

    # The scan has to be able to FIND one, or a clean result says nothing about
    # the suite and everything about the walk. A synthetic module carrying the
    # exact defect is parsed with the same code and must come back as a hit.
    control = ast.parse('X = REPO_ROOT / "../information"\n', filename="<control>")
    found = [n for n in ast.walk(control)
             if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div)
             and isinstance(n.left, ast.Name) and n.left.id == "REPO_ROOT"
             and isinstance(n.right, ast.Constant) and ".." in n.right.value]
    assert len(found) == 1, (
        "the walk did not flag a control that carries the defect, so its zero "
        "over the real suite is a property of the walk")


def test_the_scan_root_constants_are_invariant_under_a_worktree_anchor():
    """The same property, measured rather than linted -- and without a worktree.

    `resolve_worktree_main_root` is the pure half of `main_repo_root()`, split
    out exactly so the worktree branch is testable from the main checkout. Feed
    it the marker a real worktree writes and the scan root derived from its
    answer must equal the one derived here. If it ever does not, every
    anchoring assertion in this suite is measuring the wrong tree and no green
    run would say so.
    """
    marker = "gitdir: %s/.git/worktrees/agent-x" % \
        conftest.MAIN_REPO_ROOT.as_posix()
    pretend_worktree = str(conftest.MAIN_REPO_ROOT / "agent-worktrees" / "worktrees"
                           / "agent-x")

    resolved = Path(census.resolve_worktree_main_root(
        pretend_worktree, marker)).resolve()
    assert resolved == conftest.MAIN_REPO_ROOT, (
        "from a worktree the main root resolves to %s; from here it is %s"
        % (resolved, conftest.MAIN_REPO_ROOT))
    assert (resolved / "..").resolve() == conftest.SCAN_ROOT, (
        "the scan root is not invariant under the worktree anchor")

    # ... and the value a working-anchored derivation WOULD have produced is
    # named, so the difference this guards against is a measurement rather
    # than a description.
    naive = (Path(pretend_worktree) / "..").resolve()
    assert naive != conftest.SCAN_ROOT, (
        "the naive anchor agrees here, so this test cannot discriminate")
    print("worktree-invariant scan root %s; the naive anchor would give %s"
          % (conftest.SCAN_ROOT, naive))


def test_declared_scan_root_never_ENUMERATES_the_broken_fixture_tree(manifest):
    """a design rule -> a design rule, RE-KEYED from non-containment to NON-ENUMERATION.

    THE PLAN'S ORIGINAL CRITERION CANNOT BE SATISFIED, and this docstring
    records the substitution so a reader sees a reasoned re-key rather than a
    silent miss. The plan asked for:

        "the manifest's declared scan root does not CONTAIN
         fixtures/broken-artifacts/ ... by path resolution"

    This repository lives INSIDE its own scan root, so the fixture tree IS a
    descendant of it -- the assertion below proves that rather than assuming
    it. Making the original criterion pass would require shrinking the scan
    root, which would (a) invent a constraint nobody asked for and (b) break
    the reconciliation in the test above, which requires the manifest to
    declare the REAL scan root.

    The property a design rule actually needs is that no part of the fixture tree is
    ever ENUMERATED as an artifact candidate. conformance.py enumerates the
    IMMEDIATE CHILDREN of the scan root (depth 1); the fixture tree sits
    deeper. That is what is asserted here, exactly as an earlier plan already
    asserted it for the conftest end of the same pair.
    """
    declared = manifest["scan_root"]["relative_to_repo_root"]
    # Main-anchored, for the reason given at FINDING SITE 1 above. Resolved against
    # the WORKING checkout this test PASSED VACUOUSLY inside a worktree -- over
    # the two or three sibling worktrees rather than the artifact slugs -- which
    # is a recorded defect's recorded silent pass and is why it never appeared in an earlier finding's list.
    scan_root = (conftest.MAIN_REPO_ROOT / declared).resolve()
    fixtures = conftest.BROKEN_FIXTURES_DIR.resolve()

    assert scan_root.is_dir(), scan_root
    assert fixtures.is_dir(), fixtures

    # (a) CONTAINMENT HOLDS. Stated as an assertion so the re-key is justified
    #     by a measurement instead of by this docstring.
    assert fixtures.is_relative_to(scan_root), (
        "the fixture tree is NOT contained in the scan root, which would make "
        "the plan's original criterion satisfiable after all -- re-read it "
        "before keeping this re-key")

    # (b) BUT IT SITS DEEPER THAN THE ENUMERATION REACHES.
    depth = len(fixtures.relative_to(scan_root).parts)
    assert depth > manifest["scan_root"]["depth"], (
        "the fixture tree is %d level(s) below the scan root and enumeration "
        "reaches %d -- a design rule no longer holds by depth"
        % (depth, manifest["scan_root"]["depth"]))

    # (c) AND IS THEREFORE NEVER ENUMERATED.
    enumerated = sorted(child.resolve() for child in scan_root.iterdir()
                        if child.is_dir())
    assert enumerated, (
        "enumerated 0 directories under %s -- an empty scan set makes every "
        "'not in' assertion below vacuously true" % scan_root)
    assert fixtures not in enumerated, (
        "the fixture tree is one of the %d enumerated candidates under %s"
        % (len(enumerated), scan_root))

    broken_children = sorted(child.resolve() for child in fixtures.iterdir()
                             if child.is_dir())
    assert broken_children, (
        "the design rule fixture tree holds 0 subdirectories -- an unseeded tree "
        "makes the per-child assertion vacuous")
    for child in broken_children:
        assert child not in enumerated, child


def test_non_enumeration_holds_against_the_REAL_artifact_root_too(manifest):
    """The same property, re-checked over the population that actually matters.

    MEASURED WEAKNESS this closes. conftest.REPO_ROOT is derived from __file__,
    so inside a git worktree the declared rule `..` resolves to
    agent-worktrees/worktrees and enumerates TWO agent directories rather than the ~25
    trees under <home>/Research. Every "is not among the enumerated" assertion
    above still passes there -- over a population that is not the one a design rule is
    about. A pass over a population you did not confirm has verified nothing,
    so this repeats the check against the root anchored to the MAIN checkout,
    which is <home>/Research in an ordinary checkout AND in a worktree.
    """
    root = _artifact_root()
    fixtures = conftest.BROKEN_FIXTURES_DIR.resolve()
    assert root.is_dir(), root

    # FINDING SITE 2. The `>= 10` floor that stood here asserted a fact about ONE
    # MACHINE'S LAYOUT; see the helper's docstring for what replaced it and why
    # the replacement is strictly stronger rather than a relaxation.
    assert_scan_root_is_the_main_checkouts_parent(root, "the real artifact root")

    enumerated = sorted(child.resolve() for child in root.iterdir()
                        if child.is_dir())
    assert enumerated, (
        "enumerated 0 directories under %s -- an empty scan set makes every "
        "'not in' assertion below vacuously true" % root)

    assert fixtures.is_relative_to(root), (
        "containment does not hold against the real artifact root either")
    depth = len(fixtures.relative_to(root).parts)
    assert depth > manifest["scan_root"]["depth"], depth
    assert fixtures not in enumerated

    # The per-child half is where the discrimination lives, so its own
    # population is counted rather than assumed: an unseeded fixture tree would
    # make the loop below iterate zero times and report a pass.
    children = sorted(c.resolve() for c in fixtures.iterdir() if c.is_dir())
    assert len(children) >= 5, (
        "the fixture tree holds %d subdirector(ies); the non-enumeration "
        "assertion needs a seeded tree to discriminate" % len(children))
    for child in children:
        assert child not in enumerated, child

    # The manifest-versus-filesystem corroboration that used to sit here as
    # `built <= names` MOVED to test_a_built_slug_whose_directory_is_missing_is
    # _a_FAIL, which is where that property already lived. It was a duplicate,
    # and it is the half that cannot hold in a tree the artifact slugs do not
    # sit beside.


# ---------------------------------------------------------------------------
# The status rule: status, and the semantics the owner accepted
# ---------------------------------------------------------------------------

def _artifact_root():
    """Where the artifact slugs actually live.

    Anchored to the MAIN checkout deliberately. conftest.REPO_ROOT is derived
    from __file__, so inside a git worktree conftest.SCAN_ROOT resolves to
    agent-worktrees/worktrees rather than to <home>/Research -- MEASURED, and reported
    as a finding by an earlier plan rather than patched here, because
    tools/tests/conftest.py belongs to an earlier plan.
    """
    return (Path(census.main_repo_root()) / "..").resolve()


def test_status_is_built_or_pending_on_every_slug(manifest):
    for entry in manifest["slugs"]:
        assert entry.get("status") in ("built", "pending"), (
            "%s: status is %r; the status rule fixes the values to built | pending"
            % (entry["slug"], entry.get("status")))
    counts = manifest["counts"]
    built = [s for s in manifest["slugs"] if s["status"] == "built"]
    pending = [s for s in manifest["slugs"] if s["status"] == "pending"]
    assert len(built) == counts["built_expected"] == 2, \
        sorted(s["slug"] for s in built)
    assert len(pending) == counts["pending_expected"] == 12
    assert len(built) + len(pending) == 14
    assert manifest["status_field"], "the status rule's semantics must travel with the field"


def test_a_built_slug_whose_directory_is_missing_is_a_FAIL(manifest):
    """the status rule, preserved from CHECK-05's original behaviour.

    RE-KEYED by an earlier plan from `every built slug has a directory` to `the
    manifest's world is present or absent, never PARTIAL`, and the change is
    smaller than it sounds.

    The old form asserted that the artifact directories sit beside this
    checkout. That is true on the owner's machine and false everywhere else --
    in a published export, on a fresh clone, on a reviewer's laptop -- so the
    assertion was about a LAYOUT rather than about the manifest. What it was
    actually catching is a STALE MANIFEST: a row still marked `built` after its
    directory was renamed or removed. That defect always leaves a PARTIAL
    world, because the other built rows are still there, and a partial world is
    detectable in any tree.

    So: if the tree holds ANY of the manifest's slugs, it must hold every built
    one. A tree that holds none of them is not a stale manifest, it is a tree
    the world does not live in, and reporting that as a finding would be
    reporting the reader's checkout rather than the manifest.

    The predicate itself -- a built slug with no directory IS a finding -- is
    proven hermetically over a seeded world by
    test_conformance.py::test_a_missing_built_slug_is_a_finding, so nothing
    here rests on the owner's directories being present.
    """
    root = _artifact_root()
    assert root.is_dir(), root
    enumerated = {p.name for p in root.iterdir() if p.is_dir()}
    assert enumerated, "enumerated 0 directories -- the check would be vacuous"

    built = [s["slug"] for s in manifest["slugs"] if s["status"] == "built"]
    assert built, "0 built slugs makes this assertion vacuous"
    known = {s["slug"] for s in manifest["slugs"]}
    present = sorted(known & enumerated)
    missing = [slug for slug in built if slug not in enumerated]

    assert not (missing and present), (
        "%d slug(s) marked built have no directory under %s while %d other "
        "manifest slug(s) do. A PARTIAL world is a stale manifest: %s"
        % (len(missing), root, len(present), missing))

    # The population, printed, because this assertion's strength depends on it
    # and the honest statement of what was traded away belongs beside it: with
    # `present` empty the partial-world rule cannot fire, so a tree where EVERY
    # built slug vanished at once passes here. That case is an export or a
    # fresh clone far more often than it is a defect, and the hermetic
    # predicate in test_conformance.py covers the defect either way.
    print("built=%d present=%d missing=%d root=%s"
          % (len(built), len(present), len(missing), root))


def test_a_pending_slug_whose_directory_exists_is_a_FINDING(manifest):
    """the status rule: a stale manifest is a finding, not a silent upgrade."""
    root = _artifact_root()
    enumerated = {p.name for p in root.iterdir() if p.is_dir()}
    assert enumerated, "enumerated 0 directories -- the check would be vacuous"

    pending = [s["slug"] for s in manifest["slugs"] if s["status"] == "pending"]
    assert pending, "0 pending slugs makes this assertion vacuous"
    stale = [slug for slug in pending if slug in enumerated]
    assert not stale, (
        "%d slug(s) marked pending already have a directory under %s: %s -- "
        "the manifest is stale. status is owner/plan-set-set, so this is "
        "an owner edit, never a build-agent one."
        % (len(stale), root, stale))


def test_pending_reaching_zero_is_the_closeout_criterion(manifest):
    """a project requirement. The field earns its keep instead of being bookkeeping."""
    assert "a project requirement" in manifest["status_field"]
    pending = sum(1 for s in manifest["slugs"] if s["status"] == "pending")
    assert pending == manifest["counts"]["pending_derived"]
    # Today it is 12; the assertion is that the number is TRACKED, not that it
    # has any particular value -- it falls by one per phase through an earlier round.
    assert pending > 0, (
        "pending has reached 0 -- that is a project requirement's closeout criterion and "
        "should be surfaced to the owner, not absorbed silently")


# ---------------------------------------------------------------------------
# G2: the naming decision travels WITH the expected set
# ---------------------------------------------------------------------------

def test_naming_block_records_g2(manifest):
    naming = manifest["naming"]
    assert naming["figures"] == "results/figures.json"
    assert naming["expected_set"] == "tools/manifest.json"
    assert naming["banned"].startswith("results/")
    assert naming["banned"].endswith("manifest.json")
    assert naming["banned"] != naming["expected_set"]
    assert "the banned-spelling rule" in naming["note"]


def test_manifest_is_ascii_and_has_no_absolute_paths():
    """A tracked file must not bake in a home directory."""
    raw = MANIFEST_PATH.read_bytes()
    raw.decode("ascii")
    text = raw.decode("utf-8")
    assert not re.search(r"[A-Za-z]:[/\\]", text), \
        "an absolute path leaked into the manifest"
    assert "an-account-name" not in text


def test_min_population_overrides_is_present_as_an_object(manifest):
    """a design rule's adopted addition: a per-artifact floor override when one is needed."""
    assert isinstance(manifest["min_population_overrides"], dict)
