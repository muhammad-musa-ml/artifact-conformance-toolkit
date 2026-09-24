"""`tools/assemble_records.py` -- fragments, supersession, and a counted header.

a project requirement exists because a fragment written but never assembled is INVISIBLE.
Nothing errors, no count moves, and the assembled file a reader trusts is
simply missing a record. The header's fragment COUNT and hash are what turn
that into something detectable, so the tests here are mostly tests of a
NUMBER being right rather than of text being produced.

a design rule is the second subject: a superseded fragment is EXCLUDED from the body and
COUNTED, never deleted. The shared pattern note names the shipped model -- the
disagreeing run is kept and explained, because *discarding the run that
disagrees is how a benchmark lies.*
"""

import importlib.util
import json
import os
import re
import sys
from pathlib import Path

import pytest

from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT
ASSEMBLE_PATH = REPO_ROOT / "tools" / "assemble_records.py"


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


assemble = _load("assemble_records_under_test", ASSEMBLE_PATH)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _kind_dir(tmp_path, kind="judgment"):
    root = Path(tmp_path) / "_records" / kind
    root.mkdir(parents=True, exist_ok=True)
    return root


def _fragment(kind_dir, stamp, slug, kind="judgment", ident=None,
              supersedes=None, plan="an earlier plan", dated_at="2026-09-15",
              body="A judgment with no numerals in it.\n"):
    ident = ident or ("%s--%s" % (stamp, slug))
    lines = ["---", "id: %s" % ident, "plan: %s" % plan,
             "dated_at: %s" % dated_at]
    if supersedes is not None:
        lines.append("supersedes: %s" % supersedes)
    lines.append("---")
    lines.append("")
    text = "\n".join(lines) + "\n" + body
    path = kind_dir / ("%s--%s--%s.md" % (stamp, slug, kind))
    path.write_text(text, encoding="utf-8", newline="\n")
    return path, ident


def _numbers_after(text, label):
    match = re.search(r"%s\s+(\d+)" % re.escape(label), text)
    return int(match.group(1)) if match else None


# ---------------------------------------------------------------------------
# The counted, hashed header
# ---------------------------------------------------------------------------

def test_the_header_carries_assembled_superseded_and_total(tmp_path):
    kind_dir = _kind_dir(tmp_path)
    _fragment(kind_dir, "2026-09-15-090000", "alpha")
    _fragment(kind_dir, "2026-09-15-100000", "beta")
    _fragment(kind_dir, "2026-09-15-110000", "gamma")

    result = assemble.build(kind_dir)
    text = Path(result["target"]).read_text(encoding="utf-8")

    for label in ("assembled", "superseded", "total"):
        assert _numbers_after(text, label) is not None, (
            "the header does not report %r; a header without a count is "
            "exactly the shape that lets a lost fragment go unnoticed" % label
        )
    assert _numbers_after(text, "assembled") == 3
    assert _numbers_after(text, "superseded") == 0
    assert _numbers_after(text, "total") == 3


def test_total_equals_assembled_plus_superseded(tmp_path):
    kind_dir = _kind_dir(tmp_path)
    _, first = _fragment(kind_dir, "2026-09-15-090000", "alpha")
    _fragment(kind_dir, "2026-09-15-100000", "beta")
    _fragment(kind_dir, "2026-09-15-110000", "alpha-redone", supersedes=first)

    result = assemble.build(kind_dir)
    text = Path(result["target"]).read_text(encoding="utf-8")

    assembled = _numbers_after(text, "assembled")
    superseded = _numbers_after(text, "superseded")
    total = _numbers_after(text, "total")
    assert (assembled, superseded, total) == (2, 1, 3)
    assert total == assembled + superseded, (
        "the identity a reader can check is what makes these three numbers a "
        "population line rather than decoration"
    )


