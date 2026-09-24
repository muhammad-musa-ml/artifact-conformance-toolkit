"""`tools/build_register.py` -- the GENERATED register and its refusal.

The inherited register header literally said *"Figures here are copied from that
artifact's own results/RESULTS.md"*. That copy is the last hop in the whole
program where a human retypes a number, and two earlier findings overturn it: the register is
GENERATED, and only the similarity JUDGMENT is hand-written -- in
`register-fragments/<slug>.md`, numeral-free.

a design rule is the second subject. The shared pattern note supplies a shipped instance of exactly
the failure it legislates against: a regenerator with partial knowledge silently
rewrote a real score to `n/a` on every run, for an unknown period. a design rule's posture
is stronger and cheaper -- refuse to regenerate and write NOTHING.

The load-bearing test is test_trailer_mismatch_refuses_and_writes_nothing, and
it asserts the file's BYTES are unchanged by hashing it either side rather than
believing the tool's own claim about what it did.
"""

import datetime
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT
REGISTER_PATH = REPO_ROOT / "tools" / "build_register.py"
MANIFEST_PATH = REPO_ROOT / "tools" / "manifest.json"


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


register = _load("build_register_under_test", REGISTER_PATH)

MANIFEST = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
ROW_SLUGS = [s["slug"] for s in MANIFEST["slugs"] if s.get("register_row")]
NO_ROW = [s for s in MANIFEST["slugs"] if not s.get("register_row")]


# ---------------------------------------------------------------------------
# Fixtures -- synthetic artifacts under tmp_path, never the real Research tree
# ---------------------------------------------------------------------------

def _figures(slug, figure_id="p95_latency_ms", value=41.6, canon_value="about 40 ms",
             similar="CONFIRMS", population=500):
    return {
        "schema": "figures/1",
        "schema_version": 1,
        "artifact": slug,
        "gate_token": "0" * 64,
        "dated_at": "2026-09-15",
        "started_at": "2026-09-15T09:00:00+03:00",
        "started_at_utc": "2026-09-15T06:00:00Z",
        "figures": {
            figure_id: {
                "value": value,
                "unit": "ms",
                "population": population,
                "population_label": "replayed requests",
                "derived_from": ["results/raw.json"],
                "canon_bullet": "example-beta:BP-5-B2",
                "canon_value": canon_value,
                "similar": similar,
                "similar_reason_ref": "register-fragments/%s.md" % slug,
                "tier_achieved": "T1",
                "reproduce_criterion": {"kind": "relative", "tolerance": 0.1},
                "threshold_claim": False,
                "not_shown": "Nothing here was run on managed cloud.",
            }
        },
    }


