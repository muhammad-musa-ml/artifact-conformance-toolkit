"""`tools/mwlock.py` -- the program's one measurement window.

The load-bearing test here is test_live_holder_is_never_preempted_regardless_of_age.
It encodes a design rule against the shape of the analog this module was copied from
(`record_index.py:187-275`), which breaks a lock on AGE. a design rule forbids that:
*preempting a run that legitimately overran is the silent-corruption case on a
GPU measurement.* A test that only checked "a stale lock is eventually broken"
would pass against the analog's predicate and against a design rule's, so it could not
tell them apart -- this one can, because the ages it uses are absurd.

The second load-bearing test is test_pid_liveness_is_measured_against_a_real_process.
The liveness predicate is the whole of a design rule's auto-break, and on Windows the
obvious implementation (`os.kill(pid, 0)`) is MEASURED in this suite to answer
ALIVE for a process that has already exited -- a predicate that cannot
discriminate, which would make a dead holder's lock unbreakable forever while
every other test still passed.
"""

import importlib.util
import os
import subprocess
import sys
import time
import tokenize
from pathlib import Path

import pytest

from tools.tests import conftest

REPO_ROOT = conftest.REPO_ROOT
MWLOCK_PATH = REPO_ROOT / "tools" / "mwlock.py"

# A span longer than any plausible staleness window a reader might reach for,
# and longer than the whole ~103-day program. Stated as a number so the test
# cannot be satisfied by a generously-sized age threshold.
ABSURD_AGE_SECONDS = 10 * 365 * 24 * 60 * 60


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


mwlock = _load("mwlock_under_test", MWLOCK_PATH)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sleeper():
    """A real child process, started so liveness can be MEASURED not inferred."""
    return subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(120)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _dead_pid():
    """A pid that was real and is now provably gone. Started and killed here."""
    child = _sleeper()
    pid = child.pid
    child.kill()
    child.wait(timeout=30)
    # Keep the Popen referenced: on Windows the parent still holds a handle to
    # the exited process, which is the exact case os.kill(pid, 0) gets wrong.
    time.sleep(0.2)
    return pid, child


def _write_holder(lock, pid, acquired_at, uuid_hex="deadbeef" * 4):
    """Author a lock file through the module's OWN encoder.

    Never a hand-typed record: a test that types the format is testing its own
    typing, and drifts silently the first time the format changes.
    """
    text = mwlock._encode_record(pid, uuid_hex, acquired_at)
    Path(lock).parent.mkdir(parents=True, exist_ok=True)
    with open(str(lock), "w", encoding="ascii", newline="") as handle:
        handle.write(text)
    return text


# ---------------------------------------------------------------------------
# The acquire / release primitive
# ---------------------------------------------------------------------------

def test_acquire_creates_the_lock_and_records_pid_and_uuid(tmp_path):
    lock = tmp_path / "mw.lock"
    token = mwlock.acquire(lock, timeout=2.0)
    try:
        assert lock.is_file(), "acquire() did not create the lock file"
        holder = mwlock.read_holder(lock)
        assert holder is not None, "the lock carries no parseable holder record"
        assert holder["pid"] == os.getpid()
        assert holder["uuid"], "no uuid recorded; two holders with the same pid " \
                               "would be indistinguishable"
        assert token == "%d:%s" % (holder["pid"], holder["uuid"])
        assert isinstance(holder["acquired_at"], float)
    finally:
        mwlock.release(lock, token)


def test_release_removes_the_lock_when_it_carries_our_token(tmp_path):
    lock = tmp_path / "mw.lock"
    token = mwlock.acquire(lock, timeout=2.0)
    assert mwlock.release(lock, token) is True
    assert not lock.exists()


def test_release_refuses_a_lock_carrying_a_different_token(tmp_path):
    lock = tmp_path / "mw.lock"
    token = mwlock.acquire(lock, timeout=2.0)
    try:
        assert mwlock.release(lock, "999999:notourtoken") is False
        assert lock.is_file(), (
            "release() removed a lock it does not hold -- that is how one "
            "writer frees another writer's window mid-write"
        )
    finally:
        mwlock.release(lock, token)


