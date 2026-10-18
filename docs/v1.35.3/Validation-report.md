# 1.35.3 validation scope

The user approved implementation, the proposed validation work and GitHub
publication. Earlier releases' no-test instructions do not describe this patch.

| Channel | Current evidence |
| --- | --- |
| Focused regressions | 20 tests passed on Windows and the same 20 passed on WSL/Linux; 4 maintained-entry fallback tests passed on Windows |
| Native Math startup | Windows hosted and external UNO routes passed |
| Actual formula export | Windows hosted/external and WSL/Linux external routes passed |
| Formula fixture coverage | Five OMML zones: fraction, sub/superscripts, summation, integral, mixed English/Chinese text |
| Input/output integrity | Original PPTX bytes and five OMML zones retained; five native Math observations; one-page PDF independently rasterized; temporary PDF released |
| Windows complete-bundle installation | PASS: real core and Math readiness, single main-skill registration |
| Windows repeat | PASS: all 435 active skill files retained without rewriting, core resources reused, fresh Math startup probe |
| Windows partial installation resume | PASS: upgrade from only v1.35.2 skill files and no core success descriptor; sentinel retained |
| Static source/call-chain review | Performed; see Static-review.md |
| Syntax/import/CLI and package identities | Recorded by final checks and package receipts |
| macOS Apple Silicon and Intel | Physical-host installation/startup/render checks PENDING: no host available |
| Office interactive editing behavior | NOT_RUN |
| Whole original-image reconstruction | NOT_RUN; no external user-artwork acceptance claim |
| Performance/provider-token effects | NOT_RUN |

Windows sandbox named-pipe use timed out; the external UNO startup/export route
passed when run through the authorized host facility. This limitation is kept
separate from the successful in-application Windows route and from macOS status.
The first deeply nested Windows install fixture also failed to connect UNO;
the same prepared resources passed from a shorter project-private path. Deep
Windows installation paths are not qualified by this release. See
Installation-checks.json for the bounded installation conclusions.

The Mac code path is implemented and selected, but Mac compatibility remains to
be qualified on a real host. No Windows/WSL receipt is reused as Mac PASS. The
unchanged runtime 1.14.0/resource identities do not certify a newly installed
host. Public release/download/channel verification is recorded separately.
