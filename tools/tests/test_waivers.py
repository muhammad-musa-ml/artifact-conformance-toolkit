"""a design rule (HARD): the checker must not be silenceable by the thing it checks.

Build agents run unattended. A waiver a build agent can write is not a waiver,
it is an off switch, so the run's waivers record is compared against the LAST
COMMITTED version of the same file -- read back through git, never against a
cached copy -- and any waiver present in the first but not the second is ITSELF
a finding. The owner round trip is the feature, not friction to be engineered
away: adding an entry requires a human, a reason and a commit.

CHECK-10's two halves, both asserted here:

    the SHAPE      a waiver is honoured only when it carries check_id, reason
                   and dated_at, each a non-empty string
    the COUNT      the waiver count prints in the summary line, so waivers are
                   countable rather than invisible

THE TESTS THAT CARRY THE RED:

    test_uncommitted_waiver_is_finding
    test_the_waiver_count_prints_in_the_summary_line

Both fail, in the RED commit, on an assertion about a VERDICT: the runner was
registered and runnable with its waiver round trip stubbed to honour whatever it
read, and with the printed count hard-wired to zero.
"""

import json

from tools.tests import conftest
from tools.tests.test_skeleton_roundtrip import build_conformant_world
from tools.tests.test_conformance import (
    EMPTY_WAIVERS,
    artifact,
    conformance,
    core,
    entry,
    run_conformance,
    write_json,
)

REPO_ROOT = conftest.REPO_ROOT
UNCOMMITTED_FIXTURE = "broken-uncommitted-waiver"

# The finding CHECK-01 raises on an artifact whose only figure carries no
# denominator. Named here so a waiver can target it by id rather than by
# suppressing the whole check.
POPULATION_FINDING_ID = "figure:median_latency_ms"


def a_waiver(check_id="CHECK-01", finding_id=POPULATION_FINDING_ID,
             reason=None, dated_at="2026-09-15T00:00:00+03:00", drop=None):
    entry_obj = {
        "check_id": check_id,
        "finding_id": finding_id,
        "reason": (reason or "The owner accepts this figure's missing "
                             "denominator for the duration of the fixture."),
        "dated_at": dated_at,
    }
    if drop:
        entry_obj.pop(drop, None)
    return entry_obj


def waivers_record(entries):
    record = dict(EMPTY_WAIVERS)
    record["waivers"] = list(entries)
    return record


def committed_artifact(tmp_path, entries=(), population=None, slug="waived"):
    """An artifact whose waivers record is COMMITTED with `entries` in it."""
    source = artifact(tmp_path, slug=slug, population=population,
                      waivers=waivers_record(entries))
    return conftest.committed_tree(tmp_path, source)


# ---------------------------------------------------------------------------
# The round trip
# ---------------------------------------------------------------------------


def test_uncommitted_waiver_is_finding(tmp_path):
    """A waiver added to the working copy only is itself a finding.

    The artifact carries one real CHECK-01 finding. The working copy then gains
    a well-formed waiver naming it, and the committed copy does not. A checker
    that honoured it would report a clean artifact -- which is exactly what an
    unattended build agent would produce for itself.
    """
    work = committed_artifact(tmp_path, entries=())
    record = json.loads((work / "waivers.json").read_text(encoding="utf-8"))
    record["waivers"] = [a_waiver()]
    write_json(work / "waivers.json", record)

    result = run_conformance(work, report=tmp_path / "report.json")
    report = result.report
    assert report is not None, result.stdout + result.stderr

    ten = entry(report, "CHECK-10")
    assert ten is not None, report["checks"]
    assert ten["code"] == core.EXIT_FINDING, (
        "a waiver present in the working copy and absent from the committed "
        "one was honoured instead of reported. CHECK-10's line was:\n%s"
        % result.stdout)
    assert any("uncommitted" in finding for finding in ten["finding_ids"]), (
        "CHECK-10 reported a finding but named nothing: %r" % (ten,))

    one = entry(report, "CHECK-01")
    assert one["waived"] == 0, (
        "the uncommitted waiver still suppressed a finding: %r" % (one,))
    assert one["code"] == core.EXIT_FINDING, one
    assert result.exit_code == core.EXIT_FINDING, result.stdout

    census = report["artifacts"][0]["waivers"]
    assert census["committed_resolved"] is True, census
    assert census["uncommitted"] == 1 and census["honoured"] == 0, census