def test_release_of_a_missing_lock_is_false_not_an_exception(tmp_path):
    lock = tmp_path / "absent.lock"
    assert mwlock.release(lock, "1:abc") is False


def test_acquire_after_release_succeeds(tmp_path):
    lock = tmp_path / "mw.lock"
    first = mwlock.acquire(lock, timeout=2.0)
    mwlock.release(lock, first)
    second = mwlock.acquire(lock, timeout=2.0)
    try:
        assert second != first, "a re-acquire reused the previous uuid"
    finally:
        mwlock.release(lock, second)


# ---------------------------------------------------------------------------
# a design rule: liveness, never age
# ---------------------------------------------------------------------------

def test_live_holder_is_never_preempted_regardless_of_age(tmp_path):
    """THE a design rule TEST. A living holder keeps its window however old the lock is.

    The recorded acquire time here is ten years in the past. Any age-based
    predicate breaks this lock; a design rule's liveness predicate must not.
    """
    lock = tmp_path / "mw.lock"
    _write_holder(lock, os.getpid(), time.time() - ABSURD_AGE_SECONDS)
    # Backdate the file itself too, so an implementation reading mtime rather
    # than the record is equally exposed.
    old = time.time() - ABSURD_AGE_SECONDS
    os.utime(str(lock), (old, old))

    with pytest.raises(TimeoutError):
        mwlock.acquire(lock, timeout=0.4, poll_interval=0.02)

    assert lock.is_file(), "the live holder's lock was broken -- a design rule violated"
    holder = mwlock.read_holder(lock)
    assert holder["pid"] == os.getpid()


def test_dead_holder_lock_is_broken_and_acquired(tmp_path):
    lock = tmp_path / "mw.lock"
    pid, child = _dead_pid()
    assert mwlock.pid_is_alive(pid) is False, (
        "the liveness probe says a killed-and-reaped child is alive; the rest "
        "of this test cannot mean anything until that is fixed"
    )
    # A RECENT acquire time: age must play no part in the break decision.
    _write_holder(lock, pid, time.time())
    token = mwlock.acquire(lock, timeout=2.0, poll_interval=0.02)
    try:
        holder = mwlock.read_holder(lock)
        assert holder["pid"] == os.getpid(), "the lock was not re-taken by us"
    finally:
        mwlock.release(lock, token)
        del child


def test_pid_liveness_is_measured_against_a_real_process():
    """Start a process, probe it, kill it, probe again. No inference."""
    child = _sleeper()
    try:
        time.sleep(0.5)
        assert mwlock.pid_is_alive(child.pid) is True, (
            "a running child was reported dead -- its lock would be stolen"
        )
    finally:
        child.kill()
        child.wait(timeout=30)
    time.sleep(0.2)
    assert mwlock.pid_is_alive(child.pid) is False, (
        "a killed child was reported alive -- a dead holder's lock would never "
        "be broken. This is the measured failure mode of os.kill(pid, 0) on "
        "Windows and the reason this module does not use it."
    )


def test_os_kill_zero_cannot_discriminate_on_windows():
    """Pin the MEASURED reason os.kill(pid, 0) is not the predicate here.

    Measured 2026-09-15 on Python 3.12.11 / Windows 11: os.kill(pid, 0) returns
    without raising for a child that has already exited AND been reaped, so it
    answers ALIVE for both live and dead. On POSIX it raises ProcessLookupError
    for the dead one, which is why the naive implementation looks correct until
    it runs here.
    """
    if os.name != "nt":
        pytest.skip("the discrimination failure being pinned is Windows-specific")
    child = _sleeper()
    time.sleep(0.5)
    pid = child.pid
    child.kill()
    child.wait(timeout=30)
    time.sleep(0.2)

    def kill_says_alive(target):
        try:
            os.kill(target, 0)
            return True
        except OSError:
            return False

    assert kill_says_alive(pid) is True, (
        "os.kill(pid, 0) now discriminates on this platform; re-measure before "
        "changing mwlock's predicate, and update this pin with the new evidence"
    )
    assert mwlock.pid_is_alive(pid) is False, (
        "mwlock's own predicate must get this case right where os.kill does not"
    )


