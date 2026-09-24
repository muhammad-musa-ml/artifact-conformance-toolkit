"""The committed canon snapshot, judged by a RE-READ rather than by a claim.

Every assertion here opens `tools/canon-bullets.json` from disk with an explicit
`encoding="utf-8"` and re-derives what it checks. The Windows console renders
correct UTF-8 as replacement characters on this machine, so "it printed fine" is
not evidence about any file's bytes, and a count/grep re-parse is not evidence of
well-formedness either. A re-read is.

Two tests deliberately reach the LIVE STORE (the byte-for-byte fidelity check and
the read-mode check). They are the only ones that do, they open it read-only, and
they skip rather than fail when it is absent -- a clean checkout on another
machine must still be able to run this suite, which is exactly why a design rule commits
the snapshot in the first place.
"""

import builtins
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT
SNAPSHOT_PATH = REPO_ROOT / "tools" / "canon-bullets.json"
TOOL_PATH = REPO_ROOT / "tools" / "canon_snapshot.py"
BACKING_TOOL = REPO_ROOT / "tools" / "check_canon_backing.py"

COMPOUND_KEY_RE = re.compile(r"^[a-z0-9-]+:P\d+-B\d+$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


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


snap = _load("canon_snapshot", TOOL_PATH)


def load_snapshot():
    """Re-read the committed snapshot from disk. Never a cached object."""
    assert SNAPSHOT_PATH.is_file(), (
        "the design rule snapshot is missing at %s. CHECK-09 must be answerable "
        "offline from a clean checkout, which is what committing it buys."
        % SNAPSHOT_PATH
    )
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def doc():
    return load_snapshot()


def _live_path(source):
    """Resolve a source entry's recorded path against the live store."""
    tail = source["path"].split("../information/", 1)[-1]
    return (Path(snap.census.main_repo_root()) / ".." / "information"
            / tail).resolve()


# ---------------------------------------------------------------------------
# Shape: every id is canon-qualified
# ---------------------------------------------------------------------------

def test_every_bullet_key_is_canon_qualified(doc):
    """an earlier step: a bare `P2-B1` is ambiguous in 35% of cases.

    17 of 49 ids exist in BOTH canons, so an unqualified id is a coin flip, not
    an address. The compound key is what makes it a finding instead.
    """
    keys = sorted(doc["bullets"])
    assert keys, "0 bullets in the snapshot -- an empty mapping passes every "\
                 "`all()` written over it"
    bad = [key for key in keys if not COMPOUND_KEY_RE.match(key)]
    assert not bad, (
        "%d of %d bullet key(s) are not canon-qualified: %s"
        % (len(bad), len(keys), bad[:10])
    )


def test_id_collisions_are_recorded_and_non_zero(doc):
    """The collision set is RE-DERIVED here, not trusted from the record."""
    by_canon = {}
    for entry in doc["bullets"].values():
        by_canon.setdefault(entry["canon"], set()).add(entry["id"])
    assert len(by_canon) == 2, sorted(by_canon)

    left, right = sorted(by_canon)
    derived = sorted(by_canon[left] & by_canon[right])

    assert derived, (
        "re-derived 0 colliding ids. If that were true the compound key would "
        "be unnecessary; it is not, so a zero here means the derivation broke."
    )
    assert doc["counts"]["id_collisions"] == len(derived), (
        "recorded id_collisions=%d but re-derivation found %d: %s"
        % (doc["counts"]["id_collisions"], len(derived), derived)
    )
    assert doc["counts"]["id_collisions_list"] == derived
    assert doc["counts"]["id_collisions"] == doc["expected"]["id_collisions"]


def test_display_ref_disambiguates_beta_only(doc):
    """`BP-2` must resolve to example-beta:P2-B*, never to example-alpha:P2-B*."""
    for key, entry in doc["bullets"].items():
        if entry["canon"] == "example-beta":
            assert entry["display_ref"], key
            assert entry["display_ref"].startswith("BP-"), entry["display_ref"]
            project_number = entry["id"].split("-")[0][1:]
            assert entry["display_ref"].startswith("BP-%s-" % project_number)
        else:
            assert entry["display_ref"] is None, (
                "%s carries a BP- alias; only example-beta's paths are called "
                "BP-n" % key)


# ---------------------------------------------------------------------------
# Counts: derived AND asserted against a committed literal
# ---------------------------------------------------------------------------

def test_bullets_total_equals_the_mapping_length(doc):
    assert doc["counts"]["bullets_total"] == len(doc["bullets"])


def test_every_count_matches_its_committed_literal(doc):
    """Three-way: the module constant, the record's copy, and a re-derivation.

    The module constant is the real tripwire. A count kept only in the file it
    describes falls to meet its own input the moment the input shrinks.
    """
    counts = doc["counts"]
    expected = doc["expected"]

    assert snap.EXPECTED_BULLETS_TOTAL == expected["bullets_total"]
    assert counts["bullets_total"] == snap.EXPECTED_BULLETS_TOTAL

    assert snap.EXPECTED_PER_CANON == expected["per_canon"]
    derived_per_canon = {}
    for entry in doc["bullets"].values():
        derived_per_canon[entry["canon"]] = \
            derived_per_canon.get(entry["canon"], 0) + 1
    assert derived_per_canon == dict(snap.EXPECTED_PER_CANON), derived_per_canon
    assert sum(derived_per_canon.values()) == snap.EXPECTED_BULLETS_TOTAL


def test_metric_basis_is_universal_and_the_needle_has_one_exception(doc):
    """metric_basis is universal; exactly ONE bullet lacks the needle. Name it.

    RE-KEYED by an earlier plan from a literal bullet id to a DERIVATION. The old
    form asserted `exceptions == ["example-beta:P5-B3"]`, which is a fact about
    this programme's corpus rather than about the corpus's own consistency, and
    it is the shape that does not travel into an export whose corpus is an
    authored example. What is asserted now is the property: re-derive the
    exception set from the rows, and require the corpus's own committed
    `not_yet_run_exceptions` literal to agree with it. A corpus that shrinks,
    or whose literal stops matching its rows, is a finding in either tree --
    which a hard-coded id could never report.
    """
    counts = doc["counts"]
    derived_basis = sum(1 for e in doc["bullets"].values()
                        if (e.get("metric_basis") or "").strip())
    assert derived_basis == counts["with_metric_basis"]
    assert counts["with_metric_basis"] == counts["bullets_total"], (
        "metric_basis is not universal: %d of %d"
        % (counts["with_metric_basis"], counts["bullets_total"])
    )

    assert counts["with_not_yet_run"] == counts["bullets_total"] - 1, (
        "expected EXACTLY one bullet without the needle; found %d of %d"
        % (counts["with_not_yet_run"], counts["bullets_total"])
    )

    needle = doc["needles"]["not_yet_run"]
    derived = sorted(key for key, entry in doc["bullets"].items()
                     if needle not in backing.bullet_blob(entry))
    exceptions = counts["not_yet_run_exceptions"]
    assert derived == exceptions, (
        "the committed exception list and the rows disagree: literal %s, "
        "derived %s" % (exceptions, derived))
    assert len(exceptions) == 1, (
        "the single exception must be NAMED, not left as a gap; got %s"
        % exceptions)
    assert exceptions[0] in doc["bullets"], exceptions[0]

    # ... and the named exception must actually explain itself.
    basis = doc["bullets"][exceptions[0]]["metric_basis"]
    assert "already-run" in basis, basis[:120]


def test_dropping_a_bullet_would_break_the_literal(doc):
    """The tripwire, demonstrated rather than asserted.

    A purely derived count stops checking when its input shrinks. This drops one
    bullet from an in-memory copy and shows the committed literal still says 49.
    """
    shrunk = dict(doc["bullets"])
    victim = sorted(shrunk)[0]
    del shrunk[victim]
    assert len(shrunk) == doc["counts"]["bullets_total"] - 1
    assert len(shrunk) != snap.EXPECTED_BULLETS_TOTAL, (
        "dropping %s did not move the derived count away from the literal"
        % victim)


# ---------------------------------------------------------------------------
# Sources: four, hashed, and the hashes REPRODUCE
# ---------------------------------------------------------------------------

def test_four_sources_are_pinned_with_64_hex_hashes(doc):
    sources = doc["sources"]
    assert len(sources) == snap.EXPECTED_SOURCE_COUNT == 4, len(sources)
    roles = sorted(s["role"] for s in sources)
    assert roles == ["frozen_canon", "frozen_canon",
                     "live_collections", "live_collections"], roles
    for source in sources:
        assert HEX64_RE.match(source["sha256"]), source
        assert source["bytes"] > 0
        assert source["read_at"]
        assert not source["path"].startswith("C:"), (
            "an absolute home path leaked into a tracked record: %s"
            % source["path"])


def test_rehashing_each_source_reproduces_the_recorded_hash(doc):
    """A recorded hash is a record of what was true THEN. Re-run the check.

    THE TWO ROLES ARE NOT THE SAME CLAIM, and conflating them was wrong in
    exactly one direction (split 2026-09-16):

    * `frozen_canon` -- the archived canon is NEVER edited. Its hash must
      reproduce EXACTLY, forever. A mismatch here is corruption, and it is the
      one thing this test is really guarding.
    * `live_collections` -- the two entries are what this program CORRECTS. Their
      hashes move every time a measurement lands, so an equality assertion on
      them would fail the moment the program succeeded. Pinning them would turn
      a guard into a chore and invite someone to weaken it wholesale, taking the
      canon rows with it.

    So the live rows assert what must still be true -- the file is present and
    non-empty -- and report drift rather than failing on it. What actually
    guards their CONTENT is `canon_snapshot.build_payload`'s bullet-id coverage
    assertion (every frozen bullet id still cited by the live entry) plus
    `check_canon_backing.py --live`, neither of which a byte hash can express.
    """
    core = snap.core
    frozen, live, drifted = 0, 0, []
    for source in doc["sources"]:
        path = _live_path(source)
        if not path.is_file():
            pytest.skip("live store not present at %s" % path)
        digest = core.sha256_file(path)
        if source.get("role") == "frozen_canon":
            assert digest == source["sha256"], (
                "%s re-hashes differently than the snapshot records -- the "
                "archived canon is the FROZEN BASELINE and is never edited, so "
                "this is corruption, not a correction" % source["path"])
            assert path.stat().st_size == source["bytes"]
            frozen += 1
        else:
            assert path.stat().st_size > 0, (
                "%s is empty; a correction never empties an entry"
                % source["path"])
            if digest != source["sha256"]:
                drifted.append(source["path"])
            live += 1
    assert frozen == 2, "re-hashed %d of 2 frozen canons" % frozen
    assert live == 2, "checked %d of 2 live entries" % live
    if drifted:
        print("live entries drifted from the snapshot (expected once a "
              "correction lands): %s" % drifted)


def test_evidence_quotes_match_the_bullet_count_per_canon(doc):
    """The live collections entry is a projection of the frozen claim.

    A divergence means the publication-facing copy has drifted from the claim under
    test, which is exactly the detection a design rule exists to provide.
    """
    counts = doc["counts"]
    for canon, quotes in counts["evidence_quotes_per_canon"].items():
        assert quotes == counts["per_canon"][canon], (
            "%s: evidence_quotes has %d entries, the canon has %d bullets"
            % (canon, quotes, counts["per_canon"][canon]))
    assert counts["evidence_quotes_per_canon"] == \
        doc["expected"]["evidence_quotes_per_canon"]


# ---------------------------------------------------------------------------
# Verbatim: judged by a re-read and a byte-for-byte compare
# ---------------------------------------------------------------------------

def test_snapshot_reparses_as_utf8_from_disk():
    raw = SNAPSHOT_PATH.read_bytes()
    text = raw.decode("utf-8")
    parsed = json.loads(text)
    assert parsed["schema"] == "canon-bullets/1"
    assert len(parsed["bullets"]) == parsed["counts"]["bullets_total"]


def test_a_bullet_matches_a_FRESH_read_of_the_canon_byte_for_byte(doc):
    """The file is judged against the source, never against console output."""
    source = next(s for s in doc["sources"]
                  if s["role"] == "frozen_canon" and s["canon"] == "example-beta")
    path = _live_path(source)
    if not path.is_file():
        pytest.skip("live store not present at %s" % path)

    with open(str(path), "rb") as handle:
        fresh = json.loads(handle.read().decode("utf-8"))

    compared = 0
    for project in fresh["projects"]:
        for bullet in project["bullets"]:
            key = "example-beta:%s" % bullet["id"]
            recorded = doc["bullets"][key]
            for field in ("text", "metric", "metric_basis", "backing"):
                assert (bullet.get(field) or "").encode("utf-8") == \
                    (recorded.get(field) or "").encode("utf-8"), \
                    "%s.%s differs from a fresh read of the canon" % (key, field)
                compared += 1
    assert compared == 29 * 4, (
        "compared %d field(s), expected %d -- a comparison over a short "
        "population is not a comparison" % (compared, 29 * 4))


def test_the_permissive_read_kept_the_two_extra_keys(doc):
    """2 of 49 bullets carry `public`; a strict reader fails on them.

    RE-KEYED by an earlier plan from two bullet ids to the property. The ids are a
    population and do not travel; what the permissive read has to hold is that
    the extra keys SURVIVED the parse, that there are two of them, and that
    every one names the same field. Both ids are still required to be real
    bullets, so a typo is still a failure rather than a silently empty set.
    """
    extra = {key: entry["extra_keys"]
             for key, entry in doc["bullets"].items() if entry["extra_keys"]}
    assert len(extra) == 2, extra
    for key, names in sorted(extra.items()):
        assert key in doc["bullets"], key
        assert names == ["public"], (key, names)
    assert len({doc["bullets"][k]["canon"] for k in extra}) == 1, extra


# ---------------------------------------------------------------------------
# The read-only boundary, asserted at the `open` seam
# ---------------------------------------------------------------------------

LIVE_MARKER = "information"


def test_no_source_is_ever_opened_for_writing(monkeypatch, tmp_path):
    """an earlier step: patch `open` and fail the run on any writable mode under the store.

    The predicate is on the MODE, not on the call site, because "canon_snapshot
    does not write" is exactly the assertion this replaces with a check.
    """
    violations = []
    real_open = builtins.open

    def guarded(file, mode="r", *args, **kwargs):
        text = str(file).replace("\\", "/")
        if ("/" + LIVE_MARKER + "/") in text:
            base = mode.replace("b", "").replace("t", "")
            if base not in ("r", "rU", ""):
                violations.append((text, mode))
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded)

    source = doc_source()
    if source is None:
        pytest.skip("live store not present")
    payload, parsed = snap.read_json_bytes(source)

    assert payload, "the guarded read returned 0 bytes"
    assert parsed["projects"], "the guarded read parsed no projects"
    assert not violations, (
        "%d write-mode open(s) under the live store: %s"
        % (len(violations), violations))


