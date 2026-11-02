# Licensing scope and artwork notice

The MIT grant in [LICENSE](LICENSE) covers only original code and documentation for which ukr8b3g-cmyk holds the applicable rights. It does not relicense third-party material.

## Images and artwork

The following are outside that MIT grant:

- `web/assets/mannequin-atlas.png` (Git blob `35dd5fabbe138b7b181b89d55432a6e53d0e9c34`).
- Artwork, including the SVG fallback artwork in `web/avatar.js`, and images/screenshots embedded in or linked from the README and documentation.
- User-provided references and generated outputs.

The source code implementing display/layout functionality is distinct from rights in the depicted artwork. No separate image license or complete chain of rights was established by this documentation update. Inclusion in this repository does not by itself grant permission to reuse depicted characters, designs or other third-party content. Confirm applicable rights before reuse or redistribution.

## Anima UI adaptation (2026-11-02)

UI, layout calculation, preview assets and display code were adapted from the author's MOSS-Image-Character-Sheet-Designer source. Its original artwork/license notices above are retained. This adaptation does not establish additional artwork rights. The Anima compiler, independent-view records and assembler are separate from MOSS's feature-extraction path. No ComfyUI_W files are used or changed by this installation.

## External components

ComfyUI, Anima models, dependencies and external services retain their own licenses and terms. The repository's MIT grant does not extend to them or guarantee rights in generated content. Preserve applicable original licenses, attribution and notices when redistributing third-party material.

The Tagger migration replaces Ref Adapter use in the template. PixAI Tagger and its Mexes ONNX conversion, and SmilingWolf WD EVA02 Large v3, are external model distributions with Apache-2.0 notices on their model cards. Their weights are downloaded separately and are not included in this package. See the pinned repositories in `contracts/models.v1.json` and preserve their applicable notices when redistributing weights. The dedicated Tagger code was written for this package; no Booru Tagger source files were copied or modified.
