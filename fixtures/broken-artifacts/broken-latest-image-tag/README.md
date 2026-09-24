# `broken-latest-image-tag/` -- the second one-known-bad input for CHECK-08

**The defect:** `docker-compose.yml` carries two image references and neither is
pinned by digest. They are broken in **two different ways on purpose**:

| line | reference | finding kind |
|------|-----------|--------------|
| 10 | `image: postgres:18` | `image-without-digest` -- a tag, and a tag is a moving target |
| 15 | `image: grafana/k6:latest` | `latest-tag` -- the floating tag whose name means "newest" |

Two references, two DIFFERENT `finding_ids`. That is the assertion this fixture
exists to support: a check that collapsed both into one kind would tell an author
"something is unpinned" without telling them that one of the two cannot be
pinned by adding a version at all.

`postgres:18` is a genuine, useful pin in most projects and is still a defect
here -- it resolves to different bytes on different days, so "the same benchmark"
can silently mean different software. That is why the tag-only case gets its own
kind rather than being waved through as "nearly pinned".

## One reference, one finding

`grafana/k6:latest` is *both* digest-less and the floating tag. It produces
**one** finding, classified by the more specific kind, because it is one defect
with one repair: resolve the digest and pin it. A check that emitted two findings
for one string would make its own `found=` count a measure of how many rules
matched rather than how many things are wrong.

## Why the summary numbers are 2 and not 3

The population is **2**: the two image references. No other line in the file
carries the floating tag -- the header comment describes the ban **in words**
rather than quoting the string, for the same reason `templates/docker-compose.yml`
does. CHECK-08 scans the WHOLE file rather than only its `image:` keys, because a
commented-out service is one uncomment away from being a pull site, so a comment
that quoted the banned string would be a hit for it.

That is not a hypothetical either: the template records that its own first draft
did exactly that and failed the check. This fixture would have carried a third,
spurious finding if its header had been written the obvious way.

(This `README.md` does quote the string, in the table above. Markdown is not in
CHECK-08's declared scope -- the pull sites are `requirements*.txt`, compose
files and Dockerfiles, plus driver scripts under `--include-drivers` -- so the
quotation is safe here and is not safe one file over. The scope is printed on
every run precisely so that distinction is checkable rather than remembered.)

## Defect count: two, and both belong to CHECK-08

This tree carries no `results/`, no README regions and no figures record, so
CHECK-01 and CHECK-03 report DID-NOT-RUN over it -- they could not look, which is
correct and is not a defect of this tree.
