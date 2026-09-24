"""The correspondence map, and the framing rule made MECHANICAL.

Two things are tested here and they are different claims.

THE MAP must RECONCILE. Its whole value is that a reader can ask "what is this
path, what does it correspond to, what state is it in" and get an answer nobody
maintained by hand. A map that silently dropped a path, or whose per-path row
counts did not sum to the population, would answer confidently and wrongly --
and it would be believed, because a table looks like a measurement.

THE FRAMING RULE must hold in CODE, not only in prose. The owner's instruction
is that this work is shown as his own engagement work and never as something an
agent made. A rule stated only in a document is a request; these tests make it a
gate. The surfaces checked are the ones that reach a private record: the marker
text the entries carry, and the correction command this tool tells a human to
run.
"""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT
TOOL_PATH = REPO_ROOT / "tools" / "correspondence.py"
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


corr = _load("correspondence", TOOL_PATH)
backing = corr.backing


# ---------------------------------------------------------------------------
# A synthetic store. Nothing here touches the owner's live entries.
# ---------------------------------------------------------------------------

DESIGNED = ("[BACKING: designed, not yet measured -- %s has no reproducing "
            "artifact yet]")
SUBSTITUTE = ("[BACKING: measured on a substitute system -- the backing "
              "artifact is not yet verified]")


def _entry(slug, role, rows):
    return {
        "slug": slug,
        "kind": "experience",
        "company": "Example Studio",
        "role": role,
        "dates": "Month YYYY - Month YYYY",
        "detail": {"metrics": rows},
    }


def _store(tmp_path):
    root = Path(tmp_path) / "information"
    places = {
        "example-alpha": (root / "collections" / "collection-one" / "example-alpha",
                         _entry("example-alpha", "Example Role One", [
                             "P1-B1: a figure " + DESIGNED % "P1",
                             "P1-B2: a figure " + DESIGNED % "P1",
                         ])),
        "example-beta": (root / "collections" / "collection-two" / "example-beta",
                        _entry("example-beta", "Example Role Two", [
                            "P2-B1: a figure " + DESIGNED % "P2",
                            "P2-B2: a measured figure " + SUBSTITUTE,
                        ])),
    }
    for where, payload in places.values():
        where.mkdir(parents=True, exist_ok=True)
        (where / "raw.json").write_text(json.dumps(payload, indent=1),
                                        encoding="utf-8", newline="")
    return root


MANIFEST = {
    "slugs": [
        {"slug": "alpha-artifact-1", "canon": "example-alpha", "project": "P1",
         "status": "pending", "register_row": True,
         "bullets": ["example-alpha:P1-B1", "example-alpha:P1-B2"]},
        {"slug": "beta-artifact-2", "canon": "example-beta",
         "project": "P2", "status": "pending", "register_row": True,
         "bullets": ["example-beta:P2-B1", "example-beta:P2-B2"]},
        {"slug": "alpha-substrate", "canon": None, "project": None,
         "status": "pending", "register_row": False, "bullets": []},
    ]
}


# ---------------------------------------------------------------------------
# The map reconciles
# ---------------------------------------------------------------------------

def test_every_manifest_path_appears_in_the_map(tmp_path):
    """A path silently absent from a map reads as a path that does not exist."""
    root = _store(tmp_path)
    entries = corr.read_entries(str(root))
    rows = corr.build_map(MANIFEST, entries, str(root))
    assert [r["slug"] for r in rows] == [s["slug"] for s in MANIFEST["slugs"]]


def test_a_path_that_backs_no_bullet_is_listed_not_dropped(tmp_path):
    root = _store(tmp_path)
    rows = corr.build_map(MANIFEST, corr.read_entries(str(root)), str(root))
    substrate = next(r for r in rows if r["slug"] == "alpha-substrate")
    assert substrate["backs_no_bullet"] is True
    assert substrate["bullet_ids"] == []
    assert substrate["unbacked"] == 0


def test_the_per_path_row_counts_partition_the_population(tmp_path):
    """The sum is the check. Two paths claiming the same row, or a row claimed
    by none, both show up here and nowhere else."""
    root = _store(tmp_path)
    rows = corr.build_map(MANIFEST, corr.read_entries(str(root)), str(root))
    claimed = [i for r in rows for i in r["bullet_ids"]]
    assert len(claimed) == len(set(claimed)), "a row is claimed twice"
    assert sum(r["unbacked"] for r in rows) == 4


