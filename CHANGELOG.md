# Changelog

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
