# Download the complete bundle

[中文](download.zh-CN.md) · [Installation](installation.md)


The complete file is `lotraAI-image2slide-v1.31.0-bundle.zip` (2,414,649,382 bytes), including the skill and all supplied runtime resources. SHA-256: `200f65a42b96dca2a0143f43f1c3583d5150958ae1fc7ac8c6dea41969fbe657`.

## Download and assemble

Open the [v1.31.0 bundle release](https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime/releases/tag/v1.31.0). Its 18 transport assets (`.part001` through `.part018`, up to 128 MiB each) are ordered byte segments of the same complete ZIP. Save the release's [download helper](https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime/releases/download/v1.31.0/fetch_bundle.py), then run:

~~~sh
python3 fetch_bundle.py --output-dir ./downloads
~~~

On Windows, use `py fetch_bundle.py --output-dir .\downloads`. The helper reads the [version manifest](https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime/releases/download/v1.31.0/v1.31.0.json), checks every part, reassembles the ZIP, and verifies the complete SHA-256 before publishing the output file. Existing different files are preserved.

You can give Codex the [release URL](https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime/releases/tag/v1.31.0) and ask it to use the manifest and helper to obtain the complete bundle, then extract and install it. An already assembled ZIP can be handed directly to Codex.

The only assembled delivery archive is `lotraAI-image2slide-v1.31.0-bundle.zip`. Transport preserves every archived file and payload. Part sizes follow [GitHub's per-asset limit](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases#storage-and-bandwidth-quotas).
