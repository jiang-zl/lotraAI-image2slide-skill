# Usage

[中文](usage.zh-CN.md) · [README](../README.md)

## Reconstruct a figure

Open the working project after bundle installation, attach the unchanged reference image, and invoke the skill:

~~~text
Use $lotra-image2slide-skill to reconstruct this reference image as an editable
PowerPoint slide. Preserve its original wording, mathematical expressions,
grouping, and connections. Keep photographic content in its appropriate scope.
~~~

The agent interprets the source and resolves semantic ambiguity. Programs register the task, expose the current action contract, execute bounded work, check saved results and renders, and manage acceptance. Reuse the current agent; no extra model key is required.

## Make a local change

Describe both the change and the content to preserve:

~~~text
Increase the gap between the communication layer and the server layer.
Preserve the equations, wording, icon parts, and the remaining layout.
~~~

Keep the same project and task. Approved attributes and user edits are protected according to the current contract. Dependencies affected by a change still require checking.

## Resume after an interruption

Ask the agent to resume the registered task in the same project. Keep the original image and `.lotraAI-build` state available. The installed skill describes `context-control resume`, `next`, and the current packet's action references. A new image starts its own source-bound task.

## Deliverables

The reconstruction workflow exports `Final_editable.pptx` and `Report.md` with actual per-component measurements and direction indicators. Intermediate renders, working components, checkpoints, and temporary PDFs belong to the private task workflow. An accepted export is separate from an intermediate PPTX.

The three [example studies](examples/README.md) illustrate the supplied screenshots. Native decks were not supplied. Office Math structure, font resources, native edit/save/reopen behavior, and whole-result quality need evidence from the corresponding native file and host.