def test_the_header_carries_a_hash_over_the_fragment_names_and_contents(tmp_path):
    kind_dir = _kind_dir(tmp_path)
    path, _ = _fragment(kind_dir, "2026-09-15-090000", "alpha")
    first = assemble.build(kind_dir)
    before = first["fragments_sha256"]
    assert re.fullmatch(r"[0-9a-f]{64}", before), "no sha256 in the result"

    path.write_text(path.read_text(encoding="utf-8") + "\nan added line.\n",
                    encoding="utf-8", newline="\n")
    after = assemble.build(kind_dir)["fragments_sha256"]
    assert after != before, (
        "the header hash did not move when a fragment's CONTENT changed, so it "
        "cannot detect a fragment being edited"
    )

    _fragment(kind_dir, "2026-09-15-100000", "beta")
    third = assemble.build(kind_dir)["fragments_sha256"]
    assert third != after, "the hash did not move when a fragment was ADDED"


# ---------------------------------------------------------------------------
# a design rule supersession
# ---------------------------------------------------------------------------

def test_a_superseded_fragment_is_excluded_from_the_body_but_kept_on_disk(tmp_path):
    kind_dir = _kind_dir(tmp_path)
    old_path, old_id = _fragment(kind_dir, "2026-09-15-090000", "alpha",
                                 body="THE SUPERSEDED BODY TEXT.\n")
    _fragment(kind_dir, "2026-09-15-110000", "alpha-redone", supersedes=old_id,
              body="THE REPLACEMENT BODY TEXT.\n")

    result = assemble.build(kind_dir)
    text = Path(result["target"]).read_text(encoding="utf-8")

    assert "THE REPLACEMENT BODY TEXT." in text
    assert "THE SUPERSEDED BODY TEXT." not in text, (
        "a superseded fragment's body was assembled"
    )
    assert old_path.is_file(), (
        "the superseded fragment was DELETED. a design rule and a shared pattern both require it kept "
        "and counted: discarding the record that disagrees is how a benchmark lies"
    )
    assert old_id in text, (
        "the superseded fragment is not even NAMED in the assembled file, so a "
        "reader cannot tell it from one that was never written"
    )


def test_a_dangling_supersedes_fails_and_names_the_missing_id(tmp_path):
    kind_dir = _kind_dir(tmp_path)
    _fragment(kind_dir, "2026-09-15-090000", "alpha")
    _fragment(kind_dir, "2026-09-15-110000", "beta",
              supersedes="2026-01-01-000000--no-such-fragment")

    with pytest.raises(assemble.AssembleError) as caught:
        assemble.build(kind_dir)
    assert "2026-01-01-000000--no-such-fragment" in str(caught.value), (
        "the failure does not name the missing id, so the operator cannot tell "
        "which pointer is dangling"
    )


def test_a_supersedes_chain_counts_each_superseded_fragment_once(tmp_path):
    kind_dir = _kind_dir(tmp_path)
    _, first = _fragment(kind_dir, "2026-09-15-090000", "v1")
    _, second = _fragment(kind_dir, "2026-09-15-100000", "v2", supersedes=first)
    _fragment(kind_dir, "2026-09-15-110000", "v3", supersedes=second)

    result = assemble.build(kind_dir)
    assert (result["assembled"], result["superseded"], result["total"]) == (1, 2, 3)


def test_duplicate_ids_fail(tmp_path):
    kind_dir = _kind_dir(tmp_path)
    _fragment(kind_dir, "2026-09-15-090000", "alpha", ident="same-id")
    _fragment(kind_dir, "2026-09-15-100000", "beta", ident="same-id")
    with pytest.raises(assemble.AssembleError) as caught:
        assemble.build(kind_dir)
    assert "same-id" in str(caught.value)


# ---------------------------------------------------------------------------
# The zero-population refusal
# ---------------------------------------------------------------------------