def test_a_future_acquire_time_is_never_broken(tmp_path):
    """A record claiming the future is corrupt or clock-skewed; refuse to break."""
    lock = tmp_path / "mw.lock"
    pid, child = _dead_pid()
    _write_holder(lock, pid, time.time() + ABSURD_AGE_SECONDS)
    with pytest.raises(TimeoutError):
        mwlock.acquire(lock, timeout=0.4, poll_interval=0.02)
    assert lock.is_file()
    del child


def test_an_unparseable_lock_is_never_auto_broken(tmp_path):
    lock = tmp_path / "mw.lock"
    lock.write_text("this is not a holder record\n", encoding="ascii", newline="")
    with pytest.raises(TimeoutError):
        mwlock.acquire(lock, timeout=0.4, poll_interval=0.02)
    assert lock.is_file(), (
        "a lock whose record could not be read was auto-broken; the manual "
        "--break escape hatch exists for exactly this case"
    )


# ---------------------------------------------------------------------------
# The identity check
# ---------------------------------------------------------------------------

def test_a_lock_recreated_between_the_decision_and_the_unlink_is_not_stolen(
        tmp_path, monkeypatch):
    """The analog's identity check, kept verbatim in shape.

    A dead holder's lock is observed, judged breakable, and then RE-CREATED by
    another holder before the unlink. The mtime seen at the unlink differs from
    the one the decision was made on, so the break must abort.

    The perturbation alternates so it fires on EVERY decision, not just the
    first. A one-shot version passed against an implementation with no identity
    check at all, because the loop simply retried and the second decision saw a
    self-consistent pair -- the test would have been reporting the retry, not
    the guard.
    """
    lock = tmp_path / "mw.lock"
    pid, child = _dead_pid()
    _write_holder(lock, pid, time.time())

    real = mwlock._stat_mtime_ns
    calls = {"n": 0}

    def racing_stat(path):
        calls["n"] += 1
        state, mtime = real(path)
        # Every SECOND call within a decision is the re-stat before the unlink.
        if calls["n"] % 2 == 0 and state == "present":
            return state, mtime + 1  # a DIFFERENT lock sits here now
        return state, mtime

    monkeypatch.setattr(mwlock, "_stat_mtime_ns", racing_stat)

    # The predicate itself, directly: it must refuse, and leave the file alone.
    assert mwlock._break_if_holder_dead(lock) is False, (
        "the break went ahead after the lock changed identity under it"
    )
    assert lock.is_file(), "a re-created lock was stolen"
    assert calls["n"] >= 2, (
        "the break decision never re-stat'ed; there is no identity check to test"
    )

    # And through the public path, where the race recurs on every attempt.
    with pytest.raises(TimeoutError):
        mwlock.acquire(lock, timeout=0.4, poll_interval=0.02)
    assert lock.is_file(), "a re-created lock was stolen by acquire()"
    del child


def test_a_stat_failure_other_than_missing_answers_not_broken(tmp_path, monkeypatch):
    """Answering 'freed' on an arbitrary OSError burns the acquire budget.

    Measured in the analog at 2,064 os.open attempts inside a 0.2 s window,
    because 'freed' skips the backoff and sends the loop straight back round.
    """
    lock = tmp_path / "mw.lock"
    pid, child = _dead_pid()
    _write_holder(lock, pid, time.time())

    monkeypatch.setattr(mwlock, "_stat_mtime_ns",
                        lambda path: ("unknown", None))
    opens = {"n": 0}
    real_open = os.open

    def counting_open(path, flags, *args, **kwargs):
        if str(path) == str(lock):
            opens["n"] += 1
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", counting_open)

    with pytest.raises(TimeoutError):
        mwlock.acquire(lock, timeout=0.3, poll_interval=0.02)

    assert opens["n"] < 100, (
        "the acquire loop spun %d times in 0.3 s -- an unknown stat failure was "
        "treated as 'the path is free' and skipped the backoff" % opens["n"]
    )
    del child


# ---------------------------------------------------------------------------
# Timeout and the Windows delete-pending defect
# ---------------------------------------------------------------------------

