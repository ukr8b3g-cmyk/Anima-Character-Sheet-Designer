# Changelog

## 1.0.1

- Automatically acquire only the selected missing Tagger when Use Image Input is ON, including promoted controls in the supplied subgraph. Analysis device does not trigger downloads.
- Reuse verified installed files; serialize concurrent download requests and preserve pinned size/SHA verification. Keep manual installation, progress and retry controls.
- Text mode and cloning alone do not acquire weights. Existing mismatched files remain untouched.
- Add automatic-acquisition and concurrency regression coverage: 45 Python and 25 JavaScript tests pass. Generation prompts, sampler settings and workflow wiring are unchanged by this acquisition update.

Previously published on main since 1.0:

- Resolve opposing automatic lower-garment, glove and footwear tags when an explicit choice is selected. Preserve Auto, user text/additions and raw analysis.
- Add **Check model files** with English/Japanese help; recheck without downloading. Completed status expires after five seconds, and analysis refresh also checks model readiness.
- Align JSON/frontend output contracts with the native six output sockets; retain migration support for old workflows.
- Add regression checks for inferred-tag precedence, real file state transitions, GET-only refresh and native output order.
- GPU A/B comparison on ComfyUI_test used the supplied WAI-ANIMA/Turbo settings and two seeds. Lower-garment changes improved in some cases; short-trouser, detail and viewpoint variation remain.

## 1.0

First public release of Anima Character Sheet Designer for ComfyUI.

- Switch between text input and local image-to-tags input in one subgraph workflow.
- PixAI Tagger v1.0 FP16 as the recommended default; WD EVA02 Large v3 as an alternative.
- Download only the selected Tagger from its internal node, or install the linked files manually.
- Generate up to 13 independent views, then assemble them into one sheet.
- Edit the base prompt for each view in the Prompts tab; add appearance changes separately in Part prompts.
- English/Japanese controls, tooltips and locale-aware template subgraphs.
- WAI-ANIMA v1.0 (base 1.0), Anima Turbo LoRA v0.2 and native model-only LoRA wiring in the supplied template.
- Illustrated English/Japanese setup and usage guides.

Image input becomes tags for new T2I generation. It is not direct image editing or visual-reference conditioning. Identity, clothing, orientation and garment-only separation can vary; see the README limitations.
