# Unreal to Isaac USD — Unreal plugin 0.6.6

Unreal 5.7.4 / Windows, targeting Isaac Sim 6.0.1. This version adds material-node support for the PowerPlant/Jungle export, preserving the earlier headless, geometry-optimization, UV-repair and editable-material behavior. Earlier packages and user projects are preserved.

## Virtual texture and foliage recovery (0.6.6)

- Virtual Texture Feature Switch uses its connected **No** branch because the exported USD surface has no Unreal runtime virtual texture system. The original source textures, function bindings, layer masks and material-instance overrides on that branch are retained. Both scalar and Material Attributes outputs follow the selected branch. The unselected Yes branch is not traversed or exported.
- Per Instance Fade Amount exports as **1** for a static, fully visible snapshot. Texture opacity/cutout masks and their threshold are retained; Unreal distance-culling fades are not reproduced in the material.
- These decisions are recorded in extraction notes. A missing No input remains unsupported, with the source node path in the report, rather than switching to an unavailable virtual-texture branch.
- Water, unsupported sky/volume effects, camera-dependent spruce impostors and other unsupported nodes retain their previous policies. This is not an implementation of Unreal runtime virtual-texture blending or impostor camera UVs.

**Use a fresh Unreal extraction.** Previously captured unsupported markers do not contain the No branch needed to repair the existing USD alone. This update targets the 56 Virtual Texture Feature Switch materials identified in the PowerPlant/Jungle report; the final recovery count requires a fresh native extraction because additional nodes may exist beyond those switches.

## Material translation fixes

- Quality Switch follows `r.MaterialQualityLevel` during extraction, using Unreal's Default input when the selected branch is unconnected. The selected level is recorded in extraction notes.
- Get, Set and Break Material Attributes route the requested property through the source bundle. Set overrides one attribute while keeping the remaining attributes connected to its source.
- Function arguments are resolved lazily in their caller scope, then cached per attribute. A bundle passed into a function is not prematurely flattened to the outer material channel.
- Texture Objects and Texture Object Parameters can feed texture samples through functions, retaining instance overrides, source sampling and exported images.
- Runtime Virtual Texture Replace retains its ordinary visible-surface input; its virtual-texture-writing pass is not exported. Blend Material Attributes respects pixel/vertex Use A/Use B settings.
- Basic recovery preserves valid source texture layers, masks and UVs when a rendering effect alone blocks translation. It does not guess a texture for ambiguous blends or reconstruct unavailable camera effects. Supported materials retain their full graphs and editable controls.
- Headless and console retries display translated/unsupported material counts. A finished USD file can still be a partial conversion; inspect the material counts/report.

**Perform a fresh Unreal extraction with this version.** Older manifests contain shallow unsupported markers at these nodes, not the branches and source textures required to recreate them. Reopening their USD or rerunning only the USD worker cannot recover those missing branches. Water, unsupported sky and effects retain their existing exclusion/magenta policies. This does not implement every Unreal shading model or runtime rendering feature.

## Exclude hidden objects

Enable **Exclude hidden objects (actors and components)** to omit actors hidden in Unreal's editor or in game, plus scene components whose visibility is disabled or which are hidden in game. This applies to the current map and selected actors/components, including static meshes, splines, instancers, optional skeletal meshes, lights, cameras and decals. Hidden landscape components/proxies are omitted from the unified terrain's geometry while its masks retain their full-terrain coordinates.

The option starts **unchecked** to preserve earlier export behavior and remembers your choice in the project's saved plugin preferences. With it unchecked, the previous visibility behavior remains unchanged. Content Browser mesh-asset export has no actor visibility to inspect, so this option does not affect that scope. Native commandlet equivalent: `-BridgeExcludeHidden`.

The filter runs before mesh/material extraction. An asset used exclusively by skipped objects is not extracted; a shared asset still exports if a visible object needs it. This is not camera-view culling: visible objects outside the viewport and unloaded World Partition actors can still export. Unreal may load/build referenced assets when opening the map or loading an actor before the exporter can inspect its visibility; the checkbox does not eliminate that earlier RAM cost. `visibility_filter` in the source manifest and conversion report records the option and skip counts.

