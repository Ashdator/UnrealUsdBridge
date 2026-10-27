# Troubleshooting

## Plugin does not appear

Check the descriptor path: `YourProject/Plugins/UnrealUsdBridge/UnrealUsdBridge.uplugin`. Avoid an extra nested `UnrealUsdBridge/UnrealUsdBridge` folder and duplicate copies in project/engine plugin paths. Rebuild for your exact Unreal installation if binaries are absent or incompatible.

## Choose the Isaac installation

Select the installation root containing `kit/python/python.exe` and `extscache/omni.usd.libs-*`. This is not the exported scene folder. The runtime is Windows x64 and must match the bundled Python version. Conversion does not need the interactive Isaac application open.

## Conversion appears stuck

Inspect timestamped run logs, `editor-status.json` or `headless-status.json`, and process activity. Loading a map, building an individual mesh or reducing heavy source geometry may take time without a new progress percentage. A last progress line alone does not prove that a worker has stopped. Check errors before starting another worker into the same folder.

Relevant output files include:

- `unreal-extraction.log`, `unreal.log`, `unreal-engine.log`: Unreal extraction/build diagnostics.
- `headless-console.log`, `headless-status.json`, `headless-error.log`: headless supervisor state/errors.
- `usd-conversion.log`, `usd-conversion.memory.json`: USD worker and memory diagnostics.
- `editor-status.json`, `conversion-report.json`: completion state and supported/unsupported materials.

## Out of memory

The exporter keeps a small live physical/Windows allocation reserve; there is no fixed per-worker RAM budget or RAM checkbox. Closing other memory-heavy applications and using headless mode can reduce overlap. Geometry optimization works after an asset loads and cannot eliminate the earlier memory required by Unreal's own asset/Nanite build. Shader compilation/opening in Isaac is a separate memory cost. Smaller export scopes can help isolate a very large asset.

## Missing or magenta materials

Check the named material's entry in `conversion-report.json`. An unsupported graph, excluded water/effect, missing source-backed texture, or failed compilation can require manual material replacement or translator support. Preserve the complete texture/material/geometry output tree when moving a scene. Virtual Texture Feature Switch support in 0.6.6 requires fresh Unreal extraction: old unsupported markers lack the selected graph's source data.

## Retry only the USD stage

Use this only when Unreal extraction completed successfully, `manifest.json` and its mesh/texture files are intact, and no completed `Scene.usdc` exists. The writer refuses to overwrite an existing scene. A retry cannot change source geometry optimization or recover material branches absent from the manifest.

From the repository root, substituting your actual paths:

```powershell
& "E:/Omniverse/Isaacsim-6.0.1/kit/python/python.exe" -B "UnrealUsdBridge/Resources/Python/run_conversion.py" --manifest "D:/Exports/MyRun/manifest.json" --isaac "E:/Omniverse/Isaacsim-6.0.1" --console --decals 0 --cameras 0 --lights 0
```

The three optional flags shown disable decals/cameras/lights for the retry. Use `1` to include them where the extracted data contains them. If you previously cancelled, remove only that run's intentional `cancel.request` marker before restarting. Do not run simultaneous writers against one conversion folder.

## Materials are slow to appear / low FPS

Loading and compilation can take time even after USD authoring finishes. Converted shader graph complexity, decal overlap, geometry, texture memory and renderer settings affect performance. This version does not promise a particular FPS or reproduce every Unreal optimization. The synthetic suite checks USD authoring and material wiring; it does not benchmark rendering.

## Optional Isaac editing helpers

The export itself needs no Isaac extension. The existing 0.5.17 Isaac extension is optional for custom material-to-decal selection buttons/live shared-decal editing helpers; it is not bundled in this Unreal-only source repository. Standard material controls are authored into USD.
