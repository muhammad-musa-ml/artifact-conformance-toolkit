"""tools/render.py -- the tool whose job is REFUSING.

Every test here runs render.py AS A SUBPROCESS, by path, through
conftest.run_cli. That is not incidental:

  * by path, under a bare module name, is exactly how the vendored copy is run
    inside an artifact (a design rule/a design rule). A test that imported it as `tools.render`
    would exercise a code path no artifact ever takes.
  * as a subprocess, because the thing under test is an EXIT CODE. run_cli
    returns the child's own returncode, so the piped-exit-code trap -- a command
    piped into `tail` reporting the pipe's status -- is structurally impossible
    here.

THE TWO TESTS THAT CARRY THE DECISIONS are named in the plan and their RED
output is quoted in the summary:

    test_default_action_is_check_and_exits_nonzero_on_drift   (a design rule)
    test_no_force_flag_exists

The second one cannot be REDded by a stub -- a stub with no escape hatch passes
it honestly. Its evidence is a MUTATION instead: the flag is added to a
byte-snapshotted copy of render.py, the test is re-run against that copy and
observed to FAIL, and the copy is restored FROM THE SNAPSHOT (never from git --
`git checkout --` restores from HEAD and would make the verdict wrong in the
direction that flatters us). That demonstration is recorded in the summary.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT
RENDER = REPO_ROOT / "tools" / "render.py"

# BUILT FROM FRAGMENTS, NEVER PASTED. One acceptance criterion of this plan is
# that `grep -c -- '--force' tools/render.py` returns 0, and a repo-wide sweep
# for the same literal should not have to special-case this file either. The
# needle is therefore constructed, which is also the only way the assertion
# below can honestly claim the literal is absent from render.py.
_ESCAPE_HATCH_FLAG = "--" + "force"


# ---------------------------------------------------------------------------
# Fixture construction
# ---------------------------------------------------------------------------

_README = """# demo-artifact

Un-rendered prose. It carries no figure, which is what a design rule requires of it.

<!-- artifact:claim:begin -->
The median was {{figures.median_latency_ms}} ms over the replay.
<!-- artifact:claim:end -->

Prose between two regions, also carrying no figure.

<!-- artifact:env:begin -->
| Field | Value |
|---|---|
| GPU | {{figures.env_gpu_name}} |
| Runs | {{figures.run_count}} |
<!-- artifact:env:end -->

## What this does not show

