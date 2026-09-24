"""The frozen core's contract, asserted rather than promised.

HOW THIS MODULE REACHES THE CORE, AND WHY IT IS NOT A PLAIN IMPORT.
a design rule splits the frozen core OUT of the `tools` package: it is run BY PATH and
copied BY BYTES, never imported as a package module, and
test_repo_hygiene.py::test_frozen_core_is_never_imported enforces that by
scanning every repo-side module -- this file included -- for a static import of
it. So this module loads the core the same way an artifact does: by path, under
its bare sibling name. The module name is assembled from fragments for the same
reason test_repo_hygiene.py assembles its needles from fragments -- a pasted
literal here would make that guard fire against its own test suite, and the
natural "fix" for that (excluding this file from the scan) would put a hole
exactly where the guard belongs.
"""

import datetime
import importlib.util
import inspect
import json
import re
import sys
import time
import tokenize
from pathlib import Path

import pytest

from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT

_CORE_STEM = "canon" + "kit"
CORE_PATH = REPO_ROOT / "tools" / (_CORE_STEM + ".py")


def load_core():
    """Load the frozen core by PATH, exactly as a vendored copy is loaded.

    Registered in sys.modules under its bare sibling name so repeated calls
    return one module object and a dataclass defined in it stays identical
    across callers. Other test modules in this suite import this function rather
    than re-deriving the loader.
    """
    if _CORE_STEM in sys.modules:
        return sys.modules[_CORE_STEM]
    spec = importlib.util.spec_from_file_location(_CORE_STEM, str(CORE_PATH))
    if spec is None or spec.loader is None:
        raise ImportError("could not build a spec for %s" % CORE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[_CORE_STEM] = module
    spec.loader.exec_module(module)
    return module


core = load_core()


# ---------------------------------------------------------------------------
# a design rule: ASCII bytes, stdlib imports. Asserted, never eyeballed.
# ---------------------------------------------------------------------------


def test_the_core_is_ascii_bytes():
    """Decoded, not looked at.

    The Windows console renders correct UTF-8 as replacement characters, so
    "it printed fine" is evidence about the console, not about the file. This
    reads the bytes and decodes them.
    """
    payload = CORE_PATH.read_bytes()
    assert payload, "the core is empty: %s" % CORE_PATH
    payload.decode("ascii")  # raises UnicodeDecodeError on any non-ASCII byte
    assert b"\r" not in payload, (
        "the core carries %d CR byte(s). A CRLF copy hashes differently from an "
        "LF one, which breaks the vendoring assertion for a reason unrelated to "
        "content." % payload.count(b"\r")
    )


def _top_level_import_modules():
    """Every module name imported at column 0 of the core, with its line number."""
    found = []
    text = CORE_PATH.read_text(encoding="ascii")
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.startswith("import "):
            for piece in line[len("import "):].split(","):
                name = piece.strip().split(" as ")[0].strip()
                if name:
                    found.append((lineno, name.split(".")[0]))
        elif line.startswith("from "):
            name = line[len("from "):].split(" import ")[0].strip()
            if name:
                found.append((lineno, name.split(".")[0]))
    return found


def test_the_core_imports_only_stdlib():
    """a design rule, HARD: a handed-over artifact must run with no package index.

    Asserted against sys.stdlib_module_names rather than against a hand-kept
    allow-list, so a new stdlib module never needs this test edited and a
    third-party one can never be added to it.
    """
    imports = _top_level_import_modules()
    assert imports, (
        "parsed 0 top-level imports out of %s -- a parser that matched nothing "
        "would report PASS while checking nothing" % CORE_PATH
    )
    offenders = [
        "%s:%d imports %r" % (CORE_PATH.name, lineno, name)
        for lineno, name in imports
        if name not in sys.stdlib_module_names
    ]
    assert not offenders, (
        "parsed %d top-level import(s); %d are not stdlib: %s"
        % (len(imports), len(offenders), offenders)
    )


def _live_name_tokens(path):
    """Every NAME token in `path`, with its line number. Comments and strings excluded.

    A negative assertion over raw text cannot tell a CALL from a paragraph
    PROHIBITING that call, and the first draft of the test below proved it by
    firing against the core's own docstring -- the same defect an earlier plan found
    in .githooks/pre-push, where the fail-closed guard matched the comment
    explaining the fail-closed design. Tokenizing is the correctly scoped probe:
    a call is a NAME token, a prohibition of it is a STRING or COMMENT token,
    and the tokenizer is the only thing that reliably tells them apart.
    """
    names = []
    with open(str(path), "r", encoding="ascii") as handle:
        for token in tokenize.generate_tokens(handle.readline):
            if token.type == tokenize.NAME:
                names.append((token.start[0], token.string))
    return names


def test_the_core_never_calls_the_naive_utc_constructor():
    """It returns a NAIVE datetime; appending "Z" is a lie that type-checks.

    Two assertions, and the second is not redundant. The first judges LIVE CODE
    and is the real guard. The second re-derives the plan's own acceptance
    criterion (a plain `grep -c` over the file) so that criterion's result is
    MEASURED here rather than asserted elsewhere -- if a later edit reintroduces
    the token in prose, this test says so and classifies it, instead of a
    downstream sweep reporting a bare count nobody can interpret.
    """
    banned = "utc" + "now"
    names = _live_name_tokens(CORE_PATH)
    assert names, "tokenized 0 NAME tokens out of %s" % CORE_PATH
    live = ["%s:%d" % (CORE_PATH.name, lineno)
            for lineno, name in names if name == banned]
    assert not live, (
        "tokenized %d NAME token(s); the core CALLS the naive UTC constructor at %s"
        % (len(names), live)
    )

    text = CORE_PATH.read_text(encoding="ascii")
    assert text.count(banned) == 0, (
        "the token appears %d time(s) in the core's text but never in live code. "
        "That is harmless to this guard and is still worth removing: the plan's "
        "acceptance criterion for this file is a plain grep, which cannot tell a "
        "call from its prohibition." % text.count(banned)
    )


def test_the_atomic_writer_disables_text_mode_translation():
    """newline="" at the WRITE layer, beside .gitattributes at the git layer."""
    text = CORE_PATH.read_text(encoding="ascii")
    needle = 'newline=""'
    assert text.count(needle) >= 1, (
        "the core never passes %s to open(). Without it a `\\n` becomes `\\r\\n` "
        "on the way out on Windows and the sha256 an artifact records differs "
        "from the one this repository computes." % needle
    )


def test_the_core_quotes_its_source_for_the_thesis():
    """The attributed quotation is part of the contract, not decoration."""
    text = CORE_PATH.read_text(encoding="ascii")
    assert "A near-empty" in text and "UNRUN check, not a pass" in text, (
        "the finalize.py:10-11 quotation is missing from the core's docstring"
    )
    assert "finalize.py:10-11" in text, "the quotation carries no attribution"


# ---------------------------------------------------------------------------
# report() -- the population printer
# ---------------------------------------------------------------------------


def test_report_prints_on_a_pass(capsys):
    verdict = core.report("CHECK-01", True, 0, 12, 1)
    out = capsys.readouterr().out
    assert verdict == core.VERDICT_PASS
    assert out.strip(), (
        "report() printed NOTHING on a pass. A silent clean run is "
        "byte-identical to a run that never happened at the seam the caller "
        "reads (pii-scanner.py:379-398)."
    )
    assert "CHECK-01" in out


def test_report_prints_on_a_fail(capsys):
    verdict = core.report("CHECK-01", False, 3, 12, 1)
    out = capsys.readouterr().out
    assert verdict == core.VERDICT_FAIL
    assert out.strip(), "report() printed nothing on a fail"
    assert "CHECK-01" in out


def test_report_over_zero_population_is_did_not_run(capsys):
    """a design rule, HARD. This test guards a DECISION, not a mechanism.

    A future maintainer simplifying `report()` will reach for
    `verdict = "PASS" if passed else "FAIL"` -- which is correct for every
    branch except the one that matters. A check that examined nothing must say
    so; "PASS" files it as clean and "skipped" files it as deliberately omitted.
    Both are wrong in the direction that flatters the artifact.
    """
    verdict = core.report("CHECK-05", True, 0, 0, 1)
    out = capsys.readouterr().out
    assert verdict == core.VERDICT_DID_NOT_RUN, (
        "report(checked=0) returned %r; a zero-population check DID NOT RUN"
        % verdict
    )

    # THE VERDICT FIELD, NOT THE WHOLE LINE. The first draft asserted
    # `core.BANNED_VERDICT not in out` and failed against the line's own
    # `not_examined=0` COUNT column -- a needle too loose to tell a verdict from a
    # field label. The banned word is banned as a VERDICT; a count of skips is
    # exactly the population detail this line exists to carry.
    fields = out.split()
    assert len(fields) >= 2, "the population line has no verdict column: %r" % out
    assert fields[0] == "CHECK-05"
    assert fields[1] == core.VERDICT_DID_NOT_RUN, (
        "the verdict column reads %r: %r" % (fields[1], out)
    )
    assert fields[1] != core.VERDICT_PASS
    assert core.BANNED_VERDICT not in core.VERDICT_CODES, (
        "%r is a legal verdict; it reads as a deliberate, safe omission and is "
        "how a zero population gets filed as clean" % core.BANNED_VERDICT
    )


def test_report_prints_found_and_checked_as_separate_numbers(capsys):
    """found=1200 checked=0 makes a filter that removed everything visible."""
    core.report("CHECK-01", True, 1200, 0, 1, listed=1200, not_examined=1200)
    out = capsys.readouterr().out
    assert "found=1200" in out, out
    assert "checked=0" in out, out


def test_report_prints_the_effective_floor_and_the_waiver_count(capsys):
    """a design rule + CHECK-10: the PRINT is the load-bearing half of both."""
    core.report("CHECK-08", True, 0, 40, 25, waived=2)
    out = capsys.readouterr().out
    assert "floor=25" in out, out
    assert "waived=2" in out, out


def test_report_refuses_a_population_identity_that_does_not_close():
    """An identity a caller can assert is what separates a population line from decoration."""
    with pytest.raises(ValueError) as excinfo:
        core.report("CHECK-01", True, 0, 5, 1, not_examined=2, listed=99)
    assert "identity" in str(excinfo.value)


def test_report_refuses_a_negative_count():
    with pytest.raises(ValueError):
        core.report("CHECK-01", True, -1, 5, 1)


# ---------------------------------------------------------------------------
# aggregate() and summary_line()
# ---------------------------------------------------------------------------


def test_aggregate_collapses_codes_per_D18():
    assert core.aggregate([0, 0, 0]) == 0
    assert core.aggregate([0, 1, 0]) == 1
    assert core.aggregate([0, 2, 0]) == 1, (
        "a check-level 2 must aggregate UP to 1 so the artifact-level verdict "
        "is unambiguously a finding"
    )
    assert core.aggregate([0, 3, 1]) == 3
    assert core.aggregate([2]) == 1


def test_aggregate_over_zero_checks_is_did_not_run():
    """The second DECISION-encoding test. `all([])` is True; this must not be.

    An empty code list means the check set was never populated -- a glob that
    matched nothing, a discovery that imported nothing. Reporting 0 there is
    the 0/0 pass arriving one level up from where anyone looks for it.
    """
    assert core.aggregate([]) == core.EXIT_DID_NOT_RUN, (
        "aggregate([]) returned %r; an aggregate over ZERO checks did not run"
        % core.aggregate([])
    )


def test_summary_line_carries_all_five_counts():
    line = core.summary_line({
        "pass": 8, "finding": 2, "did_not_run": 1, "guard_fail": 0, "waived": 1,
    })
    assert line == "checks: 8 pass, 2 finding, 1 did-not-run, 0 guard-fail, 1 waived"


def test_summary_line_refuses_an_unknown_key():
    """A misspelled key would silently report zero for the one number this line carries."""
    with pytest.raises(ValueError):
        core.summary_line({"pass": 1, "didnotrun": 4})


def test_count_codes_round_trips_through_summary_line():
    counts = core.count_codes([0, 0, 1, 2, 3])
    assert counts["pass"] == 2
    assert counts["finding"] == 1
    assert counts["did_not_run"] == 1
    assert counts["guard_fail"] == 1
    assert "1 did-not-run" in core.summary_line(counts)


def test_exit_codes_and_verdicts_cover_each_other():
    assert (core.EXIT_PASS, core.EXIT_FINDING,
            core.EXIT_DID_NOT_RUN, core.EXIT_GUARD_FAIL) == (0, 1, 2, 3)
    assert set(core.VERDICT_CODES.values()) == {0, 1, 2, 3}
    assert core.code_for(core.VERDICT_DID_NOT_RUN) == 2
    with pytest.raises(ValueError):
        core.code_for(core.BANNED_VERDICT)


def test_die_writes_to_stderr_and_exits_with_the_given_code(capsys):
    with pytest.raises(SystemExit) as excinfo:
        core.die(core.EXIT_DID_NOT_RUN, "REFUSING: nothing to look at. Run gate.py first.")
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "REFUSING:" in captured.err
    assert captured.out == "", "a refusal on stdout is invisible to a caller redirecting it"


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------


def test_now_local_is_aware_and_carries_this_machines_real_offset():
    """Parsed, and compared against an INDEPENDENT probe of the machine's offset.

    time.localtime().tm_gmtoff does not go through datetime.astimezone(), so a
    bug in the core's own call cannot make this test agree with it by
    construction.
    """
    stamp = core.now_local()
    parsed = datetime.datetime.fromisoformat(stamp)
    assert parsed.tzinfo is not None, (
        "now_local() produced a NAIVE datetime: %r. utcnow()+'Z' is the classic "
        "way to get one, and it type-checks." % stamp
    )
    expected_offset = time.localtime().tm_gmtoff
    assert parsed.utcoffset().total_seconds() == expected_offset, (
        "now_local() reports offset %s while this machine is at %s seconds"
        % (parsed.utcoffset(), expected_offset)
    )
    if expected_offset != 0:
        assert not stamp.endswith("+00:00"), (
            "this machine is %d seconds off UTC but now_local() stamped +00:00"
            % expected_offset
        )


def test_now_utc_is_aware_and_at_zero_offset():
    parsed = datetime.datetime.fromisoformat(core.now_utc())
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def test_sha256_file_hashes_bytes_not_decoded_text(tmp_path):
    lf = tmp_path / "lf.txt"
    crlf = tmp_path / "crlf.txt"
    lf.write_bytes(b"one\ntwo\n")
    crlf.write_bytes(b"one\r\ntwo\r\n")

    assert core.sha256_file(lf) == core.sha256_bytes(b"one\ntwo\n")
    assert core.sha256_file(lf) != core.sha256_file(crlf), (
        "sha256_file() gave the same digest for LF and CRLF content -- it is "
        "reading text, not bytes, and the translation it hides is exactly the "
        "one a design rule exists to prevent"
    )


def test_sha256_bytes_refuses_a_str():
    with pytest.raises(TypeError):
        core.sha256_bytes("not bytes")


# ---------------------------------------------------------------------------
# Atomic, translation-free writes
# ---------------------------------------------------------------------------


def test_atomic_write_text_writes_lf_and_no_cr(tmp_path):
    target = tmp_path / "written.txt"
    core.atomic_write_text(target, "alpha\nbeta\n")
    payload = target.read_bytes()
    assert payload == b"alpha\nbeta\n", payload
    assert b"\r" not in payload, (
        "text-mode translation turned \\n into \\r\\n; the sha256 an artifact "
        "records would then differ from this repository's"
    )


def test_atomic_write_text_leaves_no_tmp_sibling(tmp_path):
    target = tmp_path / "written.txt"
    core.atomic_write_text(target, "payload\n")
    leftovers = sorted(p.name for p in tmp_path.glob("*.tmp"))
    assert leftovers == [], "temp files survived a successful write: %s" % leftovers


def test_atomic_write_text_leaves_no_tmp_after_a_mid_stream_raise(tmp_path):
    """The raise happens AFTER the temp file is opened, so the finally is exercised.

    chr(233) is written as a codepoint rather than pasted, so this file's own
    bytes stay ASCII. ensure_ascii=False skips the pre-flight check, which means
    the failure lands inside the open() block rather than before it -- a
    pre-flight failure would leave no temp file and would test nothing.
    """
    target = tmp_path / "doomed.txt"
    with pytest.raises(UnicodeEncodeError):
        core.atomic_write_text(target, "fine" + chr(233), encoding="ascii",
                               ensure_ascii=False)
    leftovers = sorted(p.name for p in tmp_path.glob("*.tmp"))
    assert leftovers == [], "a raise mid-write left %s behind" % leftovers
    assert not target.exists(), "a failed write created the target anyway"


def test_atomic_write_text_refuses_non_ascii_by_default(tmp_path):
    target = tmp_path / "nope.txt"
    with pytest.raises(ValueError) as excinfo:
        core.atomic_write_text(target, "cafe" + chr(233))
    assert "ASCII" in str(excinfo.value)
    assert not target.exists()


def test_atomic_write_json_is_sorted_ascii_and_reparses(tmp_path):
    target = tmp_path / "record.json"
    core.atomic_write_json(target, {"zebra": 1, "alpha": 2, "text": "caf" + chr(233)})
    payload = target.read_bytes()
    payload.decode("ascii")
    assert b"\r" not in payload
    assert payload.index(b"alpha") < payload.index(b"zebra"), (
        "keys are not sorted; a record whose key order varies hashes "
        "differently on every write"
    )
    obj = json.loads(payload.decode("ascii"))
    assert obj["text"] == "caf" + chr(233)


def test_atomic_write_json_replaces_an_existing_file(tmp_path):
    target = tmp_path / "record.json"
    core.atomic_write_json(target, {"n": 1})
    core.atomic_write_json(target, {"n": 2})
    assert json.loads(target.read_text(encoding="ascii"))["n"] == 2
    assert sorted(p.name for p in tmp_path.glob("*.tmp")) == []


def test_schema_version_is_declared():
    assert isinstance(core.SCHEMA_VERSION, str) and core.SCHEMA_VERSION
    assert "/" in core.SCHEMA_VERSION, (
        "SCHEMA_VERSION should name the producer and the version, e.g. 'x/1'"
    )


def test_the_core_is_reachable_by_path_and_not_as_a_package_module():
    """a design rule's split, re-asserted now that the file actually exists.

    an earlier plan asserted this while the file was absent, where it passes for the
    wrong reason. The file is real now: it must STILL not resolve as a package
    module, and it must still load by path.
    """
    assert CORE_PATH.is_file(), CORE_PATH
    assert Path(core.__file__).resolve() == CORE_PATH.resolve()
    assert core.__name__ == _CORE_STEM
    assert "." not in core.__name__, (
        "the core resolved as a package submodule (%r); a design rule forbids that"
        % core.__name__
    )


def test_the_core_refuses_a_dotted_package_import(tmp_path):
    """The earlier plan criterion, RE-ASSERTED now that the file is real -- and re-keyed.

    an earlier plan asserted `python -c "import tools.canonkit"` exits non-zero while
    the file DID NOT EXIST, which passes for the wrong reason: any absent module
    raises ModuleNotFoundError. The moment the file landed the dotted import
    started RESOLVING, because CPython imports any .py file sitting beside a
    package's __init__.py and setuptools has no per-module exclusion (a limit
    pyproject.toml states rather than papering over).

    So the file itself refuses. Run in a CHILD process, because this test
    process has already loaded the core under its bare name and a success here
    must not be an artifact of that.
    """
    result = conftest.run_cli(
        [sys.executable, "-c", "import tools." + _CORE_STEM], cwd=REPO_ROOT)
    assert result.exit_code != 0, (
        "the dotted package import SUCCEEDED. The frozen core is reachable as a "
        "package module, which is the drift a design rule exists to prevent."
    )
    assert "ImportError" in result.stderr, result.stderr
    assert "FROZEN CORE" in result.stderr, result.stderr


def test_the_core_does_not_import_a_schema_library():
    """a design rule: the validators are hand-written because a dependency here is forbidden.

    LIVE CODE FIRST, text second -- for the third time in this file. The first
    draft was `text.count("jsonschema") == 0` and it fired against the core's own
    comment explaining WHY the library is forbidden. `test_the_core_imports_only
    _stdlib` above already makes this impossible in general; this names the
    specific library so the failure message is the one a reader needs.
    """
    schema_libraries = {"json" + "schema", "pydantic", "cerberus", "voluptuous",
                        "marshmallow", "fastjsonschema"}
    imported = {name for _, name in _top_level_import_modules()}
    assert not (imported & schema_libraries), imported & schema_libraries

    text = CORE_PATH.read_text(encoding="ascii")
    assert text.count("json" + "schema") == 0, (
        "the token appears in the core's text but not in an import. Harmless to "
        "this guard; still removed, because the plan's acceptance criterion for "
        "this file is a plain grep."
    )


# ===========================================================================
# Task 2 -- the token, the validators, the guard shape, the numeral allow-list
# ===========================================================================


# ---------------------------------------------------------------------------
# mint_run_token
# ---------------------------------------------------------------------------

ASSERTIONS = ["free_vram_mib>=4000", "docker_running", "gate_script_sha256=abc"]
REALIZED = {"free_vram_mib": 5854, "docker": "28.4.0"}
INPUTS_HASH = "d" * 64


def test_mint_run_token_is_deterministic_across_two_calls():
    first = core.mint_run_token("demo-artifact", ASSERTIONS, REALIZED, INPUTS_HASH)
    second = core.mint_run_token("demo-artifact", ASSERTIONS, REALIZED, INPUTS_HASH)
    assert first == second
    assert len(first) == 64 and all(c in "0123456789abcdef" for c in first)


def test_mint_run_token_is_deterministic_across_two_processes(tmp_path):
    """A token that is only stable within one interpreter is not a token.

    Run in a CHILD process through conftest.run_cli, which returns the child's
    OWN exit code -- never a pipe's. The child loads the core by path under a
    neutral module name, exactly as a vendored copy is loaded.
    """
    script = (
        "import importlib.util, sys;"
        "spec = importlib.util.spec_from_file_location('frozen', r'%s');"
        "mod = importlib.util.module_from_spec(spec);"
        "spec.loader.exec_module(mod);"
        "print(mod.mint_run_token('demo-artifact', %r, %r, %r))"
        % (str(CORE_PATH), ASSERTIONS, REALIZED, INPUTS_HASH)
    )
    result = conftest.run_cli([sys.executable, "-c", script], cwd=tmp_path)
    assert result.exit_code == 0, result.stderr
    child_token = result.stdout.strip()
    assert child_token == core.mint_run_token(
        "demo-artifact", ASSERTIONS, REALIZED, INPUTS_HASH), (
        "the child process minted %r; this process mints something else"
        % child_token
    )


def test_mint_run_token_is_order_insensitive():
    forward = core.mint_run_token("demo", ASSERTIONS, REALIZED, INPUTS_HASH)
    backward = core.mint_run_token("demo", list(reversed(ASSERTIONS)),
                                   dict(reversed(list(REALIZED.items()))),
                                   INPUTS_HASH)
    assert forward == backward, (
        "the token depends on the order the gate happened to evaluate its "
        "preconditions in"
    )


def test_mint_run_token_changes_when_any_assertion_changes():
    base = core.mint_run_token("demo", ASSERTIONS, REALIZED, INPUTS_HASH)
    changed = list(ASSERTIONS)
    changed[0] = "free_vram_mib>=3000"
    assert core.mint_run_token("demo", changed, REALIZED, INPUTS_HASH) != base
    assert core.mint_run_token("other", ASSERTIONS, REALIZED, INPUTS_HASH) != base
    assert core.mint_run_token("demo", ASSERTIONS, {"free_vram_mib": 1},
                               INPUTS_HASH) != base
    assert core.mint_run_token("demo", ASSERTIONS, REALIZED, "e" * 64) != base


def test_mint_run_token_has_no_dated_at_parameter():
    """a design rule, HARD. This test guards a DECISION against a plausible future "fix".

    A maintainer reading an earlier finding's literal formula in the research will add
    `dated_at` back, because an earlier finding says to. a design rule overrides it, and a default
    argument that is merely unused would not hold: the next caller passes it.
    The parameter must not EXIST.
    """
    parameters = list(inspect.signature(core.mint_run_token).parameters)
    assert "dated_at" not in parameters, (
        "mint_run_token's signature is %s -- `dated_at` is stamped BESIDE the "
        "token in every results file, never folded into it"
        % parameters
    )
    assert parameters == ["slug", "assertions", "realized", "inputs_hash"], parameters


def test_the_token_is_blind_to_a_gate_records_date():
    """The behavioural half of the signature test, over a realistic record."""
    gate = {"slug": "demo", "assertions": ASSERTIONS, "realized": REALIZED,
            "inputs_hash": INPUTS_HASH, "dated_at": "2026-09-15T09:00:00-04:00"}
    first = core.mint_run_token(gate["slug"], gate["assertions"],
                                gate["realized"], gate["inputs_hash"])
    gate["dated_at"] = "2027-01-01T00:00:00-04:00"
    second = core.mint_run_token(gate["slug"], gate["assertions"],
                                 gate["realized"], gate["inputs_hash"])
    assert first == second


# ---------------------------------------------------------------------------
# require_gate
# ---------------------------------------------------------------------------


def _gate_record(**overrides):
    record = {
        "schema": "canonkit/gate/1",
        "schema_version": core.SCHEMA_VERSION,
        "artifact": "demo-artifact",
        "passed": True,
        "run_token": "a" * 64,
        "dated_at": "2026-09-15T09:00:00-04:00",
        "dated_at_utc": "2026-09-15T13:00:00+00:00",
        "assertions": ASSERTIONS,
        "realized": REALIZED,
        "inputs_hash": INPUTS_HASH,
        "failed_ids": [],
        "fallback_wording": "",
        "fallback_source": {"path": "canon.json", "sha256": "b" * 64,
                            "read_at": "2026-09-15"},
        "env": {"platform": "win32"},
    }
    record.update(overrides)
    return record


def _write_gate(tmp_path, record):
    results = Path(tmp_path) / "results"
    results.mkdir(parents=True, exist_ok=True)
    if record is not None:
        (results / "gate.json").write_text(
            json.dumps(record, indent=2, sort_keys=True), encoding="utf-8",
            newline="\n")
    return results


def test_require_gate_refuses_an_absent_gate(tmp_path, capsys):
    results = _write_gate(tmp_path, None)
    with pytest.raises(SystemExit) as excinfo:
        core.require_gate(results)
    assert excinfo.value.code == core.EXIT_DID_NOT_RUN
    err = capsys.readouterr().err
    assert err.startswith(core.REFUSAL_PREFIX), err
    assert "REPAIR:" in err, "the refusal does not tell the operator what to do"


def test_require_gate_refuses_an_undated_gate(tmp_path, capsys):
    results = _write_gate(tmp_path, _gate_record(dated_at=""))
    with pytest.raises(SystemExit) as excinfo:
        core.require_gate(results)
    assert excinfo.value.code == core.EXIT_DID_NOT_RUN
    err = capsys.readouterr().err
    assert err.startswith(core.REFUSAL_PREFIX)
    assert "dated_at" in err


def test_require_gate_refuses_a_failed_gate_and_echoes_the_fallback(tmp_path, capsys):
    wording = "BACKING STATUS: example project P4 not yet run."
    results = _write_gate(tmp_path, _gate_record(
        passed=False, failed_ids=["free_vram_mib>=4000"], fallback_wording=wording))
    with pytest.raises(SystemExit) as excinfo:
        core.require_gate(results)
    assert excinfo.value.code == core.EXIT_DID_NOT_RUN
    err = capsys.readouterr().err
    assert err.startswith(core.REFUSAL_PREFIX)
    assert wording in err, (
        "the refusal did not echo the canon's fallback wording verbatim; a "
        "refusal that does not say what governs instead is half a refusal"
    )
    assert "free_vram_mib>=4000" in err


def test_require_gate_returns_the_token_from_a_passing_gate(tmp_path):
    results = _write_gate(tmp_path, _gate_record(run_token="c" * 64))
    assert core.require_gate(results) == "c" * 64


def test_require_gate_in_audit_mode_returns_a_failed_gates_poisoned_token(tmp_path):
    """a design rule: a FAILED gate mints a token so an unauthorised run is DETECTABLE.

    Minting none would leave a measurement that ran anyway with no key at all.
    Minting one means it carries a POISONED token that verify.py rejects loudly.
    """
    results = _write_gate(tmp_path, _gate_record(
        passed=False, failed_ids=["docker_running"], run_token="f" * 64))
    assert core.require_gate(results, audit=True) == "f" * 64
    with pytest.raises(SystemExit):
        core.require_gate(results)


def test_require_gate_refuses_a_gate_with_no_token(tmp_path, capsys):
    results = _write_gate(tmp_path, _gate_record(run_token=""))
    with pytest.raises(SystemExit) as excinfo:
        core.require_gate(results)
    assert excinfo.value.code == core.EXIT_DID_NOT_RUN
    assert "run_token" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# validate_gate / validate_figures / validate_provenance
# ---------------------------------------------------------------------------


def test_validate_gate_accepts_a_well_formed_record_and_names_every_gap():
    assert core.validate_gate(_gate_record()) == []

    partial = _gate_record()
    del partial["inputs_hash"]
    del partial["dated_at_utc"]
    violations = core.validate_gate(partial)
    assert len(violations) == 2, violations
    assert any("inputs_hash" in v for v in violations)
    assert any("dated_at_utc" in v for v in violations)


def test_validate_gate_refuses_a_failure_that_names_nothing():
    violations = core.validate_gate(_gate_record(passed=False, failed_ids=[]))
    assert violations and any("names nothing" in v for v in violations), violations


def _figure(**overrides):
    entry = {
        "value": 0.081,
        "unit": "brier",
        "population": 4820,
        "population_label": "held-out inspections, date split",
        "derived_from": ["results.json#calibration.holdout"],
        "canon_bullet": "example-beta:P4-B2",
        "canon_value": 0.036,
        "similar": "CONFIRMS",
        "similar_reason_ref": "register-fragments/beta-artifact-4.md",
        "tier_achieved": "recompute",
        "reproduce_criterion": {"kind": "abs", "tolerance": 0.01},
        "threshold_claim": False,
        "runs": [],
        "not_shown": "A date split on one city's records.",
    }
    entry.update(overrides)
    return entry


def _figures_record(**figure_overrides):
    return {
        "schema": "canonkit/figures/1",
        "schema_version": core.SCHEMA_VERSION,
        "artifact": "beta-artifact-4",
        "gate_token": "a" * 64,
        "dated_at": "2026-11-14T09:12:03-05:00",
        "started_at": "2026-11-14T09:00:00-05:00",
        "started_at_utc": "2026-11-14T14:00:00+00:00",
        "figures": {"brier_after_calibration": _figure(**figure_overrides)},
    }


def test_validate_figures_accepts_a_well_formed_record():
    assert core.validate_figures(_figures_record()) == []


def test_validate_figures_rejects_population_zero_and_accepts_population_one():
    """a design rule: population 1 is LEGAL and rendered; 0 is the 0/0 pass in disguise.

    Peak VRAM, free VRAM at run start and disk free are legitimately
    single-sample population facts. Requiring a written reason for every n=1
    figure was considered and rejected.
    """
    zero = core.validate_figures(_figures_record(population=0))
    assert zero and any("population is 0" in v for v in zero), zero

    assert core.validate_figures(_figures_record(population=1)) == [], (
        "population: 1 must be accepted -- free VRAM at run start is a real "
        "single-sample population fact"
    )

    missing = _figures_record()
    del missing["figures"]["brier_after_calibration"]["population"]
    assert any("population" in v for v in core.validate_figures(missing))


def test_validate_figures_refuses_a_threshold_claim_without_replicates():
    """a design rule: one run landing the right side of a line is not a crossing."""
    thin = core.validate_figures(_figures_record(threshold_claim=True, runs=[1.0]))
    assert thin and any("threshold_claim" in v for v in thin), thin

    ok = core.validate_figures(
        _figures_record(threshold_claim=True, runs=[1.0, 1.1, 0.9]))
    assert ok == [], ok


def test_validate_figures_requires_a_compound_keyed_canon_bullet():
    """17 of 49 bullet ids exist in BOTH canons, so a bare id is ambiguous."""
    bare = core.validate_figures(_figures_record(canon_bullet="P2-B1"))
    assert bare and any("COMPOUND-KEYED" in v for v in bare), bare
    assert core.validate_figures(_figures_record(canon_bullet="example-beta:P2-B1")) == []
    assert core.validate_figures(_figures_record(canon_bullet="example-alpha:P1-B6")) == []


def test_validate_figures_is_permissive_about_unknown_keys():
    """2 of 49 canon bullets carry an extra `public` key; a strict reader fails on them."""
    record = _figures_record()
    record["figures"]["brier_after_calibration"]["public"] = True
    record["an_unknown_top_level_key"] = 1
    assert core.validate_figures(record) == []


def test_validate_figures_refuses_an_empty_figures_block():
    record = _figures_record()
    record["figures"] = {}
    violations = core.validate_figures(record)
    assert violations and any("EMPTY" in v for v in violations)


def _provenance_record(**overrides):
    record = {
        "schema": "canonkit/provenance/1",
        "schema_version": core.SCHEMA_VERSION,
        "sources": {"gate.py": "a" * 64},
        "images": {"redis:7.4-alpine": "redis@sha256:" + "b" * 64},
        "host": {"cpu_count": 24, "platform": "win32"},
        "run": {
            "started_at": "2026-11-14T09:00:00-05:00",
            "finished_at": "2026-11-14T09:40:00-05:00",
            "started_at_utc": "2026-11-14T14:00:00+00:00",
            "finished_at_utc": "2026-11-14T14:40:00+00:00",
            "api_spend_usd": 0.0,
            "gpu_minutes": 12.5,
            "wall_seconds": 2400,
        },
        "free_vram_mib": 5854,
    }
    record.update(overrides)
    return record


def test_validate_provenance_accepts_a_well_formed_record():
    assert core.validate_provenance(_provenance_record()) == []


def test_validate_provenance_requires_a_measured_free_vram():
    """Free VRAM has been observed at three values across two days on this machine."""
    missing = _provenance_record()
    del missing["free_vram_mib"]
    assert any("free_vram_mib" in v for v in core.validate_provenance(missing))
    assert any("free_vram_mib" in v
               for v in core.validate_provenance(_provenance_record(free_vram_mib=0)))


def test_validate_provenance_refuses_an_empty_source_census():
    assert any("EMPTY" in v
               for v in core.validate_provenance(_provenance_record(sources={})))


# ---------------------------------------------------------------------------
# validate_guards -- owner ruling C1
# ---------------------------------------------------------------------------


def _guard(**overrides):
    guard = {
        "id": "G2-coverage",
        "passed": True,
        "population": 3000,
        "population_label": "compared keys",
        "minimum_required": 500,
        "compared_keys": 3000,      # the domain-specific key, kept beside the triple
    }
    guard.update(overrides)
    return guard


def _guards_record(*guards):
    entries = list(guards) or [_guard()]
    return {"guards": entries,
            "all_guards_passed": all(g.get("passed") for g in entries)}


def test_validate_guards_accepts_the_C1_shape_with_a_domain_key_beside_it():
    assert core.validate_guards(_guards_record()) == []


def test_validate_guards_rejects_an_empty_list():
    """all() over an empty sequence is True; zero guards is a DID-NOT-RUN."""
    violations = core.validate_guards([])
    assert violations, "validate_guards([]) returned no violations"
    assert any("EMPTY" in v for v in violations), violations

    container = core.validate_guards({"guards": [], "all_guards_passed": True})
    assert any("EMPTY" in v for v in container), container


def test_validate_guards_requires_each_of_the_C1_triple():
    """C1 fixes ONE uniform shape so the program runs on ONE population convention."""
    for key in ("population", "population_label", "minimum_required"):
        guard = _guard()
        del guard[key]
        violations = core.validate_guards(_guards_record(guard))
        assert any(key in v for v in violations), (
            "a guard missing %r was accepted: %s" % (key, violations)
        )


def test_validate_guards_reports_the_shipped_redis_array_as_non_conforming():
    """The seven shipped guards, verbatim, measured rather than described.

    Only `id` and `passed` are invariant across them; the population integer
    carries FIVE different names and five of seven declare no floor at all. The
    count below is the earlier round work item: `population`, `population_label` and
    `minimum_required` must be ADDED, which is new work rather than a rename,
    because renaming a key cannot produce a floor nobody recorded.
    """
    shipped = [
        {"id": "G1a-equivalence-server-attested", "passed": True,
         "compared_keys": 3000, "mismatches": 0},
        {"id": "G1b-equivalence-client-recomputed", "passed": True,
         "compared_keys": 3000, "mismatches": 0},
        {"id": "G2-coverage", "passed": True,
         "compared_keys": 3000, "minimum_required": 500},
        {"id": "G3-driver-headroom", "passed": True,
         "driver_ceiling_rps": 32516.0, "required_factor": 1.5},
        {"id": "G4a-cache-exercised", "passed": True,
         "measured_hit_rate": 0.9857, "hits": 497982, "misses": 7245},
        {"id": "G4b-keys-bounded-by-workload", "passed": True,
         "redis_dbsize_after_run": 10536},
        {"id": "G5-two-clocks", "passed": True, "client_rps_delta": 2724.5},
    ]
    assert len(shipped) == 7
    violations = core.validate_guards({"guards": shipped, "all_guards_passed": True})

    missing_population = [v for v in violations if "'population'" in v]
    missing_label = [v for v in violations if "'population_label'" in v]
    missing_floor = [v for v in violations if "'minimum_required'" in v]

    assert len(missing_population) == 7, missing_population
    assert len(missing_label) == 7, missing_label
    assert len(missing_floor) == 6, (
        "expected 6 guards missing minimum_required (G2-coverage is the one of "
        "seven that ships it): %s" % missing_floor
    )


def test_validate_guards_catches_a_guard_passing_below_its_own_floor():
    violations = core.validate_guards(
        _guards_record(_guard(population=12, minimum_required=500)))
    assert any("below its own" in v for v in violations), violations


def test_validate_guards_catches_a_summary_flag_that_contradicts_its_guards():
    record = {"guards": [_guard(passed=False)], "all_guards_passed": True}
    violations = core.validate_guards(record)
    assert any("all_guards_passed" in v for v in violations), violations


def test_validate_guards_requires_the_top_level_flag_even_for_a_bare_list():
    """A bare list is a container missing its summary flag, never an exemption."""
    violations = core.validate_guards([_guard()])
    assert violations == ["guards record is missing top-level 'all_guards_passed'"], (
        violations
    )


# ---------------------------------------------------------------------------
# classify_numerals -- a design rule and a design rule, ONE implementation, BOTH rules
# ---------------------------------------------------------------------------


def test_classify_numerals_allows_the_five_permitted_shapes():
    text = (
        "Backs example-beta:P4-B2 and example-alpha:P1-B6, measured 2026-09-15 on\n"
        "pytest 9.1.1 with the service on localhost:8080 and the driver on port "
        "6379.\nMedian latency was {{figures.p95_ms}} at the knee.\n"
    )
    report_obj = core.classify_numerals(text)
    kinds = sorted({hit.kind for hit in report_obj.hits})
    assert report_obj.unclassified == 0, (
        "unclassified: %s"
        % [(h.token, h.context) for h in report_obj.hits
           if h.kind == core.KIND_UNCLASSIFIED]
    )
    for expected in (core.KIND_BULLET_ID, core.KIND_ISO_DATE, core.KIND_VERSION,
                     core.KIND_PORT, core.KIND_KEY_REFERENCE):
        assert expected in kinds, "%s was not classified: %s" % (expected, kinds)
    assert report_obj.classified == report_obj.total


def test_classify_numerals_reports_a_bare_numeral_in_prose():
    """a design rule: un-rendered prose may not carry a figure AT ALL."""
    report_obj = core.classify_numerals("We compared 3000 keys across the run.")
    assert report_obj.unclassified == 1, [h.token for h in report_obj.hits]
    hit = [h for h in report_obj.hits if h.kind == core.KIND_UNCLASSIFIED][0]
    assert hit.token == "3000"
    assert hit.line == 1 and hit.col >= 0


def test_classify_numerals_does_not_mistake_a_measurement_for_a_version():
    """A two-component numeral is a version only with a `v` or a specifier cue.

    `12.5` is a latency in milliseconds. A version rule loose enough to permit
    it would let every two-decimal measurement through the shape allow-list,
    and the value check cannot catch the ones that are back-solved rather than
    copied.
    """
    measured = core.classify_numerals("Median latency was 12.5 ms.")
    assert measured.unclassified == 1, [h.token for h in measured.hits]

    for permitted in ("Pinned at v1.22 today.", "Pinned at version 1.22 today.",
                      "Pinned at pytest==9.1 today.", "Pinned at 9.1.1 today."):
        report_obj = core.classify_numerals(permitted)
        assert report_obj.unclassified == 0, (permitted,
                                              [h.token for h in report_obj.hits])


def test_classify_numerals_reports_a_value_leak_the_shape_rule_permits():
    """THE CASE A SHAPE-ONLY RULE MISSES, and the reason a design rule runs both.

    8080 satisfies the shape allow-list as a port. It is ALSO a figures.json
    value, so typing it into prose is a leak -- the reader sees a number that
    the render pipeline did not put there and cannot re-derive.
    """
    text = "The service listened on port 8080 throughout."
    shape_only = core.classify_numerals(text)
    assert shape_only.unclassified == 0
    assert shape_only.value_leaks == 0

    with_values = core.classify_numerals(text, figure_values=[8080])
    assert with_values.unclassified == 0, "the shape rule still permits it"
    assert with_values.value_leaks == 1, (
        "the value check did not fire on a figure value typed into prose: %s"
        % [(leak.token, leak.context) for leak in with_values.leaks]
    )
    assert with_values.leaks[0].token == "8080"


def test_classify_numerals_does_not_leak_on_a_proper_key_reference():
    text = "Median latency was {{figures.p95_ms}} over the replay."
    report_obj = core.classify_numerals(text, figure_values={"p95_ms": 12.5})
    assert report_obj.value_leaks == 0, [leak.context for leak in report_obj.leaks]
    assert report_obj.unclassified == 0


def test_classify_numerals_accepts_a_figures_block_as_its_value_source():
    figures = _figures_record()["figures"]
    report_obj = core.classify_numerals("The Brier score was 0.081.", figures)
    assert report_obj.value_leaks == 1, [leak.token for leak in report_obj.leaks]


def test_classify_numerals_counts_are_internally_consistent():
    report_obj = core.classify_numerals(
        "Backs example-beta:P4-B2; we compared 3000 keys on 2026-09-15.")
    assert report_obj.counts["classified"] + report_obj.counts["unclassified"] == \
        report_obj.total == len(report_obj.hits)


# ---------------------------------------------------------------------------
# tools/checks/__init__.py -- the check-module contract and discovery
# ---------------------------------------------------------------------------

CHECKS_DIR = REPO_ROOT / "tools" / "checks"
CHECKS_INIT = CHECKS_DIR / "__init__.py"


def load_checks(init_path=None):
    """Load the vendored check package BY PATH, without registering it.

    Not registering means a temp COPY of the package can be loaded beside the
    real one without either shadowing the other -- which is exactly what the
    stray-module and duplicate-id tests below need.
    """
    init_path = Path(init_path) if init_path else CHECKS_INIT
    spec = importlib.util.spec_from_file_location(
        "checks_under_test", str(init_path),
        submodule_search_locations=[str(init_path.parent)])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checks = load_checks()

_CHECK_MODULE_TEMPLATE = (
    'CHECK_ID = "%s"\n'
    "DEFAULT_FLOOR = 1\n"
    "\n"
    "\n"
    "def run(artifact, ctx):\n"
    "    return None\n"
)


def _checks_copy(tmp_path, ids, name="checks"):
    """A temp copy of the check package seeded with modules declaring `ids`."""
    target = Path(tmp_path) / name
    target.mkdir(parents=True, exist_ok=True)
    (target / "__init__.py").write_text(
        CHECKS_INIT.read_text(encoding="ascii"), encoding="ascii", newline="\n")
    for index, check_id in enumerate(ids, start=1):
        (target / ("check_%02d.py" % index)).write_text(
            _CHECK_MODULE_TEMPLATE % check_id, encoding="ascii", newline="\n")
    return target


def test_the_declared_check_universe_is_ten_and_matches_its_literal():
    assert checks.DECLARED_MODULE_COUNT == 11
    assert len(checks.DECLARED_CHECK_IDS) == checks.DECLARED_MODULE_COUNT
    assert checks.DECLARED_CHECK_IDS[0] == "CHECK-01"
    assert checks.DECLARED_CHECK_IDS[-1] == "CHECK-20", (
        "the last declared id is CHECK-20, not CHECK-09: the ids are NOT "
        "contiguous, because CHECK-12..CHECK-19 were already reserved for named "
        "v2 triggers when it was declared and it took the next FREE id"
    )
    assert "CHECK-10" not in checks.DECLARED_CHECK_IDS, (
        "CHECK-10 and CHECK-11 are RUNNER properties, not modules (an earlier plan)"
    )


def test_dropping_one_id_makes_the_import_time_assertion_raise(tmp_path):
    """The literal is a tripwire on the derivation's own input.

    Raised as a real exception rather than with `assert`, so `python -O` cannot
    strip it -- a tripwire that vanishes under an optimisation flag is not one.
    """
    source = CHECKS_INIT.read_text(encoding="ascii")
    needle = '    "CHECK-20",'
    assert needle in source, "the transcribed tuple no longer looks as expected"
    mangled_dir = tmp_path / "mangled"
    mangled_dir.mkdir()
    mangled = mangled_dir / "__init__.py"
    dropped = "\n".join(line for line in source.splitlines()
                        if not line.startswith(needle))
    mangled.write_text(dropped + "\n", encoding="ascii", newline="\n")

    with pytest.raises(RuntimeError) as excinfo:
        load_checks(mangled)
    assert "DECLARED_MODULE_COUNT" in str(excinfo.value)
    # BOTH numbers, DERIVED rather than typed. This assertion read
    # `"9" in ... and "10" in ...` until 2026-09-21, and when CHECK-16 landed it
    # failed against a message that was perfectly correct -- a test pinning the
    # numbers of the day, in a message whose whole job is to report whatever the
    # two numbers happen to be. The property worth pinning is that the message
    # names the SHORTENED count and the DECLARED literal, and that is what these
    # two lines say now, at whatever values the contract currently holds.
    assert str(checks.DECLARED_MODULE_COUNT - 1) in str(excinfo.value), (
        "the message does not name the count after the drop: %s" % excinfo.value)
    assert str(checks.DECLARED_MODULE_COUNT) in str(excinfo.value), (
        "the message does not name the committed literal: %s" % excinfo.value)


def test_discover_over_a_partial_set_prints_both_numbers_and_does_not_raise(
        tmp_path, capsys):
    """A partial set is the EXPECTED state through an earlier round-8, never a failure."""
    package = _checks_copy(tmp_path, ["CHECK-01", "CHECK-03"])
    report_obj = checks.discover(package)
    out = capsys.readouterr().out
    assert "checks found 2 of 11 declared" in out, out
    assert report_obj.found == 2 and report_obj.declared == 11
    assert not report_obj.complete
    # Eleven declared minus the two seeded. A LITERAL rather than
    # `declared - found`, which would be true of any two numbers.
    assert len(report_obj.missing_ids) == 9
    assert report_obj.protocol_violations == []


def test_discover_raises_on_a_module_outside_the_declared_universe(tmp_path):
    package = _checks_copy(tmp_path, ["CHECK-01", "CHECK-99"])
    with pytest.raises(checks.DiscoveryError) as excinfo:
        checks.discover(package)
    message = str(excinfo.value)
    assert "CHECK-99" in message and "OUTSIDE" in message, message
    assert "9" in message


def test_discover_raises_on_two_modules_declaring_one_id(tmp_path):
    package = _checks_copy(tmp_path, ["CHECK-04", "CHECK-04"])
    with pytest.raises(checks.DiscoveryError) as excinfo:
        checks.discover(package)
    message = str(excinfo.value)
    assert "CHECK-04" in message
    assert "check_01.py" in message and "check_02.py" in message, message


def test_discover_over_the_real_package_reports_its_own_population(capsys):
    """Run against the live package. At an earlier round there are no check modules yet."""
    report_obj = checks.discover(CHECKS_DIR)
    out = capsys.readouterr().out
    assert "of 11 declared" in out, out
    assert report_obj.declared == 11
    assert report_obj.found == len(list(CHECKS_DIR.glob("check_*.py")))


def test_check_result_closes_its_own_population_identity():
    result = checks.CheckResult(check_id="CHECK-01", code=1, found=2, checked=10,
                                floor=1, not_examined=3)
    assert result.listed == 13
    core.report(result.check_id, result.code == 0, result.found, result.checked,
                result.floor, waived=result.waived, not_examined=result.not_examined,
                listed=result.listed)


def test_check_context_reports_the_effective_floor_not_the_declared_one():
    """a design rule: the EFFECTIVE floor is what gets printed, or the line lies."""
    ctx = checks.CheckContext(floor_overrides={"CHECK-08": 40})
    assert ctx.floor_for("CHECK-08", 25) == 40
    assert ctx.floor_for("CHECK-01", 25) == 25


def test_declared_module_count_is_defined_in_exactly_one_file():
    """A second definition would be a second source of truth for one number."""
    # ANCHORED TO AN ASSIGNMENT AT COLUMN 0. The first draft searched for the
    # bare substring `DECLARED_MODULE_COUNT =`, which is a PREFIX of this very
    # file's `checks.DECLARED_MODULE_COUNT == 11` comparison -- a needle that
    # counts a READ as a DEFINITION would have reported two sources of truth
    # for one number and been "fixed" by excluding the test file.
    pattern = re.compile(r"^DECLARED_MODULE" + r"_COUNT\s*=\s*\d", re.M)
    defining = []
    for path in sorted((REPO_ROOT / "tools").rglob("*.py")):
        if pattern.search(path.read_text(encoding="utf-8", errors="replace")):
            defining.append(str(path.relative_to(REPO_ROOT)).replace("\\", "/"))
    assert defining == ["tools/checks/__init__.py"], defining