def test_the_waiver_count_prints_in_the_summary_line(tmp_path):
    """CHECK-10's second half: waivers are countable rather than invisible."""
    work = committed_artifact(tmp_path, entries=[a_waiver()])

    result = run_conformance(work, report=tmp_path / "report.json")
    assert "waived=1" in result.stdout, (
        "the run honoured one waiver and printed none. stdout:\n%s"
        % result.stdout)
    assert "1 waived" in result.stdout, result.stdout
    one = entry(result.report, "CHECK-01")
    assert one["waived"] == 1, one
    assert result.report["summary"]["waived"] == 1, result.report["summary"]


def test_a_committed_waiver_is_honoured(tmp_path):
    """The other direction. A round trip nobody can complete is a ban.

    RUN OVER A CONFORMANT ARTIFACT, because the last assertion is about the
    WHOLE run and not about CHECK-01 alone. Over a minimal fixture the exit code
    was 1 no matter what the waiver did -- seven other checks were refusing for
    want of inputs that fixture does not build -- so the assertion could never
    pass and, worse, would not have distinguished a working waiver from a broken
    one if it somehow had.

    RE-KEYED BY AN EARLIER PLAN. The world used to ship TWO owner-committed CHECK-01
    waivers of its own, for numerals inside the canon bullet its claim table
    quotes verbatim -- and check_01.py now CLASSIFIES those numerals against the
    same corpus CHECK-09 resolves against (an earlier plan item 13), so those two findings
    no longer exist and their waivers went silently inert. `waived` fell to 0
    and this test failed, which is the mechanism working: a waiver whose finding
    was repaired must stop counting.

    The repair is NOT to weaken the assertion to `waived >= 0`. That would empty
    the only test watching the honoured direction over a whole run. The world is
    asked for a waiver ON PURPOSE instead, through `waive=True`, which adds one
    hand-typed numeral in un-rendered prose and the owner-committed waiver that
    excuses it for the duration of the fixture. So the assertion is still that
    the run reaches exit 0 WITH a waiver honoured, which is the round trip the
    test is named for.
    """
    world = build_conformant_world(tmp_path, waive=True)
    result = run_conformance(world.artifact, *world.flags(),
                             report=tmp_path / "report.json")

    one = entry(result.report, "CHECK-01")
    assert one["found"] == 0, (
        "an owner-committed waiver did not suppress its finding: %r" % (one,))
    assert one["waived"] == 1, (
        "the world authored ONE waiver and %d were honoured; nothing waived "
        "means exit 0 here says nothing about waivers: %r"
        % (one["waived"], one))
    ten = entry(result.report, "CHECK-10")
    assert ten["code"] == core.EXIT_PASS, ten
    assert result.exit_code == core.EXIT_PASS, result.stdout + result.stderr


def test_a_waiver_missing_any_required_key_is_not_honoured(tmp_path):
    """All three of check_id, reason and dated_at, one test per omission.

    A reason is prose a reader can disagree with. A date is when the owner
    decided. A check id is what was excused. Two of the three make the entry
    unreviewable and the third makes it unbounded, so none of them is optional.
    """
    for dropped in conformance.WAIVER_REQUIRED_KEYS:
        work = committed_artifact(tmp_path, entries=[a_waiver(drop=dropped)],
                                  slug="drop-%s" % dropped.replace("_", "-"))
        result = run_conformance(work, report=tmp_path / ("%s.json" % dropped))
        ten = entry(result.report, "CHECK-10")
        assert ten["code"] == core.EXIT_FINDING, (
            "a waiver with no %r was accepted: %r" % (dropped, ten))
        assert any("malformed" in finding for finding in ten["finding_ids"]), ten
        one = entry(result.report, "CHECK-01")
        assert one["found"] >= 1, (
            "a waiver with no %r still silenced its finding: %r" % (dropped, one))


