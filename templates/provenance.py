"""What the machine was when this ran: sources, images, host, run, free VRAM.

COPIED FROM A SHIPPED FILE, WITH FOUR NAMED CHANGES.
The analog is example-cache-benchmark/provenance.py (78 lines), and
the shared pattern note marks it "exact -- copy it". Its shape is kept. Four things differ,
each for a stated reason rather than taste:

  1. THE ASSERTION THE ANALOG LACKS. `SOURCES` is a literal committed list
     filtered by existence, so the printed count is DERIVED over a DECLARED set
     -- a design rule's shape, already in shipped code. What is missing there is
     `len(SOURCES) == N` against a committed literal. Without it, a name
     silently dropped from the list makes the derived count agree with the
     shorter list, and the census stops checking while still printing a number.

  2. THE UNREACHABLE-PROBE BRANCH IS KEPT. The analog writes an ERROR OBJECT
     rather than omitting the key when a probe fails. A missing key and a failed
     read are different claims; this keeps them different. Copy that.

  3. `image_digest`'s `except Exception: return None` IS NOT COPIED. It is the
     one line in the analog that must not be. Under CHECK-08 a null digest is a
     FINDING, and that bare None makes an unreachable daemon, a missing binary
     and an image genuinely without a digest into one indistinguishable value.
     The exception is caught NARROWLY, its class and message are recorded, and
     the caller gets something it can COUNT.

  4. THE WHOLE RUN BLOCK IS NEW. Neither shipped artifact carries a timestamp of
     any kind, a GPU block, or the cost triple. The probe that established that
     found exactly one isoformat hit across both trees, in a synthetic document.

FREE VRAM IS A POPULATION FACT, NOT HOUSEKEEPING.
It is READ at run time and recorded. Nothing here computes against the card's
nameplate figure: free VRAM on this machine has been observed at three values
across two days, and the desktop compositor alone has held between 287 and
1,076 MiB. The number that matters is the one measured beside the run.
"""

import json
import os
import subprocess
import sys

import canonkit

SCHEMA = "canonkit/provenance/1"

# The DECLARED source set. A literal, committed, and filtered by existence at
# hash time -- so the printed count is derived over a declared population.
SOURCES = [
    "canonkit.py",
    "gate.py",
    "runmeta.py",
    "provenance.py",
    "derive.py",
    "finalize.py",
    "verify.py",
    "run_example.py",
    "docker-compose.yml",
    "requirements.txt",
]

# THE COMMITTED LITERAL. This is change (1) above: the tripwire on the
# declaration's own input. Asserted at import, so a mismatch is loud and
# immediate rather than a quietly smaller number in a later report.
SOURCES_DECLARED = 10

# Digest-pinned. A moving tag means "the same benchmark" can silently become a
# different image on a later run -- the artifact would still produce numbers,
# and they would be numbers about something else.
IMAGES = (
    "postgres@sha256:" + "0" * 64,
    "redis@sha256:" + "0" * 64,
)


def assert_sources_declared(sources=None, declared=None):
    """Raise when the declaration and its committed literal disagree."""
    sources = SOURCES if sources is None else sources
    declared = SOURCES_DECLARED if declared is None else declared
    if len(sources) != declared:
        raise RuntimeError(
            "SOURCES names %d path(s) but the committed literal "
            "SOURCES_DECLARED says %d. Update BOTH in the same commit -- a "
            "derived count whose input shrank silently stops checking, because "
            "the expected value falls to match what was found."
            % (len(sources), declared))
    return declared


assert_sources_declared()


def _run_text(argv, runner=None):
    if runner is not None:
        return runner(argv)
    completed = subprocess.run(argv, capture_output=True, text=True, timeout=60,
                               shell=False)
    if completed.returncode != 0:
        raise OSError("%s exited %d: %s"
                      % (argv[0], completed.returncode, completed.stderr.strip()))
    return completed.stdout


