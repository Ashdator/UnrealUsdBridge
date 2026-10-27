# Changelog

## 0.6.6 - 2026-10-24

- Resolve Virtual Texture Feature Switch through its connected non-virtual No branch, retaining function scope and requested material attributes.
- Leave a missing No branch unsupported with an explicit source-node diagnostic.
- Export Per Instance Fade Amount as 1 for static foliage snapshots without dropping opacity-mask calculations or thresholds.
- Add native branch/function/channel-mask/fade regression assertions and a USD pipeline cutout test.
- Preserve existing editable materials, headless handoff, geometry optimization, splines, visibility filtering and instancing.
- Preserve 0.6.5 streaming manifest texture-path updates and interrupted readable-texture-name recovery.

Native runtime verification of the new branch extraction remains outstanding; see docs/VALIDATION.md.