def test_zero_fragments_is_did_not_run_and_writes_nothing(tmp_path):
    kind_dir = _kind_dir(tmp_path)
    target = Path(assemble.default_target(kind_dir))
    code = assemble.main(["build", "--dir", str(kind_dir)])
    assert code == 2, (
        "an empty fragment set reported something other than DID-NOT-RUN. "
        "'found nothing' and 'could not look' are different answers, "
        "and an empty assembled file reported as success is the worse one"
    )
    assert not target.exists(), (
        "an EMPTY assembled file was written; the next lint would then compare "
        "clean and the missing fragments would never surface"
    )


def test_a_directory_of_only_non_fragments_is_did_not_run(tmp_path):
    kind_dir = _kind_dir(tmp_path)
    (kind_dir / "README.md").write_text("not a fragment\n", encoding="utf-8",
                                        newline="\n")
    code = assemble.main(["build", "--dir", str(kind_dir)])
    assert code == 2


def test_non_fragment_files_are_ignored_and_counted(tmp_path, capsys):
    """A README beside the fragments must not be assembled OR silently dropped.

    `_records/census/README.md` already exists in this repository, so this is
    the live case, not a hypothetical.
    """
    kind_dir = _kind_dir(tmp_path)
    _fragment(kind_dir, "2026-09-15-090000", "alpha")
    (kind_dir / "README.md").write_text("NOT A FRAGMENT AT ALL\n",
                                        encoding="utf-8", newline="\n")
    (kind_dir / "notes.txt").write_text("also not\n", encoding="utf-8",
                                        newline="\n")

    code = assemble.main(["build", "--dir", str(kind_dir)])
    captured = capsys.readouterr()
    assert code == 0
    assert "ignored 2" in captured.out, (
        "files skipped by the fragment pattern were not counted; a scan that "
        "does not print what it skipped cannot be audited"
    )
    assert "README.md" in captured.out, "the ignored files are not named"
    body = Path(assemble.default_target(kind_dir)).read_text(encoding="utf-8")
    assert "NOT A FRAGMENT AT ALL" not in body


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------

def test_ordering_follows_the_timestamp_not_the_plan_number(tmp_path):
    """Two fragments from the SAME plan, out of plan order by timestamp.

    Plan number stops being chronological the moment the roadmap reorders, and
    five inherited waves hold 2-3 record-writing plans each.
    """
    kind_dir = _kind_dir(tmp_path)
    _fragment(kind_dir, "2026-09-15-140000", "later", plan="an earlier plan",
              body="SECOND IN TIME.\n")
    _fragment(kind_dir, "2026-09-15-080000", "earlier", plan="an earlier plan",
              body="FIRST IN TIME.\n")

    text = Path(assemble.build(kind_dir)["target"]).read_text(encoding="utf-8")
    assert text.index("FIRST IN TIME.") < text.index("SECOND IN TIME."), (
        "the assembled order does not follow the timestamp prefix"
    )


def test_a_later_plan_number_with_an_earlier_timestamp_still_sorts_first(tmp_path):
    kind_dir = _kind_dir(tmp_path)
    _fragment(kind_dir, "2026-09-15-080000", "a", plan="an earlier plan", body="EARLY.\n")
    _fragment(kind_dir, "2026-09-15-090000", "b", plan="an earlier plan", body="LATE.\n")
    text = Path(assemble.build(kind_dir)["target"]).read_text(encoding="utf-8")
    assert text.index("EARLY.") < text.index("LATE.")


# ---------------------------------------------------------------------------
# lint -- a direct append must be DETECTED
# ---------------------------------------------------------------------------

def test_lint_passes_on_a_freshly_built_file(tmp_path):
    kind_dir = _kind_dir(tmp_path)
    _fragment(kind_dir, "2026-09-15-090000", "alpha")
    assemble.build(kind_dir)
    assert assemble.main(["lint", "--dir", str(kind_dir)]) == 0


