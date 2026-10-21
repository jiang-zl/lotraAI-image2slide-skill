# lotraAI Image2Slide 1.37.0


Use the registered `start → next → submit` task loop and [1.37.0 rules](references/workflow-v137.md). Checkpoints and developer builds are unverified. Formal export plus `delivery-check` establishes the current final-file scope. No mandatory harness/service is required.

将科研图片重建为原生可编辑 PowerPoint。产品用法与案例：
https://github.com/jiang-zl/lotraAI-image2slide-skill。

准备或更新当前项目的 runtime，可使用随 skill 提供的入口：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-runtime.ps1 -Project 'C:\work\my-project'
```

```sh
sh scripts/install-runtime.sh '/absolute/path/to/my-project'
```

Shell 入口自动区分 Linux、macOS 和架构。已有解压包时，Windows 使用
-BundleRoot，macOS/Linux 使用 --bundle-root。安装器准备环境后登记一个主
skill，并保留项目已有的个性化知识、字体与任务。
