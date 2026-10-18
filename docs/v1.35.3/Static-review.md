# 1.35.3 call-chain review

Reviewed paths: installer/differential.py and install.py -> renderer_install.py
-> the candidate skill's stdlib-only editor_backend.py -> installed
portable_editor.py -> uno_editor_client.py or the private uno_host_worker.py.

- Darwin selects libreoffice_hosted and rejects subprocess_uno. Only the signed
  main application is launched. codesign verification is read-only.
- A new private profile is initialized before its fixed Basic/Python library is
  registered, avoiding first-start template replacement. User macro settings and
  existing LibreOffice profiles are not altered.
- The hosted worker gets the actual profile through LibreOffice's path service,
  verifies job ID, request digest, worker input identities and an exact operation
  set, and writes an atomic reply before closing its owned application.
- Formula export retains the existing OMML import and native Math processing.
  The canonical PPTX is unchanged. The rendering copy and formula plan are
  verified before/after; actual PDF and formula receipts are required.
- A shared finite deadline covers private profile initialization and execution.
  Client logs are file-backed so interpreter descendants cannot hold a PIPE
  open indefinitely after cancellation. Only invocation-owned processes stop.
- Backend identities bind mode, host, code, executable and available native
  libraries. Mode/code changes invalidate render identity. Install repeats
  perform a fresh startup probe and update their current evidence.
- Math startup failure cannot produce a core success claim or register the main
  skill. Prior descriptors are restored by the existing scoped journal.
- API fallback resolves the exact repository, release and asset, follows bounded
  pagination, verifies size/state, and retains original byte/SHA/range checks.
- Runtime resources, spatial algorithms, old contracts, fonts/knowledge and
  gallery images are retained. Missing physical Mac tests are explicitly pending.