def test_the_marker_kinds_are_carried_through_per_path(tmp_path):
    root = _store(tmp_path)
    rows = corr.build_map(MANIFEST, corr.read_entries(str(root)), str(root))
    pcp = next(r for r in rows if r["slug"] == "beta-artifact-2")
    assert pcp["kinds"] == {"designed": 1, "substitute": 1}, pcp["kinds"]


def test_a_manifest_row_naming_an_id_the_entry_lacks_is_visible(tmp_path):
    """THE RED THIS CATCHES: a manifest that drifted from the entry would
    otherwise report the missing row as backed -- the most flattering possible
    reading of a row nobody can find."""
    root = _store(tmp_path)
    drifted = {"slugs": [dict(MANIFEST["slugs"][0],
                              bullets=["example-alpha:P1-B9"])]}
    rows = corr.build_map(drifted, corr.read_entries(str(root)), str(root))
    assert rows[0]["kinds"] == {"MISSING-ROW": 1}, rows[0]["kinds"]
    assert rows[0]["unbacked"] == 1


def test_an_entry_missing_a_read_field_is_refused(tmp_path):
    """A `.get()` over a shape nobody enumerated turns an absent field into an
    empty one, and the map would print a blank where a fact should be."""
    root = _store(tmp_path)
    path = root / "collections" / "collection-one" / "example-alpha" / "raw.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["role"]
    path.write_text(json.dumps(payload), encoding="utf-8", newline="")
    with pytest.raises(SystemExit) as excinfo:
        corr.read_entries(str(root))
    assert excinfo.value.code == 2


def test_an_empty_manifest_is_refused(tmp_path):
    empty = tmp_path / "manifest.json"
    empty.write_text(json.dumps({"slugs": []}), encoding="utf-8", newline="")
    with pytest.raises(SystemExit) as excinfo:
        corr.read_manifest(str(empty))
    assert excinfo.value.code == 2


def test_the_real_manifest_partitions_all_49_rows():
    """Against the committed manifest, not a fixture: the eleven canon paths
    claim every row exactly once."""
    manifest = corr.read_manifest(str(MANIFEST_PATH))
    claimed = [i for s in manifest["slugs"] for i in (s.get("bullets") or [])]
    assert len(claimed) == 49, len(claimed)
    assert len(set(claimed)) == 49, "a bullet is claimed by two paths"


# ---------------------------------------------------------------------------
# The framing rule, in code
# ---------------------------------------------------------------------------

# Vocabulary that would describe the work as an agent's, or as this programme's
# bookkeeping, rather than as the owner's engagement work.
AGENT_TOKENS = ("claude", "anthropic", "agent", "llm-written", "ai-generated",
                "generated by", "co-authored", "assistant")
PROGRAMME_TOKENS = ("canon-backing", "example project", "gsd", "phase ", "plan 0")


def test_no_marker_describes_the_work_as_an_agents(tmp_path):
    """The entries are a private record. THE RED THIS CATCHES is a marker or a
    correction note that reads "built by ..." in a document whose whole job is
    to say what the owner did."""
    surfaces = [backing.LIVE_MARKER]
    surfaces += [n for _k, n in backing.LIVE_MARKER_KINDS]
    root = _store(tmp_path)
    rows = corr.build_map(MANIFEST, corr.read_entries(str(root)), str(root))
    surfaces += [corr.correction_command(r) for r in rows]

    for surface in surfaces:
        low = surface.lower()
        for token in AGENT_TOKENS:
            assert token not in low, (token, surface)


def test_no_marker_carries_this_programmes_vocabulary(tmp_path):
    """The example project is the row's own prefix. Naming the programme in a private
    record puts scaffolding somewhere it does not belong."""
    surfaces = [backing.LIVE_MARKER]
    surfaces += [n for _k, n in backing.LIVE_MARKER_KINDS]
    for surface in surfaces:
        low = surface.lower()
        for token in PROGRAMME_TOKENS:
            assert token not in low, (token, surface)


