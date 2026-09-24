"""mwlock -- the program's ONE measurement window, broken only for a dead holder.

Parallelization is ON and granularity is `fine`, so record-writing plans run
concurrently. A plan that appends to a shared assembled file directly loses the
other agent's write, silently -- there is no error, no conflict marker, and no
count that moves. This module is the mutual exclusion that makes the atomic
replace in `assemble_records.py` safe, and it is the gate a GPU measurement
takes so two runs never contend for the one RTX 4050.

WHERE THIS CAME FROM, AND THE ONE LINE THAT WAS DELIBERATELY NOT COPIED
-----------------------------------------------------------------------
The analog is `the-upstream-project/scripts/shared/record_index.py:187-275`, a
shipped, adversarially-hardened, Windows-tested file lock. Four of its
properties are copied verbatim in shape:

  1. `os.open(..., O_CREAT | O_EXCL | O_WRONLY)` as the exclusion primitive --
     ONE OS-level operation, atomic on Windows and POSIX alike. A
     check-then-create pair is not the same thing and loses the race it is
     written to win.
  2. `PermissionError` is caught alongside `FileExistsError` in the retry loop.
     See `_acquire_fd` for the measured reason.
  3. A `pid:uuid` token is written into the lock, and `release()` removes the
     file only while it still carries OUR token.
  4. A timeout is a `TimeoutError`, NEVER a falsy return. A caller writing
     `if not acquire(...)` against a falsy return proceeds UNLOCKED, which is
     the failure the lock exists to prevent, arriving through the lock's own
     API.

The ONE thing changed is the break predicate, and it is changed on purpose.

  a design rule: `mwlock.py` auto-breaks only when the recorded PID is provably dead on
  this host; a live holder is never preempted REGARDLESS OF AGE. Option (a)'s
  explicit manual break is kept as the escape hatch. A holder-declared maximum
  window was rejected: preempting a run that legitimately overran is the
  silent-corruption case on a GPU measurement -- the preempted run keeps
  writing, the preempting run starts measuring, and the numbers that come out
  belong to neither.

The analog breaks on AGE, through a constant it calls _LOCK_STALE_SECONDS.
That name appears in this module ONLY in prose, so a reader who reaches for the
analog finds the rejection recorded beside the thing they were about to copy.
`test_age_based_breaking_is_absent_from_the_source` asserts both halves, and it
classifies STRUCTURALLY via `tokenize`: a hit as a NAME token is the forbidden
live code, a hit inside a STRING or COMMENT token is this paragraph.

WHY NOT os.kill(pid, 0) -- MEASURED, NOT INFERRED
--------------------------------------------------
Measured on this machine 2026-09-15, Python 3.12.11 on Windows 11, against a
child process actually started and then killed:

    live child          os.kill(pid, 0) -> returns, no exception   ALIVE
    SAME pid, killed    os.kill(pid, 0) -> returns, no exception   ALIVE  <-- wrong
    never-existed pid   os.kill(pid, 0) -> OSError [WinError 87]   DEAD
    self                os.kill(pid, 0) -> returns, no exception   ALIVE

os.kill(pid, 0) therefore CANNOT DISCRIMINATE a dead holder from a live one on
Windows. It is not a weak check; it is a check that answers ALIVE for the case
the auto-break exists to detect, which would make every dead holder's lock
unbreakable forever while the whole suite still went green. On POSIX the same
call raises ProcessLookupError for the dead one, which is exactly why the naive
implementation looks correct right up until it runs here.

The predicate used instead is OpenProcess + WaitForSingleObject, measured
correct on all four cases above. See `_pid_is_alive_windows`.

THE PID-REUSE WINDOW IS NARROWED, NOT ELIMINATED -- SAY SO
-----------------------------------------------------------
An operating system reuses process ids. A holder can die and its pid be handed
to an unrelated process, after which this module's probe answers ALIVE and the
lock is never auto-broken. That is the SAFE direction of the error: the cost is
a stuck window an operator clears with `--break`, not a stolen one. The reverse
error -- breaking a lock whose holder is still measuring -- is the one a design rule
calls silent corruption, and every ambiguous branch in `pid_is_alive` therefore
answers ALIVE.

The recorded acquire time narrows the window a second way: a record claiming an
acquire time in the FUTURE is corrupt or clock-skewed and is never broken. This
is a sanity gate on the record, not a staleness test -- no elapsed duration
appears anywhere in the break decision.

EXIT CODES -- the canonkit contract
    0  the command did what it says
    1  a finding
    2  could NOT look: no lock present, or an unreadable record
"""