Nothing was measured here. This is a hermetic fixture.
"""


def _figures(**overrides):
    record = {
        "schema": "canonkit/figures/1",
        "schema_version": "canonkit/1",
        "artifact": "demo-artifact",
        "gate_token": "0" * 64,
        "dated_at": "2026-09-15",
        "started_at": "2026-09-15T09:00:00+05:00",
        "started_at_utc": "2026-09-15T04:00:00Z",
        "figures": {
            "median_latency_ms": {
                "value": 12.5, "unit": "ms",
                "population": 500, "population_label": "replayed requests",
            },
            "env_gpu_name": {
                "value": "NVIDIA GeForce RTX 4050 Laptop", "unit": "name",
                "population": 1, "population_label": "host",
            },
            "run_count": {
                "value": 3, "unit": "runs",
                "population": 3, "population_label": "replicates",
            },
        },
    }
    record.update(overrides)
    return record


def _artifact(tmp_path, readme=_README, figures=None, slug="demo-artifact"):
    """A minimal artifact directory carrying a README and a figures record."""
    root = Path(tmp_path) / slug
    (root / "results").mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text(readme, encoding="utf-8", newline="")
    record = _figures() if figures is None else figures
    (root / "results" / "figures.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="")
    return root


def _run(artifact, *flags, cwd=None, log_dir=None):
    argv = [sys.executable, str(RENDER), str(artifact)] + [str(f) for f in flags]
    return conftest.run_cli(argv, cwd=cwd or Path(artifact).parent,
                            log_dir=log_dir)


_BEGIN_RE = re.compile(r"<!--\s*artifact:[a-z][a-z0-9_-]*:begin\s*-->")
_END_RE = re.compile(r"<!--\s*artifact:[a-z][a-z0-9_-]*:end\s*-->")


def _outside_region_text(text):
    """Every line NOT inside a region, joined.

    Derived here from the marker LINES the test itself authored rather than from
    render.py's own parser, so this assertion cannot be satisfied by a defect the
    parser and the test share.
    """
    kept = []
    inside = False
    for line in text.splitlines(keepends=True):
        if _BEGIN_RE.search(line):
            inside = True
            kept.append(line)
            continue
        if _END_RE.search(line):
            inside = False
            kept.append(line)
            continue
        if not inside:
            kept.append(line)
    return "".join(kept)


# ---------------------------------------------------------------------------
# a design rule: the default action REPORTS. The two decision-carrying tests.
# ---------------------------------------------------------------------------


def test_default_action_is_check_and_exits_nonzero_on_drift(tmp_path):
    """a success criterion's first half: a hand edit FAILS rather than being silently overwritten.

    The analog this is modelled on (the-upstream-project/scripts/dev/sync_cache.py:154)
    has --check as OPT-IN and WRITING as the default. That default is inverted
    here, deliberately, because a tool that rewrites by default destroys the edit
    it was supposed to report.
    """
    artifact = _artifact(tmp_path)
    written = _run(artifact, "--write")
    assert written.exit_code == 0, written.stderr

    rendered = (artifact / "README.md").read_bytes().decode("utf-8")
    assert "12.5" in rendered, rendered

    # ONE CHARACTER, inside a region. The kind of edit a well-meaning author
    # makes when a number looks wrong to them.
    hand_edited = rendered.replace("12.5", "12.6", 1)
    assert hand_edited != rendered
    (artifact / "README.md").write_text(hand_edited, encoding="utf-8", newline="")

    # NO FLAG.
    result = _run(artifact)
    assert result.exit_code != 0, (
        "the default action accepted a hand edit. stdout:\n%s" % result.stdout)
    assert result.exit_code == 1, (
        "drift must be a FINDING (1), not a refusal (2): the tool DID look. "
        "exit=%d\n%s\n%s" % (result.exit_code, result.stdout, result.stderr))
    assert "12.6" in result.stdout, (
        "the printed diff does not contain the edited line:\n%s" % result.stdout)
    assert "12.5" in result.stdout, (
        "the printed diff does not contain what the line should be:\n%s"
        % result.stdout)


def test_no_force_flag_exists(tmp_path):
    """a design rule: no escape hatch in the tool whose job is refusing.

    Both halves matter. Rejecting the flag alone would still pass if a
    differently-spelled override existed; asserting the literal's absence alone
    would pass if argparse silently ignored unknown flags.
    """
    artifact = _artifact(tmp_path)
    result = _run(artifact, _ESCAPE_HATCH_FLAG)
    assert result.exit_code == 2, (
        "an escape-hatch flag was not rejected with argparse's exit 2: exit=%d\n%s"
        % (result.exit_code, result.stderr))
    assert "unrecognized arguments" in result.stderr, result.stderr

    source = RENDER.read_text(encoding="ascii")
    assert source.count(_ESCAPE_HATCH_FLAG) == 0, (
        "the escape-hatch literal appears in render.py %d time(s)"
        % source.count(_ESCAPE_HATCH_FLAG))


# ---------------------------------------------------------------------------
# --write
# ---------------------------------------------------------------------------


def test_write_renders_every_reference_and_exits_zero(tmp_path):
    artifact = _artifact(tmp_path)
    result = _run(artifact, "--write")
    assert result.exit_code == 0, result.stderr
    rendered = (artifact / "README.md").read_bytes().decode("utf-8")
    assert "12.5" in rendered
    assert "NVIDIA GeForce RTX 4050 Laptop" in rendered
    # The reference SURVIVES rendering. If it did not, a second render would
    # have nothing to render from and the idempotence test below could not hold.
    assert "median_latency_ms" in rendered


def test_a_clean_render_passes_the_default_check(tmp_path):
    artifact = _artifact(tmp_path)
    assert _run(artifact, "--write").exit_code == 0
    result = _run(artifact)
    assert result.exit_code == 0, "%s\n%s" % (result.stdout, result.stderr)


def test_rendering_is_idempotent(tmp_path):
    artifact = _artifact(tmp_path)
    assert _run(artifact, "--write").exit_code == 0
    once = (artifact / "README.md").read_bytes()
    assert _run(artifact, "--write").exit_code == 0
    twice = (artifact / "README.md").read_bytes()
    assert once == twice, "a second --write changed the bytes"


def test_content_outside_every_region_is_never_modified(tmp_path):
    artifact = _artifact(tmp_path)
    before = _outside_region_text(
        (artifact / "README.md").read_bytes().decode("utf-8"))
    assert _run(artifact, "--write").exit_code == 0
    after = _outside_region_text(
        (artifact / "README.md").read_bytes().decode("utf-8"))
    assert before == after, (
        "bytes outside every region changed:\n--- before\n%r\n--- after\n%r"
        % (before, after))


def test_a_hand_edit_OUTSIDE_a_region_does_not_fail_the_check(tmp_path):
    """The discriminating half of the drift test.

    A --check that simply diffed the whole file against a freshly generated one
    would fail on any prose edit at all, which is the opposite of the contract:
    prose is the author's, regions are the tool's. Without this test the drift
    test above passes for a tool that is merely comparing whole files.
    """
    artifact = _artifact(tmp_path)
    assert _run(artifact, "--write").exit_code == 0
    text = (artifact / "README.md").read_bytes().decode("utf-8")
    edited = text.replace("Un-rendered prose.", "Un-rendered prose, revised.", 1)
    assert edited != text
    (artifact / "README.md").write_text(edited, encoding="utf-8", newline="")
    result = _run(artifact)
    assert result.exit_code == 0, (
        "an edit OUTSIDE every region was reported as drift:\n%s" % result.stdout)


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_an_unmatched_begin_marker_is_refused_with_its_line_number(tmp_path):
    readme = (
        "# demo-artifact\n"
        "\n"
        "<!-- artifact:claim:begin -->\n"
        "The median was {{figures.median_latency_ms}} ms.\n"
        "\n"
        "No end marker follows.\n"
    )
    artifact = _artifact(tmp_path, readme=readme)
    result = _run(artifact, "--write")
    assert result.exit_code == 2, (
        "an unmatched marker must REFUSE (2), not silently no-op. exit=%d\n%s"
        % (result.exit_code, result.stdout))
    assert "REFUSING:" in result.stderr, result.stderr
    assert "line 3" in result.stderr, (
        "the refusal does not name the marker's line number:\n%s" % result.stderr)
    assert "claim" in result.stderr, result.stderr


def test_an_unmatched_end_marker_is_refused_with_its_line_number(tmp_path):
    readme = (
        "# demo-artifact\n"
        "\n"
        "An end marker with nothing open.\n"
        "<!-- artifact:claim:end -->\n"
    )
    artifact = _artifact(tmp_path, readme=readme)
    result = _run(artifact, "--write")
    assert result.exit_code == 2, result.stdout
    assert "line 4" in result.stderr, result.stderr


def test_a_reference_to_an_absent_key_is_refused_naming_the_key(tmp_path):
    readme = (
        "# demo-artifact\n"
        "\n"
        "<!-- artifact:claim:begin -->\n"
        "The value was {{figures.p99_latency_ms}}.\n"
        "<!-- artifact:claim:end -->\n"
    )
    artifact = _artifact(tmp_path, readme=readme)
    result = _run(artifact, "--write")
    assert result.exit_code == 2, result.stdout
    assert "p99_latency_ms" in result.stderr, result.stderr
    # The available keys are LISTED. "unknown key" without them makes the
    # operator go and look, which is the repair instruction's whole job.
    assert "median_latency_ms" in result.stderr, result.stderr
    assert "env_gpu_name" in result.stderr, result.stderr


def test_a_figure_with_population_zero_is_refused_naming_the_figure_key(tmp_path):
    """a success criterion: PREVENTION. A figure that cannot be rendered cannot reach a README."""
    record = _figures()
    record["figures"]["median_latency_ms"]["population"] = 0
    artifact = _artifact(tmp_path, figures=record)
    result = _run(artifact, "--write")
    assert result.exit_code == 2, result.stdout
    assert "REFUSING:" in result.stderr, result.stderr
    assert "median_latency_ms" in result.stderr, (
        "the refusal does not name the figure key, so the operator must search:\n%s"
        % result.stderr)
    assert "population" in result.stderr, result.stderr
    # PREVENTION means nothing was written.
    assert "{{figures.median_latency_ms}}" in (
        artifact / "README.md").read_bytes().decode("utf-8")


def test_a_figure_with_no_population_at_all_is_refused_naming_the_figure_key(tmp_path):
    record = _figures()
    del record["figures"]["median_latency_ms"]["population"]
    artifact = _artifact(tmp_path, figures=record)
    result = _run(artifact, "--write")
    assert result.exit_code == 2, result.stdout
    assert "median_latency_ms" in result.stderr, result.stderr


def test_population_one_renders(tmp_path):
    """a design rule: population 1 is LEGAL. Peak VRAM and free VRAM at run start are
    legitimately single-sample population facts, and a rule that refused them
    would be refusing the honest case."""
    record = _figures()
    record["figures"]["median_latency_ms"]["population"] = 1
    artifact = _artifact(tmp_path, figures=record)
    result = _run(artifact, "--write")
    assert result.exit_code == 0, "%s\n%s" % (result.stdout, result.stderr)
    assert "12.5" in (artifact / "README.md").read_bytes().decode("utf-8")


def test_a_key_reference_outside_every_region_is_refused(tmp_path):
    """a design rule: a figure reference that can never be rendered is a dead instruction.

    The renderer touches region interiors only, so a reference in un-rendered
    prose would sit there forever, un-rendered and un-reported, and the author
    would reasonably conclude the mechanism had accepted it.
    """
    readme = (
        "# demo-artifact\n"
        "\n"
        "The median was {{figures.median_latency_ms}} ms.\n"
        "\n"
        "<!-- artifact:claim:begin -->\n"
        "Nothing to render here.\n"
        "<!-- artifact:claim:end -->\n"
    )
    artifact = _artifact(tmp_path, readme=readme)
    result = _run(artifact, "--write")
    assert result.exit_code == 2, result.stdout
    assert "line 3" in result.stderr, result.stderr
    assert "median_latency_ms" in result.stderr, result.stderr


def test_a_missing_figures_record_is_refused(tmp_path):
    artifact = _artifact(tmp_path)
    (artifact / "results" / "figures.json").unlink()
    result = _run(artifact)
    assert result.exit_code == 2, result.stdout
    assert "REFUSING:" in result.stderr, result.stderr
    assert "figures.json" in result.stderr, result.stderr


def test_a_figures_record_with_zero_figures_is_refused(tmp_path):
    """The 0/0 pass, at render time. Rendering over zero figures cannot fail,
    so it must not be allowed to report success."""
    record = _figures()
    record["figures"] = {}
    artifact = _artifact(tmp_path, figures=record)
    result = _run(artifact)
    assert result.exit_code == 2, result.stdout
    assert "0" in result.stderr, result.stderr


# ---------------------------------------------------------------------------
# The population line
# ---------------------------------------------------------------------------


def test_the_report_prints_rendered_n_of_m_on_the_passing_path(tmp_path):
    artifact = _artifact(tmp_path)
    result = _run(artifact, "--write")
    match = re.search(r"rendered (\d+) of (\d+) regions", result.stdout)
    assert match, "no `rendered N of M regions` line:\n%s" % result.stdout
    assert int(match.group(2)) == 2, result.stdout
    assert int(match.group(1)) == 2, result.stdout


def test_the_report_prints_rendered_n_of_m_on_the_failing_path(tmp_path):
    """A count printed only on success tells a reader nothing about a failure."""
    artifact = _artifact(tmp_path)
    assert _run(artifact, "--write").exit_code == 0
    text = (artifact / "README.md").read_bytes().decode("utf-8")
    (artifact / "README.md").write_text(
        text.replace("12.5", "99.9", 1), encoding="utf-8", newline="")
    result = _run(artifact)
    assert result.exit_code == 1
    match = re.search(r"rendered (\d+) of (\d+) regions", result.stdout)
    assert match, "no `rendered N of M regions` line on the failing path:\n%s" % (
        result.stdout)
    assert int(match.group(2)) == 2, result.stdout


def test_the_finding_list_is_truncated_with_its_own_count(tmp_path):
    """Copied from the analog: a truncated list that does not say how much it
    truncated is a list that under-reports silently."""
    keys = ["k%02d" % index for index in range(30)]
    record = _figures()
    record["figures"] = {
        key: {"value": index, "unit": "u", "population": 7,
              "population_label": "things"}
        for index, key in enumerate(keys)
    }
    body = "\n".join("- %s" % ("{{figures." + key + "}}") for key in keys)
    readme = ("# demo-artifact\n\n<!-- artifact:figures:begin -->\n"
              + body + "\n<!-- artifact:figures:end -->\n")
    artifact = _artifact(tmp_path, readme=readme, figures=record)
    assert _run(artifact, "--write").exit_code == 0

    text = (artifact / "README.md").read_bytes().decode("utf-8")
    for index in range(30):
        text = text.replace("-->%d<!--/artifact:key-->" % index,
                            "-->%d<!--/artifact:key-->" % (index + 1000), 1)
    (artifact / "README.md").write_text(text, encoding="utf-8", newline="")

    result = _run(artifact)
    assert result.exit_code == 1, result.stdout
    match = re.search(r"\.\.\. and (\d+) more", result.stdout)
    assert match, "the finding list was truncated silently:\n%s" % result.stdout
    assert int(match.group(1)) > 0


# ---------------------------------------------------------------------------
# The structured report
# ---------------------------------------------------------------------------


def test_the_structured_report_carries_a_schema_version(tmp_path):
    artifact = _artifact(tmp_path)
    report_path = Path(tmp_path) / "render-report.json"
    result = _run(artifact, "--write", "--report", report_path)
    assert result.exit_code == 0, result.stderr
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["schema_version"], payload
    assert payload["regions_rendered"] == payload["regions_found"] == 2, payload
    assert payload["action"] == "write", payload


# ---------------------------------------------------------------------------
# The file's own contract
# ---------------------------------------------------------------------------


def test_render_py_is_pure_ascii():
    """The Windows console renders correct UTF-8 as replacement characters, so
    this decodes the BYTES rather than eyeballing them."""
    RENDER.read_bytes().decode("ascii")


def test_the_module_docstring_states_that_the_analog_default_is_INVERTED():
    """The shared pattern note's Conflicts row 1: a reviewer who knows sync_cache.py will
    expect writing to be the default. Saying so is part of the deliverable."""
    source = RENDER.read_text(encoding="ascii")
    docstring = source.split('"""')[1]
    lowered = docstring.lower()
    assert "sync_cache" in lowered, docstring
    assert "invert" in lowered, docstring
    assert "mtime" in lowered, (
        "the analog's mtime warning -- judge staleness by CONTENT, never by "
        "eyeballing timestamps -- is not in the docstring")