def test_a_held_lock_makes_a_second_acquire_raise_timeouterror(tmp_path):
    lock = tmp_path / "mw.lock"
    token = mwlock.acquire(lock, timeout=2.0)
    try:
        with pytest.raises(TimeoutError):
            mwlock.acquire(lock, timeout=0.3, poll_interval=0.02)
    finally:
        mwlock.release(lock, token)


def test_timeout_raises_rather_than_returning_a_falsy_value(tmp_path):
    """A caller that ignores a falsy return writes UNLOCKED. Raising is the point."""
    lock = tmp_path / "mw.lock"
    token = mwlock.acquire(lock, timeout=2.0)
    try:
        outcome = None
        try:
            outcome = mwlock.acquire(lock, timeout=0.3, poll_interval=0.02)
        except TimeoutError as exc:
            assert str(lock) in str(exc), (
                "the timeout message does not name the lock, so an operator "
                "cannot find what to break"
            )
        else:
            pytest.fail(
                "acquire() returned %r instead of raising; a caller writing "
                "`if not acquire(...)` would proceed UNLOCKED" % (outcome,)
            )
    finally:
        mwlock.release(lock, token)


def test_permissionerror_is_retried_not_escaped(tmp_path, monkeypatch):
    """The MEASURED Windows delete-pending defect: 1 in 40 eight-thread rounds.

    `unlink` leaves the NAME delete-pending while the last handle closes, and an
    O_CREAT|O_EXCL create against a delete-pending name fails ERROR_ACCESS_DENIED
    (PermissionError), NOT ERROR_FILE_EXISTS. Catching only FileExistsError let
    that denial escape the retry loop entirely, and the writer that hit it LOST
    ITS ENTRY.
    """
    lock = tmp_path / "mw.lock"
    real_open = os.open
    state = {"denials": 3}

    def denying_open(path, flags, *args, **kwargs):
        if str(path) == str(lock) and state["denials"] > 0:
            state["denials"] -= 1
            raise PermissionError(13, "delete-pending (simulated)")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", denying_open)

    token = mwlock.acquire(lock, timeout=3.0, poll_interval=0.01)
    monkeypatch.undo()
    try:
        assert state["denials"] == 0, "the denials were never exercised"
        assert lock.is_file()
    finally:
        mwlock.release(lock, token)


# ---------------------------------------------------------------------------
# The context manager, the paths, and the manual break
# ---------------------------------------------------------------------------

def test_held_releases_on_exit_and_on_an_exception(tmp_path):
    lock = tmp_path / "mw.lock"
    with mwlock.held(lock, timeout=2.0):
        assert lock.is_file()
    assert not lock.exists()

    with pytest.raises(ValueError):
        with mwlock.held(lock, timeout=2.0):
            raise ValueError("boom")
    assert not lock.exists(), "held() leaked the lock when the body raised"


def test_lock_path_for_keeps_the_target_suffix(tmp_path):
    target = tmp_path / "records.md"
    lock = Path(mwlock.lock_path_for(target))
    assert lock.name == "records.md.lock", (
        "the lock must be unmistakably the lock OF that file; with_suffix would "
        "drop the .md and two different targets could share one lock"
    )
    assert lock.parent == target.parent


def test_default_lock_path_is_under_the_working_checkout():
    """The lock is OUTPUT, so it is anchored to the checkout that produced it."""
    default = Path(mwlock.default_lock_path()).resolve()
    working = Path(mwlock.working_repo_root()).resolve()
    assert working in default.parents or default.parent == working


def test_manual_break_prints_what_it_broke(tmp_path, capsys):
    lock = tmp_path / "mw.lock"
    token = mwlock.acquire(lock, timeout=2.0)
    assert token
    code = mwlock.main(["--break", "--lock", str(lock)])
    captured = capsys.readouterr()
    assert code == 0
    assert not lock.exists(), "--break did not remove the lock"
    assert str(os.getpid()) in captured.out, (
        "--break printed no holder; an escape hatch that does not say what it "
        "broke is how a live run is preempted silently"
    )