## Spline meshes and blocking volumes

Spline mesh components export as ordinary static USD geometry in their current curved shape. Positions use Unreal's `CalcSliceTransform`; normals use the renderer's slice rotation and scale signs. X/Y/Z forward axes, tangents, roll, taper, offsets, smooth interpolation and custom boundaries are included. Mirrored cross-sections reverse triangle order to match Unreal's culling convention. Component placement remains separate from local deformation and uses the standard centimeter-to-meter conversion.

UV channels, material sections, component overrides, visibility and vertex colors are retained. Component paint is remapped using undeformed source coordinates, then the temporary remap arrays are released. Each component has a distinct geometry identity, so different curves sharing one source mesh cannot accidentally become identical PointInstancer prototypes. Ordinary repeated static meshes still instance as before.

The output is a static snapshot, not an editable spline or live animation. Spline components preserve their original source subdivisions and skip reduction/preferred LOD selection: simplifying the straight source first could destroy the curve's subdivisions. Non-finite or degenerate deformation is reported and omitted. Source assets and component settings are not modified.

**Blocking Volumes and Camera Blocking Volumes, including derived classes, are always skipped as complete actors.** Attached meshes/decals are also excluded. The skip happens before the plugin's actor progress callback. World Partition descriptors are filtered before explicit export loading; volumes already loaded by Unreal or loaded as dependencies can still exist in editor memory. No collision-volume geometry or physics behavior is exported.

## Install and export

1. Extract `UnrealUsdBridge-0.6.6-UE5.7.zip` into your Unreal project's `Plugins` directory. The result must be `YourProject/Plugins/UnrealUsdBridge/UnrealUsdBridge.uplugin`.
2. If the project already contains an older `UnrealUsdBridge` plugin, move that older copy outside the project first. Do not load two copies of the same module. This package already contains the extraction module.
3. Enable **Unreal to Isaac USD** in Unreal's Plugins window and restart Unreal.
4. Open **Tools > Isaac Sim > Unreal to Isaac USD**.
5. Choose a save folder and the Isaac Sim installation folder, for example `E:/Omniverse/Isaacsim-6.0.1`. Isaac's Python and USD libraries are used in a separate worker. The Isaac application can stay closed.
6. Select an export scope, set options and press **Convert to USD**. Each conversion gets a new timestamped folder. Open `Scene.usdc` in Isaac manually after completion.

Scopes:

- **Entire current map:** reads current placements, including unsaved actor transforms. World Partition actors that are not already loaded are visited with releasable actor references. Landscape proxies are retained together to gather a unified landscape. Traditional streaming levels are visited individually; their load/visibility flags are restored.
- **Selected actors / mesh components:** select actors in the viewport/Outliner, or select components in the Details tree. Component selection takes precedence over actor selection. Selecting an ISM/foliage component exports its placements; individual foliage-paint selection is not interpreted. Relevant loaded decal actors are considered when Include decals is enabled. A selected landscape exports its unified landscape, not one cut-out component.
- **Selected Content Browser static mesh:** select one Static Mesh asset. It exports at the origin with its asset material assignments. Use actor selection for multiple meshes or per-placement overrides.

With **Headless conversion** unchecked, extraction runs in the open Unreal editor with a cancellation dialog; a single native asset build or reduction may temporarily block cancellation. USD construction then runs in a separate process with a progress bar and Cancel button. Closing the panel requests cancellation of an active worker. There is no automatic scene-opening option.

## Headless conversion

Enable **Headless conversion (save, close Unreal, show command window)**, choose **Entire current map** or **Selected Content Browser static mesh**, and click **Convert to USD**. The option starts unchecked and remembers your last choice. Selected actors/components require editor mode; that scope displays an explanation and keeps the editor open if headless is checked.

The handoff follows these steps:

