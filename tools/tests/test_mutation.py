"""The mutation harness and the mutant-to-guard catalogue (the design rules).

WHY THIS MODULE IS TWO HALVES.
The first half tests the HARNESS -- the dirty-tree refusal, the byte snapshot,
the verified restore, the crash-versus-guard distinction. It uses a throwaway
three-file artifact and injected fake guards, so a harness defect cannot hide
behind a real artifact's behaviour and vice versa.

The second half runs the CATALOGUE against a template-generated artifact that
has been COMMITTED, and asserts each mutant is caught by the guard NAMED in its
entry. "Caught by some guard" is the check-that-cannot-discriminate shape: it
keeps passing while the named guard has quietly stopped working.

THE LITERAL THIS FILE MAY NOT CONTAIN.
`grep -c` over this module for the git restore form a design rule forbids must return 0,
so where the concept has to be named the needle is built categorically
(`"check" + "out --"`) rather than pasted. Pasting it into the file the grep
gates is how a scaffolding needle disarms its own gate.

WHY THE FAKE GUARDS ARE NOT A SHORTCUT.
A harness test that needed a real artifact would take ~20 s per assertion and
would fail for reasons that have nothing to do with the harness. The injected
guards make the harness's OWN behaviour -- what it runs, what it prints, what it
classifies as a crash -- separately falsifiable. The real guards are exercised
by the catalogue half, where they belong.
"""

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT
MUTATE_PATH = REPO_ROOT / "tools" / "mutate.py"
CATALOGUE_PATH = REPO_ROOT / "tools" / "mutants.json"

# The form a design rule forbids, assembled rather than written, so this module can be
# grepped for it and return 0. See the module docstring.
FORBIDDEN_RESTORE = "check" + "out --"

GIT_IDENTITY = ["-c", "user.name=artifact-conformance-toolkit tests",
                "-c", "user.email=tests@example.invalid",
                "-c", "commit.gpgsign=false",
                "-c", "core.hooksPath="]


