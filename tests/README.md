# Installation checks for 1.37.2

Run test_install_bootstraps.py with Python 3.12 for the OS bootstrap and generator
checks. Version-binding regressions are in test_install_versions.py; release-gate counterexamples are in test_release_versions.py. Both release checkouts must be present as sibling source/runtime directories. Final
distribution parsing uses tools/validate_install_entries.py on the actual loose
assets, skill ZIP and complete ZIP. Run tools/validate_release_versions.py --source SOURCE --runtime RUNTIME --assets ASSETS --bundle COMPLETE_ZIP --final --output RECEIPT.json before publication. Current evidence is described in
docs/v1.37.2/Validation-report.md and the public Installation-checks.json asset.

The following v1.34 section is historical and retains its own validation scope.

# Focused v1.34 checks

Use the prepared project runtime to run test_native_workflow_v134.py. Required
numeric/image/PPTX dependencies are the existing runtime resources; no global
installation or model key is needed. Fixtures are synthetic and retained under
.lotraAI-build/validation-v134. These checks do not accept external user artwork
or exercise Office editing behavior. Actual-render/installation trial results
and platform limits are in docs/v1.34.0/Validation-report.md.