1. Capture the current project, Unreal commandlet executable, saved map/asset package, plugin location, Isaac runtime, output folder and all conversion options. Unreal's native save dialog handles pending changes. A new map must be saved; cancelling a save or leaving dirty packages prevents the handoff.
2. Write a new `headless-job.json` in the timestamped output folder and open a visible command window. The runner validates paths, runtime libraries and the compiled extraction plugin before authorizing shutdown. Paths are passed as arguments, without a command shell interpreting spaces, Unicode or special characters.
3. Request Unreal's normal **Close Editor** operation. The runner holds a handle to that exact editor process and waits for it to exit completely before launching `UnrealEditor-Cmd.exe`. It never force-kills the original editor and never overlaps it with the extraction instance. A cancelled/vetoed shutdown times out after five minutes without starting extraction.
4. Extract the saved map/asset with `-NullRHI`, unattended mode and serial static-mesh compilation. The command window shows timestamped stages, Unreal log activity and actor progress. Map loading and individual native builds have no reliable percentage, so those stages show their current activity instead.
5. Build `Scene.usdc` in the isolated Python/USD worker. USD progress and the final scene path appear in the same window. The window stays open until Enter is pressed, including after a failure. Open the completed scene manually in Isaac.

All decal, visibility, camera, light, skeletal-reference and heavy-mesh options carry into the job. With **Exclude hidden objects** enabled, the job also captures loaded actors/components hidden only in the current editor session, because those visibility changes are not always stored in a saved map. Unloaded objects use their saved visibility.

After shutdown, use **Ctrl+C in the command window** to cancel conversion. Cancellation stops only the newly launched conversion workers and retains generated assets/logs. While the editor is waiting for the runner, its Cancel button prevents the handoff. If startup validation fails, Unreal remains open.

Headless mode avoids keeping the interactive editor and viewport resident during extraction. The new process still loads the saved map and its referenced assets; one very large asset can still exceed available memory. The existing live 2 GiB reserve, without a fixed worker RAM cap, remains in effect. This version does not add export checkpoints or automatic recovery from an interrupted extraction.

Headless logs in the output folder:

- `headless-console.log`: command-window progress, including the final result.
- `headless-job.json`: captured paths and conversion settings.
- `headless-status.json`: current phase, progress fraction and elapsed seconds.
- `unreal.log`, `unreal-engine.log`, `unreal-extraction.log`: native extraction output.
- `usd-conversion.log`, `conversion-report.json`: USD output and final report.
- `unreal.memory.json`, `usd-conversion.memory.json`: worker memory diagnostics.
- `headless-error.log`: Python traceback if the supervisor fails.

## Heavy meshes

Original geometry remains the default. Enable **Optimize heavy static meshes** to opt into reduced export copies. Defaults:

- Consider meshes above **500,000** source triangles.
- Aim for **250,000** triangles per unique mesh.
- Prefer **LOD1** if that LOD exists and is smaller. Imported source LODs and existing generated render LODs are supported. Set the LOD field to **0** to simplify the original instead.
- Maximum simplifier-reported geometric error: **1 cm**, including mesh build scale but before actor/instance scale. Existing LODs are explicitly chosen by the user and are not checked against this simplification error limit.

The reducer works on an in-memory `FMeshDescription` copy. It does not save assets or change their Nanite, LOD, reduction or material settings. A smaller existing LOD takes priority over the triangle target. Automatic reduction may also retain more triangles to preserve quality. Reductions with empty output, missing material slots, changed UV-channel count or excessive reported deviation fall back to original geometry and write a note.

Automatic reduction skips meshes whose asset materials are masked, translucent or two-sided, including typical foliage cards. An existing explicitly selected LOD can still be used. This protection is based on mesh asset materials; inspect exports where a component overrides an opaque asset with an alpha material. Landscapes and skeletal reference meshes are not simplified by this setting. Reduction cannot promise identical silhouettes, tiny details or UV sampling; review optimized assets before production use.