def test_manual_break_on_a_free_lock_reports_did_not_run(tmp_path, capsys):
    lock = tmp_path / "absent.lock"
    code = mwlock.main(["--break", "--lock", str(lock)])
    captured = capsys.readouterr()
    assert code == 2, (
        "breaking nothing reported success; 'found a problem' and 'could not "
        "look' are different answers"
    )
    assert "DID-NOT-RUN" in captured.out or "DID-NOT-RUN" in captured.err


def test_status_reports_the_holder_and_its_liveness(tmp_path, capsys):
    lock = tmp_path / "mw.lock"
    token = mwlock.acquire(lock, timeout=2.0)
    try:
        code = mwlock.main(["status", "--lock", str(lock)])
        captured = capsys.readouterr()
        assert code == 0
        assert str(os.getpid()) in captured.out
        assert "alive" in captured.out.lower()
    finally:
        mwlock.release(lock, token)


def test_the_lock_file_is_ascii_and_carries_no_carriage_return(tmp_path):
    lock = tmp_path / "mw.lock"
    token = mwlock.acquire(lock, timeout=2.0)
    try:
        raw = lock.read_bytes()
        assert b"\r" not in raw, (
            "the lock record was written through Windows text translation"
        )
        raw.decode("ascii")
    finally:
        mwlock.release(lock, token)


def test_age_based_breaking_is_absent_from_the_source():
    """a design rule's rejected predicate must not be present as LIVE code.

    The classification is STRUCTURAL, via tokenize, not textual. A first draft
    stripped `#` comments by hand and called everything else executable, which
    made the module's own DOCSTRING -- the record of why age-breaking was
    rejected -- read as a violation. Documenting the rejection is the point; a
    text predicate that cannot tell a docstring from a statement punishes it.

    LIVE  = the token appears as a NAME (an identifier being defined or read).
    FROZEN = it appears inside a STRING or a COMMENT, i.e. prose about the
             predicate that was rejected.
    """
    source = MWLOCK_PATH.read_text(encoding="ascii")
    stale_token = "_LOCK_" + "STALE_SECONDS"

    live_hits = []
    documented = 0
    with open(str(MWLOCK_PATH), "rb") as handle:
        for token in tokenize.tokenize(handle.readline):
            if stale_token not in token.string:
                continue
            if token.type == tokenize.NAME:
                live_hits.append("line %d: %s" % (token.start[0], token.string))
            elif token.type in (tokenize.STRING, tokenize.COMMENT):
                documented += 1

    assert not live_hits, (
        "the analog's age-based staleness constant appears as LIVE code, which "
        "is the one line a design rule forbids copying:\n%s" % "\n".join(live_hits)
    )
    assert documented >= 1, (
        "the rejected predicate is named nowhere in %s. The next reader will "
        "open the analog, find its age break, and reintroduce it -- the "
        "rejection has to be recorded where they will be looking."
        % MWLOCK_PATH.name
    )
    assert stale_token in source


def test_permissionerror_is_named_in_the_source():
    source = MWLOCK_PATH.read_text(encoding="ascii")
    assert source.count("PermissionError") >= 1


# ---------------------------------------------------------------------------
# The self-deadlock. REGRESSION -- found by running the module, not by a test.
# ---------------------------------------------------------------------------

_WRITER_SOURCE = """
import importlib.util, sys
spec = importlib.util.spec_from_file_location("m", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
lock, target, tag, rounds = sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])
for index in range(rounds):
    with m.held(lock, timeout=45.0, poll_interval=0.005):
        with open(target, "r", encoding="ascii", newline="") as handle:
            body = handle.read()
        body += "%s-%d\\n" % (tag, index)
        with open(target, "w", encoding="ascii", newline="") as handle:
            handle.write(body)
"""