def _artifact(root, slug, **kwargs):
    results = Path(root) / slug / "results"
    results.mkdir(parents=True, exist_ok=True)
    (results / "figures.json").write_text(
        json.dumps(_figures(slug, **kwargs), indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    return results.parent


_CLEAN_FRAGMENT = """# {slug}

verdict: CONFIRMS

The measured value sits on the same side of the canon's claim and in the same
order of magnitude, over the same denominator the bullet names. A reader of the
bullet would not be misled.
"""


def _fragment(fragments_dir, slug, text=None):
    Path(fragments_dir).mkdir(parents=True, exist_ok=True)
    path = Path(fragments_dir) / ("%s.md" % slug)
    path.write_text(text if text is not None
                    else _CLEAN_FRAGMENT.format(slug=slug),
                    encoding="utf-8", newline="\n")
    return path


def _manifest_for(tmp_path, slugs, excluded=None):
    """A synthetic manifest whose committed literal matches its row count."""
    excluded = excluded or []
    entries = []
    for slug in slugs:
        entries.append({"slug": slug, "register_row": True, "scanned": True,
                        "status": "built", "canon": "example-beta",
                        "project": "BP-5", "bullets": [], "backs_bullets": [],
                        "gpu_required": False})
    for slug, reason in excluded:
        entries.append({"slug": slug, "register_row": False, "scanned": True,
                        "status": "pending", "canon": "example-beta",
                        "project": "BP-0", "bullets": [], "backs_bullets": [],
                        "gpu_required": False, "no_row_reason": reason})
    payload = {
        "schema": "manifest/1", "schema_version": 1,
        "counts": {"register_rows_expected": len(slugs),
                   "scanned_expected": len(entries)},
        "slugs": entries,
    }
    path = Path(tmp_path) / "manifest.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8", newline="\n")
    return path


def _world(tmp_path, slugs=("example-cache-benchmark",), excluded=None,
           fragment_text=None):
    """One complete synthetic world: artifacts, fragments, manifest, paths."""
    root = Path(tmp_path)
    artifacts = root / "Research"
    artifacts.mkdir(parents=True, exist_ok=True)
    fragments = root / "repo" / "register-fragments"
    for slug in slugs:
        _artifact(artifacts, slug)
        _fragment(fragments, slug, fragment_text)
    manifest = _manifest_for(root, list(slugs), excluded)
    return {
        "artifacts_root": artifacts,
        "fragments_dir": fragments,
        "manifest": manifest,
        "register": root / "repo" / "backing-artifacts.md",
        "mirror": artifacts / "backing-artifacts.md",
    }


def _build(world, **kwargs):
    return register.build(
        artifacts_root=world["artifacts_root"],
        fragments_dir=world["fragments_dir"],
        manifest_path=world["manifest"],
        register_path=world["register"],
        mirror_path=world["mirror"],
        **kwargs)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# a design rule -- the refusal
# ---------------------------------------------------------------------------

def test_trailer_mismatch_refuses_and_writes_nothing(tmp_path):
    """THE a design rule TEST. The proof is the file's BYTES, not the tool's claim."""
    world = _world(tmp_path)
    _build(world)
    assert world["register"].is_file()

    edited = world["register"].read_text(encoding="utf-8").replace(
        "500", "5000")
    assert "5000" in edited, "the edit did not take; the test proves nothing"
    world["register"].write_text(edited, encoding="utf-8", newline="")

    before = _sha(world["register"])
    with pytest.raises(register.RegisterError) as caught:
        _build(world)
    after = _sha(world["register"])

    assert before == after, (
        "the register's bytes CHANGED across a refused build. A refusal that "
        "writes is not a refusal, and the edit it destroyed is exactly what "
        "a design rule exists to preserve"
    )
    assert "REFUS" in str(caught.value).upper()


def test_the_refusal_never_reaches_the_atomic_write(tmp_path, monkeypatch):
    """The check must run BEFORE the write call, not after it."""
    world = _world(tmp_path)
    _build(world)
    world["register"].write_text(
        world["register"].read_text(encoding="utf-8") + "\nhand edit\n",
        encoding="utf-8", newline="")

    calls = []
    monkeypatch.setattr(register.core, "atomic_write_text",
                        lambda *a, **k: calls.append(a))
    with pytest.raises(register.RegisterError):
        _build(world)
    monkeypatch.undo()

    assert calls == [], (
        "atomic_write_text was called %d time(s) on the refusal path. A "
        "trailer-checked refusal that happens after the write is not a refusal"
        % len(calls)
    )


def test_the_refusal_prints_the_diff(tmp_path, capsys):
    world = _world(tmp_path)
    _build(world)
    world["register"].write_text(
        world["register"].read_text(encoding="utf-8")
        + "\nA HAND EDIT NOBODY GENERATED.\n", encoding="utf-8", newline="")

    code = register.main([
        "--artifacts-root", str(world["artifacts_root"]),
        "--fragments-dir", str(world["fragments_dir"]),
        "--manifest", str(world["manifest"]),
        "--register", str(world["register"]),
        "--mirror", str(world["mirror"])])
    out = capsys.readouterr().out
    assert code != 0
    assert "A HAND EDIT NOBODY GENERATED." in out, (
        "the refusal did not print the difference, so the operator cannot see "
        "what would have been destroyed"
    )


def test_an_append_after_the_trailer_is_refused(tmp_path):
    """REGRESSION. The body hash alone could not see this.

    Measured: with only the body-hash check, appending after the trailer left
    the body untouched, its hash matched, and the build regenerated straight
    over the appended lines -- discarding them silently. An append is the most
    likely way anyone edits a generated file, so a guard blind to it is blind to
    the common case.
    """
    world = _world(tmp_path)
    _build(world)
    text = world["register"].read_text(encoding="utf-8")
    assert text.rstrip().endswith("-->"), "the trailer is not last in the file"

    world["register"].write_text(
        text + "\nA NOTE SOMEONE ADDED AT THE BOTTOM.\n",
        encoding="utf-8", newline="")
    before = _sha(world["register"])

    assert register.body_sha256(
        world["register"].read_text(encoding="utf-8")) == \
        register.read_trailer(text)["body_sha256"], (
        "the body hash MOVED, so this fixture is not exercising the "
        "after-the-trailer case it exists for"
    )

    with pytest.raises(register.RegisterError) as caught:
        _build(world)
    assert _sha(world["register"]) == before, "the refusal wrote to the file"
    assert "APPENDED AFTER THE TRAILER" in str(caught.value)


def test_a_clean_regeneration_is_allowed(tmp_path):
    """The guard must not make the tool unusable: an untouched file regenerates.

    RE-KEYED. This asserted raw sha256 equality across two consecutive builds,
    and it passed for a reason that had nothing to do with the guard: the
    register's own `- generated:` stamp was the constant `2`, so a register
    written a day apart was byte-identical. The defect SUPPLIED the stability
    the assertion read as a result. With a real stamp the bytes move by design,
    and an assertion that cannot tell a clock tick from a refusal is not
    asserting the property this test is named for.

    So it is split into the two claims it was conflating:

      1. the guard ALLOWS the regeneration -- the property in the docstring,
         and the only one the old assertion could ever have been about;
      2. the bytes are stable given a fixed stamp -- byte-identity with the
         clock held still, which is what makes the equality discriminating
         rather than a statement about how fast the test ran.
    """
    world = _world(tmp_path)

    # 1. ALLOWED. A refusal raises RegisterError, so reaching the next line at
    #    all is the assertion; the sha comparison never tested this.
    _build(world)
    _build(world)
    first_text = world["register"].read_text(encoding="utf-8")

    stamped = re.sub(r"(?m)^- generated: .*$", "- generated: <stamp>",
                     first_text)
    assert stamped != first_text, (
        "no `- generated:` line was normalised, so the comparison below would "
        "be trivially true and would prove nothing")

    # 2. BYTE-IDENTICAL with the clock held still. Two builds at one pinned
    #    stamp must produce the same bytes; anything else is real drift.
    pinned = "2026-09-15T09:00:00+03:00"
    _build(world, dated_at=pinned)
    pinned_sha = _sha(world["register"])
    _build(world, dated_at=pinned)
    assert _sha(world["register"]) == pinned_sha, (
        "two regenerations at one pinned stamp produced different bytes, so "
        "something other than the clock is moving")


def test_the_body_hash_is_what_detects_a_hand_edit_not_the_inputs_hash(tmp_path):
    """DISCRIMINATING: an inputs-only trailer cannot see a hand edit at all.

    A hand edit changes the register's BODY and leaves every generation INPUT
    untouched, so a guard keyed only on the inputs hash would compare equal and
    regenerate straight over the edit -- passing while checking nothing.
    """
    world = _world(tmp_path)
    _build(world)
    text = world["register"].read_text(encoding="utf-8")
    trailer = register.read_trailer(text)
    assert trailer is not None, "no trailer was emitted"
    assert re.fullmatch(r"[0-9a-f]{64}", trailer["inputs_sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", trailer["body_sha256"])

    edited = text.replace("CONFIRMS", "DOES-NOT-SUPPORT")
    world["register"].write_text(edited, encoding="utf-8", newline="")

    after = register.read_trailer(
        world["register"].read_text(encoding="utf-8"))
    assert after["inputs_sha256"] == trailer["inputs_sha256"], (
        "the hand edit moved the INPUTS hash, which would mean the inputs hash "
        "is not a hash of the inputs"
    )
    body_now = register.body_sha256(
        world["register"].read_text(encoding="utf-8"))
    assert body_now != after["body_sha256"], (
        "the body hash did not move under a hand edit, so it cannot detect one"
    )
    with pytest.raises(register.RegisterError):
        _build(world)


def test_the_inputs_hash_moves_when_a_figure_changes(tmp_path):
    world = _world(tmp_path)
    _build(world)
    first = register.read_trailer(
        world["register"].read_text(encoding="utf-8"))["inputs_sha256"]

    _artifact(world["artifacts_root"], "example-cache-benchmark", value=99.9)
    world["register"].unlink()
    _build(world)
    second = register.read_trailer(
        world["register"].read_text(encoding="utf-8"))["inputs_sha256"]
    assert second != first


# ---------------------------------------------------------------------------
# expected / found / excluded
# ---------------------------------------------------------------------------

def test_expected_is_read_from_the_manifest_and_never_typed(tmp_path, capsys):
    """N comes from tools/manifest.json's committed literal, read at run time."""
    world = _world(tmp_path, slugs=("alpha", "beta"))
    code = register.main([
        "--artifacts-root", str(world["artifacts_root"]),
        "--fragments-dir", str(world["fragments_dir"]),
        "--manifest", str(world["manifest"]),
        "--register", str(world["register"]),
        "--mirror", str(world["mirror"])])
    out = capsys.readouterr().out
    assert code == 0
    assert re.search(r"expected\s+2\b", out), out
    assert re.search(r"found\s+2\b", out), out


def test_expected_tracks_the_real_manifest_literal(tmp_path):
    """Against the REAL manifest, expected must equal its committed literal."""
    expected = MANIFEST["counts"]["register_rows_expected"]
    assert expected == len(ROW_SLUGS), (
        "the manifest's own literal (%d) disagrees with its derived row count "
        "(%d); that is the finding, not a value to pick between"
        % (expected, len(ROW_SLUGS))
    )
    world = _world(tmp_path, slugs=("example-cache-benchmark",))
    result = register.build(
        artifacts_root=world["artifacts_root"],
        fragments_dir=world["fragments_dir"],
        manifest_path=MANIFEST_PATH,
        register_path=world["register"],
        mirror_path=world["mirror"],
        allow_shortfall=True)
    assert result["expected"] == expected
    assert result["found"] == 1


def test_excluded_slugs_are_counted_with_each_reason_verbatim(tmp_path, capsys):
    reasons = [("alpha-substrate",
                "Program factoring, not a canon example project: it backs no canon bullet."),
               ("example-search-benchmark",
                "Cited by no bullet in either canon.")]
    world = _world(tmp_path, slugs=("alpha",), excluded=reasons)
    code = register.main([
        "--artifacts-root", str(world["artifacts_root"]),
        "--fragments-dir", str(world["fragments_dir"]),
        "--manifest", str(world["manifest"]),
        "--register", str(world["register"]),
        "--mirror", str(world["mirror"])])
    out = capsys.readouterr().out
    assert code == 0
    assert re.search(r"excluded:\s*2\s*\(reasons recorded\)", out), out
    for slug, reason in reasons:
        assert slug in out
        assert reason in out, (
            "the recorded reason for %s was not printed VERBATIM; a design rule's whole "
            "point is that an exclusion carries its reason" % slug
        )


def test_every_excluded_reason_also_lands_in_the_register(tmp_path):
    reasons = [("alpha-substrate", "It backs no canon bullet.")]
    world = _world(tmp_path, slugs=("alpha",), excluded=reasons)
    _build(world)
    text = world["register"].read_text(encoding="utf-8")
    assert "alpha-substrate" in text
    assert "It backs no canon bullet." in text


def test_an_exclusion_without_a_reason_fails(tmp_path):
    """a design rule requires register_row: false PLUS a no_row_reason."""
    world = _world(tmp_path, slugs=("alpha",), excluded=[("orphan", "")])
    with pytest.raises(register.RegisterError) as caught:
        _build(world)
    assert "orphan" in str(caught.value)
    assert "no_row_reason" in str(caught.value)


def test_a_row_slug_with_no_figures_is_a_shortfall_and_is_named(tmp_path, capsys):
    world = _world(tmp_path, slugs=("alpha", "beta"))
    (world["artifacts_root"] / "beta" / "results" / "figures.json").unlink()
    code = register.main([
        "--artifacts-root", str(world["artifacts_root"]),
        "--fragments-dir", str(world["fragments_dir"]),
        "--manifest", str(world["manifest"]),
        "--register", str(world["register"]),
        "--mirror", str(world["mirror"])])
    out = capsys.readouterr().out
    assert re.search(r"expected\s+2\b", out)
    assert re.search(r"found\s+1\b", out)
    assert "beta" in out
    assert code == 1, (
        "expected 2 but found 1 exited 0. A count that does not change the "
        "verdict is decoration"
    )


# ---------------------------------------------------------------------------
# The zero-population refusal
# ---------------------------------------------------------------------------

def test_zero_artifacts_is_did_not_run(tmp_path, capsys):
    world = _world(tmp_path, slugs=("alpha",))
    (world["artifacts_root"] / "alpha" / "results" / "figures.json").unlink()
    code = register.main([
        "--artifacts-root", str(world["artifacts_root"]),
        "--fragments-dir", str(world["fragments_dir"]),
        "--manifest", str(world["manifest"]),
        "--register", str(world["register"]),
        "--mirror", str(world["mirror"])])
    out = capsys.readouterr().out
    assert code == 2, (
        "zero artifacts reported %d. 'found a problem' and 'could not look' "
        "are different answers" % code
    )
    assert "DID-NOT-RUN" in out
    assert not world["register"].exists()
    assert not world["mirror"].exists()


# ---------------------------------------------------------------------------
# a design rule -- the numeral lint, BOTH rules
# ---------------------------------------------------------------------------

def test_a_bare_numeral_in_a_fragment_fails_and_names_the_line(tmp_path):
    world = _world(tmp_path, slugs=("alpha",), fragment_text=(
        "# alpha\n\nverdict: CONFIRMS\n\n"
        "The run came out at 41.6 which is close enough.\n"))
    with pytest.raises(register.RegisterError) as caught:
        _build(world)
    message = str(caught.value)
    assert "alpha.md" in message
    assert "41.6" in message
    assert "line" in message.lower(), (
        "the violation does not carry a line number, so it is not actionable"
    )


def test_a_figure_value_in_a_fragment_fails_the_value_rule(tmp_path):
    """ONLY the value rule can catch this; the shape allow-list ACCEPTS it.

    This is the discriminating fixture, and the first draft was not: it used a
    bare `500`, which the SHAPE rule rejects as an unclassified numeral, so it
    would have passed against an implementation with no value rule at all.

    Here the figure's value IS 8080 and the fragment writes "on port 8080".
    `canonkit.classify_numerals` classifies that as KIND_PORT -- allowed -- so
    the shape rule says clean. Only the value scan sees that a measured number
    has been retyped.
    """
    world = _world(tmp_path, slugs=("alpha",))
    _artifact(world["artifacts_root"], "alpha", value=8080)
    _fragment(world["fragments_dir"], "alpha",
              "# alpha\n\nverdict: CONFIRMS\n\n"
              "The service answered on port 8080 throughout.\n")

    # The shape rule ALONE must consider this clean, or the test is not
    # isolating the value rule.
    shape_only = register.lint_fragment(
        "alpha.md", "The service answered on port 8080 throughout.\n", None)
    assert shape_only == [], (
        "the shape allow-list already rejects this fixture, so it cannot "
        "demonstrate the value rule: %s" % shape_only
    )

    with pytest.raises(register.RegisterError) as caught:
        _build(world)
    message = str(caught.value)
    assert "8080" in message
    assert "VALUE" in message


def test_a_population_in_a_fragment_fails_the_value_rule(tmp_path):
    """A DENOMINATOR is a measured number too, and this must DISCRIMINATE.

    an earlier finding's recorded failure was deriving a numerator from a canon percentage and
    typing it into a sentence. A leak set covering only `value` leaves the
    denominator half of that wide open.

    THE FIRST DRAFT OF THIS TEST WAS NOT DISCRIMINATING and mutation testing
    caught it: it wrote a bare `500`, which the SHAPE rule rejects as an
    unclassified numeral, so it went on passing against a build_register whose
    leak set had been narrowed back to `value` only. The population here is
    therefore PORT-SHAPED and written behind a port cue, so the shape rule waves
    it through and only the leak set can see it.
    """
    world = _world(tmp_path, slugs=("alpha",))
    _artifact(world["artifacts_root"], "alpha", value=41.6, population=8080)
    text = ("# alpha\n\nverdict: CONFIRMS\n\n"
            "The replay ran against the service on port 8080.\n")
    _fragment(world["fragments_dir"], "alpha", text)

    assert register.lint_fragment("alpha.md", text, None) == [], (
        "the shape rule already rejects this fixture, so it cannot demonstrate "
        "that the leak set covers populations"
    )
    assert register.lint_fragment("alpha.md", text, [41.6]) == [], (
        "a leak set of VALUES only already rejects this fixture, so the test "
        "would pass against the `value`-only mutant it exists to catch"
    )

    with pytest.raises(register.RegisterError) as caught:
        _build(world)
    assert "8080" in str(caught.value)
    assert "VALUE" in str(caught.value)


def test_an_iso_date_and_a_bullet_id_in_a_fragment_are_allowed(tmp_path):
    """The allow-list must not make a legitimate fragment impossible to write."""
    world = _world(tmp_path, slugs=("alpha",), fragment_text=(
        "# alpha\n\nverdict: CONFIRMS\n\n"
        "Read against BP-5-B2 on 2026-09-15; the direction and the denominator\n"
        "both match what the bullet claims.\n"))
    result = _build(world)
    assert result["found"] == 1


def test_a_key_reference_in_a_fragment_is_allowed(tmp_path):
    """`{{figures.*}}` is the ONE permitted way to put a figure in prose."""
    world = _world(tmp_path, slugs=("alpha",), fragment_text=(
        "# alpha\n\nverdict: CONFIRMS\n\n"
        "The measured {{figures.p95_latency_ms}} sits on the same side of the\n"
        "canon's claim.\n"))
    result = _build(world)
    assert result["found"] == 1


def test_the_numeral_lint_shares_the_core_allow_list_with_d15(tmp_path):
    """a design rule and a design rule share ONE allow-list; two implementations would drift."""
    source = REGISTER_PATH.read_text(encoding="ascii")
    assert "classify_numerals" in source, (
        "the register lint does not use canonkit.classify_numerals, so a design rule and "
        "a design rule now have two allow-lists that will drift"
    )


def test_a_missing_fragment_is_counted_and_named(tmp_path, capsys):
    world = _world(tmp_path, slugs=("alpha", "beta"))
    (world["fragments_dir"] / "beta.md").unlink()
    code = register.main([
        "--artifacts-root", str(world["artifacts_root"]),
        "--fragments-dir", str(world["fragments_dir"]),
        "--manifest", str(world["manifest"]),
        "--register", str(world["register"]),
        "--mirror", str(world["mirror"])])
    out = capsys.readouterr().out
    assert "beta" in out
    assert code == 1


# ---------------------------------------------------------------------------
# a design rule -- tracked here, mirrored outside
# ---------------------------------------------------------------------------

def test_the_mirror_copy_is_byte_identical_to_the_tracked_register(tmp_path):
    """Run against a REDIRECTED root in tmp_path, never the real Research tree."""
    world = _world(tmp_path)
    _build(world)
    assert world["mirror"].is_file()
    assert world["mirror"].read_bytes() == world["register"].read_bytes(), (
        "the mirror is not byte-identical, so a reader browsing the artifacts "
        "and a reader of this repository see two different registers"
    )


def test_the_register_carries_no_carriage_return(tmp_path):
    world = _world(tmp_path)
    _build(world)
    assert b"\r" not in world["register"].read_bytes()
    assert b"\r" not in world["mirror"].read_bytes()


def test_the_artifacts_root_is_derived_from_the_MAIN_repo_root(tmp_path):
    """a recorded defect. A worktree-relative anchor scans ~2 directories and PASSES.

    `conftest.SCAN_ROOT` is `REPO_ROOT / ".."`, which inside an agent worktree
    resolves to `<repo>/agent-worktrees/worktrees` -- measured at 2 directories holding
    0 manifest slugs, against 25 directories holding 2 under the main root. A
    register generated over that population would look entirely fine.
    """
    derived = Path(register.default_artifacts_root()).resolve()
    main_root = Path(register.census.main_repo_root()).resolve()
    assert derived == (main_root / "..").resolve(), (
        "the artifacts root is not anchored to main_repo_root(); inside a "
        "worktree it will scan the wrong population and pass"
    )
    # RE-KEYED by an earlier plan. `derived.name == "Research"` is the name of ONE
    # DIRECTORY ON ONE MACHINE. It cannot hold in a published export, on a
    # fresh clone, or on anyone else's checkout, and it never added anything
    # the identity above does not already say. What replaces it is the other
    # half of the same anchor: the main root has to be a real checkout of this
    # toolkit, and it has to be one of the derived root's own children -- two
    # facts that a pair of wrong-but-agreeing values cannot both satisfy.
    assert (main_root / "tools" / "build_register.py").is_file(), (
        "main_repo_root() returned %s, which holds no tools/build_register.py, "
        "so it is not a checkout of this toolkit" % main_root)
    assert main_root.name in {p.name for p in derived.iterdir() if p.is_dir()}, (
        "the main checkout %r is not among the artifacts root's children, so "
        "%s is not its parent" % (main_root.name, derived))


def test_the_tracked_register_belongs_to_the_working_checkout():
    """Output that gets COMMITTED belongs to the checkout that produced it."""
    tracked = Path(register.default_register_path()).resolve()
    working = Path(register.working_repo_root()).resolve()
    assert tracked.parent == working


def test_build_prints_the_scan_root_and_the_population_it_covered(tmp_path, capsys):
    world = _world(tmp_path, slugs=("alpha", "beta"))
    register.main([
        "--artifacts-root", str(world["artifacts_root"]),
        "--fragments-dir", str(world["fragments_dir"]),
        "--manifest", str(world["manifest"]),
        "--register", str(world["register"]),
        "--mirror", str(world["mirror"])])
    out = capsys.readouterr().out
    assert str(world["artifacts_root"]) in out, "the scan root is not printed"
    assert "scanned" in out.lower()


def test_the_report_carries_a_schema_version(tmp_path):
    world = _world(tmp_path)
    report = Path(tmp_path) / "report.json"
    register.main([
        "--artifacts-root", str(world["artifacts_root"]),
        "--fragments-dir", str(world["fragments_dir"]),
        "--manifest", str(world["manifest"]),
        "--register", str(world["register"]),
        "--mirror", str(world["mirror"]),
        "--report", str(report)])
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["schema_version"] == register.SCHEMA_VERSION
    assert payload["expected"] == 1
    assert payload["found"] == 1


# ---------------------------------------------------------------------------
# The register is GENERATED
# ---------------------------------------------------------------------------

def test_the_figure_value_in_the_register_comes_from_figures_json(tmp_path):
    world = _world(tmp_path)
    _artifact(world["artifacts_root"], "example-cache-benchmark", value=7.25)
    _build(world)
    text = world["register"].read_text(encoding="utf-8")
    assert "7.25" in text, (
        "the register does not carry the measured value, so it is not generated "
        "from the artifact"
    )


def test_the_generated_line_carries_a_whole_timestamp(tmp_path):
    """The register's own date, on the DEFAULT path -- the one with the defect.

    `- generated:` is the register's `dated_at`: the one line that says when the
    document on disk was produced. The phase-close reading and a project requirement both
    quote it, so a stamp that is not a date makes the register undateable.

    THE DEFAULT PATH IS THE WHOLE POINT, and it is why this test passes no
    `dated_at`. An explicit stamp goes straight to `render()` and never touches
    the line that derives one, so a test that supplied its own would have agreed
    with the defect by construction -- the same reason test_canonkit parses the
    core's stamp instead of re-deriving it.
    """
    world = _world(tmp_path)
    _build(world)
    text = world["register"].read_text(encoding="utf-8")

    match = re.search(r"(?m)^- generated: (?P<stamp>.*)$", text)
    assert match is not None, (
        "the register carries no `- generated:` line at all:\n%s" % text)
    stamp = match.group("stamp")

    try:
        parsed = datetime.datetime.fromisoformat(stamp)
    except ValueError:
        parsed = None
    assert parsed is not None, (
        "the register's `- generated:` line reads %r, which is not an ISO-8601 "
        "timestamp. One character is what subscripting the core's stamp "
        "produces: `now_local()` returns a STRING, so taking element 0 of it "
        "takes the first CHARACTER of the year. Nothing errors and the line "
        "still renders, which is why this dated itself %r on every run until "
        "someone read the line instead of the exit code." % (stamp, stamp))
    assert parsed.tzinfo is not None, (
        "the register's `- generated:` stamp %r is NAIVE. a design rule needs a real UTC "
        "offset here: CHECK-02 compares a LOCAL date component against the "
        "README's date, and on this machine a silently-UTC stamp is wrong by a "
        "day for several hours of every day." % stamp)


def test_a_malformed_figures_json_fails_and_names_the_violation(tmp_path):
    world = _world(tmp_path)
    bad = world["artifacts_root"] / "example-cache-benchmark" / "results" / "figures.json"
    payload = json.loads(bad.read_text(encoding="utf-8"))
    payload["figures"]["p95_latency_ms"]["population"] = 0
    bad.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8", newline="\n")
    with pytest.raises(register.RegisterError) as caught:
        _build(world)
    assert "population" in str(caught.value)


# ---------------------------------------------------------------------------
# an earlier plan -- THE MIRROR MUST HONOUR ITS ROOT
#
# Measured before this plan, three times by three different sessions: a normal
# `pytest tools/tests` run left `<home>/Research/backing-artifacts.md` naming a
# pytest temp directory. The round trip invokes the CLI with `--artifacts-root
# <tmp>` and no `--mirror`; `default_mirror_path()` then ignored the root it was
# passed and resolved through `census.main_repo_root()` to the REAL file.
#
# That file is outside every git repository and is versioned by nothing, so the
# harm is silent and unrecoverable. It also defeats a design rule by construction: plan
# an earlier plan regenerates the register over the real scan root and the very next suite
# run -- including the pre-push hook's own -- undoes it.
#
# NOTE ON HOW THESE TESTS PROVE IT. None of them writes to the real path. The
# escape is demonstrated into a CONTROLLED fake by monkeypatching the anchor
# `default_artifacts_root()` resolves through, so the test can fail loudly
# without ever touching the owner's file. A test that proved this bug by letting
# it happen would re-commit the harm on every RED re-run.
# ---------------------------------------------------------------------------


def _fake_anchor(monkeypatch, tmp_path):
    """Point `default_artifacts_root()` at a throwaway stand-in for the real one.

    Returns the path the mirror WOULD land on if the generator ignores the root
    it was handed -- i.e. the sentinel location.

    THE SENTINEL IS A VALIDLY GENERATED REGISTER, not an arbitrary string, and
    that is the whole reason this helper exists rather than a one-line write.
    `_refuse_if_edited` already refuses to overwrite anything that does not look
    like generated output, so a sentinel reading `DO NOT OVERWRITE` is protected
    by a DIFFERENT guard and the test would pass for a reason having nothing to
    do with the one under test. The owner's real register is generated output
    with a valid trailer, which is precisely why nothing stopped the escape --
    so the fixture has to be generated output too, or it cannot express the
    defect.
    """
    fake_repo = Path(tmp_path) / "fake-checkout" / "repo"
    fake_repo.mkdir(parents=True, exist_ok=True)
    stand_in = fake_repo.parent / register.REGISTER_NAME

    # Generate a real one INSIDE its own root, then COPY the bytes to the
    # stand-in. Generating straight to the stand-in is refused by the very guard
    # under test -- correctly, since that is a throwaway scan publishing outside
    # itself -- and a fixture may not need the defect to exist in order to set
    # itself up. A byte copy is not a generation and involves no guard.
    decoy = _world(Path(tmp_path) / "decoy")
    register.build(artifacts_root=decoy["artifacts_root"],
                   fragments_dir=decoy["fragments_dir"],
                   manifest_path=decoy["manifest"],
                   register_path=decoy["register"],
                   mirror_path=decoy["mirror"])
    assert decoy["mirror"].is_file(), "the decoy register was not generated"
    stand_in.write_bytes(decoy["mirror"].read_bytes())

    monkeypatch.setattr(register.census, "main_repo_root", lambda *a, **k: str(fake_repo))
    return stand_in


def test_the_default_mirror_lands_inside_the_root_it_was_passed(tmp_path):
    """The defect at its source, in one call.

    `default_mirror_path()` took no root and resolved through the repository
    anchor, so a caller scanning one tree published into another.
    """
    root = Path(tmp_path) / "some-artifacts-root"
    root.mkdir(parents=True, exist_ok=True)
    mirror = Path(register.default_mirror_path(str(root)))
    assert mirror.parent.resolve() == root.resolve(), (
        "the default mirror for root %r landed at %r, outside it" % (str(root), str(mirror)))


def test_a_generation_with_no_mirror_flag_writes_nothing_outside_its_root(
        tmp_path, monkeypatch):
    """The harm itself, proven by a sha256 either side of the call.

    The sentinel sits where the mirror would land if the root were ignored. Its
    hash is taken before and after; an unchanged hash is the only evidence that
    nothing escaped, because a write of identical bytes is indistinguishable
    from no write by mtime alone.
    """
    stand_in = _fake_anchor(monkeypatch, tmp_path)
    before = _sha(stand_in)

    world = _world(tmp_path)
    register.build(artifacts_root=world["artifacts_root"],
                   fragments_dir=world["fragments_dir"],
                   manifest_path=world["manifest"],
                   register_path=world["register"])

    assert _sha(stand_in) == before, (
        "a generation scoped to %r wrote to %r, which is outside it"
        % (str(world["artifacts_root"]), str(stand_in)))


def test_a_throwaway_root_may_not_publish_outside_itself(tmp_path, monkeypatch):
    """The guard. A scan of a temp tree may never publish to a real location.

    Stated as the rule rather than as `refuse every temp root`, because the
    round trip legitimately scans a temp tree and writes its mirror INSIDE it --
    an earlier plan task 3 makes it name that mirror. What is forbidden is a
    throwaway scan reaching a path outside the tree it scanned.
    """
    stand_in = _fake_anchor(monkeypatch, tmp_path)
    world = _world(tmp_path)
    code = register.main([
        "--artifacts-root", str(world["artifacts_root"]),
        "--fragments-dir", str(world["fragments_dir"]),
        "--manifest", str(world["manifest"]),
        "--register", str(world["register"]),
        "--mirror", str(stand_in),
    ])
    assert code == register.core.EXIT_DID_NOT_RUN, (
        "a throwaway-rooted scan published to %r and returned %r"
        % (str(stand_in), code))


def test_the_throwaway_guard_is_by_resolution_not_by_string(tmp_path, monkeypatch):
    """A different spelling of the same directory still refuses.

    The conventions document, section 8 rule 8: a repository-relative anchor resolves
    differently inside a worktree, so every path comparison in this repository
    is by RESOLUTION. A guard keyed on a literal prefix is defeated by `..`.
    """
    stand_in = _fake_anchor(monkeypatch, tmp_path)
    world = _world(tmp_path)
    scenic = Path(str(world["artifacts_root"])) / ".." / world["artifacts_root"].name
    code = register.main([
        "--artifacts-root", str(scenic),
        "--fragments-dir", str(world["fragments_dir"]),
        "--manifest", str(world["manifest"]),
        "--register", str(world["register"]),
        "--mirror", str(stand_in),
    ])
    assert code == register.core.EXIT_DID_NOT_RUN, (
        "the same root spelled with a parent hop was not recognised: %r" % str(scenic))


def test_the_guard_discriminates_and_does_not_refuse_everything(tmp_path, monkeypatch):
    """A mirror INSIDE the scanned root is exactly the legitimate case.

    Without this the guard could be satisfied by refusing every run, which is
    the shape of a check that cannot tell its two arms apart.
    """
    _fake_anchor(monkeypatch, tmp_path)
    world = _world(tmp_path)
    code = register.main([
        "--artifacts-root", str(world["artifacts_root"]),
        "--fragments-dir", str(world["fragments_dir"]),
        "--manifest", str(world["manifest"]),
        "--register", str(world["register"]),
        "--mirror", str(world["mirror"]),
    ])
    assert code == 0, "a mirror inside the scanned root was refused"
    assert world["mirror"].is_file(), "the legitimate mirror was not written"


def test_the_refusal_names_the_root_and_carries_a_repair(tmp_path, monkeypatch, capsys):
    """A refusal nobody can act on is a stack trace with better manners."""
    stand_in = _fake_anchor(monkeypatch, tmp_path)
    world = _world(tmp_path)
    register.main([
        "--artifacts-root", str(world["artifacts_root"]),
        "--fragments-dir", str(world["fragments_dir"]),
        "--manifest", str(world["manifest"]),
        "--register", str(world["register"]),
        "--mirror", str(stand_in),
    ])
    printed = capsys.readouterr()
    combined = printed.out + printed.err
    assert "REFUSING:" in combined, combined
    assert "REPAIR:" in combined, combined
    assert str(world["artifacts_root"]).replace(chr(92), "/") in combined.replace(chr(92), "/"), (
        "the refusal does not name the root it was handed: %s" % combined)
    assert "scanned " in combined, (
        "the refusing branch printed no population line: %s" % combined)