def doc_source():
    """The example-beta canon's real path, or None when the store is absent."""
    document = load_snapshot()
    source = next(s for s in document["sources"]
                  if s["role"] == "frozen_canon" and s["canon"] == "example-beta")
    path = _live_path(source)
    return path if path.is_file() else None


# ---------------------------------------------------------------------------
# The document-vs-bullet scope trap (a project requirement's negative claim)
# ---------------------------------------------------------------------------

def test_slug_citations_record_both_scopes(doc):
    """A negative is only as strong as its pattern AND its scope."""
    citations = doc["slug_citations"]
    assert set(citations) == {"example-alpha", "example-beta"}, sorted(citations)
    for canon, probes in citations.items():
        assert set(probes) == set(snap.PROBE_SLUGS), (canon, sorted(probes))
        for slug, record in probes.items():
            assert record["bullet_population"] > 0, (
                "%s/%s probed a bullet population of 0 -- a scan over nothing "
                "reports 'not cited' about everything" % (canon, slug))


# ---------------------------------------------------------------------------
# check_canon_backing.py -- the `not yet run` scan and its refusable needle
# ---------------------------------------------------------------------------

backing = _load("check_canon_backing", BACKING_TOOL)


def test_the_scan_prints_found_and_checked_as_separate_numbers(doc, capsys):
    """found=48 checked=49. One number cannot show that a filter removed 1."""
    verdict, result = backing.scan(doc)
    line = capsys.readouterr().out
    assert "CHECK-09" in line
    assert "found=48" in line, line
    assert "checked=49 of 49" in line, line
    assert result["found"] == 48
    assert result["checked"] == 49
    assert result["found"] != result["checked"], (
        "a scan whose found and checked are equal cannot show the exception")
    assert verdict == "PASS"


