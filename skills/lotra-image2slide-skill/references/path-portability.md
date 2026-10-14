# Relative resources and native host paths

Three domains are distinct: a portable task/package resource reference; a resolved local filesystem path; a Windows/WSL/macOS tool argument. Do not validate a host-native argument as a relative resource or derive portable spelling from `str(Path(ref))`.

`core.common.portable_resource` reads the original string/path-like input, normalizes relative `\` and `/` to POSIX separators, then applies platform-independent relative-path rules. `safe_path(base,ref)` constructs the host's Path only afterward and verifies the resolved target remains inside the allowed base, including symlink resolution. This fixes the old Windows behavior where `Path('source/original.png')` inserted backslashes before a second check rejected them.

Accepted logical spellings include `source/original.png`, `source\original.png` and `./source/original.png`, with Unicode/spaces preserved. Persist new references through `relative_to(...).as_posix()`. Absolute/drive-relative/UNC/rooted paths, `..`, drive delimiters and control characters are rejected as resource references; absolute source/project/CLI/host paths use their own explicit interfaces. Do not weaken containment checks to work around a host conversion.

The shared `core.office_bridge._host_path` receives already resolved local paths. Windows uses its native string; WSL converts an existing anchor and appends new output components once. Both Office entry paths and font-provider dispatch use it. Host arguments are passed as an argument list, not built into shell text. Returned runtime resource refs re-enter through `safe_path`; a saved host filename is not a portable ref.

ZIP entry names remain strict POSIX via the separate package installer. Accepting native relative separator input does not permit unsafe ZIP paths, absolute archive entries or global installation. Canonical logical identity and platform-specific location stay separate when tasks move across Windows/WSL/Linux/macOS. Keep old snapshots/hash-bound evidence intact rather than rewriting every archived reference.