Each unique mesh is exported once. Compatible repeated placements still use PointInstancers, preserving the 0.5.17 grouping rules. Different bindings/vertex paint use separate prototypes as required. Reduction happens before decal receiving regions are computed.

## Memory and cache behavior

The plugin sets `Editor.AsyncStaticMeshCompilationMaxConcurrency=1` while enabled and restores the previous value on module shutdown if it has not been changed in the meantime. It finishes the specific mesh being exported rather than globally finishing every queued asset. Existing editor DDC configuration is reused; keep that cache between conversions.

For an editor startup that begins building the map before the plugin can apply its setting, launch Unreal with:

```text
-AsyncStaticMeshCompilation=1 -AsyncStaticMeshCompilationMaxConcurrency=1
```

This reduces simultaneous builds, not the memory required by one asset. It does not turn off Nanite or guarantee that any mesh fits in RAM. Decimation occurs after asset loading, so it cannot remove a Nanite build's earlier memory peak. Unloaded World Partition actors are released between visits; actors already loaded by the user's editor remain loaded. Complete landscapes and any reference-linked actor groups can still be large.

Extraction checks a 2 GiB physical/commit reserve between actors. The USD worker also monitors live headroom without a fixed per-process budget. There is no RAM checkbox or user memory cap. A reserve stop is reported as failure; an incomplete extraction is not published as a finished scene.

## Materials and other controls

Includes the 0.5.17 original-texture, editable material, emissive, leaf tint/brightness, unsupported-magenta, landscape-mask and decal behavior. Include decals, cameras, lights and skeletal-reference export are available. Camera-facing billboards, water shaders and unsupported Unreal graph features have the same limitations as 0.5.17. This is not an automatic conversion of every Unreal rendering feature.

Exporting alone requires no Isaac extension. To retain the custom material-to-decal selection button and live shared-decal editing helpers when working in Isaac, keep the existing 0.5.17 Isaac extension enabled. The standard material controls are stored in the USD itself.

Logs are inside the output folder: `unreal-extraction.log`, `usd-conversion.log`, `usd-conversion.memory.json`, `editor-status.json` and `conversion-report.json`. The report records geometry source and source/exported triangle counts.

## Validation

See `VALIDATION.md`. The PowerPlant/Jungle native material extraction and appearance are not verified here. The native plugin compiles on the installed UE **5.7.4** toolchain. All **208 applicable Python/USD checks** and three standalone worker checks pass. The new checks exercise path/option capture, cancellation, shutdown waiting, startup failure and a simulated extraction followed by real USD construction. Native spline/volume extraction, reduction, the Unreal panel and automatic editor shutdown have **not** been runtime verified here: tool-launched Unreal returns immediately without logs or a manifest. No full-scene RAM, appearance or FPS improvement is claimed.

The native fixture commandlet remains unverified through this tool launcher. See [VALIDATION.md](VALIDATION.md) for the native-test limitations. The saved-scene resume below was performed using 0.6.5.

## Saved conversion options

Checkbox changes and heavy-mesh threshold, target, LOD and error changes are saved immediately to the project Saved/UnrealUsdBridge/settings.json, and restored when the panel reopens. Older settings files did not contain optimization fields: the option therefore initially remains off until selected once in this update. The headless console prints the captured optimization ON/OFF state and numeric settings before editor shutdown. Numeric limits alone do not enable optimization; the checkbox must be on. Existing extracted geometry is unchanged by a USD-only retry. Re-export from Unreal to change geometry optimization.

## Lower-memory USD resume

Texture-path updates now stream the saved extraction instead of parsing a second full copy of its placements. Readable texture names from an interrupted attempt are reused safely. A saved 0.6.5 extraction USD retry completed using the original extraction: peak worker private memory was 10.7 GiB, compared with 24.0 GiB at the previous failed attempt. It translated 312/380 materials; 68 remain unsupported, primarily Virtual Texture Feature Switch cases. Direct USD-layer validation checked 1,690 local asset references without missing files. Isaac renderer opening has not been verified.
