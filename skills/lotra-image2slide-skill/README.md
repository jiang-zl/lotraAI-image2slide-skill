# lotraAI Image2Slide 1.35.3

Rebuild scientific images as native editable PowerPoint slides. Product usage
and examples: https://github.com/jiang-zl/lotraAI-image2slide-skill.

To prepare or update this project's runtime, use the supplied entry:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-runtime.ps1 -Project 'C:\work\my-project'
```

```sh
sh scripts/install-runtime.sh '/absolute/path/to/my-project'
```

The shell entry selects Linux or macOS and its architecture automatically.
A supplied extracted bundle can be selected with -BundleRoot on Windows or
--bundle-root on macOS/Linux. Installer resources prepare the environment and
register one main skill; existing project knowledge, fonts and tasks are retained.