import argparse
import contextlib
import importlib.util
import os
import sys
import time
import uuid

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)

RECORD_SCHEMA = "mwlock/1"

DEFAULT_TIMEOUT = 30.0
DEFAULT_POLL_INTERVAL = 0.05

# The lock's own name under the working checkout. One window for the whole
# program, which is what "the measurement window" means -- not one per tool.
DEFAULT_LOCK_RELATIVE = os.path.join("_records", ".measurement-window.lock")

# A cap on how many times the loop may retry WITHOUT backing off after a break
# decision reported the path free. Belt to the identity check's braces: if a
# break keeps reporting "freed" while `os.open` keeps failing, something is
# wrong that spinning cannot fix, and spinning is how the analog burned a whole
# core inside a 0.2 s budget.
_MAX_IMMEDIATE_RETRIES = 8

# HOW LONG AN UNLINK MAY KEEP TRYING, AND THE MEASUREMENT THAT SET IT.
#
# On Windows, `os.unlink` fails with PermissionError [WinError 32] while ANY
# other process holds the file open, because Python's `open()` does not request
# FILE_SHARE_DELETE. Every waiter in this module opens the lock on each poll to
# read the holder record, so a releasing holder is contending with all of them.
#
# MEASURED on this machine, 300 unlink rounds each way:
#
#     no concurrent reader   ->    0/300 failures
#     ONE concurrent reader  ->  165/300 failures   (55%)
#
# This is not a corner. The first end-to-end run of eight concurrent writers
# deadlocked 7 of 8 for the full 60 s timeout: `release()` swallowed the
# PermissionError and returned False, the lock stayed on disk carrying the
# holder's OWN still-live pid, and the holder then waited out its own record --
# a self-deadlock that a design rule's liveness predicate is powerless against, because
# the holder really is alive.
#
# The analog has this retry already (`record_index.py:180-184`,
# `_WRITE_RETRY_SECONDS`); this module copied its acquire half at :237-265 and
# initially missed it. a shared pattern names the pair.
_UNLINK_RETRY_SECONDS = 5.0
_UNLINK_RETRY_INTERVAL = 0.005

# A break DECISION opens the lock to read its holder, so polling at the acquire
# interval multiplies the open handles every releasing holder must contend with.
# The decision does not need that frequency: a dead holder discovered 0.2 s
# later is indistinguishable in effect, while the reduced handle pressure is
# what keeps the release above from needing its whole retry budget.
_BREAK_CHECK_INTERVAL = 0.2

# O_BINARY OR NOTHING -- MEASURED HERE, NOT INHERITED.
#
# `os.open` on Windows defaults to TEXT mode, so `os.write(fd, b"...\n")`
# through a descriptor opened without this flag lands `\r\n` on disk. The first
# green run of test_the_lock_file_is_ascii_and_carries_no_carriage_return caught
# exactly that:
#
#     assert b'\r' not in b'mwlock/1 51488 3b9d...73 1789487757.511469\r\n'
#
# This is the same write-layer translation a design rule and canonkit.atomic_write_text's
# `newline=""` exist to prevent, arriving through a door NEITHER of them covers:
# `newline=""` is an argument to the built-in `open`, and `os.open` does not take
# it. A lock record is not hashed, so here it costs only tidiness -- but the
# descriptor-level habit is the one that matters, because the next `os.open` in
# this program may well be writing something an artifact's sha256 is computed
# over. The constant is `getattr`-ed because O_BINARY does not exist on POSIX,
# where the translation it disables does not happen either.
_O_BINARY = getattr(os, "O_BINARY", 0)