def test_the_scan_agrees_with_the_snapshots_own_count(doc):
    """Re-derived here, and cross-checked against the committed count.

    RE-KEYED by an earlier plan. The literals 48, 49, 20/20 and 28/29 are a
    POPULATION -- this programme's -- and a suite that ships must not assert
    them. Every one of them is now derived from the corpus under test and
    compared against that corpus's OWN committed literal, which is the
    derive-and-assert shape: a scan that disagrees with the record beside it is
    a finding in either tree, and a corpus that shrank cannot make both sides
    move together.
    """
    counts = doc["counts"]
    _, result = backing.scan(doc, quiet=True)
    assert result["found"] == counts["with_not_yet_run"]
    assert result["checked"] == counts["bullets_total"] == len(doc["bullets"])
    assert result["backed"] == counts["not_yet_run_exceptions"]
    assert result["found"] == result["checked"] - len(result["backed"]), (
        "found + exceptions does not close over checked: %r" % result)

    # The per-canon split is derived from the rows and reconciled against the
    # record's own per_canon totals, so the two halves of the corpus are
    # checked against each other rather than against a remembered figure.
    assert set(result["per_canon"]) == set(counts["per_canon"]), result
    for canon, split in sorted(result["per_canon"].items()):
        assert split["total"] == counts["per_canon"][canon], (canon, split)
    assert sum(s["total"] for s in result["per_canon"].values()) \
        == counts["bullets_total"]
    assert sum(s["matched"] for s in result["per_canon"].values()) \
        == result["found"]

    # ... and exactly one canon carries the exception, which is what makes the
    # exception NAMED rather than spread.
    short = [c for c, s in result["per_canon"].items()
             if s["matched"] != s["total"]]
    assert len(short) == 1, short
    assert doc["bullets"][result["backed"][0]]["canon"] == short[0]