def test_lint_detects_a_direct_append_and_names_the_difference(tmp_path, capsys):
    """The failure mode this whole module exists for: one agent appending.

    Parallelization is ON at `fine` granularity, so two record-writing plans can
    run at once. A plan that appends straight to the assembled file loses the
    other agent's write with no error and no count moving.
    """
    kind_dir = _kind_dir(tmp_path)
    _fragment(kind_dir, "2026-09-15-090000", "alpha")
    target = Path(assemble.build(kind_dir)["target"])

    with open(str(target), "a", encoding="utf-8", newline="") as handle:
        handle.write("\nAN AGENT APPENDED THIS DIRECTLY.\n")

    code = assemble.main(["lint", "--dir", str(kind_dir)])
    captured = capsys.readouterr()
    assert code != 0, "a direct append went undetected"
    assert "AN AGENT APPENDED THIS DIRECTLY." in captured.out + captured.err, (
        "lint did not print the differing content, so an operator cannot see "
        "what changed"
    )


def test_lint_detects_a_deleted_line(tmp_path):
    kind_dir = _kind_dir(tmp_path)
    _fragment(kind_dir, "2026-09-15-090000", "alpha", body="KEEP ME.\n")
    target = Path(assemble.build(kind_dir)["target"])
    text = target.read_text(encoding="utf-8").replace("KEEP ME.\n", "")
    target.write_text(text, encoding="utf-8", newline="")
    assert assemble.main(["lint", "--dir", str(kind_dir)]) != 0


def test_lint_over_zero_fragments_is_did_not_run(tmp_path):
    kind_dir = _kind_dir(tmp_path)
    assert assemble.main(["lint", "--dir", str(kind_dir)]) == 2


def test_lint_reports_a_missing_assembled_file_as_a_finding(tmp_path):
    kind_dir = _kind_dir(tmp_path)
    _fragment(kind_dir, "2026-09-15-090000", "alpha")
    code = assemble.main(["lint", "--dir", str(kind_dir)])
    assert code == 1, (
        "fragments exist but nothing was assembled -- that is precisely the "
        "'written but never assembled' case a project requirement exists to detect, and it "
        "is a FINDING, not a did-not-run"
    )


# ---------------------------------------------------------------------------
# The write itself
# ---------------------------------------------------------------------------

def test_the_assembled_file_contains_no_carriage_return(tmp_path):
    kind_dir = _kind_dir(tmp_path)
    _fragment(kind_dir, "2026-09-15-090000", "alpha")
    target = Path(assemble.build(kind_dir)["target"])
    raw = target.read_bytes()
    assert b"\r" not in raw, (
        "the assembled file went through Windows text translation. a design rule fixes "
        "line endings at the git layer; this is the WRITE layer, and a file "
        "written without newline='' hashes differently than the one this "
        "repository computes"
    )


def test_the_temp_file_lives_in_the_target_directory(tmp_path, monkeypatch):
    """os.replace is atomic within a volume and is NOT atomic across one."""
    kind_dir = _kind_dir(tmp_path)
    _fragment(kind_dir, "2026-09-15-090000", "alpha")
    target = Path(assemble.default_target(kind_dir))

    seen = {}
    real_replace = os.replace

    def capturing_replace(src, dst, *args, **kwargs):
        seen["src"] = str(src)
        seen["dst"] = str(dst)
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", capturing_replace)
    assemble.build(kind_dir)
    monkeypatch.undo()

    assert seen, "the write never went through os.replace, so it is not atomic"
    assert Path(seen["src"]).parent == target.parent, (
        "the temp file was written to %s but the target is in %s; os.replace "
        "across a volume is not atomic" % (Path(seen["src"]).parent, target.parent)
    )
    assert seen["src"] != seen["dst"]


