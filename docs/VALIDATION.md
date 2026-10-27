# Validation

Recorded for plugin 0.6.6 on 2026-10-24:

- UE 5.7.4 Win64 Development compilation/linking succeeded.
- 208 Python/USD regression checks passed with zero failures/errors.
- Three independent worker checks passed: successful conversion, invalid runtime reporting, and cancellation.
- The packaged release passed ZIP integrity, source/runtime matching and standalone USD conversion checks.

The source upload changes documentation, test-path configuration and repository tooling; the production plugin logic is unchanged from the validated 0.6.6 files. Git may normalize text line endings.

The portable repository suite was rerun on 2026-10-27: all 208 checks passed. The build wrapper passed PowerShell syntax parsing, and all 62 Python files passed syntax parsing. This did not rerun native extraction or rendering.

## Run the Python/USD suite

Use Isaac's bundled Python, not an unrelated Python installation:

```powershell
& "E:/Omniverse/Isaacsim-6.0.1/kit/python/python.exe" -B scripts/run-tests.py --isaac "E:/Omniverse/Isaacsim-6.0.1"
```

Run from the repository root. Replace the example installation path. This loads the matching `omni.usd.libs` and DLL directories, supplies the runtime path to headless tests, and runs `tests/test_*.py`. Tests create small fixtures in ignored `work/`; they do not open the interactive Unreal or Isaac application. They do not benchmark rendering or extract a real map.

## Native material fixtures

After building/installing the plugin into an Unreal project, run the commandlet from PowerShell using a fresh output folder:

```powershell
& "C:/Program Files/Epic Games/UE_5.7/Engine/Binaries/Win64/UnrealEditor-Cmd.exe" "D:/Projects/MyProject/MyProject.uproject" -run=UnrealUsdExtract -BridgeTestMaterials -BridgeOut="D:/Exports/MaterialFixture" -unattended -nop4 -NullRHI -NoShaderCompile -stdout
```

The project must enable the compiled plugin. This fixture includes assertions for non-virtual branch selection, an unconnected No branch, attribute routing through functions, channel masks and foliage opacity masks/thresholds. A real pass requires successful commandlet execution **and a generated manifest/log**, not exit code zero alone.

## Outstanding validation

The tool-launched native process returned zero in about 1.5 seconds without an Unreal log or manifest. The new native assertions and source-asset branch recovery were therefore not runtime verified. A fresh full-scene 0.6.6 extraction, Isaac rendering, FPS and full-scene memory remain unverified.

A previous 0.6.5 scene report identified 56 Virtual Texture Feature Switch materials (35 static, 20 foliage, one landscape). This is the target of 0.6.6's fixes, not a measured recovery count. More unsupported nodes can appear beyond newly traversed switches. No environment assets or private source-scene logs are required to run the synthetic tests in this repository.