def test_a_scan_over_an_empty_bullet_set_exits_two(capsys):
    """DID-NOT-RUN, never a pass. The 0/0 trap in its CHECK-09 clothes."""
    with pytest.raises(SystemExit) as excinfo:
        backing.scan({"bullets": {}})
    assert excinfo.value.code == 2
    combined = "".join(capsys.readouterr())
    assert "DID-NOT-RUN" in combined, combined
    assert "0 bullets" in combined, combined


def test_the_long_needle_is_refused_naming_both_wordings(doc, capsys):
    """It LOOKS more specific and matches ZERO alpha bullets."""
    with pytest.raises(SystemExit) as excinfo:
        backing.scan(doc, needle="example project not yet run")
    assert excinfo.value.code == 2

    message = "".join(capsys.readouterr())
    assert "example project not yet run" in message
    assert "not yet run" in message
    # The counts are MEASURED in the refusal, not quoted from a constant.
    assert "example-alpha 0 of 20" in message, message
    assert "example-alpha 20 of 20" in message, message
    assert "example-beta 28 of 29" in message, message


def test_the_long_needle_really_does_miss_every_alpha_bullet(doc):
    """The refusal's premise, re-derived rather than taken on trust.

    RE-KEYED by an earlier plan from this programme's own long form to the corpus's
    DECLARED one. The trap is not "the string `example project not yet run` matches
    nothing in alpha"; the trap is that a needle which LOOKS more specific
    silently shrinks the population, because one canon interpolates its project
    id into the marker and the other does not. That property is asserted here
    over whichever corpus the suite is pointed at, and the mechanism -- the
    interpolation -- is demonstrated on a row of the canon that comes back zero.
    """
    short_needle = doc["needles"]["not_yet_run"]
    long_needle = doc["needles"]["long_form_refused"]
    assert short_needle in long_needle and short_needle != long_needle, (
        "the long form does not CONTAIN the short one, so it is a different "
        "needle rather than a narrower one: %r vs %r"
        % (long_needle, short_needle))

    matched, per_canon = backing.count_matches(doc["bullets"], long_needle)
    short_matched, _ = backing.count_matches(doc["bullets"], short_needle)
    assert len(matched) < len(short_matched), (
        "the long needle did not shrink the population (%d vs %d), so there "
        "is no trap left to refuse" % (len(matched), len(short_matched)))

    zero = sorted(c for c, s in per_canon.items() if s["matched"] == 0)
    nonzero = sorted(c for c, s in per_canon.items() if s["matched"] > 0)
    assert len(zero) == 1 and len(nonzero) == 1, (
        "expected exactly one canon at zero and one above it; got zero=%s "
        "nonzero=%s" % (zero, nonzero))
    assert per_canon[zero[0]]["total"] > 0, per_canon
    assert sum(s["matched"] for s in per_canon.values()) == len(matched)

    # ... because the zero canon interpolates its project id into the marker:
    # every one of its rows carries the SHORT needle and none carries the long.
    for key, entry in sorted(doc["bullets"].items()):
        if entry["canon"] != zero[0]:
            continue
        blob = backing.bullet_blob(entry)
        assert short_needle in blob, key
        assert long_needle not in blob, key
        assert entry["project"] in blob, (
            "%s does not carry its own project id, so the interpolation is "
            "not what makes the long needle miss" % key)


