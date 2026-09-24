# Host port convention

Every service this artifact publishes uses a **high, deliberately unusual host
port**. Container-side ports stay standard, so nothing inside the compose
network has to know about this file.

| Service | Host port | Container port | Rationale |
|---|---:|---:|---|
| Postgres | 55432 | 5432 | standard port prefixed with `5` |
| Redis / cache | 56379 | 6379 | standard port prefixed with `5` |
| Application / HTTP | 58000 | 8000 | standard port prefixed with `5` |

The rule is mechanical: **take the service's conventional port and prefix it
with `5`**. It is easy to apply without looking anything up, it produces a
distinct number per service, and every result lands in the ephemeral range
where nothing standard listens.

## Why not the default ports

**A collision does not announce itself as a collision.** This is a developer
laptop that also runs a local Postgres, a Docker Desktop VM, and whatever a
previous artifact left running. If this artifact published `5432` and something
else already held it, one of two things happens, and both are worse than a
crash:

- The bind fails and the stack refuses to start, which is the *good* case --
  noisy, immediate, obvious.
- The bind succeeds against a *different* process that was already there, and
  the measurement runs happily against the wrong database. Nothing errors. The
  numbers are real, reproducible, and about the wrong system.

The second failure is the one this convention exists to prevent, and it is
invisible from the artifact's own output: every guard passes, because every
guard is asking the wrong server.

## Rules when adding a service

- **Pick the same way.** Prefix the conventional port with `5`. Do not invent a
  number; do not reuse one from the table above.
- **Record it here in the same commit.** A port allocated but undocumented is
  the next collision.
- **Change the host side only.** Remapping the container side breaks every
  in-network URL and every upstream default for no benefit.
- **If a chosen port is already taken on this machine, say so in the README's
  environment section.** A port substituted quietly at run time makes two runs
  non-comparable, and nothing in the results records which port was used unless
  someone writes it down.

## What is checked, and what is not

The artifact's gate records the ports it bound and the run writes them into
`results/provenance.json`, so a reader can tell which endpoint produced a
number. Nothing scans the host for a pre-existing listener before the run --
that is a genuine gap, and it is the reason the rule above is "high and
unusual" rather than "check first".