def _load_core():
    """Load the frozen core BY PATH under a neutral name.

    Never a package import: a design rule forbids it, test_repo_hygiene.py scans every
    repo-side module for it, and the core itself raises on a dotted __name__.
    """
    path = os.path.join(_HERE, "canonkit.py")
    spec = importlib.util.spec_from_file_location("frozen_core", path)
    if spec is None or spec.loader is None:
        raise ImportError("could not build an import spec for %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = _load_core()


def working_repo_root():
    """The checkout THIS FILE runs from. A lock is OUTPUT, so this is the anchor.

    `census_live_store.py` records the read/write distinction that cost a
    measured 1.4 MB written into the wrong checkout: READ anchors resolve
    against the MAIN root, WRITE anchors against the working one. A lock is
    output and belongs to the checkout that produced it, always.
    """
    return _REPO_ROOT


def default_lock_path():
    """The one program-wide measurement window."""
    return os.path.join(working_repo_root(), DEFAULT_LOCK_RELATIVE)


def lock_path_for(target):
    """The sidecar lock beside `target`: `<name>.lock`.

    Appending to the NAME rather than replacing the suffix: the target's own
    extension must be KEPT, so the lock is unmistakably the lock OF that file.
    `with_suffix` would turn both `records.md` and `records.json` into
    `records.lock` and silently make two different targets share one window.
    """
    target = str(target)
    return target + ".lock"


# ---------------------------------------------------------------------------
# The holder record
# ---------------------------------------------------------------------------

def _encode_record(pid, uuid_hex, acquired_at):
    """Render a holder record. ASCII, single line, no trailing translation.

    Four space-separated fields so a human reading the lock in a terminal can
    answer "who holds this and since when" without a tool. The schema tag is
    first so an unrecognised future format is detectable rather than
    mis-parsed into plausible-looking numbers.
    """
    return "%s %d %s %.6f\n" % (RECORD_SCHEMA, int(pid), str(uuid_hex),
                                float(acquired_at))


def _parse_record(text):
    """Parse a holder record, or None when it is not one.

    Returns None rather than raising, and NEVER guesses. An unparseable lock is
    never auto-broken -- `--break` is the escape hatch for it -- because a
    parser that filled in a default pid would be inventing the one value the
    whole break decision turns on.
    """
    if not text:
        return None
    fields = text.strip().split()
    if len(fields) != 4 or fields[0] != RECORD_SCHEMA:
        return None
    try:
        pid = int(fields[1])
        acquired_at = float(fields[3])
    except ValueError:
        return None
    if pid <= 0 or not fields[2]:
        return None
    return {"schema": fields[0], "pid": pid, "uuid": fields[2],
            "acquired_at": acquired_at,
            "token": "%d:%s" % (pid, fields[2])}


def read_holder(lock):
    """The holder record on disk, or None if absent or unreadable."""
    try:
        with open(str(lock), "r", encoding="ascii", newline="") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError):
        return None
    return _parse_record(text)


# ---------------------------------------------------------------------------
# Liveness
# ---------------------------------------------------------------------------

_WIN_SYNCHRONIZE = 0x00100000
_WIN_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_WIN_WAIT_OBJECT_0 = 0x0
_WIN_ERROR_INVALID_PARAMETER = 87


def _pid_is_alive_windows(pid):
    """MEASURED predicate: OpenProcess + WaitForSingleObject.

    Measured 2026-09-15 on this machine against a real child process:

        live child        handle ok, WAIT_TIMEOUT       -> ALIVE
        killed and reaped handle ok, WAIT_OBJECT_0      -> DEAD
        never existed     no handle, err 87             -> DEAD
        self              handle ok, WAIT_TIMEOUT       -> ALIVE

    WaitForSingleObject rather than GetExitCodeProcess: a process handle becomes
    SIGNALLED exactly when the process exits, which is unambiguous, whereas
    GetExitCodeProcess reports STILL_ACTIVE (259) and cannot tell it apart from
    a process that legitimately exited WITH code 259.

    Every branch that cannot answer, answers ALIVE. ERROR_INVALID_PARAMETER is
    the single error Windows returns for "no such process id" and is therefore
    the only proof of death this function accepts; ACCESS_DENIED means the
    process EXISTS and belongs to someone else, which is a live holder.
    """
    import ctypes
    from ctypes import wintypes

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL,
                                         wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    except (OSError, AttributeError):
        return True  # cannot probe -> never break

    access = _WIN_SYNCHRONIZE | _WIN_PROCESS_QUERY_LIMITED_INFORMATION
    handle = kernel32.OpenProcess(access, False, int(pid))
    if not handle:
        return ctypes.get_last_error() != _WIN_ERROR_INVALID_PARAMETER
    try:
        return kernel32.WaitForSingleObject(handle, 0) != _WIN_WAIT_OBJECT_0
    finally:
        kernel32.CloseHandle(handle)