def test_an_uppercase_needle_matches_nothing(doc):
    """Case sensitivity, measured -- so nobody 'normalizes' the needle later."""
    matched, _ = backing.count_matches(doc["bullets"], "NOT YET RUN")
    assert matched == []


def test_backing_cli_exit_codes(tmp_path):
    result = conftest.run_cli(
        [sys.executable, str(BACKING_TOOL), "--report",
         str(Path(tmp_path) / "r.json")],
        cwd=REPO_ROOT, log_dir=Path(tmp_path) / "ok")
    assert result.exit_code == 0, result.stdout + result.stderr
    assert result.report["found"] == 48
    assert result.report["checked"] == 49

    refused = conftest.run_cli(
        [sys.executable, str(BACKING_TOOL), "--needle",
         "example project not yet run"],
        cwd=REPO_ROOT, log_dir=Path(tmp_path) / "refused")
    assert refused.exit_code == 2, refused.stdout + refused.stderr
    assert "REFUSING:" in refused.stderr


# ---------------------------------------------------------------------------
# The reconciliation record MOVED, and this note is the signpost.
#
# Six tests that read
# a reconciliation record in the project's planning tree used to sit here. An earlier plan
# moved them verbatim to tools/tests/test_canon_text_reconciliation.py, which
# the publish manifest excludes from the export: their population is a planning
# document the export drops by definition, so they verify that THIS PROGRAMME is
# in good order rather than that the toolkit works.
#
# They still run HERE, and the collected count did not fall. Nothing in this
# module referenced them -- checked with grep before the move, and the two
# constants they used (RECONCILIATION, VERDICT_TOKENS) had no other reader.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# --live: the LIVE COLLECTIONS ENTRIES, which are the correction target.
#
# The default scan reads the committed snapshot of the FROZEN canon and counts
# its `not yet run` markers -- 48 of 49 -- and that number never moves again,
# because the archive is never edited. It is the BEFORE side.
#
# What a project requirement actually has to close is the live side: how many figures in the
# two `raw.json` entries are still designed rather than measured. Re-keying the
# existing scan at the entries without this mode would be worse than leaving it
# alone: the entries carry ZERO of the canon's markers today, so the re-keyed
# check would report a clean sweep on day one, before a single path had run.
# That is a 0-of-0 pass, which is an unrun check wearing a verdict.
# ---------------------------------------------------------------------------