def test_render_loads_the_core_by_path_and_never_as_a_package_module():
    """a design rule. The vendored copy has no `tools` package to import from."""
    source = RENDER.read_text(encoding="ascii")
    assert "spec_from_file_location" in source
    assert ("from tools" + " import") not in source
    assert ("import tools" + ".") not in source


# ---------------------------------------------------------------------------
# Running it FOR REAL against a generated artifact.
# ---------------------------------------------------------------------------


def test_a_real_generated_artifact_renders_and_then_checks_clean(tmp_path):
    """an earlier plan's own lesson, applied here: a green unit suite said nothing
    about whether the documented command worked on a real generated tree.

    This generates an artifact with tools/new_artifact.py, derives a figures
    record covering every key the real skeletons reference, renders, and then
    runs the documented default check.
    """
    from tools import new_artifact

    artifact = Path(tmp_path) / "demo-artifact"
    new_artifact.generate("demo-artifact", tmp_path,
                          identity=("t", "t@example.invalid"),
                          stream=open(tmp_path / "gen.log", "w", encoding="utf-8"))

    referenced = set()
    for relative in ("README.md", "results/RESULTS.md"):
        path = artifact / relative
        if path.is_file():
            referenced.update(re.findall(
                r"\{\{\s*figures\.([A-Za-z0-9_.-]+?)\s*\}\}",
                path.read_text(encoding="utf-8")))
    assert len(referenced) >= 10, sorted(referenced)

    figures = {}
    for index, key in enumerate(sorted(referenced)):
        if key in ("dated_at", "started_at", "started_at_utc"):
            continue
        figures[key] = {"value": "measured-%d" % index, "unit": "u",
                        "population": index + 1, "population_label": "items"}
    record = _figures()
    record["figures"] = figures

    (artifact / "results").mkdir(parents=True, exist_ok=True)
    (artifact / "results" / "figures.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="")

    written = _run(artifact, "--write", cwd=artifact)
    assert written.exit_code == 0, "%s\n%s" % (written.stdout, written.stderr)

    checked = _run(artifact, cwd=artifact)
    assert checked.exit_code == 0, "%s\n%s" % (checked.stdout, checked.stderr)
    assert re.search(r"rendered (\d+) of (\d+) regions", checked.stdout), (
        checked.stdout)

    # And the documented instruction from the generated README itself: the
    # default check, run with no flag, from inside the artifact.
    direct = conftest.run_cli(
        [sys.executable, str(RENDER)], cwd=artifact)
    assert direct.exit_code == 0, "%s\n%s" % (direct.stdout, direct.stderr)