def image_digest(tag, runner=None):
    """Resolve one image's digest. Returns a RESULT OBJECT, never a bare None.

    This is change (3) in the module docstring, and it is the only place this
    file deliberately departs from a shipped line. The analog's
    `except Exception: return None` collapses three different facts -- the
    daemon was unreachable, the binary was missing, the image genuinely has no
    RepoDigest -- into one value that a later reader cannot tell apart from a
    successful probe of an undigested image.

    The exception is caught NARROWLY (an unexpected error is a defect here and
    should surface, not be absorbed), its class is recorded so a caller can
    COUNT failures by kind, and `ok` is a field rather than an inference from
    truthiness.
    """
    try:
        out = _run_text(
            ["docker", "inspect", "--format", "{{index .RepoDigests 0}}", tag],
            runner=runner)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return {"ok": False, "digest": None,
                "error_class": exc.__class__.__name__,
                "error": "%s: %s" % (exc.__class__.__name__, exc)}

    digest = str(out).strip()
    if not digest:
        # A SUCCESSFUL probe of an image carrying no RepoDigest. Distinct from
        # the branch above, and under CHECK-08 still a FINDING -- an unpinned
        # image is exactly what digest pinning exists to prevent.
        return {"ok": False, "digest": None,
                "error_class": "NoRepoDigest",
                "error": "docker inspect returned no RepoDigest for %s" % tag}
    return {"ok": True, "digest": digest}


def host_block(runner=None):
    """Docker Desktop version and `docker info` NCPU / MemTotal, PER RUN.

    Recorded on every run rather than once: the WSL2 memory allocation and the
    visible CPU count both move when the host configuration changes, and an
    artifact re-run months later on a reconfigured machine must say so rather
    than inherit the first run's numbers.
    """
    block = {"cpu_count": os.cpu_count(), "platform": sys.platform}
    try:
        block["docker_desktop_version"] = _run_text(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            runner=runner).strip()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        block["docker_desktop_version"] = None
        block["docker_version_error"] = "%s: %s" % (exc.__class__.__name__, exc)

    try:
        info = json.loads(_run_text(["docker", "info", "--format", "{{json .}}"],
                                    runner=runner))
        block["docker_ncpu"] = info.get("NCPU")
        block["docker_mem_total"] = info.get("MemTotal")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        block["docker_info_error"] = "%s: %s" % (exc.__class__.__name__, exc)
    return block


def hash_sources(root, sources=None):
    """sha256 every DECLARED source that exists. Bytes, never decoded text."""
    sources = SOURCES if sources is None else sources
    hashed = {}
    for name in sources:
        full = os.path.join(str(root), name)
        if os.path.isfile(full):
            hashed[name] = canonkit.sha256_file(full)
    return hashed


def build_record(root, run, free_vram_mib, images=None, image_runner=None,
                 host_runner=None, sources=None, stream=None):
    """Assemble the provenance record and PRINT its populations.

    The denominator printed beside the hashed count is the COMMITTED LITERAL
    when the declared set is used, not `len(sources)`. Printing the length of
    the very list being checked would be a denominator that moves with its own
    numerator -- the tripwire would agree with any list, including an emptied
    one, which is the failure mode change (1) exists to close.
    """
    stream = stream if stream is not None else sys.stdout
    images = IMAGES if images is None else images
    if sources is None:
        sources, declared = SOURCES, assert_sources_declared()
    else:
        declared = len(sources)

    hashed = hash_sources(root, sources)
    probes = dict((tag, image_digest(tag, runner=image_runner)) for tag in images)

    record = {
        "schema": SCHEMA,
        "schema_version": canonkit.SCHEMA_VERSION,
        "sources": hashed,
        "images": probes,
        "host": host_block(runner=host_runner),
        "run": dict(run),
        "free_vram_mib": free_vram_mib,
    }

    # Both populations printed unconditionally, on every branch. A probe that
    # failed and a probe that was never attempted are different facts, and only
    # a printed count separates them for a reader of the log.
    stream.write("[provenance] sources hashed %d of %d declared\n"
                 % (len(hashed), declared))
    failed = sorted(tag for tag, probe in probes.items() if not probe.get("ok"))
    stream.write("[provenance] images probed=%d ok=%d failed=%d\n"
                 % (len(probes), len(probes) - len(failed), len(failed)))
    for tag in failed:
        stream.write("[provenance]   FAILED %s -- %s\n"
                     % (tag, probes[tag].get("error")))
    return record


def main(argv=None):
    raise SystemExit(
        "provenance.py is written by a measurement driver, not run directly; "
        "call build_record() from run_*.py after finish_run().")


if __name__ == "__main__":
    main()