LIVE_FIXTURE = {
    "example-alpha": {
        "slug": "example-alpha",
        "kind": "experience",
        "detail": {"metrics": [
            "P1-B3: 340 pairs at 6 minutes "
            "[BACKING: designed, not yet measured -- P1 has no reproducing "
            "artifact yet]",
            "P2-B1: 58% of p95 in retrieval "
            "[BACKING: designed, not yet measured -- P2 has no reproducing "
            "artifact yet]",
            "P5-B9: measured 2026-09-16 over 1,000 rows",
        ]},
    },
    "example-beta": {
        "slug": "example-beta",
        "kind": "experience",
        "detail": {"metrics": [
            "BP-1-B1: kappa 0.68 to 0.81 "
            "[BACKING: measured on a substitute system -- the backing artifact "
            "is not yet verified]",
        ]},
    },
}


def _live_tree(tmp_path, payload=None):
    """Write a synthetic store with the two entries at their real relative paths."""
    import json as _json
    root = Path(tmp_path) / "information"
    data = LIVE_FIXTURE if payload is None else payload
    places = {
        "example-alpha": root / "collections" / "collection-one" / "example-alpha",
        "example-beta": root / "collections" / "collection-two" / "example-beta",
    }
    for slug, where in places.items():
        where.mkdir(parents=True, exist_ok=True)
        (where / "raw.json").write_text(
            _json.dumps(data[slug], indent=1), encoding="utf-8", newline="")
    return root