def test_concurrent_holders_each_land_every_entry(tmp_path):
    """Six real PROCESSES, four rounds each. Every entry must survive.

    THE REGRESSION THIS PINS was invisible to every other test in this module
    and was found only by running the thing: `release()` swallowed the
    PermissionError that `os.unlink` raises while another process holds the
    lock open, returned False, and left the window on disk carrying the
    releasing holder's OWN live pid. The holder then blocked on its own record
    -- and a design rule's liveness probe is powerless there, because the holder really
    is alive. Measured first time out: 7 of 8 writers timed out at 60 s and 7
    of 40 entries survived.

    A unit test cannot reach this. The trigger is a concurrent open HANDLE, and
    the failure rate was measured at 165 in 300 unlinks with a single reader.
    """
    lock = tmp_path / "window.lock"
    target = tmp_path / "entries.txt"
    target.write_text("", encoding="ascii", newline="")

    writers, rounds = 6, 4
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _WRITER_SOURCE, str(MWLOCK_PATH),
             str(lock), str(target), "w%d" % n, str(rounds)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for n in range(writers)
    ]
    outcomes = []
    for proc in procs:
        _, err = proc.communicate(timeout=300)
        outcomes.append((proc.returncode, err))

    failed = [err for code, err in outcomes if code != 0]
    assert not failed, (
        "%d of %d writers failed to take the window:\n%s"
        % (len(failed), writers, "\n".join(failed[:2]))
    )

    lines = [line for line in
             target.read_text(encoding="ascii").splitlines() if line.strip()]
    expected = writers * rounds
    assert len(lines) == expected, (
        "expected %d entries, found %d -- a writer's entry was lost, which is "
        "the silent failure the lock exists to prevent" % (expected, len(lines))
    )
    assert len(set(lines)) == expected, "entries were duplicated"
    assert not lock.exists(), "the window was left held after every writer exited"


def test_release_raises_rather_than_stranding_the_window(tmp_path, monkeypatch):
    """A release that cannot remove OUR lock must not report a quiet False.

    False here means "not ours", and a caller cannot tell that apart from "ours
    but stuck" -- which is a program-wide deadlock reported as an ordinary
    boolean.
    """
    lock = tmp_path / "mw.lock"
    token = mwlock.acquire(lock, timeout=2.0)

    monkeypatch.setattr(mwlock, "_unlink_with_retry", lambda path, **kw: False)
    with pytest.raises(OSError) as caught:
        mwlock.release(lock, token)
    monkeypatch.undo()

    assert "--break" in str(caught.value), (
        "the raise does not tell the operator how to clear the window"
    )
    assert mwlock.release(lock, token) is True


def test_unlink_retries_past_a_transient_sharing_violation(tmp_path, monkeypatch):
    """[WinError 32] is transient; one shot is not enough. MEASURED: 165/300."""
    target = tmp_path / "held.txt"
    target.write_text("x", encoding="ascii", newline="")

    real_unlink = os.unlink
    state = {"denials": 4}

    def denying_unlink(path, *args, **kwargs):
        if str(path) == str(target) and state["denials"] > 0:
            state["denials"] -= 1
            raise PermissionError(
                32, "The process cannot access the file because it is being "
                    "used by another process")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", denying_unlink)
    assert mwlock._unlink_with_retry(target, budget=2.0) is True
    monkeypatch.undo()
    assert state["denials"] == 0, "the denials were never exercised"
    assert not target.exists()


def test_unlink_retry_gives_up_and_says_so(tmp_path, monkeypatch):
    target = tmp_path / "stuck.txt"
    target.write_text("x", encoding="ascii", newline="")
    monkeypatch.setattr(
        os, "unlink",
        lambda *a, **k: (_ for _ in ()).throw(PermissionError(32, "stuck")))
    assert mwlock._unlink_with_retry(target, budget=0.1) is False


def test_break_reports_an_unparseable_lock_it_removed(tmp_path, capsys):
    """The auto-break refuses an unparseable record, so --break is what clears
    it -- and reporting 'broke nothing' would leave the operator believing the
    window was already clean."""
    lock = tmp_path / "mw.lock"
    lock.write_text("garbage\n", encoding="ascii", newline="")
    code = mwlock.main(["--break", "--lock", str(lock)])
    captured = capsys.readouterr()
    assert code == 0, "breaking a real (if unreadable) lock reported DID-NOT-RUN"
    assert not lock.exists()
    assert "broke the measurement window" in captured.out