def test_the_correction_command_names_the_measurement_not_the_builder(tmp_path):
    """`--note` records WHY a figure changed. It must invite a reason about the
    measurement, never about who performed the rebuild."""
    root = _store(tmp_path)
    rows = corr.build_map(MANIFEST, corr.read_entries(str(root)), str(root))
    command = corr.correction_command(
        next(r for r in rows if r["slug"] == "alpha-artifact-1"))
    assert "--note <why it changed>" in command
    assert "--supersede-done" in command, (
        "the command must correct what was DONE, not only the number")
    assert "--dry-run" in command, "the printed command is the SAFE form"


def test_the_entries_must_still_be_experience(tmp_path):
    """`kind` is where the record says these are engagement. The map prints a
    flag when it is not, so a drift is visible in the thing a reader looks at."""
    root = _store(tmp_path)
    entries = corr.read_entries(str(root))
    for canon, entry in entries.items():
        assert entry["kind"] == corr.REQUIRED_KIND, (canon, entry["kind"])


def live_store_or_skip():
    """The real store, or a skip. Never a silently smaller population."""
    live_store = (Path(corr._HERE).parent / ".." / "information").resolve()
    if not live_store.is_dir():
        pytest.skip("live store not present at %s" % live_store)
    return live_store


# The ATTRIBUTION half of the framing rule, as a needle set fit for a whole
# private record rather than for the short marker string.
#
# `AGENT_TOKENS` above carries the bare word `agent`, which is the right needle
# over the marker and the printed command -- both are a sentence long and this
# repository writes them. Over an ENTRY it is an over-match, and measurably so:
# `example-alpha` is an AI-engineering engagement whose actual subject includes
# `Agentic workflows`, a `bounded agent`, `agents` as a field token and `the
# agent drove a fixed scenario suite`. A bare substring cannot tell "built BY an
# agent" from "built a bounded agent", and the rule is about ATTRIBUTION, not
# about a word. So the entry surface uses attribution-specific forms.
ENTRY_ATTRIBUTION_TOKENS = ("claude", "anthropic", "co-authored", "ai-generated",
                            "generated by", "llm-written", "written by an agent",
                            "assistant")

# MEASURED 2026-09-17 against the live entries, per file. These are PRE-EXISTING
# and every one of them is `example project`:
#
#   example-alpha   5   the entry's own consistency notes, which discuss the
#                      designed-and-not-yet-measured disclosure and a build
#                      budget, plus one `history` row whose `--note` reads
#                      "a project requirement: marked every figure whose example project has not
#                      been run ..."
#   example-beta    3   the same shape
#
# THE BASELINE IS A PIN, NOT A PARDON. The count may not RISE: a new programme
# token reaching either entry fails this test. Closing the eight that are
# already there means editing the owner's private record, which is not a change
# a checker may make on its own -- it is surfaced as an owner decision and
# recorded here so the number is visible rather than absorbed.
KNOWN_PROGRAMME_HITS = {
    "collections/collection-one/example-alpha/raw.json": 5,
    "collections/collection-two/example-beta/raw.json": 3,
}


def entry_vocabulary_hits(blob):
    """(attribution hits, programme hits) for one entry's text, lower-cased."""
    attribution = [t for t in ENTRY_ATTRIBUTION_TOKENS if t in blob]
    programme = []
    for token in PROGRAMME_TOKENS:
        programme += [token] * blob.count(token)
    return attribution, programme