def test_the_write_happens_under_the_lock(tmp_path, monkeypatch):
    """A blocking mwlock is held AT THE MOMENT of the replace, not around it."""
    kind_dir = _kind_dir(tmp_path)
    _fragment(kind_dir, "2026-09-15-090000", "alpha")
    target = Path(assemble.default_target(kind_dir))
    lock = Path(assemble.mwlock.lock_path_for(target))

    held_during = {}
    real_replace = os.replace

    def checking_replace(src, dst, *args, **kwargs):
        held_during["locked"] = lock.is_file()
        held_during["holder"] = assemble.mwlock.read_holder(lock)
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", checking_replace)
    assemble.build(kind_dir)
    monkeypatch.undo()

    assert held_during.get("locked") is True, (
        "the assembled file was replaced with NO lock held; a concurrent "
        "writer's replace would silently win"
    )
    assert held_during["holder"]["pid"] == os.getpid()
    assert not lock.exists(), "the lock was left held after build() returned"


def test_the_target_sits_beside_the_fragment_directory_not_inside_it(tmp_path):
    """SCOPE. An aggregate inside the scanned directory is either re-assembled
    into itself or silently excluded by the pattern -- both are bugs, and the
    second is the one that reads as working."""
    kind_dir = _kind_dir(tmp_path)
    target = Path(assemble.default_target(kind_dir))
    assert target.parent == kind_dir.parent
    assert kind_dir not in target.parents


def test_build_prints_the_population_it_covered(tmp_path, capsys):
    kind_dir = _kind_dir(tmp_path)
    _fragment(kind_dir, "2026-09-15-090000", "alpha")
    _, first = _fragment(kind_dir, "2026-09-15-100000", "beta")
    _fragment(kind_dir, "2026-09-15-110000", "gamma", supersedes=first)

    assert assemble.main(["build", "--dir", str(kind_dir)]) == 0
    out = capsys.readouterr().out
    assert "assembled 2" in out
    assert "superseded 1" in out
    assert "total 3" in out
    assert str(kind_dir) in out, "the scan root it covered is not printed"


def test_the_report_carries_a_schema_version(tmp_path):
    """a design rule: a structured report beside the human text, versioned."""
    kind_dir = _kind_dir(tmp_path)
    _fragment(kind_dir, "2026-09-15-090000", "alpha")
    report = Path(tmp_path) / "report.json"
    assert assemble.main(["build", "--dir", str(kind_dir),
                          "--report", str(report)]) == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["schema_version"] == assemble.SCHEMA_VERSION
    assert payload["assembled"] == 1
    assert payload["total"] == 1


# ---------------------------------------------------------------------------
# Fragment validation
# ---------------------------------------------------------------------------

def test_a_fragment_without_front_matter_fails(tmp_path):
    kind_dir = _kind_dir(tmp_path)
    (kind_dir / "2026-09-15-090000--alpha--judgment.md").write_text(
        "no front matter here\n", encoding="utf-8", newline="\n")
    with pytest.raises(assemble.AssembleError) as caught:
        assemble.build(kind_dir)
    assert "front matter" in str(caught.value).lower()


def test_a_fragment_missing_a_required_key_fails_and_names_it(tmp_path):
    kind_dir = _kind_dir(tmp_path)
    (kind_dir / "2026-09-15-090000--alpha--judgment.md").write_text(
        "---\nid: x\nplan: an earlier plan\n---\n\nbody\n", encoding="utf-8", newline="\n")
    with pytest.raises(assemble.AssembleError) as caught:
        assemble.build(kind_dir)
    assert "dated_at" in str(caught.value)


def test_a_fragment_name_that_does_not_match_the_pattern_is_not_a_fragment(tmp_path):
    kind_dir = _kind_dir(tmp_path)
    _fragment(kind_dir, "2026-09-15-090000", "alpha")
    (kind_dir / "01-08--judgment.md").write_text(
        "---\nid: y\nplan: an earlier plan\ndated_at: 2026-09-15\n---\n\nbody\n",
        encoding="utf-8", newline="\n")
    result = assemble.build(kind_dir)
    assert result["total"] == 1
    assert result["ignored"] == 1
    assert "01-08--judgment.md" in result["ignored_names"]
