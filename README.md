# Unreal to Isaac USD

Unreal Engine editor plugin **0.6.6** for exporting environment scenes to USD for NVIDIA Isaac Sim.

## Requirements

- Windows x64.
- Unreal Engine **5.7.4** (the version used for compilation).
- Isaac Sim **6.0.1**, including its bundled Python and `omni.usd.libs` runtime.
- For source builds: Visual Studio 2022 with the C++ toolchain and Windows SDK required by your Unreal installation.

Other Unreal/Isaac versions and operating systems have not been validated.

## Install from this repository

1. Build/package the plugin using [BUILD.md](docs/BUILD.md), or obtain a matching precompiled package from the repository owner.
2. Close Unreal and place the built `UnrealUsdBridge` folder in `YourProject/Plugins/`. The descriptor must be `YourProject/Plugins/UnrealUsdBridge/UnrealUsdBridge.uplugin`.
3. Keep one copy of the plugin in the project. Move older copies outside the project before installing the replacement.
4. Open the project, enable **Unreal to Isaac USD** in Plugins, and restart if requested.
5. Open **Tools > Isaac Sim > Unreal to Isaac USD**.

This repository contains source and Python resources. Generated binaries, caches, converted scenes and third-party environment assets are not part of the source tree.

## Convert an environment

1. Open the Unreal map, or select actors/mesh components or a Content Browser static mesh.
2. Choose the export scope, destination folder, and your Isaac Sim installation folder (the folder containing `kit/python` and `extscache`).
3. Choose optional decals, cameras, lights, skeletal meshes as static reference poses, hidden-object filtering and heavy-mesh optimization.
4. Click **Convert to USD** and inspect the progress/report. Each run creates a timestamped output folder.
5. Open the completed `Scene.usdc` manually in Isaac Sim. Keep its associated geometry, texture and material files alongside it.

Outputs use **meters**, Z-up. Original source assets are not modified. Compatible repeated meshes/foliage use PointInstancers. Blocking Volumes and Camera Blocking Volumes are skipped.

For lower editor memory overhead, headless mode saves the map, requests normal editor shutdown, then launches extraction and USD conversion in sequence. It supports saved maps and Content Browser static meshes; selected actor/component export uses editor mode. The USD worker does not open the Isaac application.

## Materials

Original source textures are used with editable supported material inputs. Simple surfaces use USD Preview Surface, foliage uses OmniPBR where possible, and complex supported graphs use MDL. Emissive maps/colors, foliage tint/brightness, landscape masks and optional decals are supported within the graph translator's limits.

In 0.6.6, Virtual Texture Feature Switch follows its non-virtual **No** input. Per Instance Fade Amount becomes 1 for a fully visible static snapshot while preserving texture opacity masks. Unreal runtime virtual-texture blending, foliage wind, camera-dependent impostor UVs and all Unreal rendering effects are not reproduced. Water and unsupported effects retain their exclusion/magenta policy. A completed conversion may still contain unsupported materials: inspect `conversion-report.json`.

**Fresh extraction is required** to recover branches previously stored only as unsupported markers. A USD-only retry cannot reconstruct source graphs absent from the manifest.

## Documentation

- [Complete user guide and conversion options](docs/USER_GUIDE.md)
- [Source build and packaging](docs/BUILD.md)
- [Testing and validation limits](docs/VALIDATION.md)
- [Troubleshooting and USD-only retries](docs/TROUBLESHOOTING.md)
- [Changes in 0.6.6](CHANGELOG.md)

## Validation status

The 0.6.6 native plugin compiled and linked on UE 5.7.4. The Python/USD suite passed **208 checks**, plus three worker checks, on the original workstation. Native commandlet runtime assertions and a fresh full-scene 0.6.6 extraction/render were **not verified**: the tool-launched Unreal process exited without logs or a manifest. Do not interpret successful compilation or synthetic USD tests as full scene/render compatibility.

The exporter uses a live physical/Windows allocation reserve rather than a fixed RAM budget. Large maps, asset builds and shader compilation can still require substantial RAM/VRAM; no FPS or memory improvement is guaranteed.