def test_the_live_entries_never_attribute_the_work_to_an_agent(capsys):
    """The real entries, read from the live store. The one that matters.

    THE ENTRY IS THE SURFACE, not only the marker. Until this test was widened,
    the vocabulary rule was asserted over the marker text and the printed
    command only -- both written by this repository and both always going to be
    clean. The entry is what a reader's organization sees, and it is where a `--note`
    lands through the correction seam.

    THE POPULATION IS PRINTED and a zero-file read FAILS rather than passing. A
    guard that reports CLEAN without a count is indistinguishable from one that
    read nothing.

    MEASURED: attribution hits are ZERO in both entries. That is the half of the
    framing rule that must never move, and it is asserted at zero.

    NOT COVERED, and named so the gap is visible: the seam hardcodes
    `command = "<caller> (deliberate metric correction, a project requirement)"` in
    `the-upstream-project`'s `collections_correction.py`. `a project requirement` is that project's
    requirement id -- its vocabulary, predating this programme and not ours to
    edit from here. What this guard covers is the `--note` text, which is the
    field an earlier round author actually controls.
    """
    live_store = live_store_or_skip()

    read, attribution = 0, []
    for spec in backing.LIVE_ENTRIES:
        path = (live_store / spec["relative"]).resolve()
        if not path.is_file():
            pytest.skip("live entry not present at %s" % path)
        found, _programme = entry_vocabulary_hits(
            path.read_text(encoding="utf-8").lower())
        read += 1
        attribution += [(spec["relative"], token) for token in found]

    print("live-entry attribution guard: entries-read=%d tokens-applied=%d "
          "hits=%d" % (read, len(ENTRY_ATTRIBUTION_TOKENS), len(attribution)))
    assert read == len(backing.LIVE_ENTRIES), (
        "read %d of %d live entries; a guard over a smaller population than it "
        "claims is not a guard" % (read, len(backing.LIVE_ENTRIES)))
    assert read > 0, "the guard read zero entries, so it checked nothing"
    assert not attribution, (
        "%d live entry surface(s) attribute the work to an agent: %r"
        % (len(attribution), attribution))
    assert "entries-read=%d" % read in capsys.readouterr().out


def test_no_new_programme_vocabulary_reaches_the_live_entries(capsys):
    """RESEARCH OQ 4. The count is pinned per file and may not RISE.

    A `--note` authored in this programme lands verbatim in the entry's
    `history`, and one already has: `"a project requirement: marked every figure whose build
    path has not been run ..."`. That is the exact leak OQ 4 named, and it
    happened before any guard existed to see it.

    Pinning rather than asserting zero is deliberate and is not a weakened gate.
    Zero is unreachable from here: closing the eight existing hits means
    rewriting text inside the owner's private record, which a project requirement scopes to
    metric corrections through the named seam and which is the owner's call, not
    a checker's. What this pin does buy is the property that matters going
    forward -- the next `--note` carrying programme vocabulary fails here.
    """
    live_store = live_store_or_skip()

    measured, read = {}, 0
    for spec in backing.LIVE_ENTRIES:
        path = (live_store / spec["relative"]).resolve()
        if not path.is_file():
            pytest.skip("live entry not present at %s" % path)
        _attribution, programme = entry_vocabulary_hits(
            path.read_text(encoding="utf-8").lower())
        measured[spec["relative"]] = len(programme)
        read += 1

    print("live-entry programme-vocabulary pin: entries-read=%d "
          "tokens-applied=%d measured=%r baseline=%r"
          % (read, len(PROGRAMME_TOKENS), measured, KNOWN_PROGRAMME_HITS))
    assert read == len(backing.LIVE_ENTRIES), read
    assert sorted(measured) == sorted(KNOWN_PROGRAMME_HITS), (
        "the entry set changed shape: measured %r, pinned %r"
        % (sorted(measured), sorted(KNOWN_PROGRAMME_HITS)))

    risen = {name: (KNOWN_PROGRAMME_HITS[name], count)
             for name, count in measured.items()
             if count > KNOWN_PROGRAMME_HITS[name]}
    assert not risen, (
        "programme vocabulary reached a live entry that did not carry it "
        "before -- (baseline, measured) per file: %r. A `--note` is the usual "
        "route, and it lands verbatim in a private record." % (risen,))

    fell = {name: (KNOWN_PROGRAMME_HITS[name], count)
            for name, count in measured.items()
            if count < KNOWN_PROGRAMME_HITS[name]}
    assert not fell, (
        "the baseline is now too high, which makes it stop catching a rise back "
        "to it -- lower it in the same commit that cleaned the entry: %r"
        % (fell,))


