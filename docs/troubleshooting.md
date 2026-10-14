# Troubleshooting

[中文](troubleshooting.zh-CN.md) · [README](../README.md)

| Symptom | What to check |
| --- | --- |
| Installer cannot locate its resources | Run from a complete extracted bundle and retain its directory structure. |
| Linux filesystem case check fails | Choose a case-sensitive Linux project directory, then resume the exact installation. |
| Installer reports changed or foreign files | Preserve those files and inspect the named diagnostic before proceeding. |
| Skill source is visible but runtime is absent | Run the bundle installer into the working project. |
| Math runtime is not supplied | Use a supplied Windows/Linux x86-64 route; Python engine availability is a separate fact. |
| Setup succeeds but rendering is unverified | Inspect the task's actual renderer capability and saved-render diagnostic. |
| Fonts or equations differ on another host | Check actual font availability, resources, mathematical structure, and saved rendering. |
| Work was interrupted | Resume the registered task with the same original and project state. |

Inspect `.lotraAI-build/Bundle-install.json` and the exact diagnostic identified by the installer or current task packet. Relevant fields include product version, environment, core readiness, rendering status, native-edit readiness, and the skill entry. Report the narrow diagnostic needed to reproduce the issue, with private content reviewed before sharing.