def _load(stem, path):
    """Load a module BY PATH under a bare stem -- the local convention."""
    if stem in sys.modules:
        return sys.modules[stem]
    spec = importlib.util.spec_from_file_location(stem, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError("could not build a spec for %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[stem] = module
    spec.loader.exec_module(module)
    return module


mutate = _load("mutation_harness", MUTATE_PATH)


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(work, *args):
    completed = subprocess.run(
        ["git"] + GIT_IDENTITY + list(args),
        cwd=str(work), capture_output=True, text=True,
        encoding="utf-8", errors="replace", shell=False)
    assert completed.returncode == 0, (
        "git %s failed in %s: %s" % (" ".join(args), work, completed.stderr))
    return completed


@pytest.fixture
def committed(tmp_path):
    """A tiny COMMITTED artifact: three files, a git work tree, clean status."""
    source = conftest.tmp_artifact(tmp_path)
    return conftest.committed_tree(tmp_path, source)


# ---------------------------------------------------------------------------
# Fake guards -- the harness's own behaviour, isolated from any real checker
# ---------------------------------------------------------------------------


def _python_guard(guard_id, body, fired):
    """A Guard whose command is a one-line python program with a chosen exit."""
    return mutate.Guard(
        guard_id,
        lambda tree, workdir: [sys.executable, "-c", body],
        fired)


LOUD = _python_guard(
    "fake:loud",
    "import sys; sys.stdout.write('the named guard fired\\n'); sys.exit(1)",
    lambda probe: ("the named guard fired" in probe.stdout, "loud"))

QUIET = _python_guard(
    "fake:quiet",
    "import sys; sys.exit(0)",
    lambda probe: (probe.exit_code != 0, ""))

CRASHER = _python_guard(
    "fake:crasher",
    "raise ImportError('a mutant made this module unimportable')",
    lambda probe: (probe.exit_code != 0, "would be credited if uncounted"))


ONE_MUTANT = {
    "id": "M-TEST",
    "target": "results/figures.json",
    "operation": "replace_once",
    "find": "\"schema_version\": 1",
    "replace": "\"schema_version\": 9",
    "owning_guard": ["fake:loud"],
    "expected_exit": 1,
    "probes": ["fake:loud", "fake:quiet"],
    "why": "a harness fixture, not a claim about any artifact",
}


# ===========================================================================
# TASK 1 -- the harness
# ===========================================================================


def test_dirty_tree_is_refused_with_a_repair_instruction(committed, capsys):
    """a design rule's first half. Never mutate a file with uncommitted changes.

    The verdict a mutation run produces over a dirty tree is wrong in the
    direction that flatters it: the thing restored may be the operator's own
    uncommitted work rather than the mutant.
    """
    (committed / "results" / "figures.json").write_text(
        "{\"dirty\": true}\n", encoding="utf-8", newline="")

    with pytest.raises(SystemExit) as caught:
        mutate.mutate(committed, ONE_MUTANT, guards={"fake:loud": LOUD,
                                                     "fake:quiet": QUIET})

    assert caught.value.code == mutate.EXIT_DID_NOT_RUN, caught.value.code
    message = capsys.readouterr().err
    assert "REFUSING:" in message, message
    assert "REPAIR" in message, message
    assert "commit" in message.lower(), message
    assert "figures.json" in message, message


def test_the_refusal_reads_the_TARGET_trees_status_not_this_repositorys(tmp_path):
    """Two trees, opposite verdicts, neither of them this repository.

    A refusal keyed to the harness's OWN repository would answer the same way
    for every target -- which is the shape that cannot discriminate.
    """
    clean = conftest.committed_tree(tmp_path, conftest.tmp_artifact(tmp_path))

    other = conftest.tmp_artifact(tmp_path, slug="other-artifact")
    dirty = conftest.committed_tree(tmp_path, other)
    (dirty / "README.md").write_text("edited\n", encoding="utf-8", newline="")

    # The clean one does not raise; the dirty one does. Same harness, same run.
    mutate.assert_committed(clean)
    with pytest.raises(SystemExit) as caught:
        mutate.assert_committed(dirty)
    assert caught.value.code == mutate.EXIT_DID_NOT_RUN


def test_a_snapshot_records_the_pre_mutation_sha256(committed):
    target = committed / "results" / "figures.json"
    expected = sha256_file(target)

    snap = mutate.snapshot(target)

    assert snap.sha256 == expected, (snap.sha256, expected)
    assert snap.data == target.read_bytes()
    assert Path(snap.path) == target


def test_restore_puts_the_snapshot_bytes_back_and_verifies_the_hash(committed):
    target = committed / "results" / "figures.json"
    snap = mutate.snapshot(target)

    target.write_bytes(b"{}\n")
    assert sha256_file(target) != snap.sha256

    verified = mutate.restore(snap)

    assert verified == snap.sha256
    assert sha256_file(target) == snap.sha256
    assert target.read_bytes() == snap.data


def test_a_restore_that_does_not_hash_back_RAISES(committed):
    """A restore that does not verify is not a restore.

    Forced by handing restore() a snapshot whose recorded digest cannot match
    its own bytes. Without the verification this call would return quietly and
    every later verdict would rest on an unchecked assumption.
    """
    target = committed / "results" / "figures.json"
    snap = mutate.snapshot(target)
    lying = mutate.Snapshot(path=snap.path, data=snap.data, sha256="0" * 64)

    with pytest.raises(mutate.MutationError) as caught:
        mutate.restore(lying)

    assert "sha256" in str(caught.value).lower(), str(caught.value)


def test_the_git_restore_form_appears_in_neither_the_harness_nor_this_module():
    """an earlier step's grep gate, over both files, with the needle built categorically."""
    for path in (MUTATE_PATH, Path(__file__)):
        text = path.read_text(encoding="utf-8")
        assert FORBIDDEN_RESTORE not in text, (
            "%s contains the git restore form a design rule forbids" % path)


def test_an_exception_mid_mutation_still_restores_from_the_snapshot(committed):
    """The `finally` is what makes the harness safe to interrupt."""
    target = committed / "results" / "figures.json"
    before = sha256_file(target)

    exploding = dict(ONE_MUTANT, id="M-BOOM", owning_guard=["fake:boom"],
                     probes=["fake:boom"])

    def detonate(tree, workdir):
        raise RuntimeError("the guard set blew up mid-run")

    boom = mutate.Guard("fake:boom", detonate, lambda probe: (False, ""))

    with pytest.raises(RuntimeError):
        mutate.mutate(committed, exploding, guards={"fake:boom": boom})

    assert sha256_file(target) == before, "the mutant survived the exception"
    assert not git(committed, "status", "--porcelain").stdout.strip()


def test_mutate_on_a_missing_target_refuses_and_creates_nothing(committed, capsys):
    missing = dict(ONE_MUTANT, id="M-GONE", target="results/does-not-exist.json")

    with pytest.raises(SystemExit) as caught:
        mutate.mutate(committed, missing, guards={"fake:loud": LOUD})

    assert caught.value.code == mutate.EXIT_DID_NOT_RUN
    assert "REFUSING:" in capsys.readouterr().err
    assert not (committed / "results" / "does-not-exist.json").exists(), (
        "the harness created the target it was supposed to refuse")


def test_the_printed_output_carries_command_exit_and_guard_as_three_fields(
        committed, capsys):
    """a design rule's shape. Collapsing the three is how a report stops discriminating."""
    mutate.mutate(committed, ONE_MUTANT,
                  guards={"fake:loud": LOUD, "fake:quiet": QUIET})
    printed = capsys.readouterr().out

    fields = {}
    for line in printed.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "[mutate]":
            fields.setdefault(parts[2], []).append(line)

    for name in ("command", "exit", "guard"):
        assert name in fields, (
            "no %r field in the harness output:\n%s" % (name, printed))

    assert any(sys.executable.replace(chr(92), "/") in line.replace(chr(92), "/")
               for line in fields["command"]), fields["command"]
    assert any(line.rstrip().endswith("1") for line in fields["exit"]), fields["exit"]
    assert any("fake:loud" in line for line in fields["guard"]), fields["guard"]


def test_the_mutation_changes_only_the_intended_bytes(committed):
    """an earlier step. A line-ending change mistaken for the mutation's effect.

    Read in BINARY on both sides. A text-mode comparison cannot see the very
    translation this asserts the absence of.
    """
    target = committed / "results" / "figures.json"
    original = target.read_bytes()

    snap = mutate.snapshot(target)
    mutated = mutate.apply_operation(snap, ONE_MUTANT)

    assert mutated != original
    assert len(mutated) == len(original), (
        "byte length changed: %d -> %d" % (len(original), len(mutated)))
    assert mutated.count(b"\r\n") == original.count(b"\r\n")

    differing = [index for index, (left, right)
                 in enumerate(zip(original, mutated)) if left != right]
    assert len(differing) == 1, (
        "expected exactly one differing byte, got %d at %r"
        % (len(differing), differing[:20]))
    assert original[differing[0]:differing[0] + 1] == b"1"
    assert mutated[differing[0]:differing[0] + 1] == b"9"


def test_an_operation_that_changes_nothing_is_an_ERROR_not_a_silent_pass(committed):
    """an earlier plan's measured lesson: its first mutant changed nothing and PASSED.

    A mutation whose `find` does not occur proves nothing about any guard, so it
    must be loud rather than counted as a survivor or a kill.
    """
    inert = dict(ONE_MUTANT, id="M-INERT", find="a string that is not in the file")
    snap = mutate.snapshot(committed / "results" / "figures.json")

    with pytest.raises(mutate.MutationError) as caught:
        mutate.apply_operation(snap, inert)

    assert "0 occurrence" in str(caught.value) or "no occurrence" in str(caught.value)


def test_a_probe_that_CRASHES_is_errored_never_credited_as_a_kill(committed, capsys):
    """Lesson 2: a non-zero exit can be non-zero for the WRONG reason.

    When a mutant makes a module unimportable every probe "fails", and a harness
    that reads only the exit code calls the mutant killed -- by a crash, not by a
    guard. The kill rate is then fiction.
    """
    crashing = dict(ONE_MUTANT, id="M-CRASH", owning_guard=["fake:crasher"],
                    probes=["fake:crasher"])

    result = mutate.mutate(committed, crashing, guards={"fake:crasher": CRASHER})

    assert result.errored == ["fake:crasher"], result.errored
    assert result.fired == [], result.fired
    assert not result.killed, "a crash was counted as a kill"
    assert "errored" in capsys.readouterr().out.lower()


def test_every_probe_runs_even_after_one_fires(committed):
    """A loop that stops at the first firing guard cannot answer WHICH fired.

    Attribution needs the whole probe set: "caught by another guard" is only
    observable when the guards that were not named are run too.
    """
    result = mutate.mutate(committed, ONE_MUTANT,
                           guards={"fake:loud": LOUD, "fake:quiet": QUIET})

    assert [probe.guard_id for probe in result.probes] == ["fake:loud", "fake:quiet"]
    assert result.fired == ["fake:loud"]
    assert result.killed and result.attributed


def test_the_harness_restores_and_leaves_the_tree_clean_after_a_full_cycle(committed):
    target = committed / "results" / "figures.json"
    before = sha256_file(target)

    result = mutate.mutate(committed, ONE_MUTANT,
                           guards={"fake:loud": LOUD, "fake:quiet": QUIET})

    assert result.restored_sha256 == before
    assert sha256_file(target) == before
    assert not git(committed, "status", "--porcelain").stdout.strip(), (
        "the harness left the target tree dirty")


# ===========================================================================
# TASK 2 -- the catalogue, run against a template-generated COMMITTED artifact
# ===========================================================================

from tools.tests import test_skeleton_roundtrip as skeleton  # noqa: E402

check_03 = _load("check_03_for_mutation",
                 REPO_ROOT / "tools" / "checks" / "check_03.py")

MUTATION_SLUG = "mutation-target"
ITEM_COUNT = skeleton.ITEM_COUNT


def build_committed_artifact(workdir):
    """Generate, measure, derive, author, render, fill in, COMMIT.

    The region bodies and figure specs are IMPORTED from the walking-skeleton
    module rather than re-typed: one definition, so a change there cannot leave
    this module quietly measuring a different artifact than the one an earlier plan
    proved the chain on.

    The tree is committed and asserted clean before any mutant touches it. a success criterion
    requires exactly that, and a design rule's refusal enforces it at run time -- this
    assertion is the fixture's half of the same claim.
    """
    workdir = Path(workdir)
    generate = conftest.run_cli(
        [sys.executable, "-m", "tools.new_artifact", MUTATION_SLUG,
         "--into", str(workdir)], cwd=REPO_ROOT)
    assert generate.exit_code == 0, generate.stdout + generate.stderr
    artifact = workdir / MUTATION_SLUG

    gate = conftest.run_cli(
        [sys.executable, str(artifact / "gate.py"), "--slug", MUTATION_SLUG,
         "--root", str(artifact)], cwd=workdir)
    assert gate.exit_code == 0, gate.stdout + gate.stderr

    runmeta = skeleton.load_from_artifact("mutation_runmeta", artifact, "runmeta.py")
    results = artifact / "results"
    token = json.loads((results / "gate.json").read_text(encoding="utf-8"))["run_token"]
    handle = runmeta.start_run(str(results), "run-0001", token,
                               extra={"items": ITEM_COUNT})
    for index in range(ITEM_COUNT):
        runmeta.write_item(str(results), "item-%04d" % index,
                           {"index": index, "ok": index % 4 != 3,
                            "latency_ms": 10.0 + index})
    runmeta.finish_run(handle, api_spend_usd=0.0, gpu_minutes=0.0,
                       extra={"items_written": ITEM_COUNT})

    specs = [dict(skeleton.SPEC_COMMON, **spec) for spec in skeleton.FIGURE_SPECS]
    spec_path = artifact / "figure-specs.json"
    spec_path.write_bytes((json.dumps(specs, indent=2) + "\n").encode("ascii"))
    derived = conftest.run_cli(
        [sys.executable, str(artifact / "derive.py"), "--root", str(artifact),
         "--specs", str(spec_path)], cwd=workdir)
    assert derived.exit_code == 0, derived.stdout + derived.stderr

    for name, body in (("claim", skeleton.CLAIM_BODY),
                       ("figures", skeleton.FIGURES_BODY),
                       ("env", skeleton.ENV_BODY)):
        skeleton.replace_region_body(artifact / "README.md", name, body)
        skeleton.replace_region_body(results / "RESULTS.md", name, body)
    skeleton.replace_region_body(results / "RESULTS.md", "limits",
                                 skeleton.RESULTS_LIMITS_BODY)
    skeleton.replace_region_body(artifact / "README.md", "limits",
                                 skeleton.FILLED_IN_LIMITS)

    rendered = conftest.run_cli(
        [sys.executable, str(artifact / "render.py"), str(artifact), "--write"],
        cwd=workdir)
    assert rendered.exit_code == 0, rendered.stdout + rendered.stderr

    git(artifact, "add", "-A", "--", ".")
    git(artifact, "commit", "-q", "-m", "chore: the run, the documents, the records")
    assert not git(artifact, "status", "--porcelain").stdout.strip(), (
        "the fixture tree is dirty before any mutant has touched it")
    return artifact


@pytest.fixture(scope="module")
def artifact(tmp_path_factory):
    return build_committed_artifact(tmp_path_factory.mktemp("mutation"))


@pytest.fixture(scope="module")
def catalogue():
    """The committed catalogue, with load_catalogue's SystemExit made legible.

    `load_catalogue` refuses with exit 2, which is its contract and is tested
    directly by test_an_empty_catalogue_is_exit_2. Letting that SystemExit
    escape a MODULE-scoped fixture was MEASURED to produce one real message
    followed by twelve `assert not self._finalizers` errors from pytest's own
    machinery -- so the one line that says what is wrong is buried under twelve
    that do not. A harness whose job is a legible verdict may not report its own
    failure that way.
    """
    if not CATALOGUE_PATH.is_file():
        pytest.fail("no catalogue at %s -- tools/mutants.json is not committed"
                    % CATALOGUE_PATH)
    try:
        return mutate.load_catalogue(CATALOGUE_PATH)
    except SystemExit as refusal:
        pytest.fail("load_catalogue refused with exit %s; see stderr above"
                    % refusal.code)


@pytest.fixture(scope="module")
def campaign(artifact, catalogue, tmp_path_factory):
    """ONE campaign over the WHOLE catalogue, reused by every assertion below.

    Every entry runs before anything is reported. A suite that stopped at the
    first survivor would have learned about one mutant and nothing about the
    catalogue.
    """
    return mutate.run_catalogue(
        artifact, catalogue,
        workdir=str(tmp_path_factory.mktemp("campaign")))


def tree_hashes(work):
    listing = git(work, "ls-files").stdout.split("\n")
    digests = {}
    for relative in sorted(name.strip() for name in listing if name.strip()):
        path = Path(work) / relative
        if path.is_file():
            digests[relative] = sha256_file(path)
    return digests


# ---------------------------------------------------------------------------
# The catalogue itself
# ---------------------------------------------------------------------------


def test_the_catalogue_is_non_empty_and_every_entry_states_its_why(catalogue):
    """A mutation suite over zero mutants is a DID-NOT-RUN, never a pass."""
    mutants = catalogue["mutants"]
    assert len(mutants) >= 5, "only %d mutant(s) in the catalogue" % len(mutants)
    assert len(mutants) == sum(1 for m in mutants if m.get("why")), (
        "some entry carries no `why`; the two numbers must be equal")
    assert catalogue.get("schema") == mutate.SCHEMA, catalogue.get("schema")

    ids = [m["id"] for m in mutants]
    assert len(set(ids)) == len(ids), "duplicate mutant id(s): %r" % ids


def test_an_empty_catalogue_is_exit_2(tmp_path):
    empty = tmp_path / "empty-mutants.json"
    empty.write_text(json.dumps({"schema": mutate.SCHEMA, "schema_version": 1,
                                 "mutants": []}), encoding="utf-8", newline="")

    with pytest.raises(SystemExit) as caught:
        mutate.load_catalogue(empty)

    assert caught.value.code == mutate.EXIT_DID_NOT_RUN


def test_the_run_prints_its_mutant_COUNT(artifact, catalogue, tmp_path):
    import io

    stream = io.StringIO()
    mutate.run_catalogue(artifact, catalogue, stream=stream,
                         only=[catalogue["mutants"][0]["id"]],
                         workdir=str(tmp_path))
    assert "catalogue 1 mutant(s) to attempt" in stream.getvalue()


def test_the_limits_placeholder_body_is_PINNED_to_check_03s_own_literal(catalogue):
    """An anti-rot pin: the catalogue carries a copy, so it must be CHECKED.

    A copied literal that nobody checks is the citation-rots failure -- the
    placeholder drifts, the mutant stops expressing `unedited`, and the entry
    goes on claiming to prove a condition it no longer reaches.
    """
    entries = [m for m in catalogue["mutants"]
               if m.get("operation") == "replace_region_body"]
    assert entries, "no region-body mutant in the catalogue"
    for entry in entries:
        digest = hashlib.sha256(entry["body"].encode("utf-8")).hexdigest()
        assert digest == check_03.LIMITS_PLACEHOLDER_SHA256, (
            "%s carries a limits body hashing to %s; CHECK-03's committed "
            "literal is %s. The placeholder has drifted, so this mutant no "
            "longer expresses the `unedited` condition it names."
            % (entry["id"], digest, check_03.LIMITS_PLACEHOLDER_SHA256))


# ---------------------------------------------------------------------------
# The clean tree -- the baseline every "fired" verdict is read against
# ---------------------------------------------------------------------------


def test_every_guard_is_SILENT_on_the_unmutated_artifact(artifact, tmp_path):
    """Without this, a guard that was ALREADY firing would be credited to a mutant.

    The most flattering error a mutation report can make: every mutant looks
    caught because one check was red before any of them ran.
    """
    workdir = str(tmp_path)
    noisy = []
    for guard_id in mutate.DEFAULT_PROBES:
        guard = mutate.GUARDS[guard_id]
        probe = mutate._run_probe(guard_id, guard.build(artifact, workdir), workdir)
        assert not probe.crashed(), (guard_id, probe.stderr[:400])
        fired, evidence = guard.fired(probe)
        if fired:
            noisy.append("%s: exit=%d %s" % (guard_id, probe.exit_code, evidence))
    assert not noisy, (
        "%d guard(s) already fire on the UNMUTATED artifact, so any kill they "
        "are credited with below is fiction:\n%s" % (len(noisy), "\n".join(noisy)))


# ---------------------------------------------------------------------------
# a success criterion -- the headline mutant
# ---------------------------------------------------------------------------


def test_record_mutation_fails_verify_and_passes_again_after_restore(
        artifact, catalogue, tmp_path):
    """a success criterion, both directions, on a COMMITTED tree.

    One direction is not enough: a verify.py that failed unconditionally would
    satisfy "the mutant makes it fail" perfectly.
    """
    headline = [m for m in catalogue["mutants"]
                if "verify:chain" in m.get("owning_guard", [])][0]
    workdir = str(tmp_path)

    verify_argv = mutate.GUARDS["verify:chain"].build(artifact, workdir)
    before = mutate._run_probe("verify:chain", verify_argv, workdir)
    assert before.exit_code == mutate.EXIT_PASS, before.stdout + before.stderr

    result = mutate.mutate(artifact, dict(headline), workdir=workdir)

    assert "verify:chain" in result.fired, result.fired
    assert result.exit_of_owning == mutate.EXIT_FINDING, result.exit_of_owning

    after = mutate._run_probe("verify:chain", verify_argv, workdir)
    assert after.exit_code == mutate.EXIT_PASS, (
        "verify.py still fails after the restore:\n%s" % after.stdout)


# ---------------------------------------------------------------------------
# a design rule -- attribution, in BOTH directions
# ---------------------------------------------------------------------------


def test_every_mutant_is_killed_by_a_guard_its_own_entry_NAMES(campaign):
    """The whole point. "Caught by some guard" is the shape a design rule rejects."""
    problems = []
    for result in campaign.results:
        if result.verdict() != "KILLED":
            problems.append(
                "%s: %s -- fired=%s expected=%s errored=%s"
                % (result.mutant_id, result.verdict(), result.fired or "NOTHING",
                   result.owning_guard, result.errored or "none"))
    assert not problems, (
        "%d of %d mutant(s) were not killed by the guard they name:\n%s"
        % (len(problems), campaign.attempted, "\n".join(problems)))
    assert campaign.attempted == len(campaign.killed) > 0


def test_the_four_numbers_are_reported_separately(campaign):
    """attempted / killed / survived / errored -- one rate cannot make an unrun
    probe visible."""
    assert campaign.attempted == (len(campaign.killed) + len(campaign.survived)
                                  + len(campaign.misattributed)
                                  + len(campaign.errored))
    assert campaign.attempted >= 5


def test_every_mutants_owning_guard_was_actually_PROBED(campaign, catalogue):
    """Naming a guard that is never run is a hole the verdict cannot see."""
    by_id = {m["id"]: m for m in catalogue["mutants"]}
    for result in campaign.results:
        probed = {probe.guard_id for probe in result.probes}
        named = set(by_id[result.mutant_id]["owning_guard"])
        assert named <= probed, (
            "%s names %s but only %s were probed"
            % (result.mutant_id, sorted(named - probed), sorted(probed)))


def test_a_mutant_caught_by_NOTHING_is_SURVIVED_never_a_pass(
        artifact, catalogue, tmp_path):
    """a design rule, direction one -- DEMONSTRATED by disabling the guard, not asserted.

    verify.py's own finding list is stubbed out in a byte-SNAPSHOTTED copy, so
    the headline mutant has nothing left to catch it. The snapshot is restored
    and its sha256 re-verified afterwards; git is never used to revert.
    """
    headline = [m for m in catalogue["mutants"]
                if "verify:chain" in m.get("owning_guard", [])][0]
    entry = dict(headline, probes=["verify:chain"], owning_guard=["verify:chain"])

    guard_source = artifact / "verify.py"
    snap = mutate.snapshot(guard_source)
    blinded = snap.data.replace(b"return checked, problems", b"return checked, []")
    assert blinded != snap.data, "the disabling edit matched nothing"

    try:
        mutate.atomic_write_bytes(guard_source, blinded)
        git(artifact, "add", "--", "verify.py")
        git(artifact, "commit", "-q", "-m", "chore: temporarily blind verify.py")
        result = mutate.mutate(artifact, entry, workdir=str(tmp_path))
    finally:
        restored = mutate.restore(snap)
        git(artifact, "add", "--", "verify.py")
        git(artifact, "commit", "-q", "-m",
            "chore: restore verify.py from its byte snapshot")

    assert restored == snap.sha256
    assert sha256_file(guard_source) == snap.sha256
    assert result.fired == [], result.fired
    assert result.verdict() == "SURVIVED", result.verdict()
    assert not result.killed and not result.attributed


def test_a_mutant_caught_by_ANOTHER_guard_is_MISATTRIBUTED_never_a_kill(
        artifact, catalogue, tmp_path):
    """a design rule, direction two. The result must name BOTH sides.

    A test that only checked "something caught it" is the exact shape this
    rejects: it keeps passing while the named guard has stopped working and a
    different one is quietly doing the catching.
    """
    headline = [m for m in catalogue["mutants"]
                if "verify:chain" in m.get("owning_guard", [])][0]
    mispointed = dict(headline, id="M-MISPOINTED",
                      owning_guard=["render:check"],
                      probes=["verify:chain", "render:check"])

    result = mutate.mutate(artifact, mispointed, workdir=str(tmp_path))

    assert result.killed, "the mutant was not caught at all, so this proves nothing"
    assert result.fired == ["verify:chain"], result.fired
    assert not result.attributed
    assert result.verdict() == "MISATTRIBUTED", result.verdict()
    assert "render:check" in result.owning_guard


def test_the_overlap_entry_names_more_than_one_guard_and_is_STILL_enforced(
        artifact, catalogue, tmp_path):
    """a design rule's sanctioned DATA change -- not a relaxed rule.

    Where guards legitimately overlap the entry names them all. The run still
    fails when the guard that fires is outside that list, which is what keeps it
    a rule rather than a loophole.
    """
    overlapping = [m for m in catalogue["mutants"]
                   if len(m.get("owning_guard", [])) > 1]
    assert overlapping, (
        "no entry names more than one guard, so the overlap rule is unexercised")

    entry = overlapping[0]
    outside = dict(entry, id="M-OUTSIDE", owning_guard=["verify:token"],
                   probes=sorted(set(entry["probes"]) | {"verify:token"}))

    result = mutate.mutate(artifact, outside, workdir=str(tmp_path))

    assert result.killed
    assert result.verdict() == "MISATTRIBUTED", (
        "an overlap entry whose firing guard is outside the named list must "
        "still fail; got %s fired=%s" % (result.verdict(), result.fired))


# ---------------------------------------------------------------------------
# The restore, measured rather than trusted
# ---------------------------------------------------------------------------


def test_the_tree_hashes_back_to_its_pre_mutation_state_between_mutants(
        artifact, catalogue, tmp_path):
    """Every mutant, in sequence, with the WHOLE tracked tree hashed each time."""
    before = tree_hashes(artifact)
    for index, entry in enumerate(catalogue["mutants"]):
        mutate.mutate(artifact, dict(entry),
                      workdir=str(tmp_path / ("m%02d" % index)))
        after = tree_hashes(artifact)
        changed = [key for key in before if before[key] != after.get(key)]
        assert after == before, (
            "the tree did not hash back after %s: changed=%r missing=%r"
            % (entry["id"], changed, sorted(set(before) - set(after))))
        assert not git(artifact, "status", "--porcelain").stdout.strip(), (
            "%s left the tree dirty" % entry["id"])


def test_no_mutation_changes_the_line_ending_count(artifact, catalogue):
    """an earlier step. A CRLF introduced by a mutation would be read as its effect."""
    for entry in catalogue["mutants"]:
        mutant = dict(entry)
        target = mutate.resolve_target(artifact, mutant["target"])
        snap = mutate.snapshot(target)
        mutated = mutate.apply_operation(snap, mutant)
        assert mutated.count(b"\r\n") == snap.data.count(b"\r\n"), (
            "%s changed the CRLF count in %s" % (mutant["id"], mutant["target"]))
        assert sha256_file(target) == snap.sha256, (
            "apply_operation is not pure: it wrote to disk")


def test_derive_DESTROYS_a_figures_mutant_which_is_why_its_probe_is_scoped(
        artifact, catalogue, tmp_path):
    """The MEASURED reason `derive:refuse` is not in the default probe set.

    mutate.py's docstring states that running derive over every mutant would
    overwrite the mutant mid-probe. That is a claim about behaviour, so it is
    measured here rather than believed: a figures.json mutation is applied,
    derive is run, and the mutation is shown to be GONE. If derive ever stopped
    rewriting, the scoping would be a constraint nobody asked for and this test
    would say so.
    """
    figures = artifact / "results" / "figures.json"
    snap = mutate.snapshot(figures)
    workdir = str(tmp_path)
    entry = [m for m in catalogue["mutants"]
             if m["target"] == "results/figures.json"
             and m["operation"] == "drop_key"][0]

    try:
        mutated = mutate.apply_operation(snap, dict(entry))
        mutate.atomic_write_bytes(figures, mutated)
        assert sha256_file(figures) != snap.sha256

        probe = mutate._run_probe(
            "derive:refuse",
            mutate.GUARDS["derive:refuse"].build(artifact, workdir), workdir)
        assert probe.exit_code == mutate.EXIT_PASS, probe.stdout + probe.stderr
        after_derive = figures.read_bytes()
    finally:
        assert mutate.restore(snap) == snap.sha256

    assert after_derive != mutated, (
        "derive left the mutation in place, so the scoping of its probe is an "
        "invented constraint rather than a measured one")

    # The MUTATION specifically is gone -- the dropped key is back.
    #
    # This used to say byte equality was the WRONG assertion, because derive
    # re-stamped `dated_at` from the clock on every run and its output was not
    # byte-stable even over identical records. That was true and is not any
    # more: an earlier plan item 11 was closed in an earlier plan, and the property is pinned
    # in test_verify_chain.py in both directions. The comment is corrected
    # rather than deleted, because a note asserting the opposite of what the
    # code now does is worse than no note.
    #
    # The assertion below stays keyed to the dropped KEY rather than to bytes.
    # What this test exists to measure is that derive DESTROYS a mutant, and a
    # key-level check says that in the terms the mutant was written in; bytes
    # would also fail if an unrelated figure moved, which is a different
    # finding wearing this test's name.
    # Compared against `after_derive`, the bytes captured BEFORE the finally
    # block restored the snapshot. Comparing the file on disk here would read
    # what restore() just wrote and pass no matter what derive did -- a check
    # that cannot tell the two outcomes apart is not a check.
    assert after_derive == snap.data, (
        "re-deriving over unchanged records did not reproduce the original "
        "bytes; an earlier plan item 11 has regressed")
    rewritten = json.loads(after_derive.decode("utf-8"))
    original = json.loads(snap.data.decode("utf-8"))
    dropped = entry["path"][-1]
    for key, figure in original["figures"].items():
        assert dropped in rewritten["figures"][key], (
            "derive did not re-author %r for figure %r" % (dropped, key))
        assert rewritten["figures"][key][dropped] == figure[dropped]