def test_the_vocabulary_guard_fires_on_an_injected_token(tmp_path):
    """THE CONTROL. A negative from a search nobody proved can fire is not a
    measurement, so the same predicate is run against a deliberately dirty COPY.

    Both halves are controlled: an injected attribution phrase must be caught by
    the attribution needle, and an injected programme token must RAISE the
    programme count above the file's baseline. The copy lives in tmp_path;
    nothing under the live store is written.
    """
    live_store = live_store_or_skip()
    spec = backing.LIVE_ENTRIES[0]
    source = (live_store / spec["relative"]).resolve()
    if not source.is_file():
        pytest.skip("live entry not present at %s" % source)

    clean_attr, clean_prog = entry_vocabulary_hits(
        source.read_text(encoding="utf-8").lower())
    assert not clean_attr, clean_attr

    dirty = Path(tmp_path) / "raw.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload.setdefault("history", []).append(
        {"timestamp": "2026-01-01T00:00:00Z",
         "command": "injected for the control",
         "change": ("a note naming " + "canon" + "-backing and saying it was "
                    "generated by something other than the owner")})
    dirty.write_text(json.dumps(payload), encoding="utf-8", newline="")

    dirty_attr, dirty_prog = entry_vocabulary_hits(
        dirty.read_text(encoding="utf-8").lower())
    assert "generated by" in dirty_attr, (
        "the attribution needle did not fire on an injected phrase, so its "
        "clean verdict on the real entry proves nothing: %r" % (dirty_attr,))
    assert len(dirty_prog) == len(clean_prog) + 1, (
        "the programme count did not rise on an injected token, so the pin "
        "cannot catch a new one: %d -> %d"
        % (len(clean_prog), len(dirty_prog)))


def test_the_live_entries_are_not_written_by_this_module():
    """a project requirement: this repository reads the private record and never writes it."""
    live_store = live_store_or_skip()
    digests = {}
    for spec in backing.LIVE_ENTRIES:
        path = (live_store / spec["relative"]).resolve()
        if not path.is_file():
            pytest.skip("live entry not present at %s" % path)
        digests[spec["relative"]] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(digests) == len(backing.LIVE_ENTRIES)
    for relative, digest in digests.items():
        assert len(digest) == 64, (relative, digest)


# ---------------------------------------------------------------------------
# a design rule: both mapping fields, and a denominator that does not move
# ---------------------------------------------------------------------------

# One bullet, reached by two slugs through DIFFERENT fields. This is the shape
# the real expected set carries exactly once -- `example-beta:P5-B3`, owned by
# `beta-artifact-5` through `bullets` and cited by
# `example-cache-benchmark` through `backs_bullets` -- reproduced here so
# the distinct-keying is testable without depending on the real manifest
# staying the way it is.
TWO_FIELD_MANIFEST = {
    "slugs": [
        {"slug": "owns-the-row", "canon": "example-beta", "project": "P2",
         "status": "pending", "register_row": True,
         "bullets": ["example-beta:P2-B1"], "backs_bullets": []},
        {"slug": "cites-the-row", "canon": "example-beta", "project": None,
         "status": "built", "register_row": True,
         "bullets": [], "backs_bullets": ["example-beta:P2-B1"]},
    ]
}


def test_an_obligation_reached_only_through_backs_bullets_is_in_the_row_set(tmp_path):
    """a design rule. Reading `bullets` alone makes the map blind to precisely the slug
    that is already built AND already cited -- a confident zero produced by the
    scope of the field read, not by the state of the world."""
    root = _store(tmp_path)
    rows = corr.build_map(TWO_FIELD_MANIFEST, corr.read_entries(str(root)),
                          str(root))
    cites = next(r for r in rows if r["slug"] == "cites-the-row")
    assert cites["bullet_ids"] == ["P2-B1"], cites["bullet_ids"]
    assert cites["unbacked"] == 1, cites
    assert cites["backs_no_bullet"] is False, cites


def test_a_row_names_the_field_each_obligation_arrived_through(tmp_path):
    """Both fields count and they are not the same relationship, so the display
    must be able to say which one reached a given claim."""
    root = _store(tmp_path)
    rows = corr.build_map(TWO_FIELD_MANIFEST, corr.read_entries(str(root)),
                          str(root))
    owns = next(r for r in rows if r["slug"] == "owns-the-row")
    cites = next(r for r in rows if r["slug"] == "cites-the-row")
    assert owns["fields"] == {"P2-B1": "bullets"}, owns.get("fields")
    assert cites["fields"] == {"P2-B1": "backs_bullets"}, cites.get("fields")


