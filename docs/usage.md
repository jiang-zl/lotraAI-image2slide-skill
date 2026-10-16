# Usage

[简体中文](usage.zh-CN.md) · [Back to README](../README.md)

## Start from an image

In a working project with Image2Slide installed, attach a clear, unchanged original and send:

> Use $lotra-image2slide-skill to rebuild this image as an editable PPT.

Add any exact wording, colors or semantic relationships that must be preserved. The task is bound to the original; unreadable or ambiguous content needs an explicit record or your clarification.

## Continue from a partial slide

Attach the original image and its corresponding single partial PPT slide:

> Use $lotra-image2slide-skill to continue rebuilding from this partial PPT, following the original image.

This is a one-shot import at task start for continuing existing content. The current workflow focuses on image reconstruction and partial-slide import.

## Resume an interrupted task

Keep the working project, original and `.lotraAI-build`, then ask Codex to continue the existing task in the same project. Task records supply its current stage and next action. A new original starts a separate task.

## Deliverables

Final delivery includes an editable `.pptx` and a task report. The report should distinguish completed work, checks actually performed and remaining differences. Intermediate PPTX files, previews and checkpoints support ongoing work; use the files identified in the final delivery record.

Complete difficult components locally, then finish layout before the consolidated font review, whole-figure review and final output. A local edit does not trigger a whole-figure check each time. Chinese and English text use their corresponding font collections; equations retain structured Office Math.

The private local knowledge library retains eligible construction methods for reuse. Another figure's content or acceptance result is not transferred to a new original. See the [workflow reference](../skills/lotra-image2slide-skill/references/workflow-v134.md).

The [public examples](examples/README.md) provide originals, screenshots and details. See [evidence notes](validation.md) for their scope and this version's qualification status.