def test_an_empty_but_present_record_still_has_a_population(tmp_path):
    """The shipped waivers record is EMPTY but PRESENT, and that is a fact."""
    work = committed_artifact(tmp_path, entries=(), population=500,
                              slug="no-waivers")
    result = run_conformance(work, report=tmp_path / "report.json")
    ten = entry(result.report, "CHECK-10")
    assert ten["checked"] >= 1, (
        "an artifact declaring zero waivers reported a population of %d; "
        "'the owner declared none' is a fact, not the absence of one"
        % ten["checked"])
    assert ten["code"] == core.EXIT_PASS, ten
    assert ten["found"] == 0, ten


def test_an_absent_waivers_record_is_did_not_run_for_check_10(tmp_path):
    """No record and no committed copy: the check could not look."""
    root = artifact(tmp_path, waivers=None)
    result = run_conformance(root, report=tmp_path / "report.json")
    ten = entry(result.report, "CHECK-10")
    assert ten["checked"] == 0, ten
    assert ten["code"] == core.EXIT_DID_NOT_RUN, (
        "a waiver check with nothing to resolve reported code %d" % ten["code"])
    assert result.exit_code == core.EXIT_FINDING, result.stdout


def test_a_rewritten_reason_makes_a_committed_waiver_a_new_one(tmp_path):
    """The committed entry is the whole entry, not merely its check id.

    An owner who committed a waiver for one reason has not thereby committed a
    waiver whose reason was rewritten afterwards -- which is the edit an
    unattended agent would make to widen one.
    """
    work = committed_artifact(tmp_path, entries=[a_waiver()])
    record = json.loads((work / "waivers.json").read_text(encoding="utf-8"))
    record["waivers"][0]["reason"] = "rewritten after the commit"
    write_json(work / "waivers.json", record)

    result = run_conformance(work, report=tmp_path / "report.json")
    ten = entry(result.report, "CHECK-10")
    assert ten["code"] == core.EXIT_FINDING, ten
    assert result.report["artifacts"][0]["waivers"]["uncommitted"] == 1, \
        result.report["artifacts"][0]["waivers"]


def test_the_committed_fixture_carries_the_shape(tmp_path):
    """a design rule: the one-known-bad input is a COMMITTED tree, not a temp-path guess.

    The fixture is the SHAPE a checker has to refuse; the test dirties a copy of
    it, because a waiver that is uncommitted cannot itself be committed.
    """
    fixture = conftest.broken_fixture(UNCOMMITTED_FIXTURE)
    record = json.loads((fixture / "waivers.json").read_text(encoding="utf-8"))
    assert record["waivers"], "the fixture declares no waiver at all"
    for entry_obj in record["waivers"]:
        assert conformance.waiver_is_well_formed(entry_obj), entry_obj

    work = conftest.committed_tree(tmp_path, fixture)
    clean = run_conformance(work, report=tmp_path / "clean.json")
    assert entry(clean.report, "CHECK-10")["code"] == core.EXIT_PASS, clean.stdout

    record["waivers"].append(a_waiver(check_id="CHECK-03",
                                      finding_id="limits:unedited"))
    write_json(work / "waivers.json", record)
    dirty = run_conformance(work, report=tmp_path / "dirty.json")
    ten = entry(dirty.report, "CHECK-10")
    assert ten["code"] == core.EXIT_FINDING, (
        "the fixture's own shape did not reproduce the finding:\n%s"
        % dirty.stdout)