def test_the_totals_count_distinct_keys_rather_than_summing_rows(tmp_path):
    """THE TRAP THIS PLAN EXISTS TO AVOID. Two slugs legitimately name one
    claim, so a per-row sum reports one more obligation than the programme has
    -- and the project requirement countdown is keyed to that denominator."""
    root = _store(tmp_path)
    rows = corr.build_map(TWO_FIELD_MANIFEST, corr.read_entries(str(root)),
                          str(root))
    summed = sum(len(r["bullet_ids"]) for r in rows)
    distinct = corr.distinct_keys(rows)
    assert summed == 2, summed
    assert len(distinct) == 1, distinct
    assert sorted(distinct) == ["example-beta:P2-B1"], sorted(distinct)


def test_the_real_manifests_union_is_fifty_summed_and_forty_nine_distinct():
    """DERIVED from the committed manifest and asserted against the literal.

    The literal is the tripwire on the derivation's own input: a purely derived
    count stops checking the moment the input shrinks, because expected falls to
    match found. A disagreement between the two is the finding, never a number
    to pick between.
    """
    manifest = corr.read_manifest(str(MANIFEST_PATH))
    summed = [key for slug in manifest["slugs"]
              for field in ("bullets", "backs_bullets")
              for key in (slug.get(field) or [])]
    duplicates = sorted({key for key in summed if summed.count(key) > 1})

    assert len(summed) == 50, len(summed)
    assert len(set(summed)) == 49, len(set(summed))
    assert duplicates == ["example-beta:P5-B3"], duplicates
    claimants = sorted(
        (slug["slug"], field) for slug in manifest["slugs"]
        for field in ("bullets", "backs_bullets")
        if "example-beta:P5-B3" in (slug.get(field) or []))
    assert claimants == [("beta-artifact-5", "bullets"),
                         ("example-cache-benchmark", "backs_bullets")], claimants


def test_the_population_line_reports_the_distinct_total_not_the_sum(tmp_path):
    """The reading the project technology-stack document section 9 quotes, and a project requirement measures against."""
    live_store = live_store_or_skip()
    report_path = Path(tmp_path) / "corr.json"
    result = conftest.run_cli(
        [sys.executable, str(TOOL_PATH), "--live-store", str(live_store),
         "--report", str(report_path)], cwd=REPO_ROOT)
    assert result.exit_code == 0, result.stdout + result.stderr

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    # The DENOMINATOR is what this test is named for and what a project requirement measures
    # against: 49 distinct claims, 50 when a legitimately double-CLAIMED row is
    # summed. Both are invariants of the expected set.
    assert payload["rows_total"] == 49, payload["rows_total"]
    assert payload["rows_total_summed"] == 50, payload.get("rows_total_summed")

    # The NUMERATOR is designed to FALL to zero -- that is the whole programme --
    # so pinning it to a literal makes the first successful correction fail this
    # test. It did, on 2026-09-20, when example-beta:P5-B3 was measured and the
    # count moved 49 -> 48. Assert the printed line against the payload instead,
    # which catches the drift this test exists to catch (a line that disagrees
    # with its own report) without re-breaking every time a claim gets backed.
    assert 0 <= payload["rows_unbacked"] <= payload["rows_total"], payload
    assert ("rows still unbacked=%d of %d"
            % (payload["rows_unbacked"], payload["rows_total"])
            ) in result.stdout, result.stdout
    assert "of 50" not in result.stdout, (
        "the population line printed the SUMMED total, which would read a "
        "legitimate double-CLAIM as a double-COUNT: " + result.stdout)


def test_the_cited_slug_detail_names_the_row_it_answers_for(tmp_path):
    """`--slug example-cache-benchmark` printed an empty row list and
    `unbacked : 0` while the expected set said it backs a claim. Two tools
    disagreeing about what a path answers for is what a design rule closes."""
    live_store = live_store_or_skip()
    result = conftest.run_cli(
        [sys.executable, str(TOOL_PATH), "--live-store", str(live_store),
         "--slug", "example-cache-benchmark"], cwd=REPO_ROOT)
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "P5-B3" in result.stdout, result.stdout
    assert "backs no bullet" not in result.stdout, result.stdout
    assert "--supersede-done" in result.stdout, result.stdout