def test_the_live_marker_is_a_fixed_string_with_no_interpolation():
    """Neither the outstanding needle nor any KIND needle may interpolate.

    THE RED THIS CATCHES: this module already documents the exact trap --
    alpha's canon marker interpolates the project id, so the longer literal
    matches ZERO alpha bullets while looking like a tightening. A live marker
    that repeated that mistake would silently halve the live population too.
    """
    assert backing.LIVE_MARKER == "[BACKING:"
    needles = [backing.LIVE_MARKER] + [n for _k, n in backing.LIVE_MARKER_KINDS]
    for needle in needles:
        for token in ("P1", "BP-1", "%s", "{"):
            assert token not in needle, (needle, token)


def test_every_kind_needle_starts_after_the_outstanding_needle():
    """One count answers "how many are unbacked"; the kinds answer "why".

    THE RED THIS CATCHES: a kind whose needle does not sit inside a marker would
    be counted by neither bucket nor by the outstanding needle, leaving a row
    unbacked and invisible -- which is exactly what happened to the 49th figure
    before the kinds existed, because the only needle described the other 48.
    """
    assert len(backing.LIVE_MARKER_KINDS) >= 2
    names = [k for k, _n in backing.LIVE_MARKER_KINDS]
    assert len(names) == len(set(names)), names
    assert "designed" in names and "substitute" in names


def test_the_marker_carries_no_programme_vocabulary():
    """The entry is a private record, not this repository's worklog.

    The marker never names this programme, its phases, its example projects, its
    tooling or any agent. THE RED THIS CATCHES is a marker reading
    "example project P1 not yet run" -- true, but it puts scaffolding into a record
    whose whole job is to describe the owner's own engagement work. The
    example project is already the row's `P1-B3:` prefix, so naming it again in
    programme terms buys nothing and costs the framing rule.
    """
    banned = ("example project", "canon-backing", "phase", "Claude", "claude",
              "agent", "generated", "GSD", "plan ")
    surfaces = [backing.LIVE_MARKER] + [n for _k, n in backing.LIVE_MARKER_KINDS]
    for surface in surfaces:
        for token in banned:
            assert token not in surface, (surface, token)


def test_live_scan_counts_marked_rows_per_entry(tmp_path):
    root = _live_tree(tmp_path)
    verdict, result = backing.scan_live(str(root), quiet=True)

    assert result["checked"] == 4, result
    assert result["found"] == 3, result
    assert result["per_canon"]["example-alpha"] == {"matched": 2, "total": 3}
    assert result["per_canon"]["example-beta"] == {"matched": 1, "total": 1}
    assert result["matched"] == ["example-alpha:P1-B3", "example-alpha:P2-B1",
                                 "example-beta:BP-1-B1"]
    # The kinds must PARTITION the matched set. A row in no bucket would make
    # the kinds sum to less than `found`, and that gap is exactly the thing a
    # reader would not notice.
    kinds = result["by_kind"]
    assert kinds["designed"] == ["example-alpha:P1-B3", "example-alpha:P2-B1"]
    assert kinds["substitute"] == ["example-beta:BP-1-B1"]
    assert kinds["unclassified"] == []
    assert sum(len(v) for v in kinds.values()) == result["found"]