def _pid_is_alive_posix(pid):
    """Signal 0 on POSIX genuinely is a probe: it validates without delivering.

    ProcessLookupError (ESRCH) is proof of death. EPERM means the process exists
    and is owned by another user -- a live holder. Every other OSError is
    unanswerable and answers ALIVE.
    """
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def pid_is_alive(pid):
    """True when `pid` names a process on this host, or when we cannot tell.

    The asymmetry is deliberate and is the whole of a design rule: a false ALIVE costs a
    stuck window an operator clears with `--break`; a false DEAD costs a
    preempted measurement whose numbers belong to neither run.
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return True
    if pid <= 0:
        return True
    if os.name == "nt":
        return _pid_is_alive_windows(pid)
    return _pid_is_alive_posix(pid)


# ---------------------------------------------------------------------------
# The break decision
# ---------------------------------------------------------------------------

def _stat_mtime_ns(path):
    """Return ("present", mtime_ns) | ("vanished", None) | ("unknown", None).

    Three states rather than two, because "the lock is gone" and "I could not
    look at the lock" are different answers and collapsing them is what burns
    the acquire budget. Indirected through a module-level function so the
    re-created-lock race is TESTABLE by patching this one name -- a guard that
    can only be exercised by the timing that broke it is a guard nobody
    re-checks.
    """
    try:
        return "present", os.stat(str(path)).st_mtime_ns
    except FileNotFoundError:
        return "vanished", None
    except OSError:
        return "unknown", None


def _unlink_with_retry(path, budget=_UNLINK_RETRY_SECONDS):
    """Remove `path`, retrying while another process holds it open.

    Returns True when the path is gone (including "was already gone"), False
    when the budget expired with the file still there.

    See _UNLINK_RETRY_SECONDS for the measurement that made this necessary: at
    one concurrent reader, a single-shot unlink fails 165 times in 300.
    """
    deadline = time.monotonic() + float(budget)
    while True:
        try:
            os.unlink(str(path))
            return True
        except FileNotFoundError:
            return True
        except OSError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(_UNLINK_RETRY_INTERVAL)


def _break_if_holder_dead(lock):
    """Remove `lock` iff its recorded holder is PROVABLY dead. True if now free.

    IDENTITY-CHECKED, and the identity check is the part copied verbatim in
    shape from the analog: the `st_mtime_ns` observed when the break was decided
    must still be the one on disk at the `unlink`, so a lock another holder
    re-created in the meantime is never stolen.

    Every stat failure EXCEPT a vanished lock answers "not broken". Answering
    "freed" on an arbitrary OSError sends the acquire loop straight back to
    `os.open` with NO backoff -- measured in the analog at 2,064 attempts inside
    a 0.2 s budget, i.e. a burned core for the whole acquire budget.

    NOTE WHAT IS ABSENT: no elapsed time, no threshold, no age. a design rule.
    """
    state, observed = _stat_mtime_ns(lock)
    if state == "vanished":
        return True  # it went away under us; the path is free, retry at once
    if state != "present":
        return False  # not evidence the path is free

    holder = read_holder(lock)
    if holder is None:
        return False  # unparseable: never auto-broken, use --break

    if pid_is_alive(holder["pid"]):
        return False  # a design rule: a living holder is never preempted

    if holder["acquired_at"] > time.time():
        return False  # a record claiming the future is corrupt, not stale

    again_state, again = _stat_mtime_ns(lock)
    if again_state == "vanished":
        return True
    if again_state != "present" or again != observed:
        return False  # a DIFFERENT lock sits here now; it is not ours to break

    # A SHORT budget here, unlike release(): a break is opportunistic and the
    # acquire loop will come round again, whereas a failed release strands the
    # window permanently.
    return _unlink_with_retry(lock, budget=0.25)


# ---------------------------------------------------------------------------
# acquire / release
# ---------------------------------------------------------------------------

def acquire(lock, timeout=DEFAULT_TIMEOUT, poll_interval=DEFAULT_POLL_INTERVAL):
    """Take `lock`, blocking up to `timeout` seconds. Return our token.

    Raises:
        TimeoutError: naming the lock and its current holder. NEVER returns a
            falsy value -- a caller writing `if not acquire(...)` against one
            would proceed to write UNLOCKED, which is the exact corruption this
            module exists to prevent, arriving through its own API.
    """
    lock = str(lock)
    parent = os.path.dirname(os.path.abspath(lock))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)

    pid = os.getpid()
    uuid_hex = uuid.uuid4().hex
    token = "%d:%s" % (pid, uuid_hex)
    deadline = time.monotonic() + float(timeout)
    immediate = 0
    next_break_check = 0.0  # the first miss checks immediately

    while True:
        fd = _acquire_fd(lock)
        if fd is not None:
            try:
                os.write(fd, _encode_record(pid, uuid_hex,
                                            time.time()).encode("ascii"))
            finally:
                os.close(fd)
            return token

        now = time.monotonic()
        if now >= next_break_check:
            next_break_check = now + _BREAK_CHECK_INTERVAL
            if _break_if_holder_dead(lock) and immediate < _MAX_IMMEDIATE_RETRIES:
                immediate += 1
                next_break_check = 0.0
                continue
        immediate = 0

        if time.monotonic() >= deadline:
            holder = read_holder(lock)
            if holder is None:
                who = "an unreadable holder record"
            else:
                who = "pid %d (uuid %s), alive=%s" % (
                    holder["pid"], holder["uuid"],
                    pid_is_alive(holder["pid"]))
            raise TimeoutError(
                "could not take the measurement window %s within %.2fs: held by "
                "%s. A LIVE holder is never preempted. If you are certain "
                "the holder is gone, run: python tools/mwlock.py --break --lock %s"
                % (lock, float(timeout), who, lock))

        time.sleep(poll_interval)


def _acquire_fd(lock):
    """One O_CREAT|O_EXCL attempt. Returns an fd, or None to retry.

    BOTH `FileExistsError` AND `PermissionError` mean "someone else has it,
    try again". The second is a MEASURED Windows defect, not a theoretical one:
    `unlink` leaves the NAME delete-pending while the last handle finishes
    closing, and an `O_CREAT | O_EXCL` create against a delete-pending name
    fails ERROR_ACCESS_DENIED (`PermissionError`), NOT ERROR_FILE_EXISTS.
    Catching only `FileExistsError` let that denial escape the retry loop
    entirely -- measured in the analog at 1 of 40 eight-thread rounds, and the
    writer that hit it LOST ITS ENTRY.

    `_O_BINARY` is part of the primitive, not decoration -- see its definition.
    """
    try:
        return os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY | _O_BINARY)
    except FileExistsError:
        return None
    except PermissionError:
        return None


def release(lock, token):
    """Remove `lock` only while it still carries `token`. True if we removed it.

    The token check is what stops one writer freeing another's window mid-write:
    after a break-and-reacquire the file at this path is a DIFFERENT lock, and
    unlinking it by path alone would hand the window to a third party.

    TWO DIFFERENT FAILURES, REPORTED TWO DIFFERENT WAYS -- this distinction was
    the whole bug:

        not ours / already gone  -> return False. A decision, not a failure.
        ours, but unlink failed  -> RAISE. The window is stranded on disk under
                                    our own live pid, and every other holder
                                    will now wait out its full timeout against
                                    a record whose liveness probe correctly says
                                    ALIVE. Returning False here reports a
                                    program-wide deadlock as an ordinary
                                    boolean, which is exactly how it stayed
                                    invisible until eight concurrent writers
                                    were actually run.
    """
    holder = read_holder(lock)
    if holder is None or holder["token"] != token:
        return False
    if _unlink_with_retry(lock):
        return True
    raise OSError(
        "could not release the measurement window %s after %.1fs of retries. "
        "It still carries our own token (%s), so every other holder will now "
        "block until their timeout against a holder the liveness probe "
        "correctly reports ALIVE. Clear it with: "
        "python tools/mwlock.py --break --lock %s"
        % (lock, _UNLINK_RETRY_SECONDS, token, lock))


@contextlib.contextmanager
def held(lock, timeout=DEFAULT_TIMEOUT, poll_interval=DEFAULT_POLL_INTERVAL):
    """Hold `lock` for the body. Released in a `finally`, including on a raise.

    The `finally` is load-bearing: a body that raises with the lock still on
    disk leaves a window held by a pid that is about to exit, and the next
    acquire then waits out its whole timeout before the liveness probe clears
    it.
    """
    token = acquire(lock, timeout=timeout, poll_interval=poll_interval)
    try:
        yield token
    finally:
        release(lock, token)


def break_lock(lock):
    """The manual escape hatch. Removes `lock` whatever it says. Returns the
    holder record it broke (or a placeholder), or None when there was no lock.

    Kept because the liveness probe is deliberately conservative: a reused pid,
    a probe that cannot open a handle, or an unparseable record all answer "do
    not break", and an operator who KNOWS the holder is gone needs a way to say
    so. It prints what it broke because an escape hatch that does not is how a
    live run gets preempted silently -- the exact outcome a design rule forbids.
    """
    existed = os.path.exists(str(lock))
    holder = read_holder(lock)
    if not existed and holder is None:
        return None  # nothing to break; the caller reports DID-NOT-RUN

    if not _unlink_with_retry(lock):
        raise OSError(
            "could not break the measurement window %s after %.1fs of retries; "
            "another process still holds the file open"
            % (lock, _UNLINK_RETRY_SECONDS))

    if holder is None:
        # An UNPARSEABLE lock was broken. This must not report "broke nothing":
        # an unparseable record is the single case the auto-break refuses, so
        # it is the case this escape hatch most exists for, and a caller that
        # heard "nothing was there" would go on believing the window is clean.
        return {"schema": None, "pid": None, "uuid": None,
                "acquired_at": None, "token": None}
    return holder


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _describe(holder):
    if holder is None:
        return "no holder record"
    alive = pid_is_alive(holder["pid"]) if holder["pid"] else None
    stamp = ""
    if holder["acquired_at"]:
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S",
                              time.localtime(holder["acquired_at"]))
    return "pid=%s uuid=%s acquired_at=%s alive=%s" % (
        holder["pid"], holder["uuid"], stamp or "unknown",
        {True: "alive", False: "dead", None: "unknown"}[alive])


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="mwlock",
        description="The program's one measurement window (a design rule: a live holder "
                    "is never preempted, regardless of age).")
    parser.add_argument("command", nargs="?", default="status",
                        choices=("status",),
                        help="status: report the holder and its liveness")
    parser.add_argument("--lock", default=None,
                        help="lock path (default: the program-wide window)")
    parser.add_argument("--break", dest="do_break", action="store_true",
                        help="manually break the lock and print what was broken")
    args = parser.parse_args(list(argv) if argv is not None else None)

    lock = args.lock or default_lock_path()

    if args.do_break:
        broken = break_lock(lock)
        if broken is None:
            sys.stdout.write(
                "DID-NOT-RUN broke nothing: no lock at %s\n" % lock)
            return core.EXIT_DID_NOT_RUN
        sys.stdout.write("broke the measurement window at %s\n" % lock)
        sys.stdout.write("  held by: %s\n" % _describe(broken))
        return core.EXIT_PASS

    holder = read_holder(lock)
    if holder is None:
        if os.path.exists(str(lock)):
            sys.stdout.write(
                "DID-NOT-RUN unreadable holder record at %s -- it is never "
                "auto-broken; use --break if you are certain\n" % lock)
            return core.EXIT_DID_NOT_RUN
        sys.stdout.write("free: no lock at %s\n" % lock)
        return core.EXIT_DID_NOT_RUN
    sys.stdout.write("held: %s\n" % lock)
    sys.stdout.write("  %s\n" % _describe(holder))
    return core.EXIT_PASS


if __name__ == "__main__":
    raise SystemExit(main())