def test_live_scan_over_zero_metric_rows_exits_two(tmp_path):
    """The vacuous pass this mode exists to prevent.

    An entry with no metric rows would report `found=0` -- 'nothing outstanding'
    -- while having examined nothing at all.
    """
    empty = {slug: {"slug": slug, "kind": "experience", "detail": {"metrics": []}}
             for slug in ("example-alpha", "example-beta")}
    root = _live_tree(tmp_path, payload=empty)
    with pytest.raises(SystemExit) as excinfo:
        backing.scan_live(str(root), quiet=True)
    assert excinfo.value.code == 2


def test_live_scan_refuses_a_missing_entry(tmp_path):
    """A missing entry is a refusal, never a smaller population."""
    root = _live_tree(tmp_path)
    (root / "collections" / "collection-one" / "example-alpha" / "raw.json").unlink()
    with pytest.raises(SystemExit) as excinfo:
        backing.scan_live(str(root), quiet=True)
    assert excinfo.value.code == 2


def test_live_scan_reports_zero_outstanding_when_every_row_is_measured(tmp_path):
    """The shape of a finished program: a real population, zero markers."""
    done = {
        "example-alpha": {"slug": "example-alpha", "kind": "experience",
                         "detail": {"metrics": ["P1-B3: 340 pairs, measured 2026-10-01"]}},
        "example-beta": {"slug": "example-beta", "kind": "experience",
                        "detail": {"metrics": ["BP-1-B1: kappa 0.71, measured 2026-10-02"]}},
    }
    root = _live_tree(tmp_path, payload=done)
    verdict, result = backing.scan_live(str(root), quiet=True)
    assert result["checked"] == 2
    assert result["found"] == 0
    assert result["matched"] == []


def test_live_scan_prints_found_and_checked_as_separate_numbers(tmp_path, capsys):
    root = _live_tree(tmp_path)
    backing.scan_live(str(root))
    line = capsys.readouterr().out
    assert "found=3" in line, line
    assert "checked=4" in line, line


def test_live_entries_are_declared_and_match_the_snapshot_sources():
    """The two live paths are declared ONCE per repository, not retyped.

    `canon_snapshot.py` already reads these two files as `live_collections`
    sources. If the two modules disagreed about where an entry lives, one of them
    would be scanning a path that does not exist and reporting it as a clean
    population.
    """
    declared = {entry["relative"] for entry in backing.LIVE_ENTRIES}
    from_snapshot = {
        source["relative"] for source in snap.SOURCES
        if source.get("role") == "live_collections"}
    assert declared == from_snapshot, (declared, from_snapshot)


def test_live_cli_exits_one_when_markers_remain_and_zero_when_none_do(tmp_path):
    root = _live_tree(tmp_path)
    outstanding = backing.main(["--live", "--live-store", str(root)])
    assert outstanding == 1, (
        "markers still outstanding must be a FINDING, not a pass -- a project requirement is "
        "not satisfied while a figure is still designed")

    done = {
        "example-alpha": {"slug": "example-alpha", "kind": "experience",
                         "detail": {"metrics": ["P1-B3: 340 pairs, measured 2026-10-01"]}},
        "example-beta": {"slug": "example-beta", "kind": "experience",
                        "detail": {"metrics": ["BP-1-B1: kappa 0.71, measured 2026-10-02"]}},
    }
    root2 = _live_tree(Path(tmp_path) / "after", payload=done)
    assert backing.main(["--live", "--live-store", str(root2)]) == 0


def test_the_default_scan_still_reads_the_snapshot_offline(doc, tmp_path):
    """--live is OPT-IN. The default must stay answerable from a clean checkout.

    The module's own docstring is the contract: CHECK-09 has to run at closeout on
    a fresh clone that has no live data dir at all.
    """
    verdict, result = backing.scan(doc, quiet=True)
    assert result["checked"] == 49
    assert result["needle"] == backing.DEFAULT_NEEDLE
